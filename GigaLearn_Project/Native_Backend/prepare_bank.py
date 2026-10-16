"""Prepared native replay shards -> C++ replay BC/reset bank. No future labels."""
from pathlib import Path
import argparse,json,struct,sys,hashlib
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from slater_versatile_data import DemoDataset,valid_state
from afk_team_research import TeamObserver
from nexto_teacher import nexto_actions
from slater_v041_core import atomic_json,sha256


def body(p):
    return np.concatenate((p.position,p.rotation_mtx.T.reshape(-1),p.linear_velocity,p.angular_velocity))


def make(dataset,out,*,players=2,limit=10000):
    from rlgym_tools.rocket_league.misc.serialize import deserialize_game_state
    from rlgym.rocket_league.common_values import BOOST_LOCATIONS
    d=DemoDataset(dataset);out=Path(out).resolve()
    if not out.is_relative_to(ROOT/'data/isolated'):raise ValueError('Bank output must be under data/isolated')
    if out.exists():raise FileExistsError('Bank exists; choose a new output')
    if players not in (2,4,6) or not 100<=limit<=100000:raise ValueError('Invalid roster or sample cap')
    rows=[];observer=TeamObserver();groups={0:set(),1:set(),2:set()};counts={0:0,1:0,2:0}
    # Interleave sources, so a sample cap cannot silently remove a holdout partition.
    records=list(d.manifest['sources']);records.sort(key=lambda r:r['source_sha'])
    shards=[]
    for r in records:
        if sha256(r['path'])!=r['sha256']:raise ValueError('Replay shard changed')
        with np.load(r['path'],allow_pickle=False) as z:shards.append((r,{k:z[k] for k in ('states','q','target','weight')}))
    for sample in range(max(len(z['weight']) for _,z in shards)):
        for r,z in shards:
            if len(rows)>=limit:break
            if sample>=len(z['weight']):continue
            state=deserialize_game_state(z['states'][sample].copy())
            if len(state.cars)!=players or not valid_state(state):continue
            cars=sorted(state.cars.items(),key=lambda item:(item[1].team_num,str(item[0])))
            obs=observer.observe(state,{})
            errors=[float(np.max(np.abs(obs[aid][0][0,:24]-z['q'][sample,0,:24]))) for aid,_ in cars]
            query=int(np.argmin(errors))
            if errors[query]>1e-4:continue
            blocks=[]
            for i,(aid,car) in enumerate(cars):
                previous=z['q'][sample,0,-8:] if i==query else np.zeros(8)
                hidden=np.concatenate(([car.boost_amount,car.on_ground,car.has_jumped,car.has_double_jumped,car.has_flipped,
                    car.is_jumping,car.jump_time,car.flip_time,car.air_time_since_jump],previous,car.flip_torque,
                    car.wheels_with_contact,[bool(car.is_flipping)]))
                blocks.append(np.concatenate((body(car.physics),hidden)))
            split={'train':0,'validation':1,'test':2}[r['partition']]
            row=np.concatenate((body(state.ball),state.boost_pad_timers,*blocks,[query],z['target'][sample],[z['weight'][sample],split])).astype('<f4')
            if row.shape!=(52+43*players+93,) or not np.isfinite(row).all():raise ValueError('Invalid bank row')
            rows.append(row);groups[split].add(r.get('group',r['source_sha']));counts[split]+=1
        if len(rows)>=limit:break
    if len(groups[0])<2 or not groups[1] or not groups[2]:raise ValueError('Need independent train/validation/test groups in requested roster')
    out.parent.mkdir(parents=True,exist_ok=True);tmp=out.with_suffix('.partial')
    with tmp.open('wb') as f:
        f.write(b'SGRB');f.write(struct.pack('<IIII',1,players,len(rows),len(rows[0])))
        f.write(nexto_actions().astype('<f4').tobytes());f.write(np.asarray(BOOST_LOCATIONS,dtype='<f4').tobytes());f.write(np.stack(rows).tobytes())
    tmp.replace(out)
    report={'bank':str(out),'sha256':sha256(out),'source_manifest_sha':sha256(d.path/'manifest.json'),
            'rows':len(rows),'players':players,'partitions':counts,'groups':{k:len(v) for k,v in groups.items()},
            'note':'Reconstructed source states, not proof of authentic human controls or elite play. C++ action-table equality is checked on load.'}
    atomic_json(out.with_suffix('.json'),report);print(json.dumps(report,indent=2));return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--dataset',required=True);p.add_argument('--out',required=True)
    p.add_argument('--players',type=int,default=2);p.add_argument('--limit',type=int,default=10000)
    a=p.parse_args();make(a.dataset,a.out,players=a.players,limit=a.limit)
