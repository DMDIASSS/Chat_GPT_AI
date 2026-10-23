"""Load and freeze the separate RVQ policy without any optimizer at runtime."""
from pathlib import Path
import warnings
import torch
from replay_rvq.model import ActionCodec,StatePolicy
from slater_v041_core import sha256,read_json


def load(root,device='cpu'):
    root=Path(root);stage=root/'policy';selected=read_json(stage/'selected.json',{})
    if selected.get('sha256')!=sha256(stage/'best.pt'):raise ValueError('Selected RVQ policy changed')
    protocol=read_json(root/'protocol.json',{})
    source=Path(__file__).resolve().parents[1]
    for name in ('replay_rvq/model.py','replay_il/model.py'):
        expected=protocol.get('code',{}).get(name)
        if expected is not None and expected!=sha256(source/name):
            raise ValueError('Model interpretation source changed: '+name+'. Restore the version matching this run.')
    document=torch.load(stage/'best.pt',map_location='cpu',weights_only=True)
    if document['schema']!='replay-rvq-stage-v1' or document['stage']!='policy':raise ValueError('Not an RVQ policy checkpoint')
    if document['protocol_sha256']!=sha256(root/'protocol.json'):raise ValueError('RVQ protocol identity mismatch')
    config=document['config'];model=StatePolicy(ActionCodec(**config['codec']),**config['policy'])
    model.load_state_dict(document['model']);model.to(device).eval()
    if not all(torch.isfinite(p).all() for p in model.parameters()):raise ValueError('RVQ policy contains nonfinite weights')
    return model


def freeze(model):
    device=next(model.parameters()).device
    obs=(torch.zeros(2,1,32,device=device),torch.zeros(2,41,24,device=device),torch.zeros(2,41,device=device))
    with torch.inference_mode(),warnings.catch_warnings():
        features=model.encode(obs)
        warnings.simplefilter('ignore',torch.jit.TracerWarning)
        traced=torch.jit.trace_module(model,{'encode':(obs,),'greedy':(features,),'propose':(features,),'value':(features,)},check_trace=False)
        return torch.jit.freeze(traced,preserved_attrs=['encode','greedy','propose','value'])
