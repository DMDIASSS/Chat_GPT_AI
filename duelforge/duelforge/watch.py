import copy,json,time,webbrowser
from collections import deque
from pathlib import Path
import numpy as np
import torch
from .runtime import ROOT,model,batch,device,pin,sha,atomic_json


def watch(folder,seconds=120,opponent='initial',scene=-2,headless=False,frames=None,checkpoint=None):
    folder=Path(folder)
    if not 0<seconds<=600:raise ValueError('Watch duration must be 0..600 seconds')
    actor,ck,path=model(folder,checkpoint=checkpoint);cfg=copy.deepcopy(ck['config']);dev=device(cfg);torch.set_num_threads(cfg['torch_threads']);actor.to(dev)
    other=None;nexto=None
    if opponent=='nexto':
        from .nexto import Nexto
        nexto=Nexto();label='Nexto neural (stock scripted kickoff disabled)';opphash=nexto.identity
    elif opponent=='self':other=actor;label='same frozen learned actor';opphash=ck['_source_sha256']
    else:
        op=folder/'initial.pt' if opponent=='initial' else Path(opponent);other,d,_=model(folder,checkpoint=op,dev=dev);label='frozen initial policy' if opponent=='initial' else str(op);opphash=d['_source_sha256']
    from .viewer import Viewer
    viewer=None if headless else Viewer();env=batch(cfg,n=1,seconds=seconds+10);env.scene(scene);raw=env.observe();locations=env.pad_locations();records=deque(maxlen=1800);start=time.perf_counter();ticks=0;k=0;score=[0,0];contacts=[0,0];output=folder/'watch'/str(time.time_ns());output.mkdir(parents=True)
    print('LIVE WATCH: BLUE = learned actor,',ck['learning_transitions'],'transitions; ORANGE =',label,'; both Octane. No training. Ctrl+C saves the recording.',flush=True)
    metadata={'model_sha256':ck['_source_sha256'],'learning_transitions':ck['learning_transitions'],'opponent':label,'opponent_sha256':opphash,'scene':scene,'physics_hz':120,'tick_skip':8,'action_delay':7,'rewards':cfg['rewards'],'recording_cap_frames':1800,'note':'Actual native gameplay transitions, not replay imitation or a scripted controller. Top-down inspector is diagnostic, not the 3D viewer.'}
    try:
        with torch.inference_mode():
            while ticks<seconds*120 and (frames is None or k<frames):
                before=raw;logits,value=actor(torch.as_tensor(raw['obs'].reshape(2,109),device=dev),torch.as_tensor(raw['mask'].reshape(2,90),device=dev));ac=logits.argmax(-1).cpu().numpy().reshape(1,2)
                if nexto is not None:ac[:,1]=nexto.act(raw,locations,np.array([1]))
                elif other is not actor:ac[:,1]=other(torch.as_tensor(raw['obs'][:,1],device=dev),torch.as_tensor(raw['mask'][:,1],device=dev))[0].argmax(-1).cpu().numpy()
                probabilities=logits.softmax(-1).cpu().numpy()[0];top=np.argsort(probabilities)[-5:][::-1];v=float(value[0]);raw=env.step(ac);dt=int(raw['info'][0,3]);ticks+=dt;k+=1;g=int(raw['info'][0,0]);score[0]+=g>0;score[1]+=g<0;contacts[0]+=int(raw['info'][0,1]);contacts[1]+=int(raw['info'][0,2])
                records.append({'time':ticks/120,'world':raw['final_world'][0].tolist(),'pads':raw['final_pads'][0].tolist(),'before_world':before['world'][0].tolist(),'before_pads':before['pads'][0].tolist(),'touches':raw['info'][0,1:3].astype(bool).tolist(),'obs_blue':before['obs'][0,0].tolist(),'actions':ac[0].tolist(),'top_actions':[[int(i),float(probabilities[i])] for i in top],'value_blue':v,'reward_parts':raw['reward_parts'][0].tolist(),'goal':g,'score':score.copy(),'ticks':dt,'reset':bool(raw['terminated'][0] or raw['truncated'][0])})
                if viewer:viewer.send(raw,locations)
                if k%75==0 or g:print('WATCH:',round(ticks/120,1),'seconds; score',score,'touches',contacts,flush=True)
                if not headless:time.sleep(max(0,ticks/120-(time.perf_counter()-start)))
    except KeyboardInterrupt:print('WATCH_STOPPED: saving the completed frames.',flush=True)
    finally:
        if viewer:viewer.close()
        if records:
            np.savez_compressed(output/'frames.npz',world=np.asarray([r['world'] for r in records],np.float32),before_world=np.asarray([r['before_world'] for r in records],np.float32),before_pads=np.asarray([r['before_pads'] for r in records],np.float32),touches=np.asarray([r['touches'] for r in records],bool),pads=np.asarray([r['pads'] for r in records],np.float32),actions=np.asarray([r['actions'] for r in records],np.int64),reward_parts=np.asarray([r['reward_parts'] for r in records],np.float32),ticks=np.asarray([r['ticks'] for r in records],np.int32),obs_blue=np.asarray([r['obs_blue'] for r in records],np.float32),top_actions=np.asarray([r['top_actions'] for r in records],np.float32),value_blue=np.asarray([r['value_blue'] for r in records],np.float32),goals=np.asarray([r['goal'] for r in records],np.int8),score=np.asarray([r['score'] for r in records],np.int32))
            atomic_json(output/'metadata.json',metadata)
            from .inspector import write
            write(output/'inspect.html',metadata,records)
            print('WATCH_INSPECTOR:',output/'inspect.html',flush=True)
        else:print('No completed frames recorded.',flush=True)
    return output
