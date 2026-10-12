"""Read-only native/Nexto matches, C++ inference parity and held-out selection."""
from __future__ import annotations
import argparse,hashlib,importlib.util,json,math,os,random,shutil,subprocess,time
from pathlib import Path
from importlib.metadata import version
import numpy as np
import torch
from slater_native_actor import NativeActor,checkpoint_identity,packet,observation,action_mask,infer
from slater_v041_core import atomic_json,read_json,sha256,process_lock
from slater_nexto_scheduler_v038b import NextoV4Clock,KICKOFF_SHA
from slater_mechanics_eval import load_actor,interval
from slater_versatile_eval import sign_pvalue
from slater_versatile_data import native_observation
from nexto_teacher import nexto_actions
ROOT=Path(__file__).resolve().parent
BASE=ROOT/'data/isolated/native_quality'
TASKS=('match','ground','defense','recovery','aerial','wall','air_dribble','air_finish','reset_use','low_boost')

def helper():
    spec=importlib.util.spec_from_file_location('native_runner',ROOT/'GigaLearn_Project/Native_Backend/native_setup.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def model_identity(path):
    path=Path(path).resolve()
    return {'kind':'native',**checkpoint_identity(path)} if path.is_dir() else {'kind':'nexto','path':str(path),'sha256':sha256(path)}

def identity_digest(identity):return hashlib.sha256(json.dumps(identity,sort_keys=True).encode()).hexdigest()

def load(path):return NativeActor(path) if Path(path).is_dir() else load_actor(ROOT,Path(path))

def probe_samples():
    from rlgym.rocket_league.sim import RocketSimEngine
    from rlgym.rocket_league.state_mutators import FixedTeamSizeMutator,KickoffMutator
    from mechanics_scenarios import basis
    samples=[];rng=np.random.default_rng(910124)
    for size in (1,2,3):
        engine=RocketSimEngine(rlbot_delay=False)
        try:
            for j in range(8):
                state=engine.create_base_state();FixedTeamSizeMutator(blue_size=size,orange_size=size).apply(state,{})
                random.seed(910124+j);KickoffMutator().apply(state,{})
                state=engine.set_state(state,{});p,ids=packet(state,{},engine)
                if j:
                    p['timers']=rng.uniform(0,10,34).tolist();p['timers'][j]=0
                    for body in [p['ball'],*p['cars']]:
                        body['pos']=rng.uniform([-3500,-4500,40],[3500,4500,1600]).tolist()
                        body['vel']=rng.uniform(-2000,2000,3).tolist();body['ang']=rng.uniform(-4,4,3).tolist()
                        body['rot']=basis(rng.normal(size=3),up=rng.normal(size=3)).T.reshape(-1).tolist()
                    for i,c in enumerate(p['cars']):
                        c.update(boost=0 if j==2 else float(rng.uniform(1,100)),ground=j%3==0,
                            jumped=j%2==0,double_jumped=j==3,flipped=j==4,air_time=float(j/3),
                            demo=j==6,world_contact=j==7,contact_normal=[0,0,1] if j==7 else [0,0,0],
                            previous=nexto_actions()[int(rng.integers(90))].tolist())
                for query in ids.values():samples.append({'packet':p,'query':query})
        finally:engine.close()
    return samples

def parity(path,build_dir=None):
    model=NativeActor(path);h=helper();build=Path(build_dir or h.BASE/'build').resolve()
    binary=build/('SlaterGigaNative.exe' if os.name=='nt' else 'SlaterGigaNative')
    if not binary.is_file():raise ValueError('Build the updated native executable before parity checks')
    protocol={'model':model.identity,'binary':h.binary_identity(build),
        'adapter':sha256(ROOT/'slater_native_actor.py'),'eval':sha256(__file__)}
    folder=BASE/'parity'/identity_digest(protocol)[:24];folder.mkdir(parents=True,exist_ok=True)
    with process_lock(folder/'parity.lock'):
        cached=read_json(folder/'result.json')
        if cached and cached['protocol']==protocol and cached['passed']:return cached
        samples=probe_samples();atomic_json(folder/'input.json',samples)
        source=folder/'source'/Path(path).name
        if source.exists():
            if checkpoint_identity(source)['files']!=model.identity['files']:raise ValueError('Probe source copy changed')
        else:shutil.copytree(Path(path),source)
        args=[binary,'--meshes',h.meshes(),'--checkpoints',source.parent,'--device','cpu','--games','2',
            '--width',str(model.width),'--depth',str(model.depth),'--probe',folder/'input.json','--probe-out',folder/'output.json']
        result=subprocess.run([str(x) for x in args],cwd=build,env=h.runtime_environment(binary,folder/'pause.flag'),
            stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf8',errors='replace')
        (folder/'probe.log').write_text(result.stdout,encoding='utf8')
        if result.returncode or 'SLATER_NATIVE_PROBE_COMPLETE' not in result.stdout:
            raise RuntimeError('Native parity probe failed; see '+str(folder/'probe.log')+'\n'+result.stdout[-2500:])
        output=read_json(folder/'output.json');errors=[];mask_errors=actions=0
        if len(output)!=len(samples):raise ValueError('Incomplete C++ probe')
        for sample,actual in zip(samples,output):
            p=sample['packet'];query=sample['query'];car=next(c for c in p['cars'] if c['id']==query)
            obs=observation(p,query);mask=action_mask(car)
            with torch.no_grad():probs=model.probabilities(torch.from_numpy(obs[None]),torch.from_numpy(mask[None])).numpy()[0]
            errors.append((float(np.max(np.abs(obs-actual['obs']))),float(np.max(np.abs(probs-actual['probs'])))))
            mask_errors+=int(not np.array_equal(mask,np.array(actual['mask'],dtype=bool)))
            actions+=int(int(probs.argmax())!=actual['action'])
        maximum=np.max(errors,axis=0)
        passed=bool(maximum[0]<3e-6 and maximum[1]<1e-5 and not mask_errors and not actions)
        report={'protocol':protocol,'passed':passed,'samples':len(samples),'max_observation_error':maximum[0],
            'max_probability_error':maximum[1],'mask_mismatches':mask_errors,'action_mismatches':actions,
            'note':'Observation/mask/float32 inference parity; not physics parity between simulator versions.'}
        if checkpoint_identity(path)!=model.identity:raise RuntimeError('Protected checkpoint changed')
        atomic_json(folder/'result.json',report)
        print('NATIVE_PARITY',passed,len(samples),maximum.tolist(),flush=True)
        if not passed:raise RuntimeError('Native parity failed; evaluation is blocked: '+str(folder/'result.json'))
        return report

class Controller:
    def __init__(self,actor):
        self.actor=actor;self.native=isinstance(actor,NativeActor);self.clock=NextoV4Clock(hardcoded=True,stochastic=False)
        self.held=np.zeros(8,dtype=np.float32);self.pending=self.held.copy();self.script_ticks=0
    def controls(self,state,aid,previous,engine,tick,kickoff,observer):
        ids=sorted(state.cars);positions=np.array([state.cars[k].physics.position[:2] for k in ids]);teams=np.array([state.cars[k].team_num for k in ids])
        if self.native:
            # Source-matched native cadence: observe before one old-control tick,
            # then apply the selected action for seven ticks. Scripts are external.
            if tick%8==0:
                p,keys=packet(state,previous,engine);self.pending=nexto_actions()[infer(self.actor,p,keys[aid])].copy()
            if tick%8==1:self.held=self.pending.copy()
            frame=self.clock.frame(is_kickoff_pause=kickoff,ball_xy=state.ball.position[:2],positions=positions,
                teams=teams,index=ids.index(aid),infer=lambda prev,beta:(0,self.held))
            if frame.script_applied:self.script_ticks+=1;return frame.controls
            return self.held.copy()
        def predict(prev,beta):
            from slater_cycle9_native_ppo_v025 import logits_of
            before=dict(previous);before[aid]=prev
            obs=native_observation(observer.observe(state,before)[aid])
            with torch.no_grad():index=int(logits_of(self.actor,tuple(torch.from_numpy(x[None]) for x in obs)).argmax(-1))
            return index,nexto_actions()[index]
        frame=self.clock.frame(is_kickoff_pause=kickoff,ball_xy=state.ball.position[:2],positions=positions,teams=teams,index=ids.index(aid),infer=predict)
        self.script_ticks+=int(frame.script_applied);return frame.controls

def match(candidate,rival,*,side,seed,seconds,task='match',team_size=1):
    from rlgym.rocket_league.sim import RocketSimEngine
    from rlgym.rocket_league.state_mutators import FixedTeamSizeMutator,KickoffMutator
    from afk_team_research import TeamObserver
    from slater_mechanics_env import configure_mechanic
    from mechanics_scenarios import configure,set_ball,set_car
    engine=RocketSimEngine(rlbot_delay=False);observer=TeamObserver();target=round(seconds*120)
    ticks=gf=ga=episodes=successes=scripts=0;team=0 if side=='blue' else 1
    try:
        while ticks<target:
            # Reserve a disjoint episode namespace inside each experiment seed.
            episode_seed=(int(seed)<<20)+episodes;rng=np.random.default_rng(episode_seed)
            state=engine.create_base_state();FixedTeamSizeMutator(blue_size=team_size,orange_size=team_size).apply(state,{})
            random.seed(episode_seed);KickoffMutator().apply(state,{})
            ours=('blue-' if team==0 else 'orange-')+'0';enemy=('orange-' if team==0 else 'blue-')+'0';sign=1 if team==0 else -1
            if task in ('air_dribble','air_finish','reset_use'):configure_mechanic(state,task,ours,enemy,episode_seed,.65)
            elif task in ('recovery','aerial'):configure(state,'recovery' if task=='recovery' else 'aerial_touch',ours,enemy,rng)
            elif task in ('ground','low_boost','wall','defense'):
                bp=[rng.uniform(-600,600),-sign*2800 if task=='defense' else rng.uniform(-2400,2400),500 if task=='wall' else 93]
                if task=='wall':bp[0]=3700
                set_ball(state.ball,bp,[0,-sign*900 if task=='defense' else sign*400,0])
                for aid,c in state.cars.items():
                    cp=[rng.uniform(-1200,1200),-sign*4200 if aid==ours and task=='defense' else rng.uniform(-3500,3500),17]
                    if aid==ours and task=='wall':cp=[3550,bp[1]-sign*300,350]
                    set_car(c,cp,bp,boost=10 if task=='low_boost' else 70,on_ground=task!='wall' or aid!=ours)
            state=engine.set_state(state,{});controllers={aid:Controller(candidate if c.team_num==team else rival) for aid,c in state.cars.items()}
            previous={};episode_ticks=0;touched=False;success=False;max_ticks=target-ticks if task=='match' else min(1200,target-ticks)
            from slater_mechanics_core import MechanicTracker
            tracker=MechanicTracker(task,state,ours,enemy) if task in ('air_dribble','air_finish','reset_use') else None
            while episode_ticks<max_ticks:
                kickoff=task=='match' and not touched and episode_ticks<168 and np.linalg.norm(state.ball.position[:2])<1 and state.ball.position[2]<100
                commands={aid:control.controls(state,aid,previous,engine,episode_ticks,kickoff,observer)[None] for aid,control in controllers.items()}
                before=state;state=engine.step(commands,{})
                previous={aid:a[0].copy() for aid,a in commands.items()};ticks+=1;episode_ticks+=1
                touched|=any(c.ball_touches for c in state.cars.values());car=state.cars[ours]
                if tracker:tracker.tick(before,state,commands[ours][0]);success|=tracker.events.success
                elif task=='recovery':success|=car.on_ground and car.physics.rotation_mtx[2,2]>.8
                elif task in ('aerial','wall'):success|=bool(car.ball_touches and car.physics.position[2]>250)
                elif task=='defense':success|=bool(car.ball_touches and sign*state.ball.linear_velocity[1]>100)
                if state.goal_scored:
                    scored=sign*state.ball.position[1]>0;gf+=scored;ga+=not scored
                    if task in ('ground','low_boost'):success|=scored
                    break
            scripts+=sum(c.script_ticks for c in controllers.values());episodes+=1;successes+=success
    finally:engine.close()
    return {'side':side,'seed':seed,'task':task,'team_size':team_size,'seconds':ticks/120,
        'goals_for':int(gf),'goals_against':int(ga),'goal_diff':int(gf-ga),'wins':int(gf>ga),'draws':int(gf==ga),'losses':int(gf<ga),
        'episodes':episodes,'successes':int(successes),'script_ticks':scripts}

def code_identity():
    names=('slater_native_actor.py','slater_native_eval.py','slater_mechanics_core.py','slater_mechanics_env.py',
        'slater_nexto_scheduler_v038b.py','mechanics_scenarios.py','nexto_teacher.py','afk_team_research.py','vendor/nexto/nexto_obs.py','slater_versatile_data.py',
        'GigaLearn_Project/Native_Backend/native_setup.py','slater_native_holdout.py')
    return {n:sha256(ROOT/n) for n in names}

def evaluate(candidates,rivals,*,out,seeds=4,seconds=120,seed_base=930000000,build_dir=None,tasks=('match',),team_size=1):
    if not 1<=seeds<=64 or not 8<=seconds<=300 or len(candidates)>8 or not candidates or not rivals:raise ValueError('Invalid bounded evaluation budget')
    torch.set_num_threads(2)
    out=Path(out).resolve()
    if not out.is_relative_to(BASE):raise ValueError('Evaluation outputs must be under data/isolated/native_quality')
    identities={group:{name:model_identity(p) for name,p in paths.items()} for group,paths in (('candidates',candidates),('rivals',rivals))}
    for group in identities.values():
        for item in group.values():
            if item['kind']=='native':parity(item['path'],build_dir)
    protocol={**identities,'seeds':seeds,'seconds':seconds,'seed_base':seed_base,'tasks':list(tasks),'team_size':team_size,
        'code':code_identity(),'runtime':{n:version(n) for n in ('torch','numpy','rocketsim','rlgym-rocket-league')},
        'kickoff_sha':KICKOFF_SHA,'scripted_kickoff_all':True,'cadence':'native8+1; NextoV4Clock per tick',
        'physics':'Python RocketSim; not claimed equal to bundled CPP RocketSim'}
    with process_lock(out.with_suffix('.lock')):
        state=read_json(out,{'protocol':protocol,'records':[],'done':False})
        if state['protocol']!=protocol:raise ValueError('Cached evaluation protocol changed; use another output name')
        if state['done']:return state
        actors={n:load(p) for n,p in candidates.items()};opponents={n:load(p) for n,p in rivals.items()}
        done={(r['candidate'],r['rival'],r['side'],r['seed'],r['task']) for r in state['records']}
        total=len(candidates)*len(rivals)*2*seeds*len(tasks);started=time.perf_counter();new=0
        print('NATIVE_EVAL_BEGIN matches',total,'remaining',total-len(done),flush=True)
        for task in tasks:
            for j in range(seeds):
                seed=seed_base+997*j
                for rival in rivals:
                    for side in ('blue','orange'):
                        for name,actor in actors.items():
                            key=(name,rival,side,seed,task)
                            if key in done:continue
                            row=match(actor,opponents[rival],side=side,seed=seed,seconds=seconds,task=task,team_size=team_size)
                            row.update(candidate=name,rival=rival);state['records'].append(row);new+=1;atomic_json(out,state)
                            eta=(time.perf_counter()-started)/new*(total-len(state['records']))
                            print('NATIVE_EVAL',len(state['records']),'/',total,name,rival,side,task,
                                f"{row['goals_for']}:{row['goals_against']}",'eta_minutes',round(eta/60,1),flush=True)
        ranking=[]
        for name in candidates:
            rows=[r for r in state['records'] if r['candidate']==name]
            ranking.append({'candidate':name,'matches':len(rows),'mean_goal_diff':float(np.mean([r['goal_diff'] for r in rows])),
                **{k:sum(r[k] for r in rows) for k in ('wins','draws','losses','goals_for','goals_against','successes')}})
        state.update(ranking=sorted(ranking,key=lambda r:(r['mean_goal_diff'],r['wins']-r['losses']),reverse=True),done=True)
        for group,paths in (('candidates',candidates),('rivals',rivals)):
            if {n:model_identity(p) for n,p in paths.items()}!=identities[group]:raise RuntimeError('Protected evaluation input changed')
        atomic_json(out,state);return state

def paired_verdict(result,leader,reference,*,alpha=.05):
    grouped={};per_rival={};rows=result['records'];seconds=result['protocol']['seconds']
    table={(r['candidate'],r['rival'],r['side'],r['seed'],r['task']):r for r in rows}
    if len(table)!=len(rows):raise ValueError('Duplicate evaluation record')
    protocol=result['protocol']
    required={(n,rival,side,protocol['seed_base']+997*j,task) for n in (leader,reference)
        for rival in protocol['rivals'] for side in ('blue','orange') for j in range(protocol['seeds']) for task in protocol['tasks']}
    if not required.issubset(table):raise ValueError('Incomplete paired evaluation')
    for r in rows:
        if r['candidate']!=leader:continue
        key=(reference,r['rival'],r['side'],r['seed'],r['task'])
        if key not in table:raise ValueError('Incomplete paired evaluation')
        delta=(r['goal_diff']-table[key]['goal_diff'])*60/seconds
        grouped.setdefault(r['seed'],[]).append(delta);per_rival.setdefault(r['rival'],{}).setdefault(r['seed'],[]).append(delta)
    diffs=[float(np.mean(v)) for v in grouped.values()];ci=interval(diffs);p=sign_pvalue(diffs)
    rivals={n:interval([float(np.mean(v)) for v in g.values()]) for n,g in per_rival.items()}
    passed=len(diffs)>=8 and p<=alpha and ci['lower'] is not None and ci['lower']>0 and all(
        c['lower'] is not None and c['lower']>=-.5 for c in rivals.values())
    return {'passed':bool(passed),'leader':leader,'reference':reference,'paired_goal_diff_per_minute':ci,'per_rival':rivals,
        'sign_p':p,'alpha':alpha,'note':'Seed-clustered simulator evidence; no guaranteed universal winner or SSL rank.'}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=('parity','compare'))
    p.add_argument('--candidate',action='append',required=True);p.add_argument('--rival',action='append')
    p.add_argument('--out',default=str(BASE/'comparison01.json'));p.add_argument('--build-dir')
    p.add_argument('--seeds',type=int,default=4);p.add_argument('--seconds',type=int,default=120);p.add_argument('--seed-base',type=int,default=930000000)
    a=p.parse_args()
    if a.command=='parity':
        for path in a.candidate:parity(path,a.build_dir)
        return
    candidates={f'candidate_{i}_{Path(path).name}':path for i,path in enumerate(a.candidate)}
    rivals={f'rival_{i}_{Path(path).stem}':path for i,path in enumerate(a.rival or [ROOT/'vendor/nexto/nexto-model.pt'])}
    print(json.dumps(evaluate(candidates,rivals,out=a.out,seeds=a.seeds,seconds=a.seconds,seed_base=a.seed_base,build_dir=a.build_dir)['ranking'],indent=2))

if __name__=='__main__':main()
