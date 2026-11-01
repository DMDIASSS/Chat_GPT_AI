"""Offline supervised optimization. Never collects games or calls PPO."""
from collections import OrderedDict
from pathlib import Path
import hashlib,json,random,time
from importlib.metadata import version
import numpy as np
import torch
from torch.nn import functional as F
from replay_il.model import ChunkPolicy
from replay_il.tokens import fit,tokenize,distances
from replay_il.data import ROOT
from replay_il.monitor import Monitor
from slater_v041_core import atomic_json,read_json,sha256,process_lock

def save(path,payload):
    tmp=path.with_suffix('.partial')
    with tmp.open('wb') as stream:torch.save(payload,stream)
    tmp.replace(path)

class Dataset:
    def __init__(self,path,book=None):
        self.path=Path(path);self.manifest=read_json(self.path/'manifest.json')
        if not self.manifest or self.manifest.get('schema')!='replay-il-v2-raw':raise ValueError('Prepare a raw-observation replay dataset first')
        self.records=self.manifest['sources'];self.cache=OrderedDict();self.rows={k:[] for k in ('train','validation','test')}
        seen=set();self.sample_count=0
        for index,record in enumerate(self.records):
            if record['group'] in seen:raise ValueError('Duplicate match group / split leakage')
            seen.add(record['group'])
            if sha256(record['shard'])!=record['sha256']:raise ValueError('Replay shard changed')
            self.rows[record['split']].extend((index,j) for j in range(record['samples']));self.sample_count+=record['samples']
        if any(len({r for r,_ in rows})<2 for rows in self.rows.values()):raise ValueError('Need two independent matches per split')
        self.book=book
    def shard(self,index):
        if index in self.cache:self.cache.move_to_end(index);return self.cache[index]
        with np.load(self.records[index]['shard'],allow_pickle=False) as z:row={k:z[k] for k in z.files}
        if any(row[k].shape[1:]!=shape for k,shape in [('q',(8,1,32)),('kv',(8,41,24)),('mask',(8,41)),('controls',(32,8))]):raise ValueError('Unsupported replay observation/chunk shapes')
        if not all(np.isfinite(row[k]).all() for k in ('q','kv','mask','controls','value')):raise ValueError('Nonfinite replay data')
        if self.book is not None:
            digest=hashlib.sha256(self.book.tobytes()).hexdigest()[:16]
            labels=Path(self.records[index]['shard']).with_suffix('.tokens_'+digest+'.npy')
            if labels.exists():row['token']=np.load(labels,allow_pickle=False)
            else:row['token'],_=tokenize(row['controls'],self.book);np.save(labels,row['token'])
            if row['token'].shape!=(len(row['controls']),) or np.any(row['token']<0) or np.any(row['token']>=len(self.book)):raise ValueError('Cached token labels are corrupt')
        self.cache[index]=row
        while len(self.cache)>4:self.cache.popitem(last=False)
        return row
    def take(self,indices):
        grouped={}
        for position,(r,j) in enumerate(indices):grouped.setdefault(r,[]).append((position,j))
        keys=('q','kv','mask','controls','value','players')+ (('token',) if self.book is not None else ())
        result={}
        for record,positions in grouped.items():
            shard=self.shard(record);where,rows=map(np.asarray,zip(*positions))
            for key in keys:
                if key not in result:result[key]=np.empty((len(indices),*shard[key].shape[1:]),np.int64 if key=='token' else np.float32)
                result[key][where]=shard[key][rows]
        # Bootstrap heads by whole replay, not by adjacent frames.
        result['bootstrap']=np.asarray([[int(hashlib.sha256((self.records[r]['group']+str(head)).encode()).hexdigest()[:2],16)%3!=0 for head in range(3)] for r,_ in indices],np.float32)
        result['bootstrap'][:,0]=1 # At least one supervised head for every match.
        return result
    def vocabulary(self,size,seed):
        rng=np.random.default_rng(seed);ids=self.rows['train']
        chosen=rng.choice(len(ids),min(20000,len(ids)),replace=False)
        chunks=self.take([ids[j] for j in chosen])['controls']
        return fit(chunks,size,seed)

def batches(rows,size):
    for start in range(0,len(rows),size):yield rows[start:start+size]

def evaluate(model,data,split_name,device,batch_size=128,limit=20000):
    ids=data.rows[split_name]
    if len(ids)>limit:ids=[ids[j] for j in np.linspace(0,len(ids)-1,limit,dtype=int)]
    total=0;ce=mse=correct=top5=uncertainty=control_error=constant_mse=0.
    model.eval()
    with torch.no_grad():
        for rows in batches(ids,batch_size):
            batch=data.take(rows);x=tuple(torch.as_tensor(batch[k],device=device) for k in ('q','kv','mask'))
            target=torch.as_tensor(batch['token'],device=device);value=torch.as_tensor(batch['value'],device=device)
            logits,values=model(x);n=len(rows);total+=n
            ce+=float(F.cross_entropy(logits,target,reduction='sum'));pred=logits.argmax(-1)
            correct+=int((pred==target).sum());top5+=int((logits.topk(min(5,logits.shape[-1]),-1).indices==target[:,None]).any(1).sum())
            mean=values.mean(-1);mse+=float(((mean-value)**2).sum());constant_mse+=float((value**2).sum());uncertainty+=float(values.std(-1).sum())
            decoded=data.book[pred.cpu().numpy()]
            control_error+=float(np.mean((decoded-batch['controls'])**2,axis=(1,2)).sum())
    return {'samples':total,'token_ce':ce/total,'token_top1':correct/total,'token_top5':top5/total,
            'value_mse':mse/total,'constant_zero_value_mse':constant_mse/total,'value_disagreement':uncertainty/total,
            'chunk_control_mse':control_error/total,
            'interpretation':'Offline held-out imitation/value accuracy; not competitive strength.'}

def code_identity():
    files=list((ROOT/'replay_il').glob('*.py'))+[ROOT/'afk_team_research.py',ROOT/'nexto_teacher.py',ROOT/'slater_versatile_data.py']
    return {str(p.relative_to(ROOT)):sha256(p) for p in sorted(files)}

def train(dataset,folder,*,epochs=20,batch_size=128,lr=2e-4,device='auto',resume=False,wandb=None):
    folder=Path(folder).resolve()
    if not folder.is_relative_to(ROOT/'data/isolated'):raise ValueError('Runs must be under data/isolated')
    if not 1<=epochs<=200 or not 4<=batch_size<=1024 or not 1e-6<=lr<=.001:raise ValueError('Invalid training budget')
    if device=='auto':device='cuda' if torch.cuda.is_available() else 'cpu'
    if device not in ('cpu','cuda') or device=='cuda' and not torch.cuda.is_available():raise ValueError('Requested training device is unavailable')
    data=Dataset(dataset)
    settings=wandb or {'mode':'online','project':'slater-replay-imitation','entity':''}
    if settings['mode'] not in ('online','offline','disabled'):raise ValueError('Invalid W&B mode')
    if set(settings)-{'mode','project','entity'}:raise ValueError('Keep API keys out of configuration; use local W&B login')
    protocol={'schema':'replay-il-training-v2','initialization':'random_all_parameters_trainable',
        'dataset_sha256':sha256(Path(dataset)/'manifest.json'),'code':code_identity(),'seed':20261016,
        'batch_size':batch_size,'lr':lr,'learning':'pure_replay_imitation','rl_updates':0,'self_play_games':0,
        'runtime':{name:version(name) for name in ('torch','numpy','rocketsim','rlgym-tools')}}
    if folder.exists() and not resume:raise FileExistsError('Run exists. Resume it or choose a new --run name.')
    folder.mkdir(parents=True,exist_ok=True)
    with process_lock(folder/'train.lock'):
        torch.manual_seed(20261016);random.seed(20261016);np.random.seed(20261016);torch.set_num_threads(2)
        if resume:
            if read_json(folder/'protocol.json')!=protocol:raise ValueError('Code/source/dataset/settings changed. Start a new run.')
            if read_json(folder/'tokenizer.json')['book_sha256']!=sha256(folder/'tokens.npy'):raise ValueError('Action vocabulary changed')
            book=np.load(folder/'tokens.npy',allow_pickle=False)
        else:
            book,stats=data.vocabulary(256,20261016);np.save(folder/'tokens.npy',book)
            stats['book_sha256']=sha256(folder/'tokens.npy');atomic_json(folder/'tokenizer.json',stats)
            atomic_json(folder/'protocol.json',protocol)
            # Books use only training matches, including their whole input stream.
            entries=[]
            for record in data.records:
                if record['split']=='train':entries.extend(read_json(Path(record['shard']).with_suffix('.kickoffs.json'),{}).get('entries',[]))
            entries.sort(key=lambda e:e['touch_ticks']);atomic_json(folder/'kickoff_book.json',{'entries':entries[:256],'fit_split':'train_only'})
        data.book=book;data.cache.clear()
        model=ChunkPolicy(len(book));model.to(device);opt=torch.optim.AdamW(model.parameters(),lr=lr,weight_decay=.01)
        progress={'epoch':0,'updates':0,'best_validation_ce':None,'best_validation_score':None,'stale_epochs':0}
        if resume:
            doc=torch.load(folder/'latest.pt',map_location=device,weights_only=True)
            if doc['protocol_sha256']!=sha256(folder/'protocol.json'):raise ValueError('Checkpoint protocol mismatch')
            model.load_state_dict(doc['model']);opt.load_state_dict(doc['optimizer']);progress=doc['progress']
            torch.set_rng_state(doc['torch_rng'].cpu());random.setstate(doc['python_rng'])
        else:
            atomic_json(folder/'model.json',{**model.describe(),'initialization':'random','pretrained_weights_loaded':False})
            save(folder/'latest.pt',{'model':model.state_dict(),'optimizer':opt.state_dict(),'progress':dict(progress),'config':model.config,
                'torch_rng':torch.get_rng_state(),'python_rng':random.getstate(),'protocol_sha256':sha256(folder/'protocol.json')})
            atomic_json(folder/'progress.json',progress)
        monitor=Monitor(folder,settings,protocol,prompt=True)
        initial={k:v.detach().clone() for k,v in model.named_parameters() if v.requires_grad}
        (folder/'pause.flag').unlink(missing_ok=True)
        try:
            baseline=evaluate(model,data,'validation',device,batch_size)
            initial_report=folder/'validation_initial.json'
            kind='validation_resume' if initial_report.exists() else 'validation_initial'
            monitor.emit(progress['updates'],kind,{'validation':baseline})
            atomic_json(folder/(f'validation_resume_{progress["updates"]:08d}.json' if initial_report.exists() else 'validation_initial.json'),baseline)
            for epoch in range(progress['epoch'],progress['epoch']+epochs):
                if (folder/'pause.flag').exists():break
                rng=np.random.default_rng(20261016+epoch)
                # Shuffle matches, then rows within each match. This keeps disk
                # reads sequential instead of decompressing 128 files per batch.
                grouped={}
                for r,j in data.rows['train']:grouped.setdefault(r,[]).append((r,j))
                order=list(grouped);rng.shuffle(order)
                ids=[grouped[r][j] for r in order for j in rng.permutation(len(grouped[r]))]
                model.train();losses=[];started=time.perf_counter()
                for rows in batches(ids,batch_size):
                    if (folder/'pause.flag').exists():break
                    batch=data.take(rows);x=tuple(torch.as_tensor(batch[k],device=device) for k in ('q','kv','mask'))
                    target=torch.as_tensor(batch['token'],device=device);value=torch.as_tensor(batch['value'],device=device)
                    bootstrap=torch.as_tensor(batch['bootstrap'],device=device)
                    logits,values=model(x);ce=F.cross_entropy(logits,target)
                    value_loss=(((values-value[:,None])**2)*bootstrap).sum()/bootstrap.sum().clamp_min(1)
                    loss=ce+value_loss
                    if not torch.isfinite(loss):raise FloatingPointError('Nonfinite imitation loss')
                    opt.zero_grad(set_to_none=True);loss.backward();grad=torch.nn.utils.clip_grad_norm_(model.parameters(),1.)
                    if not torch.isfinite(grad):raise FloatingPointError('Nonfinite imitation gradient')
                    opt.step();progress['updates']+=1;losses.append(float(loss.detach()))
                    monitor.emit(progress['updates'],'supervised_batch',{'train':{'policy_ce':float(ce.detach()),'value_loss':float(value_loss.detach()),'gradient_norm':float(grad),'epoch':epoch+1}})
                if not losses:break
                validation=evaluate(model,data,'validation',device,batch_size)
                paused=(folder/'pause.flag').exists()
                # A paused partial epoch resumes from its start; optimizer/RNG are
                # saved, but the report explicitly records repeated examples.
                progress['epoch']=epoch if paused else epoch+1
                score=validation['token_ce']+validation['value_mse']
                improved=progress['best_validation_score'] is None or score<progress['best_validation_score']-1e-4
                if improved:progress['best_validation_ce']=validation['token_ce'];progress['best_validation_score']=score;progress['stale_epochs']=0
                else:progress['stale_epochs']+=1
                change=float(torch.sqrt(sum(((v.detach()-initial[k])**2).sum() for k,v in model.named_parameters() if k in initial)))
                if not change>0:raise RuntimeError('Optimizer completed but trainable weights did not change')
                checkpoint={'model':model.state_dict(),'optimizer':opt.state_dict(),'progress':dict(progress),'config':model.config,
                    'torch_rng':torch.get_rng_state(),'python_rng':random.getstate(),'protocol_sha256':sha256(folder/'protocol.json')}
                save(folder/'latest.pt',checkpoint)
                if improved:
                    save(folder/'best.pt',checkpoint)
                    atomic_json(folder/'selected.json',{'checkpoint':str(folder/'best.pt'),'status':'OFFLINE_VALIDATION_ONLY',
                        'sha256':sha256(folder/'best.pt'),'validation':validation,'playing_model_changed':False,'competitive_improvement_verified':False})
                report={'epoch':epoch+1,'updates':progress['updates'],'validation':validation,'train_loss':float(np.mean(losses)),
                    'parameter_change_l2':change,'seconds':time.perf_counter()-started,'paused_mid_epoch':paused,'rl_updates':0,'self_play_games':0}
                atomic_json(folder/f'epoch_{epoch+1:04d}.json',report);atomic_json(folder/'progress.json',progress)
                monitor.emit(progress['updates'],'validation',{'validation':validation,'learning':{'parameter_change_l2':change}})
                print('IMITATION_EPOCH',json.dumps(report),flush=True)
                if paused or progress['stale_epochs']>=4:break
        finally:monitor.close()
        return folder
