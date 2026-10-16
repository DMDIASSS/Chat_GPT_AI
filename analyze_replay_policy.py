"""Validation-only action-distribution diagnostics; never generates training games."""
from pathlib import Path
import argparse
import hashlib
import numpy as np
import torch
from replay_il.planner import load
from replay_il.train import Dataset
from slater_v041_core import atomic_json,read_json,sha256


def analyze(folder,dataset,*,device='auto',limit=2000):
    if not 1<=limit<=20000:raise ValueError('Analysis sample limit must be 1..20000')
    folder=Path(folder);dataset=Path(dataset);protocol=read_json(folder/'protocol.json',{})
    if protocol.get('dataset_sha256')!=sha256(dataset/'manifest.json'):raise ValueError('Run/dataset identity mismatch')
    device='cuda' if device=='auto' and torch.cuda.is_available() else 'cpu' if device=='auto' else device
    if device not in ('cpu','cuda') or device=='cuda' and not torch.cuda.is_available():raise ValueError('Requested analysis device is unavailable')
    torch.set_num_threads(2);model,book=load(folder,device='cpu');model.to(device).eval();data=Dataset(dataset,book)
    rows=data.rows['validation']
    if len(rows)>limit:rows=[rows[i] for i in np.linspace(0,len(rows)-1,limit,dtype=int)]
    predictions=[];targets=[];control_error=0.;value_error=zero_error=0.
    with torch.inference_mode():
        for start in range(0,len(rows),64):
            batch=data.take(rows[start:start+64]);observations=tuple(torch.as_tensor(batch[k],device=device) for k in ('q','kv','mask'))
            logits,values=model(observations);chosen=logits.argmax(-1).cpu().numpy()
            predictions.extend(chosen.tolist());targets.extend(batch['token'].tolist())
            control_error+=float(((book[chosen]-batch['controls'])**2).mean(axis=(1,2)).sum())
            predicted_value=values.mean(-1).cpu().numpy()
            value_error+=float(((predicted_value-batch['value'])**2).sum());zero_error+=float((batch['value']**2).sum())
    if not predictions:raise ValueError('No validation samples available')
    counts=np.zeros(len(book),np.int64);counted=0;total_train=len(data.rows['train'])
    digest=hashlib.sha256(book.tobytes()).hexdigest()[:16]
    # Training created these labels already. Do not decompress all training
    # histories or silently claim a complete baseline if caches are missing.
    for record in data.records:
        if record['split']!='train':continue
        path=Path(record['shard']).with_suffix('.tokens_'+digest+'.npy')
        if not path.exists():continue
        labels=np.load(path,allow_pickle=False)
        if labels.shape!=(record['samples'],) or labels.dtype.kind not in 'iu' or np.any(labels<0) or np.any(labels>=len(book)):
            raise ValueError('Cached training token labels are invalid')
        counts+=np.bincount(labels,minlength=len(book));counted+=len(labels)
    predictions=np.asarray(predictions);targets=np.asarray(targets);n=len(predictions)
    pred_counts=np.bincount(predictions,minlength=len(book));target_counts=np.bincount(targets,minlength=len(book))
    no_drive=(np.abs(book[:,:8,0]).max(1)<=.05)&(~book[:,:8,6].astype(bool).any(1))
    majority=int(counts.argmax()) if counted else None
    report={'schema':'replay-il-validation-diagnostics-v1','checkpoint_sha256':sha256(folder/'best.pt'),
        'dataset_sha256':sha256(dataset/'manifest.json'),'split':'validation','samples':n,'device':device,
        'token_top1':float((predictions==targets).mean()),'control_mse':control_error/n,
        'value_mse':value_error/n,'constant_zero_value_mse':zero_error/n,
        'most_predicted_token':int(pred_counts.argmax()),'most_predicted_token_fraction':float(pred_counts.max()/n),
        'predicted_token_counts':pred_counts.tolist(),'target_token_counts':target_counts.tolist(),
        'predicted_no_throttle_boost_first8_fraction':float(no_drive[predictions].mean()),
        'target_no_throttle_boost_first8_fraction':float(no_drive[targets].mean()),
        'training_majority_token':majority,'training_labels_counted':counted,'training_labels_total':total_train,
        'training_constant_baseline_top1':float((targets==majority).mean()) if majority is not None else None,
        'training_baseline_complete':counted==total_train,'competitive_strength_verified':False,
        'note':'No held-out test access or training update. Compare model and constant baseline on the same sampled validation rows. '
               'No throttle/boost can be legitimate coasting or aerial control; this diagnostic is not a movement penalty.'}
    atomic_json(folder/'validation_diagnostics.json',report)
    print('VALIDATION_DIAGNOSTICS:',{k:report[k] for k in ('samples','token_top1','training_constant_baseline_top1',
        'training_baseline_complete','most_predicted_token','most_predicted_token_fraction','predicted_no_throttle_boost_first8_fraction')},flush=True)
    print('REPORT:',folder/'validation_diagnostics.json',flush=True);return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--run-folder',type=Path,required=True)
    parser.add_argument('--dataset',type=Path,required=True);parser.add_argument('--device',choices=('auto','cpu','cuda'),default='auto')
    parser.add_argument('--samples',type=int,default=2000);args=parser.parse_args()
    try:analyze(args.run_folder,args.dataset,device=args.device,limit=args.samples)
    except (ValueError,RuntimeError,OSError) as error:print('STOPPED:',str(error),flush=True);raise SystemExit(1)
