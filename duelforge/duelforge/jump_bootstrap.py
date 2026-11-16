"""Successful RocketSim jump demonstrations + ground-policy retention, no jump reward."""
import copy,json,os,shutil,tempfile,time,zipfile
from pathlib import Path
import numpy as np
import torch
from .runtime import ROOT,batch,load,save,sha,atomic_json,model,device,lock
from .observation import ACTIONS
NEUTRAL=int(np.flatnonzero(np.all(ACTIONS==0,axis=1))[0])
from .air_recovery import elevated_hits,air_states
def launch_states(rng,n):
 w=air_states(rng,n);w[:,0,2]=rng.uniform(270,360,n);w[:,0,5]=rng.uniform(140,220,n)
 w[:,0,3:5]=0
 for side in (0,1):
  ang=rng.uniform(-np.pi,np.pi,n);f=np.stack([np.cos(ang),np.sin(ang),np.zeros(n)],-1)
  w[:,side+1,9:12]=f;w[:,side+1,:2]=w[:,0,:2]-f[:,:2]*rng.uniform(20,80,n)[:,None];w[:,side+1,3:6]=f*rng.uniform(0,80,n)[:,None]
 return w

def demonstrations(c,n=64,seed=1):
 e=batch(c,n=n,seed=seed);w=launch_states(np.random.default_rng(seed),n);colors=np.arange(n)%2;ix=np.arange(n)
 for i in range(n):w[i,2-colors[i],:3]=[3400,4200,17];w[i,2-colors[i],3:9]=0;e.inject(i,w[i])
 raw=e.observe();ok=np.zeros(n,bool);history=[[] for _ in range(n)]
 jump=int(np.flatnonzero((ACTIONS[:,5]==1)&(ACTIONS[:,2]==0)&(ACTIONS[:,4]==0)&(ACTIONS[:,6]==0))[0])
 for k in range(21):
  ac=np.full((n,2),NEUTRAL,np.int64);wanted=jump if k<3 or 4<=k<7 else NEUTRAL
  acts=np.where(raw['mask'][ix,colors,wanted],wanted,NEUTRAL)
  for i in range(n):
   if not ok[i]:history[i].append((raw['obs'][i,colors[i]].copy(),raw['mask'][i,colors[i]].copy(),acts[i]))
  ac[ix,colors]=acts;b=raw['world'];raw=e.step(ac);ok|=elevated_hits(b,raw)[ix,colors]
 rows=[r for i,h in enumerate(history) if ok[i] for r in h]
 if len(rows)<20:raise RuntimeError('Too few successful physical teacher demonstrations; no fitting performed')
 print('DEMO',ok.mean(),len(rows),flush=True)
 result=tuple(np.asarray(a) for a in zip(*rows))
 if not result[1][np.arange(len(result[2])),result[2]].all():raise RuntimeError('Teacher produced masked-out labels; no fitting allowed')
 return result

def skill(m,c,seed=99,n=64):
 e=batch(c,n=n,seed=seed);w=launch_states(np.random.default_rng(seed),n);cols=np.arange(n)%2;ix=np.arange(n)
 for i in range(n):w[i,2-cols[i],:3]=[3400,4200,17];w[i,2-cols[i],3:9]=0;e.inject(i,w[i])
 raw=e.observe();ok=np.zeros(n,bool);j=ok.copy()
 with torch.no_grad():
  for k in range(21):
   ac=np.full((n,2),NEUTRAL,np.int64);ac[ix,cols]=m(torch.as_tensor(raw['obs'][ix,cols],device=next(m.parameters()).device),torch.as_tensor(raw['mask'][ix,cols],device=next(m.parameters()).device))[0].argmax(-1).cpu().numpy();j|=ACTIONS[ac[ix,cols],5]>.5
   b=raw['world'];raw=e.step(ac);ok|=elevated_hits(b,raw)[ix,cols]
 return {'contact_rate':float(ok.mean()),'jump_rate':float(j.mean()),'raw_contacts':ok.tolist(),'raw_jump':j.tolist(),'seed':seed,'trials':n}

def prepare(root,source):
 root=Path(root);source=Path(source)
 if root.exists():
  info=json.loads((root/'curriculum.json').read_text())
  if info['version']!='jump-demo-v2' or sha(root/'baseline.pt')!=info['source_sha256']:raise ValueError('Bootstrap source identity changed')
  return root/'03_trajectory'
 root.parent.mkdir(parents=True,exist_ok=True);stage=Path(tempfile.mkdtemp(prefix='.jump_fork_',dir=root.parent))
 try:
  shutil.copy2(source,stage/'baseline.pt');ck=load(source);folder=stage/'03_trajectory';folder.mkdir()
  shutil.copy2(source,folder/'initial.pt');ck['wandb_id']=None
  ck['config']['wandb']['name']='jump01_supervised_contact'
  ck['config']['jump_bootstrap']={'version':'jump-demo-v2','training':'successful native demonstrations + frozen ground-policy KL','reinforcement_learning_steps_added':0}
  (folder/'history').mkdir()
  save(folder/'history/confirmed_reference.pt',{'model':ck['model'],'config':ck['config'],'learning_transitions':ck['learning_transitions']})
  ck['history']=['confirmed_reference.pt']
  save(folder/'latest.pt',ck);atomic_json(folder/'config.json',ck['config'])
  atomic_json(stage/'curriculum.json',{'version':'jump-demo-v2','stage_index':2,'status':'ready',
    'source_sha256':sha(stage/'baseline.pt'),'origin_transitions':ck['learning_transitions'],
    'scope':'Separate supervised candidate, not a promotion or replacement of the confirmed actor.'})
  os.rename(stage,root)
 finally:
  if stage.exists():shutil.rmtree(stage)
 return root/'03_trajectory'

def normal_data(source,c,seed=0xA0200000):
 e=batch(c,n=64,seed=seed);raw=e.observe();xs=[];ls=[];ps=[];dev=next(source.parameters()).device
 with torch.inference_mode():
  for _ in range(64):
   x=raw['obs'].reshape(-1,109);l=raw['mask'].reshape(-1,90)
   logits=source(torch.as_tensor(x,device=dev),torch.as_tensor(l,device=dev))[0]
   keep=np.repeat(raw['world'][:,0,2]<170,2)
   xs.append(x[keep].copy());ls.append(l[keep].copy());ps.append(logits.softmax(-1).cpu().numpy()[keep].copy())
   raw=e.step(logits.argmax(-1).reshape(-1,2).cpu().numpy())
 if sum(len(x) for x in xs)<256:raise RuntimeError('Too few ground retention states')
 return np.concatenate(xs),np.concatenate(ls),np.concatenate(ps)

def tensor_features(actor,x,dev):
 output=[]
 with torch.inference_mode():
  for k in range(0,len(x),512):output.append(actor[:6](torch.as_tensor(x[k:k+512],device=dev)).detach())
 # Clone outside inference mode: trainable layers must be able to save inputs.
 return torch.cat(output).clone()

def save_candidate(folder,template,m,step,kl):
 child=copy.deepcopy(template);child['model']={k:v.detach().cpu().clone() for k,v in m.state_dict().items()}
 names=[name for name,_ in m.named_parameters()];ids=[i for g in child['optimizer']['param_groups'] for i in g['params']]
 if len(names)!=len(ids):raise ValueError('Optimizer parameter mapping changed')
 for name,index in zip(names,ids):
  if name.startswith(('actor.6.','actor.7.','actor.9.')):child['optimizer']['state'].pop(index,None)
 child['jump_bootstrap_updates']=step;child['jump_bootstrap_ground_kl']=kl
 save(folder/'latest.pt',child)

def fit(root,updates=300):
 root=Path(root);folder=root/'03_trajectory';template=load(folder/'latest.pt')
 source,ck,_=model(root,checkpoint=root/'baseline.pt');c=copy.deepcopy(template['config']);dev=device(c)
 torch.set_num_threads(c['torch_threads']);source.to(dev).eval()
 m,_,_=model(folder);m.to(dev).eval()
 before=skill(source,c,seed=0xA0300000)
 atomic_json(root/'bootstrap_before.json',before)
 cache=root/'bootstrap_data.npz'
 if not cache.is_file():
  x,l,a=demonstrations(c,n=256,seed=0xA0100000);gx,gl,gp=normal_data(source,c)
  np.savez_compressed(cache,x=x,l=l,a=a,gx=gx,gl=gl,gp=gp)
 data=np.load(cache);x=data['x'];l=data['l'];a=data['a'];gx=data['gx'];gl=data['gl'];gp=data['gp']
 if not l[np.arange(len(a)),a].all():raise ValueError('Cached demonstration labels violate native masks')
 xf=tensor_features(m.actor,x,dev);gf=tensor_features(m.actor,gx,dev)
 masks=torch.as_tensor(l,device=dev);targets=torch.as_tensor(a,device=dev,dtype=torch.long)
 ground_masks=torch.as_tensor(gl,device=dev);ground_probs=torch.as_tensor(gp,device=dev)
 for p in m.parameters():p.requires_grad_(False)
 for p in m.actor[6:].parameters():p.requires_grad_(True)
 opt=torch.optim.Adam(m.actor[6:].parameters(),lr=.001);rng=np.random.default_rng(0xA0400000)
 statefile=root/'bootstrap_state.pt';start=0;best=-1.;bestkl=float('inf')
 if statefile.is_file():
  previous=load(statefile);m.load_state_dict(previous['model']);opt.load_state_dict(previous['optimizer']);rng.bit_generator.state=previous['rng']
  start=previous['updates'];best=previous['best'];bestkl=previous['best_kl']
 for step in range(start,updates):
  if (root/'STOP').exists():break
  ii=torch.as_tensor(rng.integers(len(x),size=256),device=dev);gg=torch.as_tensor(rng.integers(len(gx),size=256),device=dev)
  prediction=m.actor[6:](xf[ii]).masked_fill(~masks[ii],-1e9)
  retained=m.actor[6:](gf[gg]).masked_fill(~ground_masks[gg],-1e9).log_softmax(-1)
  ce=torch.nn.functional.cross_entropy(prediction,targets[ii]);kl=torch.nn.functional.kl_div(retained,ground_probs[gg],reduction='batchmean')
  loss=ce+2*kl;opt.zero_grad(set_to_none=True);loss.backward()
  norm=torch.nn.utils.clip_grad_norm_(m.actor[6:].parameters(),1,error_if_nonfinite=True)
  if not torch.isfinite(loss):raise FloatingPointError('Nonfinite bootstrap loss; last complete checkpoint preserved')
  opt.step()
  if (step+1)%25==0 or step+1==updates:
   validation=skill(m,c,seed=0xA0300000)
   with torch.inference_mode():
    rp=m.actor[6:](gf).masked_fill(~ground_masks,-1e9).log_softmax(-1)
    ground_kl=max(0.,float(torch.nn.functional.kl_div(rp,ground_probs,reduction='batchmean').cpu()))
   value=validation['contact_rate']
   if ground_kl<=.05 and (value>best or (value==best and ground_kl<bestkl)):
    best=value;bestkl=ground_kl;save_candidate(folder,template,m,step+1,ground_kl)
   row={'logging_step':step+1,'learning_transitions':ck['learning_transitions'],
        'bootstrap/update':step+1,'bootstrap/contact_validation':value,'bootstrap/ground_kl':ground_kl,
        'bootstrap/loss':float(loss.detach().cpu()),'bootstrap/demo_examples':len(x)}
   with (folder/'metrics.jsonl').open('a') as f:f.write(json.dumps(row)+'\n')
   atomic_json(root/'bootstrap_progress.json',row)
   save(statefile,{'model':m.state_dict(),'optimizer':opt.state_dict(),'rng':rng.bit_generator.state,
                   'updates':step+1,'best':best,'best_kl':bestkl})
   print('JUMP_BOOTSTRAP:',step+1,'/',updates,'validation contact',round(value*100,1),'% ground KL',round(ground_kl,4),flush=True)
 return folder,before

def report(root):
 from .report import report as stage_report
 root=Path(root);stage=stage_report(root/'03_trajectory');out=ROOT/f'DuelForge_jump01_report_{time.time_ns()}.zip'
 with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
  for f in root.glob('*.json'):z.write(f,f.name)
  z.write(stage,'stage_reports/'+stage.name);z.write(ROOT/'JUMP_BOOTSTRAP.md','JUMP_BOOTSTRAP.md')
 print('JUMP_REPORT_READY:',out,flush=True);return out

def start(root=None,source=None,updates=300,match_games=200):
 if not 25<=updates<=1000:raise ValueError('Use 25..1000 bounded supervised updates')
 root=Path(root or ROOT/'runs/jump01')
 if not root.exists():
  if source is None:
   from .match_guard import reference
   old=ROOT/'runs/contact01';f=old/'03_trajectory';ref=reference(old,f)
   if ref is None:raise RuntimeError('Exact confirmed source required; no model substituted')
   source=f/ref['actor_path']
  prepare(root,source)
 else:prepare(root,root/'baseline.pt')
 with lock(root):
  root.joinpath('STOP').unlink(missing_ok=True)
  state=json.loads((root/'curriculum.json').read_text())
  if sha(root/'baseline.pt')!=state['source_sha256']:raise ValueError('Source changed')
  folder,before=fit(root,updates)
  if not (root/'STOP').exists():
   candidate,ck,_=model(folder);c=ck['config'];dev=device(c);candidate.to(dev)
   heldout=skill(candidate,c,seed=0xA0500000);parent,_,_=model(root,checkpoint=root/'baseline.pt',dev=dev)
   baseline_heldout=skill(parent,c,seed=0xA0500000)
   from .air_experiment import probe as wider_probe
   wider=wider_probe(folder/'latest.pt',seed=0x90002000)
   from .evaluate import evaluate
   matches=evaluate(folder,games_per_context=match_games,seconds=100,contexts=['match'])
   atomic_json(root/'bootstrap_result.json',{'validation_before':before,'heldout_candidate':heldout,'heldout_source':baseline_heldout,
      'wider_air_probe':wider,'matches':matches['overall'],'candidate_sha256':sha(folder/'latest.pt'),
      'source_sha256':state['source_sha256'],'supervised_updates':load(root/'bootstrap_state.pt')['updates'],
      'reinforcement_learning_steps_added':0,'promotion':'none; require both real contact improvement and match retention'})
  state['status']='paused';atomic_json(root/'curriculum.json',state);report(root)
  return state

