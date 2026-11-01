"""Read existing immutable shards; keep RVQ labels in the new run only."""
from collections import defaultdict,OrderedDict
from pathlib import Path
import numpy as np
import torch
from replay_il.train import Dataset
from slater_v041_core import sha256


def validate_controls(controls):
    if controls.ndim!=3 or controls.shape[1:]!=(32,8) or not np.isfinite(controls).all():
        raise ValueError('Expected finite cached 32-by-8 control chunks')
    if np.any(np.abs(controls)>1.001) or not np.isin(controls[:,:,5:],[0,1]).all():
        raise ValueError('Cached controls contain invalid analogue values/buttons')


def sample_controls(data,limit=4096,seed=20261022):
    rows=data.rows['train'];rng=np.random.default_rng(seed)
    chosen=rng.choice(len(rows),min(limit,len(rows)),replace=False);grouped=defaultdict(list)
    for position,where in enumerate(chosen):
        record,index=rows[int(where)];grouped[record].append((position,index))
    result=np.empty((len(chosen),32,8),np.float32)
    for record,positions in grouped.items():
        with np.load(data.records[record]['shard'],allow_pickle=False) as z:
            controls=z['controls'];validate_controls(controls)
            for position,index in positions:result[position]=controls[index]
    return result


def positive_weights(controls):
    pressed=(controls[:,:,5:]>0.5).sum((0,1));total=controls.shape[0]*32
    # Training-only counts, bounded weighting, no validation-driven prevalence.
    return np.sqrt((total-pressed+1)/(pressed+1)).clip(1,20).astype(np.float32)


def epoch_rows(data,split,epoch=0,limit=None):
    rows=data.rows[split]
    if split!='train':
        if limit and len(rows)>limit:return [rows[i] for i in np.linspace(0,len(rows)-1,limit,dtype=int)]
        return rows
    rng=np.random.default_rng(20261022+epoch);grouped=defaultdict(list)
    for record,index in rows:grouped[record].append((record,index))
    order=list(grouped);rng.shuffle(order)
    return [grouped[r][j] for r in order for j in rng.permutation(len(grouped[r]))]


class RVQData:
    def __init__(self,folder,label_folder):
        self.raw=Dataset(folder);self.labels={};self.label_folder=Path(label_folder);self.control_cache=OrderedDict()
        self.codec=None;self.codec_digest=None;self.device=None

    def use_codec(self,codec,digest,device):
        self.codec=codec;self.codec_digest=digest;self.device=device
        self.label_folder.mkdir(parents=True,exist_ok=True)

    def take_controls(self,rows,device):
        grouped=defaultdict(list);result=np.empty((len(rows),32,8),np.float32)
        for position,(record,index) in enumerate(rows):grouped[record].append((position,index))
        for record,positions in grouped.items():
            if record not in self.control_cache:
                with np.load(self.raw.records[record]['shard'],allow_pickle=False) as z:controls=z['controls'].astype(np.float32)
                validate_controls(controls);self.control_cache[record]=controls
                while len(self.control_cache)>8:self.control_cache.popitem(last=False)
            self.control_cache.move_to_end(record)
            for position,index in positions:result[position]=self.control_cache[record][index]
        return torch.as_tensor(result,device=device)

    def take(self,rows,device):
        batch=self.raw.take(rows);validate_controls(batch['controls'])
        if np.any(np.abs(batch['value'])>1.001):raise ValueError('Invalid value labels')
        obs=tuple(torch.as_tensor(batch[k][:,-1],device=device) for k in ('q','kv','mask'))
        target=torch.as_tensor(batch['controls'],device=device)
        labels=None
        if self.codec is not None:
            grouped=defaultdict(list)
            for position,(record,index) in enumerate(rows):grouped[record].append((position,index))
            labels=np.empty((len(rows),self.codec.levels),np.int64)
            for record,positions in grouped.items():
                if record not in self.labels:
                    metadata=self.raw.records[record]
                    name=metadata['sha256']+'_'+self.codec_digest[:16]+'.npy'
                    path=self.label_folder/name
                    if path.exists():values=np.load(path,allow_pickle=False)
                    else:
                        with np.load(metadata['shard'],allow_pickle=False) as z:controls=z['controls'].astype(np.float32)
                        validate_controls(controls);values=[]
                        with torch.inference_mode():
                            for start in range(0,len(controls),256):
                                z=self.codec.encoder(torch.as_tensor(controls[start:start+256],device=self.device))
                                values.append(self.codec.quantize(z)[1].cpu().numpy())
                        values=np.concatenate(values);temporary=path.with_suffix('.partial')
                        with temporary.open('wb') as stream:np.save(stream,values,allow_pickle=False)
                        temporary.replace(path)
                    if values.shape!=(metadata['samples'],self.codec.levels) or values.dtype.kind not in 'iu' or np.any(values<0) or np.any(values>=self.codec.codes):
                        raise ValueError('RVQ label cache is corrupt; original data are preserved')
                    self.labels[record]=values
                for position,index in positions:labels[position]=self.labels[record][index]
            labels=torch.as_tensor(labels,device=device)
        return obs,target,labels,torch.as_tensor(batch['value'],device=device),torch.as_tensor(batch['bootstrap'],device=device)
