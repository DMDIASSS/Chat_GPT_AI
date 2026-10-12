"""Slater v0.4.1 native RocketSim worker. Not a standalone nightly process.

All six opponents get Nexto's simulator-approximated scripted kickoff.
Student uses ONLY the learned 90-action policy, never the hardcoded kickoff.
"""
from __future__ import annotations
import argparse
import json
import random
import os
from pathlib import Path

import numpy as np
import torch

import slater_cycle9_native_ppo_v025 as base
import slater_nexto_kickoff_v037a as old
import slater_v040_multirival as v040
from afk_team_research import TeamObserver
from slater_v041_core import RIVAL_NAMES, sha256, read_json, training_mode_index

POOL_MODES=tuple('p_'+n for n in RIVAL_NAMES)+('p_leader',)


def model_from_checkpoint(checkpoint: Path, vendor: Path, *, nexto=False):
    """Load a real RLBot-exported nexto-model.pt OR full PPO .pt checkpoint.

    Exact TorchScript forward signature must match legacy Nexto (q,kv,mask)
    and return 90 logits. Fail closed for incompatible architectures.
    """
    checkpoint=Path(checkpoint)
    try:
        actor=torch.jit.load(str(checkpoint),map_location='cpu')
    except (RuntimeError, ValueError):
        try:
            doc=torch.load(str(checkpoint),map_location='cpu',weights_only=True)
        except Exception as e:
            raise ValueError(f'Cannot load PPO or TorchScript model at {checkpoint}: {e}') from e
        weights=doc.get('actor') if isinstance(doc,dict) else None
        if not isinstance(weights,dict):
            raise ValueError(f'{checkpoint} does not contain a native Nexto actor state_dict')
        actor=torch.jit.load(str(vendor),map_location='cpu')
        actor.load_state_dict(weights,strict=True)
    actor.eval()
    for param in actor.parameters():param.requires_grad_(False)
    with torch.no_grad():
        try:
            x=(torch.zeros((1,1,32)),torch.zeros((1,37,24)),torch.zeros((1,37)))
            logits=base.logits_of(actor,x)
            if tuple(logits.shape)!=(1,90) or not torch.isfinite(logits).all():
                raise ValueError('Bad Nexto action logits shape or values')
        except Exception as e:
            raise ValueError(f'Policy {checkpoint} incompatible with native Nexto observation/action encoding: {e}') from e
    return actor

def load_pool(root, manifest, *, leader_path=None):
    vendor=root/'vendor/nexto/nexto-model.pt'
    pools={}
    for name in RIVAL_NAMES:
        item=manifest[name]
        p=Path(item['path'])
        if sha256(p)!=item['sha256']:
            raise RuntimeError(f'Opponent changed on disk during overnight run: {name}')
        pools['p_'+name]=model_from_checkpoint(p,vendor,nexto=name=='nexto')
    if leader_path is not None:
        leader_path=Path(leader_path)
        pools['p_leader']=model_from_checkpoint(leader_path,vendor)
    return pools


class ScriptedPoolEnv(v040.RivalEnv):
    VALID_MODES=tuple(v040.RivalEnv.VALID_MODES)+POOL_MODES

    def __init__(self, actions, observer, originals, frozen_u60, max_steps, device,
                 pool, modes, fixed_side=None):
        if any(m not in pool for m in modes):
            raise ValueError('Unknown scripted pool opponent')
        self.pool=pool
        self._mode_offset=None
        super().__init__(actions, observer, originals, frozen_u60, max_steps,
                         device=device, modes=modes, fixed_side=fixed_side)

    def reset(self, seed):
        obs=super().reset(seed)
        # The parent rotates modes after pairs of episodes. Small PPO trials may
        # never meet half the pool. Rotate EACH episode with a seeded offset,
        # while preserving the parent Blue/Orange side scheduling.
        if self._mode_offset is None:
            self._mode_offset=int(seed) % len(self.modes)
        idx=training_mode_index(len(self.modes),self.episode_count,self._mode_offset)
        self.current_opponent=self.modes[idx]
        self.opponent=self.pool[self.current_opponent]
        return obs

    def _opponent_commands(self, oid):
        active=(not self.kickoff_ball_touched
                and old.is_stationary_center(float(self.state.ball.position[1]))
                and self.t * base.ACTION_REPEAT < old.SCRIPT_TICKS)
        if active:
            self.script_action_steps += 1
            self.last_control_source='scripted_rival'
            return old.grouped_control(self.t*base.ACTION_REPEAT, enabled=True, active=True,
                                       nn_control=np.zeros(8,dtype=np.float32),
                                       action_repeat=base.ACTION_REPEAT)
        obs=base.read_obs(self.state, self.previous, self.observer, oid)
        with torch.no_grad():
            index=int(base.logits_of(self.opponent,base.to_tensors(obs, self.device)).argmax(-1).item())
        control=np.asarray(self.actions[index],dtype=np.float32)
        self.neural_action_steps+=1
        self.last_control_source='neural_rival'
        return np.repeat(control[None],base.ACTION_REPEAT,axis=0)


def run_episode(actor, mode, side, seed, max_steps, actions, original, nexto, u60, pool):
    env=ScriptedPoolEnv(actions, TeamObserver(), (original,nexto),u60,
                        max_steps,'cpu',pool=pool,modes=(mode,),fixed_side=side)
    try:
        obs=env.reset(seed)
        while True:
            with torch.no_grad():
                act=int(base.logits_of(actor,base.to_tensors(obs)).argmax(-1).item())
            obs, _, done, info=env.step(act)
            if done:
                return {'outcome':int(info['outcome']), 'timeout':bool(info['timeout']),
                        'steps':info['steps'],'scripted_steps':info['script_action_steps'],
                        'student_touches':info['student_touches'],
                        'opponent_touches':info['opponent_touches']}
    finally:env.close()


def paired_eval(root, manifest, candidate_path, leader_path, *, seeds, seed_base,
                episode_steps, modes=None):
    from slater_v041_core import paired_scores
    torch.set_num_threads(2)
    actor, original, nexto, actions, _, _=old.load_protected(root, Path(candidate_path).resolve())
    u60=v040.load_original_v60_anchor(
        root,actor,checkpoint_arg='data/isolated/slater_v027_campaign01_u0060.pt',
        source_sha=old.previous_train.CYCLE9_SHA if hasattr(old.previous_train,'CYCLE9_SHA') else __import__('slater_research.checkpoint',fromlist=['CYCLE9_SHA']).CYCLE9_SHA,
        nexto_sha=old.EXPECTED_NEXTO_SHA)[0]
    pool=load_pool(root,manifest,leader_path=leader_path)
    leader=model_from_checkpoint(Path(leader_path),root/'vendor/nexto/nexto-model.pt')
    use_modes=modes or tuple('p_'+name for name in RIVAL_NAMES)
    rows=[]
    for j in range(seeds):
        seed=int(seed_base+j*997)
        for side in ('blue','orange'):
            for mode in use_modes:
                c=run_episode(actor,mode,side,seed,episode_steps,actions,original,nexto,u60,pool)
                b=run_episode(leader,mode,side,seed,episode_steps,actions,original,nexto,u60,pool)
                rows.append({'rival':mode[2:] if mode.startswith('p_') else mode,
                             'side':side,'seed':seed,
                             'candidate_outcome':c['outcome'],
                             'leader_outcome':b['outcome'],
                             'candidate_steps':c['steps'],'leader_steps':b['steps'],
                             'candidate_timeout':c['timeout'],'leader_timeout':b['timeout']})
    return {'summary':paired_scores(rows),'records':rows,'seed_base':seed_base,
            'seeds':seeds,'episode_steps':episode_steps,
            'note':'First-goal RocketSim comparisons, not five-minute RLBot matches.'}


def train_trial(root, args):
    torch.set_num_threads(2)
    torch.manual_seed(args.seed);np.random.seed(args.seed);random.seed(args.seed)
    checkpoint=(root/args.source).resolve()
    if not checkpoint.is_relative_to((root/'data/isolated').resolve()):
        raise ValueError('Training source must be within isolated data')
    manifest=read_json(root/args.manifest)
    if not manifest:raise ValueError('Missing opponent manifest')
    if old.control_hash()!=old.EXPECTED_SCRIPT_SHA256:raise RuntimeError('Kickoff script has changed')
    actor, original, nexto, actions,doc, provenance=old.load_protected(root,checkpoint)
    if not all(x in doc for x in ('critic','actor_optimizer','critic_optimizer')):
        raise ValueError('Full PPO checkpoint required. RLBot nexto-model.pt is an opponent only.')
    critic=base.ValueNet();critic.load_state_dict(doc['critic'])
    ao=torch.optim.Adam(actor.parameters(),lr=args.actor_lr)
    co=torch.optim.Adam(critic.parameters(),lr=1e-4)
    ao.load_state_dict(doc['actor_optimizer']);co.load_state_dict(doc['critic_optimizer'])
    for group in ao.param_groups:group['lr']=args.actor_lr
    for group in co.param_groups:group['lr']=1e-4
    from slater_research.checkpoint import CYCLE9_SHA
    anchor,anchor_sha=v040.load_original_v60_anchor(root,actor,
                   checkpoint_arg='data/isolated/slater_v027_campaign01_u0060.pt',
                   source_sha=CYCLE9_SHA,nexto_sha=old.EXPECTED_NEXTO_SHA)
    leader_path=(root/args.leader_checkpoint).resolve() if args.leader_checkpoint else None
    if leader_path is not None and not leader_path.is_relative_to((root/'data/isolated').resolve()):
        raise ValueError('Leader sparring model must be an isolated checkpoint')
    pool=load_pool(root,manifest,leader_path=leader_path)
    modes=tuple(pool)
    env=ScriptedPoolEnv(actions,TeamObserver(),(original,nexto),anchor,
            args.episode_steps,'cpu',pool=pool,modes=modes)
    output_dir=(root/args.output_dir).resolve()
    if not output_dir.is_relative_to((root/'data/isolated/v041_overnight').resolve()):
        raise ValueError('Output must stay inside data/isolated/v041_overnight')
    output_dir.mkdir(parents=True,exist_ok=True)
    source_sha=sha256(checkpoint)
    logs=[]
    try:
        episode_seed=args.seed+10000
        obs=env.reset(episode_seed)
        start_update=int(doc['global_updates'])
        for i in range(args.updates):
            rows,finished,obs,episode_seed,trunc=v040.collect_continuous(
                actor,critic,env,obs,episode_seed,args.rollout_steps)
            metric=base.update(actor,anchor,critic,ao,co,rows,args.epochs,
                      args.minibatch,args.teacher_weight,args.seed+i+1,'cpu')
            idx=start_update+i+1
            metric.update({'update':idx,'timeout_bootstraps':trunc,
                           'finished_episodes':len(finished),
                           'opponents_finished':[x['opponent'] for x in finished],
                           'wins':sum(x['outcome']==1 for x in finished),
                           'losses':sum(x['outcome']==-1 for x in finished),
                           'timeouts':sum(x['timeout'] for x in finished)})
            logs.append(metric)
            out=output_dir/f'{args.run}_u{idx:04d}.pt'
            report=out.with_suffix('.json')
            payload={'stage':'slater_v037','source_sha':CYCLE9_SHA,
                     'global_updates':idx,'actor':actor.state_dict(),
                     'critic':critic.state_dict(),
                     'actor_optimizer':ao.state_dict(),
                     'critic_optimizer':co.state_dict(),
                     'meta':{'nexto_sha':old.EXPECTED_NEXTO_SHA,
                             'origin_stage':'slater_v041','source_checkpoint_sha':source_sha,
                             'protected_v60_sha256':anchor_sha,
                             'teacher_weight':args.teacher_weight,
                             'opponents':list(modes)}}
            if out.exists():raise FileExistsError(f'Checkpoint overwrite refused: {out}')
            temp=out.with_suffix('.pt.incomplete')
            if temp.exists():temp.unlink()  # stale artifact from a dead worker; protected by parent process lock
            with temp.open('xb') as fh:
                torch.save(payload,fh);fh.flush();os.fsync(fh.fileno())
            os.replace(temp,out)
            old.report_create(str(report),root,{'stage':'slater_v041','update':idx,
                    'source_sha256':source_sha,'metrics':metric,
                    'scripted_kickoff_for':'all_opponents_only',
                    'student_has_scripted_kickoff':False})
            print('V041_UPDATE',json.dumps(metric,sort_keys=True),flush=True)
            print('V041_CHECKPOINT',str(out),flush=True)
    finally:env.close()
    if sha256(checkpoint)!=source_sha:
        raise RuntimeError('Source mutated during training')
    print('V041_TRAIN_SUCCESS', flush=True)


def cli(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',required=True)
    p.add_argument('--leader-checkpoint',help='Provisional current leader for additional scripted-kickoff self-play')
    p.add_argument('--manifest',required=True)
    p.add_argument('--run',required=True)
    p.add_argument('--output-dir',required=True)
    p.add_argument('--seed',type=int,required=True)
    p.add_argument('--updates',type=int,default=3)
    p.add_argument('--rollout-steps',type=int,default=512)
    p.add_argument('--episode-steps',type=int,default=300)
    p.add_argument('--actor-lr',type=float,default=2e-6)
    p.add_argument('--teacher-weight',type=float,default=.3)
    p.add_argument('--epochs',type=int,default=2)
    p.add_argument('--minibatch',type=int,default=128)
    a=p.parse_args(argv)
    if not (1<=a.updates<=12 and 128<=a.rollout_steps<=4096
            and 120<=a.episode_steps<=4500 and 1<=a.seed<2**31-10000
            and 1<=a.epochs<=8 and 16<=a.minibatch<=a.rollout_steps
            and 0<a.actor_lr<=1e-5 and .05<=a.teacher_weight<=1):
        p.error('Unsafe training configuration')
    root=Path.cwd().resolve()
    train_trial(root,a)

if __name__=='__main__':cli()
