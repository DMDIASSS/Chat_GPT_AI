import argparse,copy,json,os,shutil,sys,time,webbrowser
from pathlib import Path
import numpy as np
import torch
from .runtime import ROOT,config,batch,device,atomic_json,load,save,sha,lock,model,CONTRACT


def verify(cfg=None):
    cfg=cfg or config();from . import _native
    from .observation import ACTIONS,encode
    from .model import ActorCritic
    torch.set_num_threads(2);np.testing.assert_array_equal(_native.action_table(),ACTIONS);env=batch(cfg,n=2);r=env.observe();locations=env.pad_locations()
    for _ in range(30):
        x,l=encode(r['world'],r['pads'],locations);np.testing.assert_allclose(x,r['obs'],atol=2e-6,rtol=2e-6);np.testing.assert_array_equal(l,r['mask']);r=env.step(np.full((2,2),16,np.int64));assert np.isfinite(r['world']).all()
    m=ActorCritic(cfg['width']).eval()
    with torch.inference_mode():a,v=m(torch.from_numpy(r['obs'].reshape(-1,109)),torch.from_numpy(r['mask'].reshape(-1,90)))
    assert a.shape==(4,90) and torch.isfinite(a).all() and torch.isfinite(v).all()
    print('VERIFY_PASS: native load, 109 observation features, DF90-v1 actions/masks, finite physics/rewards/model. This does not certify playing strength.',flush=True)


def benchmark(cfg=None,seconds=5):
    cfg=cfg or config();torch.set_num_threads(cfg['torch_threads']);dev=device(cfg)
    from .model import ActorCritic
    actor=torch.jit.script(ActorCritic(cfg['width']).to(dev).eval());rows=[]
    for n,workers in ((32,1),(64,2),(128,2),(128,3)):
        c=copy.deepcopy(cfg);c['native_threads']=workers;env=batch(c,n=n);raw=env.observe();count=physics=0;start=None
        with torch.inference_mode():
            for k in range(1000000):
                if k==10:start=time.perf_counter()
                logits,_=actor(torch.as_tensor(raw['obs'].reshape(-1,109),device=dev),torch.as_tensor(raw['mask'].reshape(-1,90),device=dev));raw=env.step(logits.argmax(-1).cpu().numpy().reshape(n,2))
                if start is not None:
                    count+=n*2;physics+=int(raw['info'][:,3].sum())
                    if time.perf_counter()-start>=seconds:break
        elapsed=time.perf_counter()-start;row={'arenas':n,'workers':workers,'device':str(dev),'player_decisions_per_second':count/elapsed,'physics_ticks_per_second':physics/elapsed,'seconds':elapsed,'scope':'Native physics + observations + masks + rewards + neural inference + transfer. PPO updates excluded.'};rows.append(row);print('COLLECTION_BENCHMARK:',json.dumps(row),flush=True)
    atomic_json(ROOT/'results/collection_benchmark.json',{'results':rows,'recommendation':'Default remains 64 arenas/2 workers until complete PPO throughput is measured; no automatic training config changes.'});return rows


def fork(source,target,nexto=False):
    source=Path(source);target=Path(target)
    if target.exists():raise FileExistsError(f'{target} exists; preserved')
    if nexto:
        from .nexto import fetch
        fetch()
    import tempfile
    target.parent.mkdir(parents=True,exist_ok=True)
    with lock(source):
        if not (source/'initial.pt').is_file():raise FileNotFoundError('Source initial policy missing; no alternative parent was selected')
        state=load(source/'latest.pt');h=sha(source/'latest.pt');stage=Path(tempfile.mkdtemp(prefix='.fork_',dir=target.parent))
        try:
            for name in state['history']:
                if Path(name).name!=name:raise ValueError('Invalid history path')
                (stage/'history').mkdir(exist_ok=True);shutil.copy2(source/'history'/name,stage/'history'/name)
            shutil.copy2(source/'initial.pt',stage/'initial.pt');shutil.copy2(source/'latest.pt',stage/'fork_parent.pt');state['config']=copy.deepcopy(state['config']);state['wandb_id']=None
            if nexto:state['config']['league']['nexto_fraction']=.2
            save(stage/'latest.pt',state);atomic_json(stage/'config.json',state['config']);atomic_json(stage/'provenance.json',{'source':str(source),'parent_checkpoint_sha256':h,'model_optimizer_counters_preserved':True,'nexto_neural_fraction':state['config']['league'].get('nexto_fraction',0),'scripted_kickoff':False})
            os.rename(stage,target)
        finally:
            if stage.exists():shutil.rmtree(stage)
    return target


def start_learning(minutes=60,max_updates=None):
    from .train import train
    folder=ROOT/'runs/duel02'
    if (folder/'latest.pt').is_file():return train(folder,minutes=minutes,max_updates=max_updates)
    cfg=config(ROOT/'config_learning.json')
    from .profile import profile,select_arenas
    # Profile scratch models once before creating the real run. No old run is
    # resumed; the selected arena count then stays frozen in its checkpoint.
    result=profile(seconds=1.,full=True,cfg=cfg)
    cfg['n_envs']=select_arenas(result,cfg['n_envs'])
    chosen=next((r for r in result['full_training'] if r['arenas']==cfg['n_envs']),None)
    if chosen:cfg['ppo']['steps']=chosen['rollout_steps']
    print('LEARNING_V2_START:',cfg['n_envs'],'arenas,',cfg['ppo']['steps'],'rollout decisions; 0.03 -> 0.003 entropy coefficient; temporary approach/contact bootstrap. New run duel02; duel01 preserved.',flush=True)
    return train(folder,cfg,minutes=minutes,max_updates=max_updates)


def pause(folder):
    targets=[];folder=Path(folder)
    if folder.is_dir():targets.append(folder)
    for name in ('duel02','potential01'):
        learning=ROOT/'runs'/name
        if learning.is_dir():targets.append(learning)
    active=ROOT/'experiments/pilot001/active.json'
    if active.is_file():
        state=json.loads(active.read_text());name=state.get('run','')
        if state.get('status')=='training' and name and Path(name).name==name:targets.append(ROOT/'runs'/name)
    if not targets:raise FileNotFoundError('No run or active pilot to pause')
    for target in set(targets):(target/'STOP').write_text('pause requested\n')
    print('PAUSE_REQUESTED:',', '.join(p.name for p in targets),'; wait for PAUSED_AND_SAVED in the trainer console.',flush=True)


def inspect_recording(path):
    import functools,http.server,threading
    path=Path(path).resolve();handler=functools.partial(http.server.SimpleHTTPRequestHandler,directory=str(path.parent));server=http.server.ThreadingHTTPServer(('127.0.0.1',0),handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();url=f'http://127.0.0.1:{server.server_port}/'+__import__('urllib.parse',fromlist=['quote']).quote(path.name)
    try:
        print('INSPECTOR:',url,'; press Enter here to close its local server.',flush=True);webbrowser.open(url);input()
    finally:server.shutdown();server.server_close();thread.join(timeout=2)


def menu(run='duel01'):
    folder=ROOT/'runs'/run
    while True:
        print('\nDUELFORGE — '+run+'\n1 Start / resume (60-minute cap, saves automatically)\n2 Pause and save\n3 Watch latest vs frozen initial policy (3D + recording)\n4 Watch open play vs initial\n5 Evaluate six contexts vs initial (120 games x 60s)\n6 Create report ZIP\n7 Export latest actor for RLBot v5\n8 Open last frame inspector\n9 Complete collection benchmark (no training)\n10 Fetch / verify Nexto neural opponent\n11 Watch latest vs Nexto neural\n12 Evaluate vs Nexto neural\n13 Fork this run with 20% Nexto training\n14 Bounded 90-minute A/B research pilot\n15 Watch exact best validation pin (unverified)\n16 Confirm 2000 fresh paired games vs frozen initial (100s)\n17 Start / resume learning-v2 experiment (separate duel02, 60 min)\n18 Watch learning-v2 open play\n19 Report learning-v2\n20 Profile physics / inference / full training\n23 Start/resume potential fork from trained duel02\n24 Watch potential fork vs trained parent\n25 Report potential experiment\n26 Evaluate potential vs parent (200 games x 100s)\n27 Export potential actor to RLBot v5\n0 Exit',flush=True)
        try:
            choice=input('Choose: ').strip()
            if choice=='0':return
            if choice=='1':
                from .train import train
                train(folder,minutes=60)
            elif choice=='2':
                pause(folder)
            elif choice in ('3','4','11','15'):
                from .watch import watch
                checkpoint=None
                if choice=='15':
                    info=json.loads((folder/'validation_best.json').read_text());checkpoint=folder/info['actor_path']
                    if not checkpoint.is_file() or sha(checkpoint)!=info['actor_sha256']:raise FileNotFoundError('Exact validation actor is missing/changed; no substitution')
                    print('UNVERIFIED_PIN:',info['learning_transitions'],'transitions, repeated open-play score',info['score_rate'])
                watch(folder,opponent='nexto' if choice=='11' else 'initial',scene=5 if choice in ('4','15') else -2,checkpoint=checkpoint)
            elif choice in ('5','12','16'):
                from .evaluate import evaluate
                evaluate(folder,games_per_context=2000 if choice=='16' else 20,seconds=100 if choice=='16' else 60,opponent='nexto' if choice=='12' else None,contexts=['match'] if choice=='16' else None)
            elif choice=='6':
                from .report import report
                report(folder)
            elif choice=='7':
                from .export import export
                export(folder)
            elif choice=='8':
                files=sorted((folder/'watch').glob('*/inspect.html'))
                if not files:raise FileNotFoundError('No watch recording exists; run Watch first')
                inspect_recording(files[-1])
            elif choice=='9':benchmark()
            elif choice=='10':
                from .nexto import fetch
                fetch()
            elif choice=='13':
                target=ROOT/'runs'/(run+'_nexto')
                if not target.exists():fork(folder,target,nexto=True)
                if not (target/'latest.pt').is_file() or load(target/'latest.pt')['config']['league'].get('nexto_fraction')!=.2:raise FileExistsError('Existing Nexto fork is incomplete or has a different config; preserved')
                from .train import train
                train(target,minutes=60)
            elif choice=='17':
                from .train import train
                start_learning()
            elif choice=='18':
                from .watch import watch
                watch(ROOT/'runs/duel02',scene=5)
            elif choice=='19':
                from .report import report
                report(ROOT/'runs/duel02')
            elif choice=='23':
                from .potential_experiment import start
                start()
            elif choice=='24':
                from .watch import watch
                watch(ROOT/'runs/potential01',scene=5)
            elif choice=='25':
                from .report import report
                report(ROOT/'runs/potential01')
            elif choice=='26':
                from .evaluate import evaluate
                evaluate(ROOT/'runs/potential01',200,100,contexts=['match'])
            elif choice=='27':
                from .export import export
                export(ROOT/'runs/potential01')
            elif choice=='20':
                from .profile import profile
                profile()
            elif choice=='14':
                from .pilot import run_pilot
                run_pilot()
        except KeyboardInterrupt:print('Stopped; completed checkpoints/recordings preserved.',flush=True)
        except Exception as ex:
            import traceback
            folder.mkdir(parents=True,exist_ok=True);atomic_json(folder/f'error_{time.time_ns()}.json',{'type':type(ex).__name__,'message':str(ex),'traceback':traceback.format_exc()})
            print(type(ex).__name__+': '+str(ex)+'\nOperation failed; error record saved for Report.',flush=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['menu','train','pause','watch','evaluate','report','export','verify','benchmark','fetch-nexto','pilot','profile','learn-v2','learn-potential']);p.add_argument('--run',default='duel01');p.add_argument('--config');p.add_argument('--minutes',type=float,default=60);p.add_argument('--updates',type=int);p.add_argument('--seconds',type=float,default=60);p.add_argument('--games',type=int,default=20);p.add_argument('--seed',type=int);p.add_argument('--opponent',default='initial');p.add_argument('--scene',type=int,default=-2);p.add_argument('--frames',type=int);p.add_argument('--headless',action='store_true');p.add_argument('--context',choices=list(__import__('duelforge.evaluate',fromlist=['CONTEXTS']).CONTEXTS));a=p.parse_args()
    if Path(a.run).name!=a.run or a.run in ('.','..'):p.error('Run name must be a simple directory name')
    folder=ROOT/'runs'/a.run
    if a.command=='menu':menu(a.run)
    elif a.command=='train':
        from .train import train
        train(folder,config(a.config) if a.config else None,a.minutes,a.updates)
    elif a.command=='pause':
        pause(folder)
    elif a.command=='verify':verify(config(a.config))
    elif a.command=='benchmark':benchmark(config(a.config),a.seconds)
    elif a.command=='watch':
        from .watch import watch
        watch(folder,a.seconds,a.opponent,a.scene,a.headless,a.frames)
    elif a.command=='evaluate':
        from .evaluate import evaluate
        evaluate(folder,a.games,a.seconds,a.seed,None if a.opponent=='initial' else a.opponent,[a.context] if a.context else None)
    elif a.command=='report':
        from .report import report
        report(folder)
    elif a.command=='export':
        from .export import export
        export(folder)
    elif a.command=='fetch-nexto':
        from .nexto import fetch
        fetch()
    elif a.command=='learn-potential':
        from .potential_experiment import start
        start(a.minutes,a.updates)
    elif a.command=='learn-v2':
        start_learning(a.minutes,a.updates)
    elif a.command=='profile':
        from .profile import profile
        profile()
    elif a.command=='pilot':
        from .pilot import run_pilot
        run_pilot()

if __name__=='__main__':main()
