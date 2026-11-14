import argparse,json,time,os,platform,zipfile,hashlib
from pathlib import Path
import numpy as np
import torch
from .runtime import ROOT,config,batch,device,atomic_json,source_hashes,save_checkpoint
from .model import ActorCritic
from .observation import encode,ACTIONS
from .train import train,load

def policy(folder,dev):
    p=Path(folder)/'latest.pt'
    if not p.is_file():raise FileNotFoundError(f'No trained checkpoint: {p}. Start training first; another bot is never substituted.')
    saved=load(p,dev);model=ActorCritic(**saved['config']['network']).to(dev).eval();model.load_state_dict(saved['model']);return model,saved

def benchmark(cfg,seconds=10):
    torch.set_num_threads(cfg['torch_threads']);dev=device(cfg);env=batch(cfg);loc=env.pad_locations();raw=env.observe();model=ActorCritic(**cfg['network']).to(dev).eval()
    n=cfg['n_envs'];a=cfg['team_size']*2
    # Warmup and measured loop include encoding, transfer, inference and simulation.
    count=0;physics=0;start=None
    with torch.no_grad():
        for i in range(1000000):
            if i==20:start=time.perf_counter()
            ob,lm=encode(raw['world'],raw['pads'],loc)
            logits,_=model(torch.as_tensor(ob.reshape(-1,43,40),device=dev),torch.as_tensor(lm.reshape(-1,90),device=dev))
            raw=env.step(logits.argmax(-1).cpu().numpy().reshape(n,a))
            if start is not None:
                count+=n;physics+=int(raw['info'][:,7].sum())
                if time.perf_counter()-start>=seconds:break
    elapsed=time.perf_counter()-start
    result={'device':str(dev),'cpu':platform.processor(),'arenas':n,'native_threads':cfg['native_threads'],'network_parameters':sum(p.numel() for p in model.parameters()),'seconds':elapsed,'env_decisions_per_second':count/elapsed,'player_decisions_per_second':count*a/elapsed,'physics_ticks_per_second':physics/elapsed,'scope':'simulation + encoding + inference; excludes PPO updates; not a learning-speed claim'}
    atomic_json(ROOT/'benchmark.json',result);print(json.dumps(result,indent=2));return result

def verify(cfg):
    from . import _attention_native as native
    torch.set_num_threads(cfg['torch_threads']);np.testing.assert_array_equal(native.action_table(),ACTIONS)
    env=batch(cfg,n=2);r=env.observe();o,m=encode(r['world'],r['pads'],env.pad_locations());model=ActorCritic(**cfg['network']).eval()
    with torch.no_grad():logits,v=model(torch.from_numpy(o.reshape(-1,43,40)),torch.from_numpy(m.reshape(-1,90)))
    assert torch.isfinite(logits).all() and torch.isfinite(v).all()
    for _ in range(30):r=env.step(np.full((2,cfg['team_size']*2),8,np.int64))
    assert np.isfinite(r['world']).all() and np.isfinite(r['rewards']).all();
    if cfg['rewards'].get('profile')!='rlgym_simple_v1':np.testing.assert_allclose(r['rewards'].sum(1),0,atol=1e-6)
    print('VERIFY_PASS: native load, 90-action parity, finite public observations, attention inference, finite rewards. This does not certify playing strength.',flush=True)

def report(folder):
    folder=Path(folder)
    if not folder.is_dir():raise FileNotFoundError(folder)
    target=ROOT/f'AttentionForge_report_{folder.name}_{time.strftime("%Y%m%d_%H%M%S",time.gmtime())}.zip'
    manifest={'run':folder.name,'generated_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'runtime':{'python':platform.python_version(),'torch':torch.__version__,'cuda_available':torch.cuda.is_available(),'torch_cuda':torch.version.cuda,'gpu_name':torch.cuda.get_device_name(0) if torch.cuda.is_available() else None},'source_hashes':source_hashes(),'checkpoint_hash':hashlib.sha256((folder/'latest.pt').read_bytes()).hexdigest() if (folder/'latest.pt').is_file() else None,'note':'No weights, credentials, environment variables, or W&B files are included.'}
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
        z.writestr('manifest.json',json.dumps(manifest,indent=2))
        for pattern in ('config.json','status.json','provenance.json','metrics.jsonl','wandb_status.json','eval_*.json'):
            for p in folder.glob(pattern):z.write(p,'run/'+p.name)
        for p in (ROOT/'attentionforge').glob('*.py'):z.write(p,'source/attentionforge/'+p.name)
        for p in (ROOT/'native/core.cpp',ROOT/'config.json',ROOT/'benchmark.json',ROOT/'laptop_autotune.json',ROOT/'FRAMEWORK_REVIEW.md',ROOT/'REWARD_SOURCES.md'):
            if p.is_file():z.write(p,'source/'+str(p.relative_to(ROOT)))
    print('REPORT_READY:',target);return target

def watch(cfg,folder,frames=None,headless=False):
    torch.set_num_threads(cfg['torch_threads']);dev=device(cfg);model,saved=policy(folder,dev);cfg=saved['config'];env=batch(cfg,n=1,kickoffs=True);loc=env.pad_locations();raw=env.observe();viewer=None
    if not headless:
        from .viewer import Viewer
        viewer=Viewer()
    print('LIVE MATCH: blue = latest attention policy; orange = same policy. Both Octane. No scripted controller. Ctrl+C exits; no training.',flush=True)
    start=time.perf_counter();k=0
    try:
        with torch.no_grad():
            while frames is None or k<frames:
                ob,lm=encode(raw['world'],raw['pads'],loc);logits,_=model(torch.as_tensor(ob.reshape(-1,43,40),device=dev),torch.as_tensor(lm.reshape(-1,90),device=dev))
                raw=env.step(logits.argmax(-1).cpu().numpy().reshape(1,-1));k+=1
                if viewer:viewer.send(raw,loc)
                if k%75==0 or raw['info'][0,0]:print('WATCH:',round(k*cfg['tick_skip']/120,1),'seconds; goal blue/orange:',raw['info'][0,0],'; touches this decision:',raw['info'][0,1:3].tolist(),flush=True)
                if not headless:time.sleep(max(0,k*cfg['tick_skip']/120-(time.perf_counter()-start)))
    except KeyboardInterrupt:pass
    finally:
        if viewer:viewer.close()

def export(folder):
    model,saved=policy(folder,torch.device('cpu'));out=ROOT/'exports'/f'{Path(folder).name}_{saved["learning_transitions"]:016d}'
    if out.exists():raise FileExistsError(f'Export already exists: {out}; preserved.')
    out.mkdir(parents=True);ob=torch.zeros(3,43,40);ob[:,0,39]=1;ob[:,1,39]=2;lm=torch.ones(3,90,dtype=torch.bool)
    # Disable native MHA inference fastpath so the graph accepts arbitrary batch sizes.
    torch.backends.mha.set_fastpath_enabled(False)
    frozen=torch.jit.trace(model,(ob,lm),check_trace=True);frozen.save(str(out/'actor.pt'))
    rng=np.random.default_rng(913);test=torch.from_numpy(rng.normal(size=(7,43,40)).astype(np.float32));test[:,:,39]=torch.randint(0,7,(7,43));test[:,0,39]=1;legal=torch.rand(7,90)>0.2;legal[:,0]=True
    with torch.no_grad():
        a,_=model(test,legal);b,_=torch.jit.load(str(out/'actor.pt'))(test,legal)
    torch.testing.assert_close(a,b);assert torch.equal(a.argmax(-1),b.argmax(-1))
    atomic_json(out/'model_config.json',saved['config']);atomic_json(out/'export_manifest.json',{'learning_transitions':saved['learning_transitions'],'actor_sha256':hashlib.sha256((out/'actor.pt').read_bytes()).hexdigest(),'logit_max_abs_error':float((a-b).abs().max()),'action_agreement':1.0,'hitbox':'Octane','architecture':'2-block ego-query attention','format':'TorchScript; not a renamed .lt','scope':'native play and RLBot v4 wrapper; v5 exporter not implemented'})
    import shutil
    shutil.copy(ROOT/'attentionforge/rlbot4_agent.py',out/'bot.py')
    # Copy the same observation implementation used for training; no native module needed in game.
    shutil.copy(ROOT/'attentionforge/observation.py',out/'observation.py')
    shutil.copy(ROOT/'export_bot.cfg',out/'bot.cfg');shutil.copy(ROOT/'appearance.cfg',out/'appearance.cfg')
    (out/'INSTALL.bat').write_text('@echo off\r\ncd /d "%~dp0"\r\npy -3.11 -m pip install "rlbot>=1.68,<2" "numpy>=1.26,<3" torch\r\npause\r\n')
    print('EXPORT_READY:',out,'; logits/actions match. RLBot v4 game launch requires local testing. v5/.lt is not claimed.',flush=True)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('command',choices=['verify','benchmark','train','pause','watch','report','export','evaluate','tune','laptop']);ap.add_argument('--run',default='attention01');ap.add_argument('--config');ap.add_argument('--minutes',type=float);ap.add_argument('--updates',type=int);ap.add_argument('--seconds',type=float,default=10);ap.add_argument('--frames',type=int);ap.add_argument('--headless',action='store_true');ap.add_argument('--rounds',type=int,default=100);ap.add_argument('--opponent');ap.add_argument('--seed',type=int);args=ap.parse_args()
    if Path(args.run).name!=args.run or args.run in ('.','..'):ap.error('--run must be a simple folder name')
    cfg=config(args.config);folder=ROOT/'runs'/args.run
    if args.command=='train':train(cfg,folder,args.updates,args.minutes)
    elif args.command=='pause':
        if not folder.is_dir():raise FileNotFoundError(folder)
        (folder/'STOP').write_text('pause requested\n');print('PAUSE_REQUESTED. Wait for PAUSED_AND_SAVED in the trainer window.')
    elif args.command=='watch':watch(cfg,folder,args.frames,args.headless)
    elif args.command=='export':export(folder)
    elif args.command=='report':report(folder)
    elif args.command=='verify':verify(cfg)
    elif args.command=='benchmark':benchmark(cfg,args.seconds)
    elif args.command=='tune':
        from .tune import tune
        tune()
    elif args.command=='laptop':
        from .laptop import menu
        menu(args.run)
    elif args.command=='evaluate':
        from .evaluate import evaluate
        evaluate(folder,args.rounds,args.seconds,args.opponent,args.seed)
if __name__=='__main__':main()
