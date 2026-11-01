"""Replay preparation, native learning and resumable checkpoint screening until paused.

Screens are exploratory and share seeds. Confirmation has fresh, separate seeds
and a summable error budget. Checkpoints and unresolved candidates are retained.
"""
from __future__ import annotations
import argparse,json,os,shutil,subprocess,sys,time
from pathlib import Path
from slater_v041_core import atomic_json,read_json,sha256,process_lock
from slater_native_actor import NativeActor,checkpoint_identity
from slater_native_eval import evaluate,paired_verdict,model_identity,identity_digest,EvaluationPaused,check_pause,code_identity
from slater_native_campaign import ROOT,BASE,helper,paths,discover,frozen_rivals,checkpoints,SKILLS,guard
import slater_replay_supply as supply

DEFAULT={
    'games':64,'steps':32768,'threads':2,'decisions_per_chunk':1000000,
    'iteration_limit':200,'old_chance':1.,'bc_epochs':5,
    'screen_seeds':2,'screen_seconds':45,'skill_seeds':2,'skill_seconds':8,
    'confirm_every':3,'confirm_seeds':12,'confirm_seconds':90,
    'min_disk_gb':10,'family_alpha':.05,
    'exploration_margin':.5,
    'kickoff_epochs':1,'kickoff_demos':32,
}
SCREEN_SEED=5100000000
QUALITY_BANK=ROOT/'data/isolated/ranked_duels_quality_bank01.bin'

def validate(cfg):
    for key,low,high in (('games',2,128),('steps',512,131072),('threads',1,8),
        ('decisions_per_chunk',1000,10000000),('iteration_limit',1,2000),
        ('bc_epochs',0,10),('screen_seeds',1,8),('screen_seconds',8,120),
        ('skill_seeds',1,8),('skill_seconds',8,30),('confirm_every',1,100),
        ('confirm_seeds',8,64),('confirm_seconds',8,300),('kickoff_epochs',0,5),('kickoff_demos',10,128)):
        if not isinstance(cfg[key],int) or not low<=cfg[key]<=high:raise ValueError('Invalid '+key)
    if not 0<=cfg['old_chance']<=1 or not 0<cfg['family_alpha']<=.05 or cfg['min_disk_gb']<0 or not 0<=cfg['exploration_margin']<=2:
        raise ValueError('Invalid opponent probability, error budget or disk floor')

def write_status(folder,state,**fields):
    state.update(fields);atomic_json(folder/'status.json',state)

def capacity(folder,cfg):
    free=shutil.disk_usage(folder).free/1024**3
    if free<cfg['min_disk_gb']:
        raise EvaluationPaused(f'Disk floor reached: {free:.1f} GiB free; checkpoints preserved')

def shortlist(folder,registry,state,limit=10):
    # JSON persistence sorts object keys; scores tied on resume must not change
    # the frozen confirmation challenger or exploratory warm-start choice.
    rows=sorted(registry.values(),key=lambda r:(-r['score']['mean_goal_diff'],
        -(r['score']['wins']-r['score']['losses']),r['path']))
    native=[r for r in rows if r['identity']['kind']=='native']
    report={'status':'PROVISIONAL_SHORT_MATCH_RANKING','screen_seconds':state['config']['screen_seconds'],
        'screen_seeds':state['config']['screen_seeds'],'native_shortlist':native[:limit],
        'overall_shortlist':rows[:limit],'models_preserved':len(rows),
        'confirmed_playing_checkpoint':state['confirmed_playing'],
        'specialists':state.get('specialists',{}),
        'unscripted_learner_report':state.get('unscripted_learner_report'),
        'note':'All screens use the same rivals, seeds and colors. These are exploratory scores, not an independent best-model guarantee.'}
    atomic_json(folder/'shortlist.json',report)
    lines=['# Overnight checkpoint shortlist','',report['note'],'',
        f"Preserved and screened models: {len(rows)}",'',
        '| Rank | Native checkpoint | Goal difference/game | W / D / L |',
        '| --- | --- | ---: | --- |']
    for i,r in enumerate(native[:limit],1):
        s=r['score'];lines.append(f"| {i} | `{r['path']}` | {s['mean_goal_diff']:.3f} | {s['wins']} / {s['draws']} / {s['losses']} |")
    lines+=['',f"Confirmed playing incumbent: `{state['confirmed_playing']}`",'',
        'Skill specialists (practice scores, not certified mastery):','']
    lines.extend(f"- {task}: `{r['path']}` (success rate {r['rate']:.3f})" for task,r in state.get('specialists',{}).items())
    if state.get('unscripted_learner_report'):
        lines+=['',f"Learner kickoff script OFF, rivals ON: `{state['unscripted_learner_report']}`"]
    tmp=folder/'SHORTLIST.md.writing';tmp.write_text('\n'.join(lines)+'\n',encoding='utf8');os.replace(tmp,folder/'SHORTLIST.md')
    return native

def screen(path,origin,folder,registry,state,rivals,build,stop):
    identity=model_identity(path);key=identity_digest(identity)
    if key not in registry:
        check_pause(stop)
        result=evaluate({'model':str(path)},rivals,out=folder/'screens'/f'{key}.json',
            seeds=state['config']['screen_seeds'],seconds=state['config']['screen_seconds'],
            seed_base=SCREEN_SEED,build_dir=build,stop_file=stop)
        registry[key]={'path':str(Path(path).resolve()),'identity':identity,'origin':origin,
            'score':result['ranking'][0],'report':str(folder/'screens'/f'{key}.json')}
        atomic_json(folder/'models.json',registry)
    shortlist(folder,registry,state)

def practice(path,folder,state,rivals,build,stop):
    cfg=state['config']
    report=evaluate({'model':path},{'fixed':next(iter(rivals.values()))},out=folder/'skills.json',
        seeds=cfg['skill_seeds'],seconds=cfg['skill_seconds'],seed_base=5200000000,
        build_dir=build,tasks=SKILLS,stop_file=stop)
    rates={}
    for task in SKILLS:
        rows=[r for r in report['records'] if r['task']==task]
        rate=sum(r['successes'] for r in rows)/max(1,sum(r['episodes'] for r in rows));rates[task]=rate
        best=state.setdefault('specialists',{}).get(task)
        if not best or rate>best['rate']:state['specialists'][task]={'path':path,'rate':rate,'report':str(folder/'skills.json')}
    # Rotate equally weak tasks instead of getting stuck on the first zero.
    order=list(SKILLS);cycle=state['cycle']
    focus=min(order,key=lambda task:(rates[task],(order.index(task)-cycle)%len(order)))
    if focus=='air_finish':focus='air_dribble'
    atomic_json(folder/'weaknesses.json',{'rates':rates,'focus':focus});return focus

def child(args,folder,state,stop,*,native_name=None):
    check_pause(stop);write_status(folder,state,active_run=native_name)
    proc=subprocess.Popen([str(a) for a in args],cwd=ROOT)
    try:
        while proc.poll() is None:
            if stop.exists() and native_name:
                active=helper().BASE/'runs'/native_name
                if active.is_dir():(active/'pause.flag').touch()
            time.sleep(.25)
        if stop.exists():raise EvaluationPaused('Pause completed; resume the same overnight launcher')
        if proc.returncode:raise RuntimeError(f'Child exited {proc.returncode}; see the saved native training log')
    finally:
        write_status(folder,state,active_run=None)

def learn(name,source,bank,focus,pool,folder,state,build,stop,*,bootstrap=False,bc_epochs=None):
    cfg=state['config'];h=helper();run=h.BASE/'runs'/name
    completed=read_json(run/'overnight_completed.json')
    if completed:
        results=[Path(p) for p in completed['checkpoints']]
        for p in results:checkpoint_identity(p)
        return results
    actor=NativeActor(source)
    capacity(folder,cfg);saved=checkpoints(run/'checkpoints');initial=int(Path(source).name)
    already=max(0,int(saved[-1].name)-initial) if saved else 0
    remaining=max(0,cfg['decisions_per_chunk']-already)
    protocol=read_json(run/'protocol.json')
    if bootstrap or remaining:
        args=[sys.executable,'-u',h.HERE/'native_setup.py','resume' if protocol else 'train',
            '--run',name,'--build-dir',build,'--device','auto','--games',cfg['games'],
            '--steps',cfg['steps'],'--threads',cfg['threads'],'--width',actor.width,'--depth',actor.depth,
            '--iterations',2 if bootstrap else cfg['iteration_limit'],
            '--bc-epochs',(cfg['bc_epochs'] if bc_epochs is None else bc_epochs) if bootstrap else 0,
            '--kickoff-epochs',cfg['kickoff_epochs'],'--kickoff-demos',cfg['kickoff_demos'],
            '--campaign','--focus','mixed' if bootstrap else focus,
            '--old-chance',cfg['old_chance'],'--save-every',cfg['decisions_per_chunk']]
        if not bootstrap:
            args+=['--decisions',remaining]
        if not protocol:
            args+=['--initial-checkpoint',source,'--replay-bank',bank]
            for path in pool or [source]:args+=['--frozen-checkpoint',path]
        child(args,folder,state,stop,native_name=name)
    saved=checkpoints(run/'checkpoints')
    if not saved:raise RuntimeError('Training produced no complete checkpoint')
    if not bootstrap and int(saved[-1].name)-initial<cfg['decisions_per_chunk']:
        raise RuntimeError('Iteration cap reached before the learner decision budget; checkpoints kept')
    # Bootstrap can overwrite only its private source copy with BC weights.
    results=saved if bootstrap else [p for p in saved if int(p.name)>initial]
    for p in results:checkpoint_identity(p)
    atomic_json(run/'overnight_completed.json',{'checkpoints':[str(p) for p in results]})
    return results

def refresh_replays(name,folder,state,registry,rivals,build,stop):
    settings={**supply.DEFAULT,**read_json(supply.CONFIG,{'enabled':False})}
    if not settings['enabled'] or not state['cycle'] or state['cycle']%settings['refresh_cycles']:return
    cycle=state['cycle']
    if state.get('replay_refresh_cycle')==cycle:return
    write_status(folder,state,status='ACQUIRING_FRESH_REPLAYS')
    try:pack=supply.batch(folder,cycle,cfg=settings,stop_file=stop)
    except supply.SupplyPaused as exc:raise EvaluationPaused(str(exc)) from None
    if pack:
        try:
            child([sys.executable,'-u',ROOT/'slater_native_campaign.py','prepare',
                '--inputs',pack['inputs'],'--dataset',pack['dataset'],'--bank',pack['bank'],
                '--max-replays',settings['batch_size']],folder,state,stop)
        except RuntimeError as exc:
            atomic_json(folder/'replay_supply_status.json',{'using_cached_bank':True,'reason':'Fresh batch preparation failed; inspect parser logs'})
            write_status(folder,state,replay_refresh_cycle=cycle);return
        previous=shortlist(folder,registry,state)[0]['path']
        for p in learn(f'{name}_replay_{cycle:05d}',previous,pack['bank'],'mixed',[],
            folder,state,build,stop,bootstrap=True,bc_epochs=2):
            screen(p,f'fresh_replay_batch_{cycle}',folder,registry,state,rivals,build,stop)
        state['active_bank']=pack['bank'];state['active_bank_sha']=sha256(pack['bank'])
    write_status(folder,state,replay_refresh_cycle=cycle)

def confirm(candidate,folder,state,rivals,build,stop):
    if Path(candidate).resolve()==Path(state['confirmed_playing']).resolve():return
    cfg=state['config'];attempt=state['confirmation_attempts']+1
    out=folder/'confirmations'/f'attempt_{attempt:04d}.json'
    # Challenger is frozen in this record before fresh confirmation is opened.
    record=out.with_suffix('.selection.json')
    frozen={'candidate':candidate,'reference':state['confirmed_playing'],'attempt':attempt}
    old=read_json(record)
    if old and old!=frozen:raise ValueError('Frozen confirmation candidate changed')
    atomic_json(record,frozen)
    result=evaluate({'challenger':candidate,'incumbent':state['confirmed_playing']},rivals,
        out=out,seeds=cfg['confirm_seeds'],seconds=cfg['confirm_seconds'],
        seed_base=5300000000+attempt*100000,build_dir=build,stop_file=stop)
    # Sum of 1/(k*(k+1)) is one: indefinite attempts retain an error budget.
    alpha=cfg['family_alpha']/(attempt*(attempt+1))
    verdict=paired_verdict(result,'challenger','incumbent',alpha=alpha)
    verdict.update(candidate_path=candidate,reference_path=state['confirmed_playing'])
    if verdict['passed']:
        verdict['retention_passed']=guard(candidate,state['confirmed_playing'],rivals,
            folder/'confirmations'/f'guard_{attempt:04d}',cfg,5400000000+attempt*100000,build,stop_file=stop)
        verdict['passed'] &= verdict['retention_passed']
    atomic_json(out.with_suffix('.verdict.json'),verdict)
    state['confirmation_attempts']=attempt
    if verdict['passed']:state['confirmed_playing']=candidate
    write_status(folder,state,last_confirmation=verdict)
    print('OVERNIGHT_CONFIRMATION', 'PASSED' if verdict['passed'] else 'CLOSE_OR_INCONCLUSIVE',flush=True)

def run(name,*,bank=QUALITY_BANK,build_dir=None,config=None,candidates=None,prepare=True,max_cycles=0):
    folder=paths(name);folder.mkdir(parents=True,exist_ok=True);stop=folder/'pause.flag'
    cfg={**DEFAULT,**(config or {})};validate(cfg)
    if max_cycles<0:raise ValueError('Invalid cycle limit')
    with process_lock(folder/'overnight.lock'):
        # Only the new owner may clear a prior pause request.
        stop.unlink(missing_ok=True)
        state=read_json(folder/'status.json',{})
        write_status(folder,state,status='PREPARING_REPLAYS',active_run=None)
        if prepare and not (folder/'protocol.json').is_file():
            try:
                child([sys.executable,'-u',ROOT/'slater_native_campaign.py','prepare','--bank',bank],folder,state,stop)
            except EvaluationPaused as exc:
                write_status(folder,state,status='PAUSED',reason=str(exc));return state
            except Exception as exc:
                write_status(folder,state,status='ERROR',reason=str(exc));raise
        h=helper();build=Path(build_dir or h.BASE/'build').resolve()
        old=read_json(folder/'protocol.json')
        if candidates is None:
            candidates={n:r['path'] for n,r in old['candidates'].items()} if old else discover()
        rivals=frozen_rivals(candidates)
        protocol={'candidates':{n:model_identity(p) for n,p in candidates.items()},'rivals':{n:model_identity(p) for n,p in rivals.items()},
            'config':cfg,'bank':str(Path(bank).resolve()),'bank_sha':sha256(bank),
            'build':str(build),'binary':h.binary_identity(build),'code':{**code_identity(),'overnight':sha256(__file__),
                'campaign':sha256(ROOT/'slater_native_campaign.py'),'supply':sha256(supply.__file__)}}
        if old and old!=protocol:raise ValueError('Overnight inputs changed; use a new --run name')
        if not old:atomic_json(folder/'protocol.json',protocol)
        if 'cycle' not in state:
            playing=str(next((p for n,p in candidates.items() if n=='update180'),next(iter(rivals.values()))))
            state.update(cycle=0,bootstrap_done=False,confirmed_playing=playing,confirmation_attempts=0,specialists={},lineages={})
        state['config']=cfg;registry=read_json(folder/'models.json',{})
        state.setdefault('active_bank',str(Path(bank).resolve()));state.setdefault('active_bank_sha',sha256(bank))
        if sha256(state['active_bank'])!=state['active_bank_sha']:raise ValueError('Active replay bank changed')
        supply.initial_seen(folder)
        try:
            write_status(folder,state,status='INITIAL_SCREEN')
            for label,path in candidates.items():screen(path,label,folder,registry,state,rivals,build,stop)
            native=shortlist(folder,registry,state)
            if not native:raise ValueError('No native checkpoint to train')
            if not state['bootstrap_done']:
                source=native[0]['path'];state.setdefault('bootstrap_source',source)
                write_status(folder,state,status='REPLAY_PRETRAINING')
                for p in learn(name+'_bc',state['bootstrap_source'],bank,'mixed',[],folder,state,build,stop,bootstrap=True):
                    screen(p,'replay_bc',folder,registry,state,rivals,build,stop)
                write_status(folder,state,bootstrap_done=True)
            while not max_cycles or state['cycle']<max_cycles:
                check_pause(stop);capacity(folder,cfg);index=state['cycle'];round_folder=folder/f'cycle_{index+1:05d}'
                refresh_replays(name,folder,state,registry,rivals,build,stop)
                plan=read_json(round_folder/'plan.json')
                if not plan:
                    native=shortlist(folder,registry,state);source=native[0]['path'];actor=NativeActor(source)
                    write_status(folder,state,status='MEASURING_MECHANICS')
                    focus=practice(source,round_folder/'before',state,rivals,build,stop)
                    pool=[r['path'] for r in native if (NativeActor(r['path']).width,NativeActor(r['path']).depth)==(actor.width,actor.depth)][:4]
                    sources={}
                    for label in ('mixed','focused'):
                        previous=state.get('lineages',{}).get(label)
                        row=next((r for r in native if r['path']==previous),None)
                        # Continue close exploration lineages without discarding the archive leader.
                        same_arch=bool(row) and (NativeActor(previous).width,NativeActor(previous).depth)==(actor.width,actor.depth)
                        sources[label]=previous if same_arch and row['score']['mean_goal_diff']>=native[0]['score']['mean_goal_diff']-cfg['exploration_margin'] else source
                    plan={'source':source,'sources':sources,'focus':focus,'pool':pool,
                        'bank':state['active_bank'],'bank_sha':state['active_bank_sha']};atomic_json(round_folder/'plan.json',plan)
                for label,focus in (('mixed','mixed'),('focused',plan['focus'])):
                    check_pause(stop);write_status(folder,state,status='TRAINING_'+label.upper(),cycle_focus=plan['focus'])
                    chunk=f'{name}_c{index+1:05d}_{label}'
                    if sha256(plan['bank'])!=plan['bank_sha']:raise ValueError('Planned replay bank changed')
                    learned=learn(chunk,plan['sources'][label],plan['bank'],focus,plan['pool'],folder,state,build,stop)
                    for p in learned:
                        write_status(folder,state,status='SCREENING_CHECKPOINTS')
                        screen(p,f'cycle_{index+1}_{label}',folder,registry,state,rivals,build,stop)
                    state.setdefault('lineages',{})[label]=str(learned[-1].resolve())
                native=shortlist(folder,registry,state)
                practice(native[0]['path'],round_folder/'after',state,rivals,build,stop)
                raw=evaluate({'leader':native[0]['path'],'reference':plan['source']},rivals,
                    out=round_folder/'unscripted_learner.json',seeds=cfg['screen_seeds'],seconds=cfg['screen_seconds'],
                    seed_base=5500000000,build_dir=build,stop_file=stop,learner_scripted=False)
                state['unscripted_learner_report']=str(round_folder/'unscripted_learner.json')
                if (index+1)%cfg['confirm_every']==0:
                    write_status(folder,state,status='INDEPENDENT_CONFIRMATION')
                    confirm(native[0]['path'],folder,state,rivals,build,stop)
                write_status(folder,state,cycle=index+1,status='CYCLE_COMPLETE',active_run=None)
                shortlist(folder,registry,state)
                print('OVERNIGHT_CYCLE_COMPLETE',index+1,'shortlist',folder/'SHORTLIST.md',flush=True)
            write_status(folder,state,status='CYCLE_LIMIT_REACHED')
        except EvaluationPaused as exc:
            write_status(folder,state,status='PAUSED',reason=str(exc),active_run=None)
            shortlist(folder,registry,state)
            print('OVERNIGHT_PAUSED',str(exc),flush=True)
        except Exception as exc:
            write_status(folder,state,status='ERROR',reason=str(exc),active_run=None)
            shortlist(folder,registry,state);raise
    return state

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=('run','pause','status'))
    p.add_argument('--run',default='native_overnight03');p.add_argument('--bank',default=str(QUALITY_BANK))
    p.add_argument('--build-dir');p.add_argument('--config');p.add_argument('--candidate',action='append')
    p.add_argument('--skip-prepare',action='store_true');p.add_argument('--max-cycles',type=int,default=0)
    a=p.parse_args();folder=paths(a.run)
    if a.command=='status':print(json.dumps(read_json(folder/'status.json',{}),indent=2));return
    if a.command=='pause':
        folder.mkdir(parents=True,exist_ok=True);(folder/'pause.flag').touch();state=read_json(folder/'status.json',{})
        if state.get('active_run'):
            active=helper().BASE/'runs'/state['active_run']
            if active.is_dir():(active/'pause.flag').touch()
        print('Pause requested. Native training saves after its current iteration; evaluation stops after its current match.');return
    candidates={f'model_{i}':str(Path(path).resolve()) for i,path in enumerate(a.candidate)} if a.candidate else None
    run(a.run,bank=a.bank,build_dir=a.build_dir,config=read_json(a.config,{}) if a.config else None,
        candidates=candidates,prepare=not a.skip_prepare,max_cycles=a.max_cycles)

if __name__=='__main__':main()
