"""Isolated attention continuation and matched checks across 1..3 players/side."""
from __future__ import annotations
import argparse
import json
import shutil
import time
from pathlib import Path
from importlib.metadata import version
import numpy as np
import torch
from slater_team_env import TeamEnv, FORMATS
from slater_team_eval import evaluate, EvaluationPaused
from slater_mechanics_env import collect_batched
from slater_mechanics_eval import load_actor
from slater_versatile_env import VersatileCritic
from slater_versatile_trainer import code_identity as shared_code
from slater_ppo import trust_region_update
from slater_v041_overnight import write_checkpoint
from slater_v041_core import atomic_json, read_json, sha256, process_lock

ROOT=Path(__file__).resolve().parent
BASE=ROOT/'data/isolated/team_campaigns'
DEFAULT_SOURCE=ROOT/'data/isolated/mechanics_curriculum/selected7_mechanics01/update_000180.pt'
CONFIG={'n_envs':8,'steps_per_env':128,'actor_lr':3e-6,'critic_lr':1e-4,'epochs':1,
        'minibatch':256,'target_kl':.005,'teacher_anchor':.1,'episode_seconds':12,
        'updates':40,'check_every':20,'screen_seconds':15,'screen_seeds':1,'seed':20261013}


def name_path(name):
    if not name or len(name)>48 or not name.replace('_','').replace('-','').isalnum():
        raise ValueError('Use a short letters/digits/_/- run name')
    return BASE/name


def code_identity():
    return {**shared_code(),**{n:sha256(ROOT/n) for n in
        ('slater_team_env.py','slater_team_eval.py','slater_team_campaign.py')}}


def snapshot(source,path):
    source=Path(source).resolve();path=Path(path)
    digest=sha256(source)
    if path.exists():
        if sha256(path)!=digest:raise ValueError('Saved private snapshot differs')
    else:
        path.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,path)
    if sha256(source)!=digest or sha256(path)!=digest:
        raise ValueError('Source changed during copying; choose a completed checkpoint')
    return {'path':str(path.resolve()),'source':str(source),'sha256':digest}


def current_pair(continuation='update180_continue02'):
    folder=ROOT/'data/isolated/versatile'/continuation
    progress=read_json(folder/'progress.json');protocol=read_json(folder/'protocol.json')
    if not progress or not protocol:raise FileNotFoundError('No saved continuation reports: '+str(folder))
    # Latest resume can contain a rollback. Inspect the trained candidate explicitly.
    candidate=Path(progress.get('candidate') or progress['latest'])
    expected=progress.get('candidate_sha') if progress.get('candidate') else progress['latest_sha']
    reference=Path(protocol['source']['path'])
    if sha256(candidate)!=expected or sha256(reference)!=protocol['source']['sha256']:
        raise ValueError('Saved candidate/source changed')
    return candidate,reference


def write_shortlist(folder,records,reference):
    rows=['# Team experiment candidates','',
          'All checkpoints are preserved. Scores are exploratory; the protected playing reference remains unchanged.','',
          '| Candidate | Evaluation report |','| --- | --- |']
    rows.extend(f"| `{r['checkpoint']}` | `{r['report']}` |" for r in records)
    rows.extend(['',f'Protected reference: `{reference}`',
        'These checks control one learner car with frozen supporting teammates. They do not certify an entire squad of the candidate or a competitive rank.'])
    (folder/'SHORTLIST.md').write_text('\n'.join(rows)+'\n',encoding='utf-8')


def check(candidate,reference,*,name=None,seeds=1,seconds=15,scripted=False):
    if not 1<=seeds<=32 or not 5<=seconds<=180:raise ValueError('Invalid matched check budget')
    folder=name_path(name or 'check_'+str(time.time_ns()));folder.mkdir(parents=True,exist_ok=True)
    c=snapshot(candidate,folder/'candidate.pt');r=snapshot(reference,folder/'reference.pt')
    torch.set_num_threads(2)
    ca=load_actor(ROOT,Path(c['path']));ra=load_actor(ROOT,Path(r['path']))
    nexto=ROOT/'vendor/nexto/nexto-model.pt';rivals={'nexto':load_actor(ROOT,nexto),'source':ra}
    identity={'candidate':c,'reference':r,'nexto_sha':sha256(nexto),'code':code_identity()}
    result=evaluate(ca,ra,rivals,out=folder/'comparison.json',identity=identity,formats=FORMATS,
        seeds=seeds,seconds=seconds,seed_base=1700000000,scripted_student=scripted)
    write_shortlist(folder,[{'checkpoint':str(candidate),'report':str(folder/'comparison.json')}],reference)
    print('TEAM_CHECK_REPORT',folder/'comparison.json',flush=True)
    return result


def train(name,source=None,config=None):
    folder=name_path(name);saved=read_json(folder/'protocol.json')
    cfg=saved['config'] if saved else {**CONFIG,**(config or {})}
    if not 2<=cfg['n_envs']<=16 or not 8<=cfg['steps_per_env']<=512 or not 1<=cfg['updates']<=1000:
        raise ValueError('Invalid finite training budget')
    if not 1<=cfg['check_every']<=cfg['updates'] or cfg['minibatch']>cfg['n_envs']*cfg['steps_per_env']:
        raise ValueError('Invalid update/check budget')
    source=Path(saved['source']['path'] if saved else source or DEFAULT_SOURCE).resolve()
    nexto=ROOT/'vendor/nexto/nexto-model.pt'
    protocol={'source':{'path':str(source),'sha256':sha256(source)},'config':cfg,
              'nexto_sha':sha256(nexto),'code':code_identity(),
              'runtime':{n:version(n) for n in ('torch','numpy','rlgym-rocket-league','rocketsim')}}
    if saved and protocol!=saved:raise ValueError('Experiment settings/code/source changed; use a new run name')
    folder.mkdir(parents=True,exist_ok=True);stop=folder/'pause.flag';torch.set_num_threads(2);torch.manual_seed(cfg['seed'])
    with process_lock(folder/'trainer.lock'):
        if not saved:atomic_json(folder/'protocol.json',protocol)
        actor=load_actor(ROOT,source,trainable=True);teacher=load_actor(ROOT,source)
        if not saved and not all(torch.equal(v,teacher.state_dict()[k]) for k,v in actor.state_dict().items()):
            raise ValueError('Initial actor differs from source')
        critic=VersatileCritic();ao=torch.optim.Adam(actor.parameters(),lr=cfg['actor_lr']);co=torch.optim.Adam(critic.parameters(),lr=cfg['critic_lr'])
        state=read_json(folder/'progress.json',{'updates':0,'decisions':0,'phase':'training','checks':[],
                    'source':str(source),'playing_model':str(source)})
        if saved:
            if sha256(state['latest'])!=state['latest_sha']:raise ValueError('Resume checkpoint changed')
            doc=torch.load(state['latest'],map_location='cpu',weights_only=True)
            actor.load_state_dict(doc['actor']);critic.load_state_dict(doc['critic']);ao.load_state_dict(doc['actor_optimizer']);co.load_state_dict(doc['critic_optimizer'])
        def commit(label):
            p=folder/(label+'.pt')
            write_checkpoint(p,{'actor':actor.state_dict(),'critic':critic.state_dict(),
                'actor_optimizer':ao.state_dict(),'critic_optimizer':co.state_dict(),'global_updates':state['updates'],
                'stage':'team_experiment','torch_rng':torch.get_rng_state(),'meta':{'source_sha256':protocol['source']['sha256']}})
            state.update(latest=str(p),latest_sha=sha256(p));atomic_json(folder/'progress.json',state)
            return p
        if not saved:commit('initial')
        stop.unlink(missing_ok=True)
        rivals={'nexto':load_actor(ROOT,nexto),'source':teacher}

        if saved and 'torch_rng' in doc:torch.set_rng_state(doc['torch_rng'])
        state['status']='RUNNING';atomic_json(folder/'progress.json',state);started=time.perf_counter()
        try:
            while state['updates']<cfg['updates'] or state['phase']=='evaluation':
                if stop.exists():raise EvaluationPaused()
                if shutil.disk_usage(folder).free<2*1024**3:raise RuntimeError('Less than 2 GiB free')
                if state['phase']=='training':
                    offset=state['updates']*cfg['n_envs'];envs=[]
                    for j in range(cfg['n_envs']):
                        ours,theirs=FORMATS[(offset+j)%len(FORMATS)]
                        task=('match','match','ground','match','defense','match','recovery','low_boost')[(j+state['updates']//4)%8]
                        envs.append(TeamEnv(rivals,our_size=ours,their_size=theirs,teammate_actor=teacher,
                            task_name=task,max_seconds=cfg['episode_seconds'],anchor_weight=cfg['teacher_anchor']))
                    try:
                        seeds=[cfg['seed']+state['updates']*100003+j*7919 for j in range(len(envs))]
                        obs=[e.reset(s) for e,s in zip(envs,seeds)]
                        t=time.perf_counter();rows,episodes,*_=collect_batched(actor,critic,envs,obs,seeds,cfg['steps_per_env']);collection=time.perf_counter()-t
                        t=time.perf_counter()
                        for g in ao.param_groups:g['lr']=cfg['actor_lr']
                        metrics=trust_region_update(actor,teacher,critic,ao,co,rows,cfg['epochs'],cfg['minibatch'],
                            cfg['teacher_anchor'],cfg['seed']+state['updates'],target_kl=cfg['target_kl'])
                        optimization=time.perf_counter()-t
                        metrics.update(formats=[e.format for e in envs],tasks=[e.task_name for e in envs],
                            collection_seconds=collection,optimization_seconds=optimization,
                            learner_decisions_per_second=len(rows['action'])/(collection+optimization),
                            physics_ticks_per_second=sum(e.total_ticks for e in envs)/collection,
                            episode_outcomes=episodes,human_replay_gradients=False,learner_scripted_kickoff=False)
                    finally:
                        for e in envs:e.close()
                    state['updates']+=1;state['decisions']+=len(rows['action'])
                    if state['updates']%cfg['check_every']==0 or state['updates']==cfg['updates']:state['phase']='evaluation'
                    checkpoint=commit(f"update_{state['updates']:06d}")
                    atomic_json(checkpoint.with_suffix('.json'),metrics)
                    print('TEAM_UPDATE',state['updates'],json.dumps(metrics),flush=True)
                if state['phase']=='evaluation':
                    candidate=Path(state['latest']);out=folder/'evaluations'/f"update_{state['updates']:06d}.json"
                    identity={'candidate':{'path':str(candidate),'sha256':sha256(candidate)},'reference':protocol['source'],
                        'nexto':{'path':str(nexto),'sha256':protocol['nexto_sha']},'code':protocol['code']}
                    evaluate(load_actor(ROOT,candidate),teacher,rivals,out=out,identity=identity,formats=FORMATS,
                        seeds=cfg['screen_seeds'],seconds=cfg['screen_seconds'],seed_base=1800000000+state['updates']*1000,
                        scripted_student=False,pause_path=stop)
                    state['checks'].append({'checkpoint':str(candidate),'report':str(out)});state['phase']='training'
                    atomic_json(folder/'progress.json',state);write_shortlist(folder,state['checks'],source)
            state['status']='FINITE_EXPERIMENT_COMPLETE';atomic_json(folder/'progress.json',state)
        except EvaluationPaused:
            state['status']='PAUSED';atomic_json(folder/'progress.json',state);print('TEAM_PAUSED: saved checkpoints; same launcher resumes.',flush=True)
        finally:
            if sha256(source)!=protocol['source']['sha256']:raise RuntimeError('Protected source changed')
            atomic_json(folder/'session_summary.json',{'seconds':time.perf_counter()-started,'updates':state['updates'],'status':state.get('status')})
    print('TEAM_EXPERIMENT_REPORT',folder/'SHORTLIST.md',flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=('check-current','check','train','pause','status'))
    p.add_argument('--run');p.add_argument('--source',type=Path);p.add_argument('--candidate',type=Path)
    p.add_argument('--continuation',default='update180_continue02');p.add_argument('--seeds',type=int,default=1)
    p.add_argument('--seconds',type=int,default=15);p.add_argument('--scripted-student',action='store_true');p.add_argument('--config',type=Path)
    a=p.parse_args()
    if a.command in ('pause','status'):
        f=name_path(a.run or 'update180_teams01')
        if a.command=='pause':
            if not (f/'progress.json').is_file():raise FileNotFoundError('No started team experiment')
            (f/'pause.flag').touch();print('Pause requested; wait for TEAM_PAUSED.');return
        print(json.dumps(read_json(f/'progress.json',{}),indent=2));return
    if a.command in ('check','check-current'):
        c,r=current_pair(a.continuation) if a.command=='check-current' else (a.candidate,a.source or DEFAULT_SOURCE)
        if not c:raise ValueError('--candidate is required')
        check(c,r,name=a.run,seeds=a.seeds,seconds=a.seconds,scripted=a.scripted_student);return
    train(a.run or 'update180_teams01',a.source,read_json(a.config) if a.config else None)

if __name__=='__main__':main()
