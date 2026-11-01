"""Report untouched replay-bank test labels only after model selection."""
import json,struct
from pathlib import Path
import numpy as np
import torch
from slater_native_actor import NativeActor,observation,action_mask
from slater_v041_core import sha256,atomic_json
from nexto_teacher import nexto_actions

def test_report(checkpoint,bank,out):
    out=Path(out)
    model=NativeActor(checkpoint)
    if out.exists():
        cached=json.loads(out.read_text())
        if cached['checkpoint']!=model.identity or cached['bank_sha']!=sha256(bank):raise ValueError('Replay test inputs changed')
        return cached
    with open(bank,'rb') as f:
        if f.read(4)!=b'SGRB':raise ValueError('Invalid bank')
        version,players,count,width=struct.unpack('<IIII',f.read(16))
        if version!=1 or width!=52+43*players+93:raise ValueError('Invalid bank layout')
        table=np.frombuffer(f.read(720*4),dtype='<f4').reshape(90,8)
        if not np.array_equal(table,nexto_actions()):raise ValueError('Action table mismatch')
        f.read(102*4);data=np.frombuffer(f.read(),dtype='<f4').reshape(count,width)
    observations=[];labels=[];weights=[];dropped=0
    def physical(row):return {'pos':row[:3].tolist(),'rot':row[3:12].tolist(),'vel':row[12:15].tolist(),'ang':row[15:18].tolist()}
    for row in data:
        if row[-1]!=2:continue
        p={'ball':physical(row),'timers':row[18:52].tolist(),'cars':[]};query=int(row[52+43*players])
        for i in range(players):
            body=row[52+43*i:52+43*(i+1)];team=int(i>=players//2);car_id=2*(i%(players//2))+1+team
            p['cars'].append({'id':car_id,'team':team,**physical(body),'boost':float(body[18]),'ground':bool(body[19]),
                'jumped':bool(body[20]),'double_jumped':bool(body[21]),'flipped':bool(body[22]),'air_time':float(body[26]),
                'demo':False,'world_contact':False,'contact_normal':[0,0,0],'previous':body[27:35].tolist()})
        car=p['cars'][query];mask=action_mask(car);target=row[53+43*players:143+43*players]*mask
        if target.sum()<.5:dropped+=1;continue
        observations.append(observation(p,car['id']));labels.append(target/target.sum());weights.append(row[-2])
    if not observations:raise ValueError('No feasible untouched replay test labels')
    losses=[]
    with torch.no_grad():
        for start in range(0,len(observations),256):
            x=torch.tensor(np.array(observations[start:start+256]));y=torch.tensor(np.array(labels[start:start+256]))
            losses.extend((-(model(x).log_softmax(-1)*y).sum(-1)).tolist())
    result={'checkpoint':model.identity,'bank_sha':sha256(bank),'partition':'test','samples':len(losses),'dropped_mask_mass':dropped,
        'unmasked_label_cross_entropy':float(np.mean(losses)),'confidence_weighted_ce':float(np.average(losses,weights=weights)),
        'note':'Reported after selection only; reconstructed replay labels, not match strength. Use fresh test data for subsequent tuning.'}
    atomic_json(out,result);return result
