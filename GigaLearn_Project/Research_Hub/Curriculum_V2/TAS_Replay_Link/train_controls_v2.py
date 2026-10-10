"""TAS next-input prediction with an optional, unpaired replay-cadence prior.

Only an offline motor input-model, NOT a state-conditioned native GigaLearn policy.
Doesn't invent TAS physics trajectories or map unverified TAS float fields.
"""
from __future__ import annotations
import argparse,datetime,json,pathlib,random,sys,uuid
from collections import defaultdict
import numpy as np
from tas_replay_link import tas_clips,read_replay_rows,ACTIONS,sig


def replay_prior(dataset):
    """Action-cadence → mean replay action vector; descriptive, NOT a TAS target."""
    groups=defaultdict(list)
    for _,rid,team,act in read_replay_rows(pathlib.Path(dataset)/'replay_train.txt'):
        groups[(rid,team)].append(act)
    bins=defaultdict(list)
    for acts in groups.values():
        data=ACTIONS[acts]
        keys=sig(data[:,[0,1,2,3,4]],data[:,[5,6,7]])
        for key,v in zip(keys,data):bins[key].append(v)
    prior={k:np.concatenate((np.mean(items,axis=0),[min(1.,len(items)/25.)])).astype('float32') for k,items in bins.items()}
    return prior


def tensors(clips,indices,prior,k=4,stride=3,maxrows=95000):
    # Return samples with at least k previous controls within the same TAS file.
    arrx,arry,arrb,arrc=[],[],[],[]
    budget=max(16,maxrows//max(1,len(indices)))
    for idx in indices:
        clip=clips[idx];raw=clip['analog'][::stride]
        bits=np.asarray([[(int(x)>>i)&1 for i in range(7)] for x in clip['flags'][::stride]],dtype='float32')
        feats=np.concatenate((raw,bits),axis=1)
        keys=sig(raw,bits)
        n=len(feats)
        if n<k+2:continue
        step=max(1,n//budget)
        for i in range(k,n,step):
            arrx.append(feats[i-k:i].reshape(-1))
            arry.append(raw[i]);arrb.append(bits[i])
            arrc.append(prior.get(keys[i-1],np.zeros(9,dtype='float32')))
    if not arrx:raise ValueError('No TAS next-input examples could be made')
    return (np.asarray(arrx,dtype='float32'),np.asarray(arry,dtype='float32'),
            np.asarray(arrb,dtype='float32'),np.asarray(arrc,dtype='float32'))


def train(tas_folder, replay_folder, dest, epochs=4,stride=3):
    if not 1<=epochs<=20 or not 1<=stride<=20:raise ValueError('Unsafe training params')
    try:
        import torch
        from torch import nn
    except ImportError as exc:raise RuntimeError('PyTorch missing from Python3.11 venv') from exc
    torch.set_num_threads(max(1,min(4,torch.get_num_threads())))
    torch.manual_seed(1029);random.seed(1029)
    clips,errors=tas_clips(tas_folder)
    if len(clips)<6:raise ValueError('Need 6+ TAS clips for train/held-out-clip validation')
    idx=list(range(len(clips)));random.Random(1029).shuffle(idx)
    boundary=max(1,int(len(idx)*.2))
    vid=idx[:boundary];tid=idx[boundary:]
    # Prior learned from REPLAY TRAIN ONLY. Replay validation is untouched.
    prior=replay_prior(replay_folder)
    tx,ty,tb,tc=tensors(clips,tid,prior,stride=stride)
    vx,vy,vb,vc=tensors(clips,vid,prior,stride=stride)
    baseline_analog=float(np.abs(vx[:,-14:-7]-vy).mean())
    baseline_flags=float((vx[:,-7:]==vb).all(axis=1).mean())
    summary={'kind':'offline_tas_next_input_v2','status':'experimental_input_prediction_not_gigalearn',
        'train_tas_clips':len(tid),'heldout_tas_clips':len(vid),'train_samples':len(tx),'heldout_samples':len(vx),
        'replay_cadence_keys':len(prior),'tas_errors':errors,
        'last_input_persistence_analog_mae':baseline_analog,
        'last_input_persistence_flag_exact':baseline_flags,
        'caveat':'TAS flags/analogs have unverified Rocket League channel semantics. Replay prior uses cadence similarity only. No TAS game states. Cannot seed GigaLearn.'}
    results={}
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'_'+uuid.uuid4().hex[:6]
    dest=pathlib.Path(dest)/('tas_controls_'+stamp)
    if dest.exists():raise FileExistsError(dest)
    dest.mkdir(parents=True)
    X=torch.tensor(tx);Y=torch.tensor(ty);B=torch.tensor(tb);C=torch.tensor(tc)
    VX=torch.tensor(vx);VY=torch.tensor(vy);VB=torch.tensor(vb);VC=torch.tensor(vc)
    def mk_model(dim):
        model=nn.Sequential(nn.Linear(dim,96),nn.ReLU(),nn.Linear(96,96),nn.ReLU(),nn.Linear(96,14))
        # Start by copying the previous control rather than random buttons.
        nn.init.zeros_(model[-1].weight);nn.init.zeros_(model[-1].bias)
        return model
    for enabled in (False,True):
        name='with_replay_cadence' if enabled else 'tas_only'
        model=mk_model(56+(9 if enabled else 0))
        opt=torch.optim.AdamW(model.parameters(),lr=0.0006,weight_decay=.0001)
        history=[];bestscore=float('inf');best=None
        for epoch in range(1,epochs+1):
            model.train();perm=torch.randperm(len(X))
            for chunk in perm.split(512):
                features=torch.cat((X[chunk],C[chunk]),axis=1) if enabled else X[chunk]
                output=model(features)
                analog=(X[chunk,-14:-7]+0.5*torch.tanh(output[:,:7])).clamp(-1,1)
                flag_logits=(X[chunk,-7:]*2-1)*4.0+output[:,7:]
                loss=nn.functional.smooth_l1_loss(analog,Y[chunk])+0.12*nn.functional.binary_cross_entropy_with_logits(flag_logits,B[chunk])
                opt.zero_grad(set_to_none=True);loss.backward();opt.step()
            model.eval()
            with torch.no_grad():
                inp=torch.cat((VX,VC),axis=1) if enabled else VX
                out=model(inp)
                pred_analog=(VX[:,-14:-7]+0.5*torch.tanh(out[:,:7])).clamp(-1,1)
                pred_flags=(VX[:,-7:]*2-1)*4.0+out[:,7:]
                mae=float((pred_analog-VY).abs().mean())
                exact=float(((pred_flags>=0)==VB.bool()).all(axis=1).float().mean())
                score=mae+0.12*(1-exact)
            history.append({'epoch':epoch,'heldout_analog_mae':round(mae,6),'heldout_exact_flags':round(exact,6)})
            if score<bestscore:
                bestscore=score
                best={'state_dict':{k:v.detach().cpu().clone() for k,v in model.state_dict().items()},
                      'type':'offline_tas_input_predictor_not_gigalearn',
                      'uses_replay_cadence':enabled,'history_length':4,'stride':stride, 'prediction':'residual_over_previous_controls'}
        assert best is not None
        torch.save(best,dest/(name+'.pt'))
        results[name]={'best_combined_score':round(bestscore,6),'history':history,
                       'model':str(dest/(name+'.pt'))}
        print(json.dumps({'mode':name,**history[-1]},indent=2),flush=True)
    score0=results['tas_only']['best_combined_score'];score1=results['with_replay_cadence']['best_combined_score']
    baseline_score=baseline_analog+0.12*(1-baseline_flags)
    summary.update({'input_persistence_combined_score':round(baseline_score,6),
                    'results':results,
                    'best_model':'with_replay_cadence' if score1<score0 else 'tas_only',
                    'replay_context_helped':bool(score1<score0),
                    'beats_last_input_persistence':bool(min(score0,score1)<baseline_score),
                    'can_seed_gigalearn':False})
    summary['status']='heldout_input_prediction_above_baseline' if summary['beats_last_input_persistence'] else 'rejected_below_persistence_baseline'
    (dest/'report.json').write_text(json.dumps(summary,indent=2),encoding='utf8')
    return {'status':summary['status'],'best_model':summary['best_model'],'replay_context_helped':summary['replay_context_helped'],
            'beats_last_input_persistence':summary['beats_last_input_persistence'],
            'persist_baseline':round(baseline_score,5),'tas_only_score':score0,'with_replay_score':score1,
            'report':str(dest/'report.json')}

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--tas',required=True);p.add_argument('--replay',required=True);p.add_argument('--output',required=True)
    p.add_argument('--epochs',type=int,default=4);p.add_argument('--stride',type=int,default=3)
    a=p.parse_args();print(json.dumps(train(a.tas,a.replay,a.output,epochs=a.epochs,stride=a.stride),indent=2))
if __name__=='__main__':
    try:main()
    except Exception as ex:print('INPUT FOLLOWING FAILED:',ex,file=sys.stderr);sys.exit(1)
