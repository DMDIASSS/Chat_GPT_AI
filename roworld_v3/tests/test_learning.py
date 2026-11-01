"""PyTorch/Luau ranker parity and a real PPO gradient step; requires training dependencies."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import torch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"training"))
from model import Model,batch,CONTEXT,ACTION
from train import optimize,advantages
from bridge import build


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--luau",required=True);args=p.parse_args()
    torch.set_num_threads(2);torch.manual_seed(71)
    model=Model();rows=[]
    for k in (1,3,17,96):
        rows.append({"context":torch.randn(CONTEXT).tolist(),"candidates":torch.randn(k,ACTION).tolist(),
                     "priors":torch.randn(k).tolist()})
    logits,values=model(*batch(rows,'cpu'))
    weights=model.export()
    script=build.modules_source()+"\nlocal weights="+build.literal(weights)+"\nlocal rows="+build.literal(rows)+r'''
assert(Neural.validate(weights))
for i,r in ipairs(rows) do
 local candidates={};for j,f in ipairs(r.candidates) do candidates[j]={features=f,bias=r.priors[j]} end
 local scores,value=Neural.score(weights,r.context,candidates)
 print('VALUE',i,value);for j,v in ipairs(scores) do print('LOGIT',i,j,v) end
end
weights.context.w[1][1]=0/0;assert(not Neural.validate(weights))
'''
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'parity.luau';path.write_text(script,encoding='utf8')
        result=subprocess.run([args.luau,str(path)],capture_output=True,text=True,check=True,timeout=30)
    error=0
    for line in result.stdout.splitlines():
        parts=line.split()
        if parts[0]=='VALUE': expected=values[int(parts[1])-1].item();actual=float(parts[2])
        elif parts[0]=='LOGIT': expected=logits[int(parts[1])-1,int(parts[2])-1].item();actual=float(parts[3])
        else: continue
        error=max(error,abs(expected-actual))
    assert error<2e-5,error
    print('PASS Python/Luau export parity across 117 candidate logits; max error',error)
    old=torch.cat([p.detach().flatten().clone() for p in model.parameters()])
    for i,row in enumerate(rows):
        k=len(row['candidates']);probs=logits[i,:k].detach().softmax(-1)
        row.update(choice=1,logp=probs[0].log().item(),value=values[i].item(),reward=float(i+1),done=i==len(rows)-1)
    episode={'rows':rows,'bootstrap':0};advantages(episode)
    assert abs(rows[-1]['return']-rows[-1]['reward'])<1e-5
    stats=optimize(model,torch.optim.Adam(model.parameters(),lr=3e-4),rows,'cpu',epochs=2)
    new=torch.cat([p.detach().flatten() for p in model.parameters()])
    assert not torch.equal(old,new) and all(torch.isfinite(torch.tensor(v)) for v in stats.values())
    print('PASS PPO changes parameters; terminal targets and masked variable action counts')
    truncated={'rows':[{'reward':1.,'value':2.,'done':False}],'bootstrap':3.}
    advantages(truncated);assert abs(truncated['rows'][0]['return']-(1+.997*3))<1e-7
    print('PASS truncated episode bootstraps instead of fabricating a loss or win')


if __name__=='__main__':main()
