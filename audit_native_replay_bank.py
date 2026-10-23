"""Read-only training-label audit; excludes validation/test rows from summaries."""
import argparse,json,struct
from pathlib import Path
import numpy as np

def audit(path):
    with open(path,'rb') as f:
        if f.read(4)!=b'SGRB':raise ValueError('Invalid bank')
        version,players,count,width=struct.unpack('<IIII',f.read(16));f.read((720+102)*4)
        if version!=1 or players not in (2,4,6) or width!=52+43*players+93 or count>100000:raise ValueError('Invalid bank dimensions')
        raw=f.read()
    if len(raw)!=count*width*4:raise ValueError('Truncated bank')
    rows=np.frombuffer(raw,dtype='<f4').reshape(count,width);rows=rows[rows[:,-1]==0]
    if not len(rows):raise ValueError('No training rows')
    target=rows[:,53+43*players:143+43*players];query=rows[:,52+43*players].astype(int)
    ground=np.array([bool(r[52+43*q+19]) for r,q in zip(rows,query)])
    histogram=target.mean(0)
    return {'bank':str(Path(path).resolve()),'partition':'train','rows':len(rows),
        'idle_target_mass':float(histogram[8]),'ground_rows':int(ground.sum()),
        'ground_idle_target_mass':float(target[ground,8].mean()) if ground.any() else None,
        'top_actions':[{'action':int(i),'mean_target_mass':float(histogram[i])} for i in histogram.argsort()[-10:][::-1]],
        'note':'High idle mass is a warning to inspect recorded throttle/steer coverage, not proof of parser failure.'}
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--bank',default='data/isolated/ranked_duels_quality_bank01.bin');a=p.parse_args()
    result=audit(a.bank);out=Path(a.bank).with_suffix('.label_audit.json');out.write_text(json.dumps(result,indent=2),encoding='utf8');print(json.dumps(result,indent=2));print('REPORT',out)
