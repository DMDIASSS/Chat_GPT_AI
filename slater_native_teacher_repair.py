"""Current-state teacher labels for native recovery; copied checkpoints only."""
import argparse,importlib.util,json,random,struct,sys
from pathlib import Path
import numpy as np
import torch
from slater_native_actor import NativeActor,packet,observation,action_mask
from slater_native_eval import Controller,load,helper,match,evaluate
from nexto_teacher import NextoTeacher,nexto_actions
from slater_v041_core import atomic_json,sha256
ROOT=Path(__file__).resolve().parent
BASE=ROOT/'data/isolated/native_teacher_repair'

def bank_rows(rows,bank,teacher,groups):
    from rlgym.rocket_league.common_values import BOOST_LOCATIONS
    bank=Path(bank);bank.parent.mkdir(parents=True,exist_ok=True)
    if bank.exists():raise FileExistsError('Teacher bank exists; preserve it and choose a new run')
    rows=np.asarray(rows,dtype='<f4')
    if rows.ndim!=2 or rows.shape[1]!=231 or len(rows)<100 or not np.isfinite(rows).all():raise ValueError('Insufficient or invalid teacher rows')
    labels=rows[:,139:229]
    if not np.allclose(labels.sum(1),1,atol=1e-5):raise ValueError('Invalid teacher labels')
    if not all(np.any(rows[:,-1]==i) for i in range(3)):raise ValueError('Teacher bank needs train, validation and test episodes')
    with bank.with_suffix('.partial').open('wb') as f:
        f.write(b'SGRB');f.write(struct.pack('<IIII',1,2,len(rows),231));f.write(nexto_actions().astype('<f4').tobytes());f.write(np.asarray(BOOST_LOCATIONS,dtype='<f4').tobytes());f.write(rows.tobytes())
    bank.with_suffix('.partial').replace(bank)
    result={'kind':'current_state_teacher_policy','teacher':str(teacher),'teacher_sha':sha256(teacher),'bank_sha':sha256(bank),
            'rows':len(rows),'groups':groups,'partitions':{str(i):int((rows[:,-1]==i).sum()) for i in range(3)},
            'train_idle_target_mass':float(labels[rows[:,-1]==0,8].mean()),'note':'Synthetic simulator episodes, grouped splits; teacher targets use current state only. Not human replay labels.'}
    atomic_json(bank.with_suffix('.json'),result);return result

def collect(bank,teacher,*,episodes=128,seconds=20):
    from rlgym.rocket_league.sim import RocketSimEngine
    from rlgym.rocket_league.state_mutators import FixedTeamSizeMutator,KickoffMutator
    from afk_team_research import TeamObserver
    from mechanics_scenarios import set_ball,set_car
    if not 12<=episodes<=256 or not 4<=seconds<=30:raise ValueError('Use 12..256 episodes and 4..30 seconds')
    if Path(bank).exists():raise FileExistsError('Teacher bank exists')
    actor=load(teacher);teacher_policy=NextoTeacher();teacher_policy.actor=actor
    observer=TeamObserver();engine=RocketSimEngine(rlbot_delay=False);rows=[];groups={0:[],1:[],2:[]};torch.set_num_threads(1)
    try:
        for episode in range(episodes):
            split=2 if episode%10==0 else 1 if episode%10==1 else 0;seed=941500000+episode;groups[split].append(seed)
            random.seed(seed);rng=np.random.default_rng(seed);state=engine.create_base_state();FixedTeamSizeMutator(blue_size=1,orange_size=1).apply(state,{})
            KickoffMutator().apply(state,{})
            if episode%3:
                bp=[rng.uniform(-2200,2200),rng.uniform(-3000,3000),93];set_ball(state.ball,bp,[0,rng.uniform(-400,400),0])
                for aid,c in state.cars.items():set_car(c,[rng.uniform(-2500,2500),rng.uniform(-3800,3800),17],bp,boost=rng.uniform(20,100),on_ground=True)
            state=engine.set_state(state,{});ids=sorted(state.cars,key=lambda aid:(state.cars[aid].team_num,str(aid)))
            controls={aid:Controller(actor,scripted=True) for aid in ids};previous={};touched=False
            for tick in range(seconds*120):
                kickoff=episode%3==0 and not touched and tick<168 and np.linalg.norm(state.ball.position[:2])<1
                if tick%24==0:
                    p,keys=packet(state,previous,engine);obs=teacher_policy.observe(state,previous);logits=teacher_policy.logits([(q,kv,mask) for _,q,kv,mask in obs]);probs=torch.softmax(torch.from_numpy(logits),-1).numpy()
                    for j,(aid,*_) in enumerate(obs):
                        car=next(c for c in p['cars'] if c['id']==keys[aid]);target=probs[j]*action_mask(car)
                        if target.sum()<.05:continue
                        target=target/target.sum();blocks=[]
                        def body(b):return np.r_[b['pos'],b['rot'],b['vel'],b['ang']]
                        for other in ids:
                            c=state.cars[other];raw=next(b for b in p['cars'] if b['id']==keys[other]);hidden=np.r_[raw['boost'],raw['ground'],raw['jumped'],raw['double_jumped'],raw['flipped'],c.is_jumping,c.jump_time,c.flip_time,raw['air_time'],raw['previous'],c.flip_torque,c.wheels_with_contact,bool(c.is_flipping)]
                            blocks.append(np.r_[body(raw),hidden])
                        rows.append(np.r_[body(p['ball']),p['timers'],*blocks,ids.index(aid),target,1,split])
                commands={aid:control.controls(state,aid,previous,engine,tick,kickoff,observer)[None] for aid,control in controls.items()}
                state=engine.step(commands,{});previous={aid:a[0].copy() for aid,a in commands.items()};touched|=any(c.ball_touches for c in state.cars.values())
                if state.goal_scored:break
            print('TEACHER_COLLECT',episode+1,'/',episodes,'rows',len(rows),flush=True)
    finally:engine.close()
    return bank_rows(rows,bank,teacher,groups)

def validation(checkpoint,bank):
    actor=NativeActor(checkpoint)
    with open(bank,'rb') as f:
        if f.read(4)!=b'SGRB':raise ValueError('Invalid bank')
        version,players,count,width=struct.unpack('<IIII',f.read(16));f.read((720+102)*4);rows=np.frombuffer(f.read(),dtype='<f4').reshape(count,width)
    if version!=1 or players!=2 or width!=231:raise ValueError('Expected duel bank')
    x=[];ys=[];masks=[]
    for row in rows:
        if row[-1]!=1:continue
        def body(b):return dict(pos=b[:3].tolist(),rot=b[3:12].tolist(),vel=b[12:15].tolist(),ang=b[15:18].tolist())
        p=dict(ball=body(row),timers=row[18:52].tolist(),cars=[])
        for i in range(2):
            b=row[52+43*i:95+43*i];p['cars'].append(dict(id=i+1,team=i,**body(b),boost=float(b[18]),ground=bool(b[19]),jumped=bool(b[20]),double_jumped=bool(b[21]),flipped=bool(b[22]),air_time=float(b[26]),demo=False,world_contact=False,contact_normal=[0,0,0],previous=b[27:35].tolist()))
        query=int(row[138]);car=p['cars'][query];mask=action_mask(car);y=row[139:229]*mask
        if y.sum()<.5:continue
        x.append(observation(p,query+1));ys.append(y/y.sum());masks.append(mask)
    if not x:raise ValueError('No usable validation rows')
    ce=[];kl=[];idle=[]
    with torch.no_grad():
        for start in range(0,len(x),256):
            y=torch.tensor(np.asarray(ys[start:start+256]));probs=actor.probabilities(torch.tensor(np.asarray(x[start:start+256])),torch.tensor(np.asarray(masks[start:start+256])))
            ce.extend((-(y*probs.log()).sum(-1)).tolist());kl.extend((y*(y.clamp_min(1e-11).log()-probs.log())).sum(-1).tolist());idle.extend((probs.argmax(-1)==8).tolist())
    return dict(samples=len(x),actor_cross_entropy=float(np.mean(ce)),teacher_kl=float(np.mean(kl)),idle_argmax_fraction=float(np.mean(idle)))

def main():
    p=argparse.ArgumentParser();p.add_argument('--run',default='native_teacher_repair01');p.add_argument('--episodes',type=int,default=128);p.add_argument('--seconds',type=int,default=20)
    p.add_argument('--source',default=str(ROOT/'data/isolated/gigalearn_native/runs/ranked_duels_train01/checkpoints/3711232'))
    p.add_argument('--build-dir');p.add_argument('--teacher');p.add_argument('--compare',action='store_true');p.add_argument('--bank');p.add_argument('--collect-only',action='store_true');a=p.parse_args()
    from export_rlbot_v4 import validate_name
    validate_name(a.run);folder=BASE/a.run;bank=Path(a.bank or folder/'teacher_bank.bin')
    if not bank.resolve().is_relative_to(BASE):raise ValueError('Repair bank must be under data/isolated/native_teacher_repair')
    if a.teacher:teacher=Path(a.teacher)
    else:
        best=ROOT/'data/isolated/mechanics_curriculum/selected7_mechanics01/update_000180.pt';teacher=best if best.is_file() else ROOT/'vendor/nexto/nexto-model.pt'
    if not bank.exists():print(json.dumps(collect(bank,teacher,episodes=a.episodes,seconds=a.seconds),indent=2),flush=True)
    metadata=json.loads(bank.with_suffix('.json').read_text())
    if metadata['teacher_sha']!=sha256(teacher):raise ValueError('Teacher changed; use a new repair run/bank')
    if a.collect_only:return
    h=helper();model=NativeActor(a.source);run=h.BASE/'runs'/a.run
    if run.exists():raise FileExistsError('Repair run exists; preserve it and use a new --run')
    before=validation(a.source,bank);atomic_json(folder/'before.json',before);print('REPAIR_BEFORE',json.dumps(before),flush=True)
    h.command([sys.executable,'-u',h.HERE/'native_setup.py','train','--build-dir',a.build_dir or h.BASE/'build','--run',a.run,'--device','auto','--games','32','--steps','16384','--iterations','2',
               '--width',str(model.width),'--depth',str(model.depth),'--initial-checkpoint',a.source,'--replay-bank',bank,'--bc-epochs','10','--kickoff-epochs','0'])
    result=json.loads((run/'last_result.json').read_text());after=validation(result['checkpoint'],bank)
    record=dict(source=model.identity,checkpoint=result['checkpoint'],before=before,after=after,
                improved_teacher_fit=after['teacher_kl']<before['teacher_kl'],note='Teacher fit is not match strength; compare preserved checkpoints before resuming overnight.')
    atomic_json(folder/'repair_report.json',record);print('REPAIR_AFTER',json.dumps(record,indent=2),flush=True)
    if a.compare:
        out=ROOT/'data/isolated/native_quality'/'teacher_repairs'/a.run/'comparison.json'
        result=evaluate({'original':a.source,'repaired':result['checkpoint']},{'teacher':str(teacher)},out=out,seeds=2,seconds=45,build_dir=a.build_dir)
        ranking={row['candidate']:row for row in result['ranking']}
        record['comparison']=str(out)
        record['comparison_ranking']=result['ranking']
        record['passed_preliminary_match_gate']=bool(ranking['repaired']['goals_for']>0 and ranking['repaired']['mean_goal_diff']>ranking['original']['mean_goal_diff'])
        record['recommended_for_play']=False
        record['selection_note']='A preliminary gate is not independent confirmation. Keep update180 as the playing model until longer fresh-seed tests pass.'
        atomic_json(folder/'repair_report.json',record)
        print('REPAIR_COMPARISON',out,flush=True)
        print(json.dumps(result['ranking'],indent=2),flush=True)
        print('PRELIMINARY_MATCH_GATE', 'PASSED_NEEDS_CONFIRMATION' if record['passed_preliminary_match_gate'] else 'FAILED_KEEP_EXISTING_PLAYING_MODEL',flush=True)
if __name__=='__main__':main()
