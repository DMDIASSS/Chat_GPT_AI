"""Read-only native rollouts, behavior metrics, HTML playback and RLViser."""
import argparse,json,math,os,random,shutil,time,webbrowser
from pathlib import Path
import numpy as np
import torch
from nexto_teacher import nexto_actions
from slater_native_actor import NativeActor,checkpoint_identity,packet,observation,action_mask
from slater_native_eval import Controller,load,model_identity,check_pause
from slater_v041_core import atomic_json,read_json,sha256
ROOT=Path(__file__).resolve().parent
BASE=ROOT/'data/isolated/native_inspection'

def current_checkpoint(require_paused=False):
    for name in ('focused_teacher01','focused_curriculum01'):
        state=read_json(ROOT/f'data/isolated/event_curriculum/{name}/status.json')
        if state and state.get('latest'):
            if require_paused and state.get('status') not in ('PAUSED','BUDGET_REACHED','STAGE_BUDGET_REACHED','CURRICULUM_COMPLETE','PERSISTENT_IDLE','ERROR'):
                raise ValueError(f'Pause {name} first and wait for PAUSED; checkpoint inspection itself can run during training')
            return Path(state['latest'])
    raise ValueError('No current native checkpoint; supply --checkpoint with the numbered checkpoint directory')

def snapshot(source,out):
    source=Path(source).resolve();out=Path(out);out.mkdir(parents=True,exist_ok=True)
    if source.is_dir():
        identity=checkpoint_identity(source);dest=out/source.name
        if dest.exists():raise FileExistsError('Snapshot already exists; use a new inspection name')
        dest.mkdir()
        for name in identity['files']:shutil.copy2(source/name,dest/name)
        if checkpoint_identity(source)!=identity or checkpoint_identity(dest)['files']!=identity['files']:
            shutil.rmtree(dest);raise RuntimeError('Checkpoint changed while being copied; choose a previous complete checkpoint')
    else:
        identity=model_identity(source);dest=out/source.name;shutil.copy2(source,dest)
        if sha256(source)!=identity['sha256'] or sha256(dest)!=identity['sha256']:raise RuntimeError('Attention checkpoint changed during snapshot')
    atomic_json(out/'source.json',identity);return dest

class SamplingController(Controller):
    def __init__(self,actor,seed,scripted=False):super().__init__(actor,scripted=scripted);self.rng=np.random.default_rng(seed)
    def controls(self,state,aid,previous,engine,tick,kickoff,observer):
        if not self.native:return super().controls(state,aid,previous,engine,tick,kickoff,observer)
        if tick%8==0:
            p,ids=packet(state,previous,engine);car=next(c for c in p['cars'] if c['id']==ids[aid])
            with torch.inference_mode():probs=self.actor.probabilities(torch.from_numpy(observation(p,ids[aid])[None]),torch.from_numpy(action_mask(car)[None])).numpy()[0]
            self.pending=nexto_actions()[self.rng.choice(90,p=probs/probs.sum())].copy()
        if tick%8==1:self.held=self.pending.copy()
        ids=sorted(state.cars);positions=np.array([state.cars[k].physics.position[:2] for k in ids]);teams=np.array([state.cars[k].team_num for k in ids])
        frame=self.clock.frame(is_kickoff_pause=kickoff,ball_xy=state.ball.position[:2],positions=positions,teams=teams,index=ids.index(aid),infer=lambda prev,beta:(0,self.held))
        if frame.script_applied:self.script_ticks+=1;return frame.controls
        return self.held.copy()

class Behavior:
    def __init__(self,team):
        self.sign=1 if team==0 else -1;self.ticks=0;self.idle=0;self.touch_ticks=0;self.contacts=0;self.goalward_contacts=0;self.shot_proxies=0;self.goal_for=0;self.goal_against=0;self.episodes=0
        self.speed=0.;self.distance=0.;self.behind=0;self.close=0;self.boost_spent=0.;self.ahead=0;self.touch_edge=False;self.actions={}
    def tick(self,before,after,ours,controls):
        car=after.cars[ours];prior=before.cars[ours];self.ticks+=1;self.idle+=not np.any(controls);touch=bool(car.ball_touches)
        self.touch_ticks+=touch;self.speed+=float(np.linalg.norm(car.physics.linear_velocity));self.distance+=float(np.linalg.norm(car.physics.position-prior.physics.position))
        relative=self.sign*(car.physics.position[1]-after.ball.position[1]);self.behind+=relative<0;self.ahead+=relative>200
        self.close+=np.linalg.norm(car.physics.position-after.ball.position)<400;self.boost_spent+=max(0,float(prior.boost_amount-car.boost_amount))
        if touch and not self.touch_edge:
            self.contacts+=1;p=after.ball.position;v=after.ball.linear_velocity;goal=np.array([0,self.sign*5120,100.]);direction=goal-p
            goalward=float(v@direction/max(1,float(np.linalg.norm(direction))))>200;self.goalward_contacts+=goalward
            tau=(self.sign*5120-p[1])/v[1] if abs(v[1])>1e-6 else -1
            self.shot_proxies+=bool(goalward and 0<tau<3 and abs(p[0]+v[0]*tau)<800 and p[2]<650)
        self.touch_edge=touch
        if after.goal_scored:
            self.goal_for+=self.sign*after.ball.position[1]>0;self.goal_against+=self.sign*after.ball.position[1]<0
    def result(self):
        n=max(1,self.ticks)
        return dict(seconds=self.ticks/120,idle_fraction=self.idle/n,mean_speed=self.speed/n,travel_distance=self.distance,
                    contact_events=self.contacts,touch_ticks=self.touch_ticks,goalward_contacts=self.goalward_contacts,
                    projected_shots_on_target=self.shot_proxies,goals_for=int(self.goal_for),goals_against=int(self.goal_against),
                    behind_ball_fraction=self.behind/n,ahead_of_ball_fraction=self.ahead/n,near_ball_fraction=self.close/n,
                    boost_spent=self.boost_spent,episodes=self.episodes,
                    note='Contacts are touch edges; shot projection is a geometric proxy, not a physics-verified shot or save.')

def rollout(actor,rival,*,task,side,seed,seconds=12,sampled=False,difficulty=0,record=True,renderer=None,stop=None):
    from rlgym.rocket_league.sim import RocketSimEngine
    from rlgym.rocket_league.state_mutators import FixedTeamSizeMutator,KickoffMutator
    from slater_focus_evaluation import setup
    from mechanics_scenarios import set_ball,set_car
    from afk_team_research import TeamObserver
    team=0 if side=='blue' else 1;sign=1 if team==0 else -1;ours=side+'-0';enemy=('orange' if team==0 else 'blue')+'-0'
    engine=RocketSimEngine(rlbot_delay=False);observer=TeamObserver();metrics=Behavior(team);frames=[];target=round(seconds*120);ticks=0;is_match=task in ('match','match_scripted');scripted=task=='match_scripted';learner_scripts=0
    try:
        while ticks<target:
            episode_seed=seed+metrics.episodes*7919;random.seed(episode_seed);rng=np.random.default_rng(episode_seed)
            state=engine.create_base_state();FixedTeamSizeMutator(blue_size=1,orange_size=1).apply(state,{});KickoffMutator().apply(state,{})
            if task=='open_goal':
                bp=np.array([rng.uniform(-200,200),sign*rng.uniform(4100,4300),93.]);set_ball(state.ball,bp,[0,0,0])
                set_car(state.cars[ours],bp-[0,sign*250,76],bp-[0,0,76],boost=70,on_ground=True)
                set_car(state.cars[enemy],[-3000,-sign*3500,17],[0,0,17],boost=0,on_ground=True)
            elif not is_match:setup(state,task,ours,enemy,episode_seed,difficulty)
            state=engine.set_state(state,{});learner=SamplingController(actor,episode_seed,scripted=scripted) if sampled else Controller(actor,scripted=scripted);opponent=Controller(rival,scripted=True)
            previous={};local=0;touched=False;metrics.episodes+=1;metrics.touch_edge=False;deadline=time.perf_counter()
            while ticks<target:
                if local%120==0:check_pause(stop)
                kickoff=is_match and not touched and local<168 and np.linalg.norm(state.ball.position[:2])<1 and state.ball.position[2]<100
                a=learner.controls(state,ours,previous,engine,local,kickoff,observer)
                b=np.zeros(8,dtype=np.float32) if task=='open_goal' else opponent.controls(state,enemy,previous,engine,local,kickoff,observer)
                if record and local%4==0:
                    f=dict(t=ticks/120,episode=metrics.episodes,ball=state.ball.position.tolist(),cars=[dict(team=c.team_num,pos=c.physics.position.tolist(),forward=c.physics.rotation_mtx[:,0].tolist(),boost=float(c.boost_amount)) for c in state.cars.values()],controls=a.tolist(),ours=team)
                    if isinstance(actor,NativeActor) and local%8==0:
                        p,ids=packet(state,previous,engine);car=next(c for c in p['cars'] if c['id']==ids[ours])
                        with torch.inference_mode():prob=actor.probabilities(torch.from_numpy(observation(p,ids[ours])[None]),torch.from_numpy(action_mask(car)[None])).numpy()[0]
                        f['policy']=dict(top_action=int(prob.argmax()),idle_probability=float(prob[8]),entropy=float(-(prob*np.log(prob)).sum()))
                    frames.append(f)
                if renderer is not None and local%4==0:
                    renderer.render(state,{})
                    delay=deadline-time.perf_counter()
                    if delay>0:time.sleep(min(delay,.1))
                    deadline=max(deadline+1/30,time.perf_counter())
                before=state;state=engine.step({ours:a[None],enemy:b[None]},{});metrics.tick(before,state,ours,a)
                previous={ours:a.copy(),enemy:b.copy()};ticks+=1;local+=1;touched|=any(c.ball_touches for c in state.cars.values())
                if state.goal_scored:
                    if record:frames.append(dict(t=ticks/120,episode=metrics.episodes,ball=state.ball.position.tolist(),cars=[dict(team=c.team_num,pos=c.physics.position.tolist(),forward=c.physics.rotation_mtx[:,0].tolist(),boost=float(c.boost_amount)) for c in state.cars.values()],controls=a.tolist(),ours=team))
                    break
            # A drill is a single start; full matches reset after a goal.
            learner_scripts+=learner.script_ticks
            if not is_match:break
        return dict(task=task,side=side,seed=seed,sampled=sampled,difficulty=difficulty,learner_scripted=scripted,learner_script_ticks=learner_scripts,**metrics.result(),frames=frames)
    finally:engine.close()

def write_html(report,path):
    template=(ROOT/'native_inspection_viewer.html').read_text(encoding='utf8')
    data=json.dumps(report,separators=(',',':'),allow_nan=False).replace('<','\\u003c')
    Path(path).write_text(template.replace('__REPORT_DATA__',data),encoding='utf8')

def inspect(checkpoint,out,*,rival=None,seeds=2,tasks=('open_goal','ground_score','match','match_scripted'),seconds=20,difficulty=0,include_sampled=True,stop=None):
    out=Path(out).resolve()
    if out.exists():raise FileExistsError('Inspection exists; use a new --run')
    out.mkdir(parents=True);torch.set_num_threads(1)
    teacher=Path(rival or ROOT/'data/isolated/mechanics_curriculum/selected7_mechanics01/update_000180.pt')
    if not teacher.is_file():raise FileNotFoundError('Attention rival missing; supply --rival explicitly: '+str(teacher))
    native_path=snapshot(checkpoint,out/'student');teacher_path=snapshot(teacher,out/'teacher');actor=load(native_path);opponent=load(teacher_path)
    if include_sampled and not isinstance(actor,NativeActor):raise ValueError('Sampled comparison requires a native checkpoint directory')
    report=dict(version=1,source=model_identity(checkpoint),rival=model_identity(teacher),seeds=seeds,seconds=seconds,difficulty=difficulty,records=[],
                focus_setup_sha=sha256(ROOT/'slater_focus_evaluation.py'),note='Exploratory read-only rollouts; match=raw learner kickoff, match_scripted=learner kickoff script ON, rival script ON in both. HTML is a 2D replay of actual simulator states. Simulator versions may differ from native training.')
    variants=[('student_greedy',actor,False),('teacher_greedy',opponent,False)]
    if include_sampled:variants.insert(1,('student_sampled',actor,True))
    for task in tasks:
        for j in range(seeds):
            for side in ('blue','orange'):
                for name,model,sampled in variants:
                    check_pause(stop);row=rollout(model,opponent,task=task,side=side,seed=18100000000+j*997,seconds=seconds if task.startswith('match') else min(seconds,12),sampled=sampled,difficulty=difficulty,stop=stop)
                    row['model']=name;report['records'].append(row);atomic_json(out/'report.json',report)
                    print('INSPECT',name,task,side,f"goals {row['goals_for']}:{row['goals_against']}",'touches',row['contact_events'],'goalward',row['goalward_contacts'],'idle',round(row['idle_fraction'],3),flush=True)
    report['summary']=summarize(report['records']);atomic_json(out/'report.json',report);write_html(report,out/'WATCH.html')
    print('INSPECTION_REPORT',out/'WATCH.html',flush=True);return report

def summarize(records):
    groups={}
    for r in records:groups.setdefault((r['model'],r['task']),[]).append(r)
    rows=[]
    for (model,task),cases in groups.items():
        rows.append(dict(model=model,task=task,cases=len(cases),goals_for=sum(r['goals_for'] for r in cases),goals_against=sum(r['goals_against'] for r in cases),
                         scored_cases=sum(r['goals_for']>0 for r in cases),contact_events=sum(r['contact_events'] for r in cases),goalward_contacts=sum(r['goalward_contacts'] for r in cases),
                         idle_fraction=float(np.mean([r['idle_fraction'] for r in cases])),mean_speed=float(np.mean([r['mean_speed'] for r in cases]))))
    return rows

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=('analyze','watch'));p.add_argument('--checkpoint');p.add_argument('--rival');p.add_argument('--run');p.add_argument('--seeds',type=int,default=2);p.add_argument('--seconds',type=int,default=20);p.add_argument('--difficulty',type=float,default=0);p.add_argument('--no-sampled',action='store_true');p.add_argument('--open',action='store_true');p.add_argument('--task',choices=('open_goal','ground_score','match','match_scripted'),default='match');p.add_argument('--side',choices=('blue','orange'),default='blue');a=p.parse_args()
    if not 1<=a.seeds<=16 or not 2<=a.seconds<=300 or not 0<=a.difficulty<=1:p.error('Invalid inspection budget/difficulty')
    checkpoint=Path(a.checkpoint) if a.checkpoint else current_checkpoint()
    out=BASE/(a.run or time.strftime('inspect_%Y%m%dT%H%M%S')+'_'+str(time.time_ns())[-6:])
    if a.command=='analyze':
        inspect(checkpoint,out,rival=a.rival,seeds=a.seeds,seconds=a.seconds,difficulty=a.difficulty,include_sampled=not a.no_sampled)
        if a.open:webbrowser.open((out/'WATCH.html').resolve().as_uri())
    else:
        try:from rlgym.rocket_league.rlviser import RLViserRenderer
        except ImportError as exc:raise RuntimeError('Install rlviser-py with NATIVE_17_INSTALL_RLVISER.bat, then open the RLViser application first') from exc
        teacher=Path(a.rival or ROOT/'data/isolated/mechanics_curriculum/selected7_mechanics01/update_000180.pt')
        native=snapshot(checkpoint,out/'student');op=snapshot(teacher,out/'teacher');torch.set_num_threads(1);renderer=RLViserRenderer(tick_rate=30)
        try:row=rollout(load(native),load(op),task=a.task,side=a.side,seed=18100000000,seconds=a.seconds,difficulty=a.difficulty,renderer=renderer)
        finally:renderer.close()
        atomic_json(out/'watch.json',row);print('WATCH_RESULT',json.dumps({k:v for k,v in row.items() if k!='frames'}),flush=True)
if __name__=='__main__':main()
