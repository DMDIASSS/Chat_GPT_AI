"""Read-only color-symmetry diagnostic using the exact local learned actor."""
import argparse,json,sys
from pathlib import Path
import numpy as np
import torch
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from duelforge.runtime import batch,model,atomic_json
from duelforge.observation import encode,ACTIONS

def check(run='duel02',decisions=100):
    if Path(run).name!=run or run in ('.','..'):raise ValueError('Simple run name required')
    folder=ROOT/'runs'/run;actor,ck,_=model(folder);torch.set_num_threads(1);env=batch(ck['config'],n=8,seed=791733);rng=np.random.default_rng(7301)
    locations=env.pad_locations();sign=np.asarray([-1,-1,1]*5,np.float32);rot=locations[:,:3]*np.asarray([-1,-1,1]);inverse=np.argmin(((rot[:,None]-locations[None,:,:3])**2).sum(-1),axis=1);worst=0.
    with torch.inference_mode():
        for k in range(decisions):
            raw=env.observe();world=raw['world'].copy();world[:,:,:15]*=sign;world[:,[1,2]]=world[:,[2,1]];pads=raw['pads'][:,inverse]
            obs,mask=encode(world,pads,locations);worst=max(worst,float(np.abs(obs-raw['obs'][:,::-1]).max()))
            np.testing.assert_allclose(obs,raw['obs'][:,::-1],atol=2e-6,rtol=2e-6);np.testing.assert_array_equal(mask,raw['mask'][:,::-1])
            a=actor(torch.from_numpy(obs.reshape(-1,109)),torch.from_numpy(mask.reshape(-1,90)))[0].argmax(-1).numpy().reshape(8,2)
            b=actor(torch.from_numpy(raw['obs'].reshape(-1,109)),torch.from_numpy(raw['mask'].reshape(-1,90)))[0].argmax(-1).numpy().reshape(8,2)
            np.testing.assert_array_equal(a,b[:,::-1]);env.step(rng.integers(0,90,(8,2),dtype=np.int64))
    result={'status':'pass','model_sha256':ck['_source_sha256'],'learning_transitions':ck['learning_transitions'],'mirrored_player_decisions':decisions*16,'maximum_feature_error':worst,'masks_and_actions_match':True,'training_started':False,'checkpoint_modified':False}
    if (folder/'initial.pt').is_file():
        initial,ic,_=model(folder,checkpoint=folder/'initial.pt');result['initial_sha256']=ic['_source_sha256'];actions=[]
        with torch.inference_mode():
            for scene in range(5):
                env.scene(scene);raw=env.observe();a=initial(torch.from_numpy(raw['obs'].reshape(-1,109)),torch.from_numpy(raw['mask'].reshape(-1,90)))[0].argmax(-1).numpy().reshape(8,2)[0]
                actions.append({'kickoff':scene,'blue_action':int(a[0]),'orange_action':int(a[1]),'throttle_blue':float(ACTIONS[a[0],0]),'throttle_orange':float(ACTIONS[a[1],0])})
        result['initial_policy_kickoff_choices']=actions
    atomic_json(folder/'side_diagnostic.json',result);print('SIDE_SYMMETRY_PASS',json.dumps(result,indent=2),flush=True);return result
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',default='duel02');a=p.parse_args();check(a.run)
