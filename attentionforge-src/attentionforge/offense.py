"""Continuation experiment: aim, useful aerials, recovery, and scenario panels."""
import copy,json,math,secrets,shutil,time,os,tempfile,io,hashlib
from pathlib import Path
import numpy as np
import torch
from .runtime import ROOT,atomic_json,save_checkpoint,sha,source_hashes,batch,device,config
from .train import lock_run,load
from .model import ActorCritic
from .observation import encode,ACTIONS
from .gpu_profile import model_hash

SCENES={'center':0,'diagonal_left':1,'diagonal_right':2,'offcenter_left':3,'offcenter_right':4,'open_play':5,'finishing':6,'jump_touch':7,'recovery':8}
MATCH_CONTEXTS=tuple(SCENES)[:6]


def setup(source,target):
    source=Path(source);target=Path(target)
    if target.exists():
        if (target/'latest.pt').is_file() and (target/'attack_provenance.json').is_file():return
        raise FileExistsError(f'{target} exists without a valid offense checkpoint; preserved.')
    from . import _attention_native as native
    if getattr(native,'reward_version',0)<3:raise RuntimeError('Close Python windows, extract the OFFENSE update and restart; native reward version 3 is required.')
    with lock_run(source):
        original=source/'latest.pt'
        if not original.is_file():raise FileNotFoundError(f'{original}: train skills01 first; no replacement model was selected.')
        saved=load(original,torch.device('cpu'));cfg=saved['config']
        if cfg['team_size']!=1:raise ValueError('Offense continuation is currently 1v1 only')
        if cfg['rewards'].get('profile')!='skills_v1':raise ValueError('This continuation requires a trained skills_v1 parent')
        before=sha(original);weights=model_hash(saved['model']);target.parent.mkdir(parents=True,exist_ok=True)
        stage=Path(tempfile.mkdtemp(prefix='.offense_',dir=target.parent))
        try:
            payload=copy.deepcopy(saved);new=payload['config'];start=saved['learning_transitions']
            new['version']='attentionforge-attack-v1';new['rewards'].update(profile='attack_v1',goal=20.,approach=.3,touch=.1,control_progress=0.)
            new['ppo']['entropy']=max(.008,new['ppo']['entropy'])
            new['skills']['auxiliary_initial']=0. # the early driving tutor conflicts with jump/flip rehearsal
            new['attack']={'version':1,'start_learning_transitions':start,'validation_every':500000,'match_every':2000000,'games_per_context':40,'match_seconds':60,'rehearsal':{'version':1,'weight':.02,'decay_new_transitions':5000000,'seed':983717},'training_reset_mix':{'all_five_kickoffs':.3,'finishing':.35,'jump_touch':.2,'recovery':.15}}
            payload['wandb_id']=None;payload['recovery_attempts']=0
            for name in payload.get('history',[]):
                if Path(name).name!=name:raise ValueError('Unexpected history checkpoint name')
                (stage/'history').mkdir(exist_ok=True);shutil.copy2(source/'history'/name,stage/'history'/name)
            if (source/'baseline.pt').is_file():shutil.copy2(source/'baseline.pt',stage/'baseline.pt')
            shutil.copy2(original,stage/'reward_parent.pt');save_checkpoint(stage/'latest.pt',payload);save_checkpoint(stage/'best_contact.pt',payload)
            atomic_json(stage/'config.json',new)
            record={'created_utc':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),'parent':str(original.resolve()),'parent_sha256':before,'parent_actor_state_sha256':weights,'starting_learning_transitions':start,'old_rewards':cfg['rewards'],'new_rewards':new['rewards'],'initial_actor_unchanged':model_hash(payload['model'])==weights,'optimizer':'Adam moments/step values/LR inherited unchanged','config_changes':['new reward profile','new reset mixture','entropy floor 0.008','disable early driving tutor','temporary verified mechanics rehearsal','scenario-stratified diagnostics'],'source_hashes':source_hashes()}
            atomic_json(stage/'attack_provenance.json',record);atomic_json(stage/'provenance.json',record)
            assert sha(original)==before
            os.rename(stage,target)
        finally:
            if stage.exists():shutil.rmtree(stage)
    print('OFFENSE_FORK_READY:',target,'; trained actor unchanged; inherited transitions:',start,flush=True)


def model_pair(folder,opponent=None):
    folder=Path(folder)
    def snapshot(path):
        data=Path(path).read_bytes();out=torch.load(io.BytesIO(data),map_location='cpu',weights_only=False);out['_loaded_sha256']=hashlib.sha256(data).hexdigest();return out
    candidate=snapshot(folder/'latest.pt');baseline=snapshot(opponent or folder/'reward_parent.pt')
    provenance=folder/'attack_provenance.json'
    if opponent is None and provenance.exists() and baseline['_loaded_sha256']!=json.loads(provenance.read_text())['parent_sha256']:raise ValueError('Pinned parent changed; refusing to compare a different actor')
    cfg=copy.deepcopy(candidate['config'])
    if any(cfg[k]!=baseline['config'][k] for k in ('network','team_size','tick_skip','action_delay')):raise ValueError('Model contracts differ')
    dev=device(cfg);torch.set_num_threads(cfg['torch_threads']);models=[]
    for data in (candidate,baseline):
        m=ActorCritic(**cfg['network']).to(dev).eval();m.load_state_dict(data['model']);models.append(m)
    # Reward/curriculum are neutral for both actors during evaluation.
    cfg['rewards']={'profile':'rlgym_simple_v1','goal':0.,'approach':0.,'touch':0.,'control_progress':0.}
    return models,cfg,candidate,baseline


def evaluate(folder,games_per_context=40,seconds=60,seed=None,contexts=MATCH_CONTEXTS):
    folder=Path(folder)
    if games_per_context<4 or games_per_context%2:raise ValueError('Use an even number of games per context, at least four')
    if seconds<1 or seconds>600:raise ValueError('Duration must be 1..600 seconds')
    if not contexts or len(set(contexts))!=len(contexts) or any(x not in SCENES for x in contexts):raise ValueError('Unknown/repeated evaluation context')
    models,cfg,candidate,baseline=model_pair(folder);
    if cfg['team_size']!=1:raise ValueError('Scenario panels currently support 1v1 only')
    cfg['episode_seconds']=seconds+10;cfg['no_touch_seconds']=seconds+10
    master=int(seed if seed is not None else 0xC0000000+secrets.randbelow(0x10000000));dev=next(models[0].parameters()).device
    rows=[];summary={};begin_wall=time.perf_counter()
    print('SCENARIO_PANEL_START:',len(contexts)*games_per_context,'games;',seconds,'seconds; fixed paired contexts, equal kickoff boost.',flush=True)
    with torch.no_grad():
        for ci,context in enumerate(contexts):
            print('SCENARIO_RUNNING:',context,flush=True)
            group=[];pairs=games_per_context//2
            for first in range(0,pairs,32):
                n=min(32,pairs-first);base=(master+ci*1000003+7919*first)%(1<<32)
                for color in (0,1):
                    env=batch(cfg,n=n,seed=base,kickoffs=True);env.scenario(SCENES[context]);loc=env.pad_locations();raw=env.observe();ticks=np.zeros(n,np.int64);gf=ticks.copy();ga=ticks.copy()
                    initial=raw['world'].copy();ages=np.zeros(n,np.int64);ct=np.zeros(n,np.int64);otouch=np.zeros(n,np.int64);events=[[] for _ in range(n)]
                    while np.any(ticks<seconds*120):
                        active=ticks<seconds*120;ob,lm=encode(raw['world'],raw['pads'],loc);x=torch.as_tensor(ob.reshape(-1,43,40),device=dev);l=torch.as_tensor(lm.reshape(-1,90),device=dev)
                        ac=models[0](x,l)[0].argmax(-1).cpu().numpy().reshape(n,2);bc=models[1](x,l)[0].argmax(-1).cpu().numpy().reshape(n,2)
                        ac[:,1-color]=bc[:,1-color]
                        raw=env.step(ac);g=raw['info'][:,0]*(1 if color==0 else -1)
                        used=raw['info'][:,7].astype(np.int64);ages+=used*active
                        ct+=((raw['info'][:,1+color]>0)&active);otouch+=((raw['info'][:,2-color]>0)&active)
                        for j in np.flatnonzero(active&(g!=0)):
                            events[j].append({'for_candidate':bool(g[j]>0),'seconds_since_reset':float(ages[j]/120),'candidate_touch_decisions':int(ct[j]),'opponent_touch_decisions':int(otouch[j])})
                            ages[j]=ct[j]=otouch[j]=0
                        gf+=active&(g>0);ga+=active&(g<0);ticks+=used*active
                    for j in range(n):
                        score=1. if gf[j]>ga[j] else 0. if gf[j]<ga[j] else .5
                        group.append({'context':context,'seed':int((base+7919*j)%(1<<32)),'color':color,'goals_for':int(gf[j]),'goals_against':int(ga[j]),'score':score,'initial_ball':initial[j,0,:6].tolist(),'initial_blue':initial[j,1,:3].tolist(),'initial_orange':initial[j,2,:3].tolist(),'initial_boost':[float(initial[j,1,15]),float(initial[j,2,15])],'ticks':int(ticks[j]),'goal_events':events[j]})
            summary[context]=statistics(group);rows.extend(group)
            print('SCENARIO_EVAL:',context,summary[context],flush=True)
    macro=float(np.mean([x['score_rate'] for x in summary.values()]));overall=statistics(rows)
    result={'contract':'attentionforge-scenario-panels-v1','candidate_sha256':candidate['_loaded_sha256'],'baseline_sha256':baseline['_loaded_sha256'],'candidate_actor_state_sha256':model_hash(candidate['model']),'candidate_transitions':candidate['learning_transitions'],'baseline_transitions':baseline['learning_transitions'],'master_seed':master,'seed_namespace':'reserved evaluation band' if seed is None else 'explicit reproducibility/test seed','games_per_context':games_per_context,'seconds':seconds,'contexts':summary,'macro_score_rate':macro,'overall':overall,'games':rows,'wall_seconds':time.perf_counter()-begin_wall,'rules':'Fixed context after each goal, both colors on matched initial seeds, equal boost at every kickoff, no overtime. Open-play panel contains no kickoff resets. These are scenario diagnostics, not a regulation tournament or proof of general strength.','promotion':'none; evaluation-based model pins are unverified candidates.'}
    non_center=[v['score_rate'] for k,v in summary.items() if k!='center']
    result['non_center_macro_score']=float(np.mean(non_center)) if non_center else None
    result['open_play_score']=summary.get('open_play',{}).get('score_rate')
    result['center_only_advantage_warning']=summary.get('center',{}).get('score_rate',0)>.5 and bool(non_center) and max(non_center)<=.5
    print('SCORING_PANEL_SUMMARY: open play',result['open_play_score'],'; non-center mean',result['non_center_macro_score'],'; center-only warning',result['center_only_advantage_warning'],flush=True)
    path=folder/f'match_eval_{time.time_ns()}.json';atomic_json(path,result);pin_candidate(folder,result,path,payload=candidate)
    print('SCENARIO_PANEL_SAVED:',path,flush=True);return result


def statistics(rows):
    blocks={}
    for row in rows:blocks.setdefault((row['context'],row['seed']),[]).append(row['score'])
    means=np.asarray([np.mean(v) for v in blocks.values()]);mean=float(means.mean());radius=math.sqrt(math.log(40)/(2*len(means)))
    return {'games':len(rows),'wins':sum(x['score']==1 for x in rows),'draws':sum(x['score']==.5 for x in rows),'losses':sum(x['score']==0 for x in rows),'score_rate':mean,'score_interval_95':[max(0.,mean-radius),min(1.,mean+radius)],'goals_for':sum(x['goals_for'] for x in rows),'goals_against':sum(x['goals_against'] for x in rows),'early_goals_for':sum(e['for_candidate'] and e['seconds_since_reset']<=5 for x in rows for e in x.get('goal_events',[])),'later_goals_for':sum(e['for_candidate'] and e['seconds_since_reset']>5 for x in rows for e in x.get('goal_events',[])),'interval_method':'Bounded Hoeffding interval on paired-color blocks; exploratory repeated panels are not multiplicity-adjusted.'}


def pin_candidate(folder,result,evaluation_path,payload=None):
    path=folder/'match_best.json';best=json.loads(path.read_text()) if path.exists() else {}
    scores={k:v['score_rate'] for k,v in result['contexts'].items()};scores['macro']=result['macro_score_rate']
    improved=[k for k,v in scores.items() if k not in best or v>best[k]['score_rate']]
    if not improved:return
    payload=payload if payload is not None else load(folder/'latest.pt',torch.device('cpu'));actor=model_hash(payload['model']);
    if actor!=result['candidate_actor_state_sha256']:raise ValueError('Refusing to pin a different actor from the one evaluated')
    pins=folder/'match_pins';pins.mkdir(exist_ok=True);target=pins/(actor+'.pt')
    if target.exists() and model_hash(load(target,torch.device('cpu'))['model'])!=actor:raise ValueError('Existing immutable pin has changed')
    if not target.exists():save_checkpoint(target,{'model':payload['model'],'config':payload['config'],'learning_transitions':payload['learning_transitions'],'pin_kind':'actor only; not a full training resume','source_full_checkpoint_sha256':result['candidate_sha256']})
    for k in improved:best[k]={'score_rate':scores[k],'actor_path':str(target.relative_to(folder)),'actor_sha256':sha(target),'actor_state_sha256':actor,'learning_transitions':payload['learning_transitions'],'evaluation':evaluation_path.name,'status':'unverified scenario-panel candidate'}
    atomic_json(path,best);atomic_json(folder/'match_pins_inventory.json',{p.name:{'bytes':p.stat().st_size,'sha256':sha(p)} for p in pins.glob('*.pt')})


def monitor(model,cfg,folder,count):
    from .skills import drills
    model.eval();quality=drills(model,cfg,seed=880001,n=16)
    score=min(x[k] for x in quality.values() for k in ('blue_contact_fraction','orange_contact_fraction'))
    r={'learning_transitions':count,'contact_quality':quality,'minimum_contact_fraction':score,'purpose':'Contact retention gate; scenario panels measure scoring separately'}
    with (folder/'attack_validation.jsonl').open('a') as f:f.write(json.dumps(r)+'\n')
    bestfile=folder/'best_contact.json';best=json.loads(bestfile.read_text()) if bestfile.exists() else {'minimum_contact_fraction':score}
    if not bestfile.exists() or score>best['minimum_contact_fraction']:
        shutil.copy2(folder/'latest.pt',folder/'best_contact.pt');atomic_json(bestfile,r)
    print('ATTACK_CONTACT_VALIDATION:',r,flush=True)
    okay=score>=max(.3,best['minimum_contact_fraction']*.6)
    if not okay:atomic_json(folder/'skill_regression.json',r)
    start=cfg['attack']['start_learning_transitions'];elapsed=count-start;period=cfg['attack']['match_every']
    if okay and elapsed//period>(elapsed-cfg['attack']['validation_every'])//period:
        panel=evaluate(folder,cfg['attack']['games_per_context'],cfg['attack']['match_seconds'])
        # Preserve promising actors; do not make noisy automatic champion claims.
        bad=panel['macro_score_rate']<.4 or panel['contexts']['open_play']['score_rate']<.25
        history=folder/'match_guard.json';last=json.loads(history.read_text()) if history.exists() else {'bad_panels':0}
        last={'bad_panels':last['bad_panels']+1 if bad else 0,'last_macro_score':panel['macro_score_rate']};atomic_json(history,last)
        if last['bad_panels']>=2:
            atomic_json(folder/'match_regression.json',last);print('MATCH_REGRESSION_PAUSE: two poor scenario panels; parent and evaluation pins preserved.',flush=True);okay=False
    probe=skill_probes(model,cfg,n=16)
    probe['learning_transitions']=count
    with (folder/'offense_skill_probes.jsonl').open('a') as f:f.write(json.dumps(probe)+'\n')
    print('OFFENSE_SKILL_PROBES:',json.dumps(probe),flush=True)
    model.train();return okay


def menu(run='attack01'):
    folder=ROOT/'runs'/run
    while True:
        print('\nOFFENSE — '+run+'\n1 Fork skills01 once / resume offense training\n2 Watch open play vs pinned parent\n3 Watch all kickoff variants vs parent\n4 Report ZIP\n5 Export latest PT/CFG + LT/TOML\n6 Balanced scenario evaluation\n7 Pause\n8 Watch pinned open-play candidate\n9 Export pinned open-play candidate\n10 Measure shots / jumps / recovery\n0 Exit',flush=True)
        try:
            x=input('Choose: ').strip()
            if x=='0':return
            if x=='1':
                setup(ROOT/'runs/skills01',folder)
                from .skills import run as train_run
                train_run(folder)
            elif x in ('2','3'):
                from .cli import watch
                watch(config(),folder,opponent=folder/'reward_parent.pt',scenario=5 if x=='2' else -2)
            elif x in ('8','9'):
                pin=selected_pin(folder,'open_play')
                if x=='8':
                    from .cli import watch
                    watch(config(),folder,opponent=folder/'reward_parent.pt',scenario=5,checkpoint=pin)
                else:
                    from .cli import export
                    export(folder,checkpoint=pin)
            elif x=='10':
                from .cli import policy
                m,s=policy(folder,device(config(folder/'config.json')));p=skill_probes(m,s['config'],seed=secrets.randbelow(1000000000)+2000000000,n=64);atomic_json(folder/f'offense_probe_{time.time_ns()}.json',p);print(json.dumps(p,indent=2))
            elif x=='4':
                from .cli import report
                report(folder)
            elif x=='5':
                from .cli import export
                export(folder)
            elif x=='6':evaluate(folder,games_per_context=100,seconds=90)
            elif x=='7':
                if not folder.exists():raise FileNotFoundError(folder)
                (folder/'STOP').write_text('pause\n');print('Wait for PAUSED_AND_SAVED in trainer console.')
        except KeyboardInterrupt:print('Interrupted; completed checkpoints preserved.')
        except Exception as ex:print(type(ex).__name__+': '+str(ex)+'\nOperation failed; existing runs were preserved.',flush=True)


def selected_pin(folder,key):
    folder=Path(folder);path=folder/'match_best.json'
    if not path.exists():raise FileNotFoundError('No scenario candidate pinned yet. Run the balanced scenario evaluation first.')
    item=json.loads(path.read_text())[key];actor=folder/item['actor_path']
    if not actor.is_file() or sha(actor)!=item['actor_sha256']:raise FileNotFoundError('Exact pinned actor is missing or changed; no other bot was substituted.')
    print('PINNED_CANDIDATE:',key,item['learning_transitions'],'transitions; exploratory score',item['score_rate'],'; unverified.',flush=True)
    return actor


def skill_probes(model,cfg,seed=8847219,n=32,seconds=5):
    """Isolated execution drills, with a parked other car; not match strength."""
    cfg=copy.deepcopy(cfg);cfg['episode_seconds']=seconds+5;cfg['no_touch_seconds']=seconds+5
    dev=next(model.parameters()).device;was_training=model.training;model.eval();result={}
    try:
        for ti,task in enumerate(('finishing','jump_touch','recovery','forward_flip')):
            scene=8 if task=='forward_flip' else SCENES[task]
            env=batch(cfg,n=n,seed=seed+ti*100003,kickoffs=True);env.scenario(scene);w=env.observe()['world'];actors=np.arange(n)%2
            if task=='finishing':actors=(w[:,0,1]<0).astype(int)
            for j in range(n):
                world=w[j].copy();a=int(actors[j])+1;other=3-a
                if task=='forward_flip':world[a,9:12]*=-1
                world[other,:3]=[3500,-4500 if a==1 else 4500,17];world[other,3:9]=0
                env.set_ground(j,world)
            raw=env.observe();loc=env.pad_locations();alive=np.ones(n,bool);goal=np.zeros(n,bool);touch=goal.copy();air=goal.copy();recovery=goal.copy();flip=goal.copy();jump=goal.copy();back=0.;observations=0
            with torch.no_grad():
                for k in range(int(seconds*120/cfg['tick_skip'])):
                    ob,lm=encode(raw['world'],raw['pads'],loc);ix=np.arange(n);x=ob[ix,actors];l=lm[ix,actors]
                    ac=np.full((n,2),8,np.int64);chosen=model(torch.as_tensor(x,device=dev),torch.as_tensor(l,device=dev))[0].argmax(-1).cpu().numpy();ac[ix,actors]=chosen
                    jump|=alive&(ACTIONS[chosen,5]>0)
                    raw=env.step(ac);g=raw['info'][:,0]*np.where(actors==0,1,-1)
                    goal|=alive&(g>0);touch|=alive&(raw['info'][ix,1+actors]>0);air|=alive&(raw['attack_info'][:,4]>0);recovery|=alive&(raw['attack_info'][:,3]>0);flip|=alive&(raw['attack_info'][:,2]>0)
                    cars=raw['final_world'][ix,1+actors];back+=float(((np.sum(cars[:,3:6]*cars[:,9:12],axis=-1)<-300)&alive).sum());observations+=int(alive.sum());alive&=~(raw['terminated']|raw['truncated'])
            result[task]={'trials':n,'goal_fraction':float(goal.mean()),'contact_fraction':float(touch.mean()),'air_contact_fraction':float(air.mean()),'useful_flip_fraction':float(flip.mean()),'backflip_recovery_fraction':float(recovery.mean()),'jump_used_fraction':float(jump.mean()),'backward_fraction':back/max(1,observations)}
    finally:model.train(was_training)
    return {'seed':seed,'seconds':seconds,'tasks':result,'scope':'Isolated physical skill validation with parked opposition. Goals are actual RocketSim goals; maneuver outcomes are detector proxies, not rank or match strength.'}
