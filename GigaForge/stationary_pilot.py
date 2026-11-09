"""A separate, bounded Chronos experiment: goal-only versus small PBRS. No promotion."""
from pathlib import Path
import argparse, csv, importlib.util, json, math, os, random, shutil, subprocess, sys, time, zipfile
from stationary_jobs import PilotPaused, digest, evaluate, launch, model_identity, summary, paired_difference

ROOT=Path(__file__).resolve().parent
ARMS={'goal_only':[0.,0.,0.,0.,0.], 'goal_potential':[.12,.05,.10,.08,.08]}

def runtime():
    spec=importlib.util.spec_from_file_location('stationary_runner',ROOT/'run.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    import torch
    if torch.__version__.split('+')[0]!='2.9.1':raise RuntimeError('Use the selected PyTorch 2.9.1 runtime')
    torch.set_num_threads(1)
    return m

def native_contract(m):
    r=subprocess.run([str(m.binary()),'--stationary-contract'],env=m.environment(),capture_output=True,text=True)
    try:d=json.loads(r.stdout)
    except ValueError:raise RuntimeError('Install the COMPLETE stationary-pilot update including native/GigaForge.exe; existing models remain untouched') from None
    if r.returncode or d.get('version')!='stationary-pilot-v1':raise RuntimeError('Native stationary contract unavailable')
    return d

def latest(path):
    choices=[p for p in Path(path).glob('*') if p.name.isdigit() and p.is_dir() and (p/'COMPLETE').is_file()]
    return max(choices,key=lambda p:int(p.name)) if choices else None

def pin(m,study,source,family):
    identity=model_identity(m,source,family);target=study/'pins'/digest(identity)[:20]
    if not target.exists():
        target.mkdir(parents=True)
        for name in identity['files']:shutil.copy2(Path(source)/name,target/name)
        m.seal_generation(target,family)
    if model_identity(m,target,family)!=identity:raise ValueError('Pinned actor identity changed')
    return target

def historical_seed_ranges(m):
    """Read saved evaluation requests/rows, not model files or login data."""
    ranges=[]
    def visit(value):
        if isinstance(value,dict):
            seed=value.get('seed',value.get('base_seed'))
            if type(seed) is int:
                pairs=value.get('pairs',value.get('rounds',2)//2)
                pairs=pairs if type(pairs) is int and pairs>0 else 1
                opponents=len(value.get('opponents',[])) if isinstance(value.get('opponents'),list) else 1
                ranges.append((seed,seed+pairs-1+10000*max(0,opponents-1)))
            for child in value.values():visit(child)
        elif isinstance(value,list):
            for child in value:visit(child)
    for run in (m.ROOT/'runs').glob('*'):
        for folder in ('evaluations','h2h'):
            for p in (run/folder).rglob('*.json'):
                if p.is_symlink() or p.stat().st_size>16*1024**2:continue
                try:visit(m.read(p))
                except (OSError,ValueError):continue
    return ranges

def seed_plan(m):
    used=historical_seed_ranges(m);rng=random.SystemRandom()
    for _ in range(1000):
        base=rng.randrange(1_000_000_000,1_850_000_000,10000)
        # Reserve a wide interval for all fixed development/final jobs.
        if all(base+100000<a or base>b for a,b in used):
            return dict(development_base=base,confirmation_base=base+50000,
                        reserved_interval=[base,base+100000],
                        historical_range_count=len(used),
                        scope='Disjoint from readable saved evaluation seeds/requests; no claim of unseen physical states')
    raise RuntimeError('Could not reserve fresh evaluation seeds')

def initialize(m,name,args):
    study=m.folder(name);native_contract(m)
    config=dict(version='stationary-pilot-v1',family='chronos',hitbox='breakout',device=m.device(args.device),
                decisions=args.decisions,rollout=args.rollout,games=args.games,warmup_iterations=args.warmup,
                batch=256,minibatch=256,epochs=2,actor_lr=3e-6,critic_lr=3e-4,anchor_coef=.04,
                gamma=.999,gae_lambda=.97,clip_range=.05,temperature=.25,
                training_seed=371031,opponent='original_chronos',development_pairs=args.pairs,
                evaluation_seconds=args.seconds,arms=ARMS,native_sha256=m.sha(m.binary()),
                controller_sha256=m.sha(Path(__file__)),jobs_sha256=m.sha(ROOT/'stationary_jobs.py'))
    path=study/'pilot_config.json'
    if path.exists():
        previous=m.read(path)
        if args.device=='auto':config['device']=previous['device']
        if previous!=config:raise ValueError('Experiment configuration or executable changed. Use the original settings/binary or a NEW --run; no in-place objective change.')
        return study,previous
    if study.exists():raise FileExistsError('Use a new run name; existing studies are never converted')
    from nova.teachers import fetch_teachers,verify_teacher
    fetch_teachers(['chronos','galactus'])
    study.mkdir(parents=True)
    parents={}
    for family in ('chronos','galactus'):
        parent=study/'parents'/family;parent.mkdir(parents=True)
        for name_ in ('SHARED_HEAD.lt','POLICY.lt'):shutil.copy2(verify_teacher(family)/name_,parent/name_)
        m.seal_generation(parent,family);parents[family]=model_identity(m,parent,family)
    m.write(path,config)
    m.write(study/'initialization.json',dict(parents=parents,seed_plan=seed_plan(m),native_contract=native_contract(m),
                objective='Stationary +/-10 goal outcome; no event bonuses, shared win-rate counters, or defensive curriculum. Same original Chronos opponent and initialization in both arms.',
                critic='Fresh identical seeded critic; warmup; critic gradients detached from frozen actor trunk',
                resumption='Native optimizers/counters resume; simulator arenas restart at native invocation boundaries, not bitwise uninterrupted trajectory restoration',
                telemetry_limits='Available RAM and NVIDIA GPU temperature/memory monitored. No claim of CPU temperature coverage.'))
    m.write(study/'pilot_state.json',dict(status='ready',arms={},automatic_promotion=False))
    return study,config

def recipe(m,study,cfg,arm):
    import rlgym.rocket_league.sim as sim
    branch=study/'arms'/arm;branch.mkdir(parents=True,exist_ok=True)
    return dict(family='chronos',hitbox='breakout',device=cfg['device'],seed=cfg['training_seed'],
                games=cfg['games'],simulation_threads=4,torch_threads=1,
                gamma=cfg['gamma'],gae_lambda=cfg['gae_lambda'],clip_range=cfg['clip_range'],epochs=cfg['epochs'],
                rollout=cfg['rollout'],batch=cfg['batch'],minibatch=cfg['minibatch'],
                actor_lr=cfg['actor_lr'],critic_lr=cfg['critic_lr'],policy_temperature=cfg['temperature'],
                warmup_iterations=cfg['warmup_iterations'],freeze_shared=True,anchor_coef=cfg['anchor_coef'],
                stationary_objective=arm,potential_weights=cfg['arms'][arm],
                winrate_dominance_reward=False,mechanics_reward=False,defensive_mechanics_reward=False,
                validated_antidive_reward=False,defensive_curriculum_prob=0.,
                trajectory_seconds=60.,fixed_rollout=True,stop_at=cfg['decisions'],
                anchor=str(study/'parents/chronos'),opponent=m.descriptor(study/'parents/chronos','chronos'),
                checkpoints=str(branch/'checkpoints'),metrics_file=str(branch/'metrics.jsonl'),stop_file=str(study/'STOP'),
                meshes=str(Path(sim.__file__).parent/'collision_meshes'))

def checkpoint_checks(m,parent,candidate,metrics):
    import torch
    from nova.giga_teachers import GigaNetwork
    a=GigaNetwork(parent,'chronos').state_dict();b=GigaNetwork(candidate,'chronos').state_dict()
    if not all(torch.equal(a[k],b[k]) for k in a if k.startswith('head.')):raise ValueError('Frozen shared trunk changed')
    rows=[json.loads(s) for s in Path(metrics).read_text().splitlines() if s.strip()]
    if any(r['Collected Timesteps']!=r['Used Timesteps'] or r.get('Data Use Fraction')!=1 for r in rows):raise ValueError('Learner data lost or reused across rollouts')
    if not all((candidate/n).is_file() for n in ('CRITIC.lt','POLICY_OPTIM.lt','CRITIC_OPTIM.lt','RUNNING_STATS.json')):
        raise ValueError('Missing resumable optimizer/critic state')
    return dict(logged_collected=sum(r['Collected Timesteps'] for r in rows),
                logged_used=sum(r['Used Timesteps'] for r in rows),
                actor_sample_uses=sum(r.get('Actor Sample Uses',0) for r in rows),
                actor_steps=sum(r.get('Actor Optimizer Steps',0) for r in rows),
                collection_seconds=sum(r.get('Collection Time',0) for r in rows),
                consumption_seconds=sum(r.get('Consumption Time',0) for r in rows),frozen_trunk_verified=True)

def study_lock(m,name):
    from filelock import FileLock
    m.folder(name) # validate before constructing a lock path
    folder=m.ROOT/'work/stationary_locks';folder.mkdir(parents=True,exist_ok=True)
    return FileLock(str(folder/(name+'.lock')),timeout=0)

def train(m,name,args):
    with study_lock(m,name):return train_locked(m,name,args)

def train_locked(m,name,args):
    study,cfg=initialize(m,name,args);stop=study/'STOP';stop.unlink(missing_ok=True)
    deadline=time.monotonic()+args.minutes*60
    state=m.read(study/'pilot_state.json');state.pop('error',None)
    print('STATIONARY_PILOT:',study,'two matched arms; original Chronos/Breakout; no champion changes',flush=True)
    print('BUDGET:',args.minutes,'wall minutes; combined resident RAM cap 12 GiB; GPU stop 86 C / 3584 MiB; minimum available RAM 2 GiB. CPU temperature unavailable.',flush=True)
    try:
        state['status']='training';m.write(study/'pilot_state.json',state)
        for arm in ARMS:
            branch=study/'arms'/arm;spec=recipe(m,study,cfg,arm)
            current=latest(branch/'checkpoints')
            if current is None or int(current.name)<cfg['decisions']:
                print('PILOT_ARM:',arm,'target learner decisions',cfg['decisions'],flush=True)
                launch(m,spec,branch,stop,deadline,metrics=spec['metrics_file'],guard=not args.no_resource_guard)
                current=latest(branch/'checkpoints')
            if current is None or int(current.name)<cfg['decisions']:raise PilotPaused('Native job stopped before the target')
            checks=checkpoint_checks(m,study/'parents/chronos',current,spec['metrics_file'])
            pinned=pin(m,study,current,'chronos')
            state['arms'][arm]=dict(checkpoint=str(current),pin=str(pinned),checks=checks)
            m.write(study/'pilot_state.json',state)
        state['status']='development_evaluation';m.write(study/'pilot_state.json',state)
        base=m.read(study/'initialization.json')['seed_plan']['development_base']
        rows_by_model={}
        # Original reference and both arms see the same two frozen opponents and seeds.
        for label,candidate in [('original_chronos',study/'parents/chronos')]+[(a,Path(state['arms'][a]['pin'])) for a in ARMS]:
            rows=[]
            for index,family in enumerate(('chronos','galactus')):
                print('PILOT_EVAL:',label,'vs original_'+family,flush=True)
                rows+=evaluate(m,study,candidate,study/'parents'/family,'chronos',family,'original_'+family,
                    pairs=cfg['development_pairs'],seed=base+index*10000,seconds=cfg['evaluation_seconds'],
                    device=cfg['device'],stop=stop,deadline=deadline,guard=not args.no_resource_guard)
            rows_by_model[label]=rows
            s=summary(rows);print('PILOT_SCORE:',label,s,flush=True)
            m.write(study/'development_progress.json',{k:summary(v) for k,v in rows_by_model.items()})
        report={}
        baseline=summary(rows_by_model['original_chronos'])['score_rate']
        for label,rows in rows_by_model.items():
            report[label]=dict(summary=summary(rows),per_opponent={f:summary([r for r in rows if r['opponent']=='original_'+f]) for f in ('chronos','galactus')},
                               panel_score_difference_vs_original=summary(rows)['score_rate']-baseline,
                               paired_panel_difference=paired_difference(rows,rows_by_model['original_chronos']))
        chosen=max(ARMS,key=lambda a:report[a]['summary']['score_rate'])
        state.update(status='pilot_complete',selected_preview=chosen,development=report,
                     conclusion='Development screen only. No independent strength claim or automatic promotion.')
        m.write(study/'development_raw.json',rows_by_model)
        print('PILOT_COMPLETE:',chosen,'unverified preview; compare development panel differences before spending on final confirmation',flush=True)
    except PilotPaused as error:state.update(status='paused',reason=str(error));print('PILOT_PAUSED:',error,flush=True)
    except Exception as error:state.update(status='error',error=str(error));raise
    finally:m.write(study/'pilot_state.json',state)
    return state

def actor(m,study):
    import torch
    from nova.giga_teachers import GigaNetwork
    from nova.forge_models import DirectActor,save_actor
    state=m.read(study/'pilot_state.json');arm=state.get('selected_preview')
    if not arm:raise RuntimeError('Complete both pilot arms and the development screen before watching/exporting the selected preview')
    source=Path(state['arms'][arm]['pin']);target=source/'actor.lt'
    if not target.exists():
        network=DirectActor('chronos');network.core.load_state_dict(GigaNetwork(source,'chronos').state_dict(),strict=True)
        save_actor(network,target,'chronos',hitbox='breakout',role='unverified stationary pilot '+arm,
                   source_native=m.read(source/'native.json'))
    return target

def watch_actor(m,study):
    import torch
    from contextlib import chdir
    from filelock import FileLock
    from nova.forge_env import ForgeEnv
    from nova.forge_eval import action
    from nova.forge_models import check_actor
    from nova.viewer import prepare_viewer,learner_first_state
    path=actor(m,study);check_actor(path,'chronos');model=torch.jit.load(str(path),map_location='cpu').eval()
    cfg=m.read(m.NOVA/'configs/forge_league.json');cfg['hitboxes']={'chronos':'breakout','galactus':'octane'}
    lock=m.NOVA/'work/rlviser-watch.lock';lock.parent.mkdir(parents=True,exist_ok=True)
    with FileLock(str(lock),timeout=0),chdir(m.NOVA):
        prepare_viewer(mode='auto')
        from rlgym.rocket_league.rlviser import RLViserRenderer
        env=ForgeEnv(cfg,'chronos',[dict(name='chronos')],profile='match',side=0,scenario='kickoff',seconds=135.)
        renderer=RLViserRenderer(tick_rate=15)
        try:
            obs,_=env.reset(seed=271031)
            print('WATCH: BLUE = unverified stationary preview; ORANGE = original Chronos. Both Breakout. Ctrl+C stops.',flush=True)
            while True:
                started=time.monotonic();obs,_,done,_,info=env.step(action(model,obs,'chronos'))
                renderer.render(learner_first_state(env.arena.state,env.arena.agent),{})
                if done:print('MATCH:',info,flush=True);obs,_=env.reset()
                time.sleep(max(0.,1/15-(time.monotonic()-started)))
        except KeyboardInterrupt:pass
        finally:
            try:renderer.close()
            finally:env.close()

def confirm(m,study,args):
    with study_lock(m,study.name):return confirm_locked(m,study,args)

def confirm_locked(m,study,args):
    cfg=m.read(study/'pilot_config.json');native_contract(m)
    if m.sha(m.binary())!=cfg['native_sha256']:raise ValueError('Native executable changed; do not combine evaluations')
    state=m.read(study/'pilot_state.json');arm=state.get('selected_preview')
    if not arm:raise RuntimeError('No selected development candidate')
    if state['development'][arm]['panel_score_difference_vs_original']<=0:
        raise RuntimeError('Selected preview did not beat the original panel score in development. Do not spend a final test on this unchanged candidate.')
    stop=study/'STOP';stop.unlink(missing_ok=True);deadline=time.monotonic()+args.minutes*60
    base=m.read(study/'initialization.json')['seed_plan']['confirmation_base']
    result_file=study/'confirmation.json'
    rows=[]
    for offset in range(0,1000,50):
        rows+=evaluate(m,study,Path(state['arms'][arm]['pin']),study/'parents/chronos','chronos','chronos','original_chronos',
                       pairs=50,seed=base+offset,seconds=135.,device=cfg['device'],stop=stop,deadline=deadline,guard=not args.no_resource_guard)
        print('CONFIRM_PROGRESS:',summary(rows),flush=True)
    result=dict(candidate=arm,identity=model_identity(m,Path(state['arms'][arm]['pin'])),summary=summary(rows),trials=rows,
                qualifies_primary_test=summary(rows)['score_interval_95'][0]>.5,
                automatic_promotion=False,scope='One predeclared finalist; broader regressions and deployment still require review')
    m.write(result_file,result)
    print('CONFIRM_RESULT:',result['summary'],'primary criterion',result['qualifies_primary_test'],flush=True)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['train','pause','status','watch','export','report','confirm','verify'])
    p.add_argument('--run',default='stationary01');p.add_argument('--device',choices=['auto','cpu','cuda'],default='auto')
    p.add_argument('--minutes',type=float,default=30.);p.add_argument('--decisions',type=int,default=393216)
    p.add_argument('--rollout',type=int,default=8192);p.add_argument('--games',type=int,default=64)
    p.add_argument('--warmup',type=int,default=8);p.add_argument('--pairs',type=int,default=32)
    p.add_argument('--seconds',type=float,default=135.);p.add_argument('--no-resource-guard',action='store_true',help=argparse.SUPPRESS)
    args=p.parse_args()
    if not math.isfinite(args.minutes) or args.minutes<=0 or args.warmup<1 or args.rollout<256 or args.rollout%256 or args.decisions%args.rollout or args.decisions<=args.warmup*args.rollout:
        p.error('Use positive budgets, rollout multiples of 256, and decisions beyond critic warmup')
    if not 1<=args.games<=256 or args.rollout%args.games or not 1<=args.pairs<=128 or not math.isfinite(args.seconds) or args.seconds<=0 or args.seconds*15!=round(args.seconds*15):
        p.error('Use valid game/evaluation counts, games dividing the rollout, and positive durations aligned to 1/15s')
    m=runtime();study=m.folder(args.run)
    if args.command=='train':train(m,args.run,args)
    elif args.command=='verify':print(native_contract(m));subprocess.run([str(m.binary()),'--stationary-selftest'],env=m.environment(),check=True)
    elif not (study/'pilot_state.json').is_file():raise FileNotFoundError('Pilot study not created; use 36_START_STATIONARY_PILOT first')
    elif args.command=='pause':(study/'STOP').touch();print('Pause requested for this pilot only; wait for native checkpoint completion')
    elif args.command=='status':print(json.dumps(m.read(study/'pilot_state.json'),indent=2))
    elif args.command=='confirm':confirm(m,study,args)
    elif args.command=='watch':watch_actor(m,study)
    elif args.command=='export':
        from nova.forge_export import export_actor_bundle
        print(export_actor_bundle(actor(m,study),m.ROOT/'exports'/args.run,label='unverified stationary pilot'))
    elif args.command=='report':
        target=m.ROOT/'reports'/f'{args.run}_{time.time_ns()}.zip';target.parent.mkdir(exist_ok=True)
        with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
            for file in study.rglob('*'):
                if file.is_file() and file.suffix in ('.json','.jsonl','.csv','.log') and not any(v in file.parts for v in ('checkpoints','pins','parents')):
                    z.write(file,file.relative_to(study))
        print('PILOT_REPORT:',target,flush=True)

if __name__=='__main__':
    try:main()
    except PilotPaused as error:print('PILOT_PAUSED:',error,flush=True)
