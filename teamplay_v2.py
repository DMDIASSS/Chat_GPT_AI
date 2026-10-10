"""Experimental, isolated Cycle9 2v2 shared-policy PPO training vs 2 frozen Nextos.

Uses existing Chat_GPT_AI afk_team_research and native_nexto modules. It never
changes original checkpoints, never updates RLBot exports, and never auto-promotes.

The 2 teammates BOTH use the SAME neural network; no passive role-controller.
Reward terms are deliberately small heuristics, not proof of good rotations.
"""
from __future__ import annotations

import argparse
import contextlib
import copy
import hashlib
import json
import math
import os
import random
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F
from torch.distributions import Categorical

from afk_team_research import (TeamMatch, TeamObserver, TeamCritic, action, tensors,
                               load_actor, sha)
from auto_league import atomic_json
from native_nexto import actor_logits, discounted_gae
from nexto_teacher import NextoTeacher

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'data' / 'autoleague' / 'backups' / '20261008T224518_775472Z_cycle0009_steps000008192_candidate.pt'
SOURCE_HASH = '50f34d4a3723bc2849c97200e8e42969e0cc1d82328473b017505994be1966d2'
DEFAULT_RUN = ROOT / 'data' / 'teamplay_v2' / 'cycle9_shared_2v2'


def vec(x):
    return np.asarray(x, dtype=np.float64).reshape(3)


def eta_to_ball(car, ball):
    """Approximate arrival score in seconds. Used ONLY to shape rewards."""
    pos = vec(car.physics.position)
    velocity = vec(car.physics.linear_velocity)
    delta = ball - pos
    distance = float(np.linalg.norm(delta))
    if distance < 1: return 0.0
    closing = float(np.dot(velocity, delta / distance))
    reach_speed = max(450.0, min(2200.0, 1120.0 + .55 * closing + 3.0 * float(car.boost_amount)))
    return distance / reach_speed


def primary_for_state(state, ids, previous=None):
    ball = vec(state.ball.position)
    ranks = [(eta_to_ball(state.cars[aid], ball), str(aid), aid) for aid in ids]
    ranks.sort()
    if previous in ids:
        old = next(v for v in ranks if v[2] == previous)
        if old[0] <= ranks[0][0] + .18: return previous
    return ranks[0][2]


def support_target(state, orange, first_id):
    """Dynamic SECOND-MAN position, not a parking spot; advance with the play."""
    ball = vec(state.ball.position)
    first = vec(state.cars[first_id].physics.position)
    attack = -1.0 if orange else 1.0
    # Approximately 1050 behind the ball, rotated laterally to cover rebounds.
    # Near our goal don't sit on the goal line: use an inside backpost angle.
    y = float(np.clip(ball[1] - attack * 1100.0, -4380.0, 4380.0))
    x = float(np.clip(.42 * ball[0] - .22 * first[0], -2050.0, 2050.0))
    return np.array([x, y, 17.0], dtype=np.float64)


def shaping(pre_pos, pre_target, post_state, our_ids, orange, primary):
    """Small learning signals. Never override the neural network's controller."""
    our_ids = list(our_ids)
    if len(our_ids) != 2: raise ValueError('This curriculum requires exactly two learners')
    secondary = next(i for i in our_ids if i != primary)
    after_ball = vec(post_state.ball.position)
    target = pre_target
    # Small incremental progress toward useful support, not a static reward for staying there.
    before = np.linalg.norm(pre_pos[secondary] - target)
    after = np.linalg.norm(vec(post_state.cars[secondary].physics.position) - target)
    support_delta = float(np.clip((before - after) / 550., -.8, .8))
    secondary_bonus = .008 * support_delta
    secondary_speed = np.linalg.norm(vec(post_state.cars[secondary].physics.linear_velocity))
    if secondary_speed < 180 and np.linalg.norm(target - vec(post_state.cars[secondary].physics.position)) > 500:
        secondary_bonus -= .0015  # explicitly discourage an inactive second player

    attack = -1.0 if orange else 1.0
    pos0 = vec(post_state.cars[our_ids[0]].physics.position)
    pos1 = vec(post_state.cars[our_ids[1]].physics.position)
    v0 = vec(post_state.cars[our_ids[0]].physics.linear_velocity)
    v1 = vec(post_state.cars[our_ids[1]].physics.linear_velocity)
    friendly_dist = float(np.linalg.norm(pos0-pos1))
    closing = float(np.dot(v0-v1, (pos1-pos0)/max(friendly_dist,1.)))
    near_ball = all(np.linalg.norm(p - after_ball) < 850 for p in (pos0,pos1))
    goal_exposed = all(attack * (p[1] - after_ball[1]) > -300 for p in (pos0,pos1))
    ball_reversing = attack * float(post_state.ball.linear_velocity[1]) < -350
    # Two players chasing high while ball goes toward own goal is bad;
    # two near the ball when covering the goal is NOT automatically bad.
    dual_commit_risk = bool(near_ball and goal_exposed and ball_reversing)
    teammate_collision_risk = bool(friendly_dist < 230 and closing > 300)
    result = {aid:0.0 for aid in our_ids}
    result[secondary] += secondary_bonus
    if dual_commit_risk:
        for aid in our_ids: result[aid] -= .018
    if teammate_collision_risk:
        for aid in our_ids: result[aid] -= .025
    # Avoid encouraging random drifting toward the ball. Goal outcomes remain dominant.
    return result, {'dual_commit_risk':int(dual_commit_risk),
                    'teammate_collision_risk':int(teammate_collision_risk),
                    'second_man_idle':int(secondary_speed<180 and np.linalg.norm(target-pos1 if secondary==our_ids[1] else target-pos0)>500),
                    'support_progress':support_delta}


class SharedPolicy2v2Match(TeamMatch):
    def reset(self):
        self.metrics = Counter()
        self.previous_primary = None
        self.last_risk_decision = -10000
        return super().reset()

    def step(self, actions, max_decisions):
        # Parent executes actual RocketSim physics and handles goal outcomes.
        pre = self.state
        pre_pos = {aid:vec(pre.cars[aid].physics.position).copy() for aid in self.our_ids}
        primary = primary_for_state(pre, self.our_ids, self.previous_primary)
        pre_target = support_target(pre, self.orange, primary)
        self.previous_primary = primary
        reward, done, winner = super().step(actions, max_decisions)
        # Remove parent's always-on ball chasing reward; BOTH learners must not chase.
        post_ball = vec(self.state.ball.position)
        for aid in self.our_ids:
            old_dist = float(np.linalg.norm(pre_pos[aid]-post_ball))
            new_dist = float(np.linalg.norm(vec(self.state.cars[aid].physics.position)-post_ball))
            reward[aid] -= float(np.clip((old_dist-.995*new_dist)/6000.,-.1,.1))*.02
        extra, met = shaping(pre_pos, pre_target, self.state, self.our_ids, self.orange, primary)
        for aid in self.our_ids:reward[aid] += extra[aid]
        self.metrics.update({k:v for k,v in met.items() if k!='support_progress'})
        if met['dual_commit_risk']: self.last_risk_decision = self.decisions
        if done and winner=='them' and self.decisions-self.last_risk_decision <= 20:
            self.metrics['conceded_after_dual_commit_risk'] += 1
        return reward, done, winner


def check_protected_source():
    if not SOURCE.is_file(): raise FileNotFoundError(f'Original Cycle9 checkpoint not found: {SOURCE}')
    actual = sha(SOURCE)
    if actual != SOURCE_HASH: raise RuntimeError('Cycle9 source checksum mismatch! Not training.')
    return actual


@contextlib.contextmanager
def no_simultaneous_afk():
    """Hold the real main AutoLeague OS lock throughout this experiment.

    Historical AFK STATUS.json files can incorrectly remain at 'training' after
    a process has died. The OS lock is released when the process exits, so it
    distinguishes a genuinely active AFK/AutoLeague run from stale metadata.
    Using a held context (rather than a brief probe) prevents a second trainer
    starting halfway through the 2v2 run.
    """
    from auto_league import exclusive_league_lock
    try:
        with exclusive_league_lock(ROOT / 'data' / 'autoleague'):
            yield
    except RuntimeError as exc:
        if 'Another AutoLeague is running for this data-dir' not in str(exc):
            raise
        raise RuntimeError(
            'An AFK or main AutoLeague process STILL holds the live training lock. '
            'Finish or safely pause that process before 2v2 training. '
            'Old STATUS.json files alone do not block this version.'
        ) from exc


@contextlib.contextmanager
def run_lock(run):
    run.mkdir(parents=True,exist_ok=True)
    f = (run / '.trainer_lock').open('a+b')
    try:
        f.seek(0);f.write(b'0');f.flush();f.seek(0)
        if os.name=='nt':
            import msvcrt
            try:msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
            except OSError as ex: raise RuntimeError('Another teamplay_v2 process is active') from ex
        else:
            import fcntl
            try:fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError as ex: raise RuntimeError('Another teamplay_v2 process is active') from ex
        yield
    finally:
        if os.name=='nt':
            try:f.seek(0);msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
            except OSError:pass
        f.close()


def mode_reset(match, generator, *, fixed_scenario=None):
    match.orange = bool(generator.randrange(2))
    match.scenario = fixed_scenario or generator.choices(['kickoff','grounded','pressure'],weights=[.3,.4,.3])[0]
    match.reset()
    return generator.random() < .70  # 70% original Nexto pair, 30% frozen Cycle9 pair


def choose_opp(frozen_nexto, frozen_cycle9, use_nexto):
    return frozen_nexto if use_nexto else frozen_cycle9


def predict(actor, observations, ids, stochastic=False):
    # Same shared actor, independently applied to each bot's own observation.
    return {aid:action(actor,observations[aid],stochastic=stochastic)[0] for aid in ids}


def checkpoint_save(path, learner, critic, actor_optim, critic_optim, count, matches, metrics, source_hash):
    if sha(SOURCE)!=source_hash: raise RuntimeError('Original source changed midrun; refusing save')
    data = {'actor':{k:v.detach().cpu().clone() for k,v in learner.state_dict().items()},
            'critic':critic.state_dict(), 'actor_optimizer':actor_optim.state_dict(),
            'critic_optimizer':critic_optim.state_dict(), 'controlled_samples':count,
            'episodes':matches, 'metrics':dict(metrics),'source_sha':source_hash,
            'description':'2v2 shared-policy Cycle9 PPO, NOT a validated competitive model'}
    tmp=path.with_suffix('.partial')
    torch.save(data,tmp)
    os.replace(tmp,path)
    atomic_json(path.with_suffix('.json'), {'controlled_samples':count,'episodes':matches,
                                           'metrics':dict(metrics),'source_sha':source_hash,
                                           'saved_at':datetime.now(timezone.utc).isoformat()})


def train(args):
    from rlgym.rocket_league.sim import RocketSimEngine
    if args.samples<1 or args.rollout<8 or args.minibatch<4 or args.episodes<8:raise ValueError('Invalid training sizes')
    if not 0<args.lr<=5e-5:raise ValueError('Unsafe learning rate')
    source_hash=check_protected_source()
    run=Path(args.run_dir).resolve();out=run/'candidate.pt'
    allowed=(ROOT/'data'/'teamplay_v2').resolve()
    if allowed != run.parent and allowed not in run.parents: raise ValueError('Output must stay under data/teamplay_v2')
    with run_lock(run):
        if out.exists() and not args.resume:raise FileExistsError('Existing run found. Use --resume (or new --run-dir): '+str(out))
        if args.resume and not out.exists():raise FileNotFoundError('Cannot resume: '+str(out))
        random.seed(args.seed);np.random.seed(args.seed);torch.manual_seed(args.seed);torch.set_num_threads(2)
        learner=load_actor(SOURCE);anchor=load_actor(SOURCE);frozen_cycle9=load_actor(SOURCE)
        frozen_nexto=NextoTeacher('cpu').actor
        for frozen in (anchor,frozen_cycle9,frozen_nexto):
            frozen.eval()
            for p in frozen.parameters():p.requires_grad_(False)
        critic=TeamCritic(); actor_opt=torch.optim.Adam(learner.parameters(),lr=args.lr)
        critic_opt=torch.optim.Adam(critic.parameters(),lr=2e-4)
        controlled_samples=0;episodes=0;metrics=Counter();gen=random.Random(args.seed+991)
        if args.resume:
            state=torch.load(out,map_location='cpu',weights_only=True)
            if state['source_sha']!=source_hash:raise RuntimeError('Resume checkpoint source differs')
            learner.load_state_dict(state['actor']);critic.load_state_dict(state['critic'])
            actor_opt.load_state_dict(state['actor_optimizer']);critic_opt.load_state_dict(state['critic_optimizer'])
            controlled_samples=int(state['controlled_samples']);episodes=int(state['episodes']);metrics.update(state['metrics'])
            print('RESUMED',controlled_samples,'controlled samples (episode sequence restarts; not deterministic resume)',flush=True)
        engine=RocketSimEngine(rlbot_delay=False);observer=TeamObserver()
        try:
            match=SharedPolicy2v2Match(engine,observer,ours=2,them=2,scenario='kickoff',seed=args.seed)
            nexto_flag=mode_reset(match,gen)
            while controlled_samples<args.samples:
                transitions=[[],[]]; horizon=min(args.rollout,math.ceil((args.samples-controlled_samples)/2))
                for _ in range(horizon):
                    views=observer.observe(match.state,match.prev)
                    opponent=choose_opp(frozen_nexto,frozen_cycle9,nexto_flag)
                    cmds=predict(opponent,views,match.their_ids,stochastic=False)
                    for i,aid in enumerate(match.our_ids):
                        obs=views[aid];chosen,logp=action(learner,obs,stochastic=True)
                        with torch.no_grad():value=float(critic(*tensors(obs)).item())
                        transitions[i].append([obs,chosen,logp,value,None,None])
                        cmds[aid]=chosen
                    reward,done,who=match.step(cmds,args.episodes)
                    for i,aid in enumerate(match.our_ids):transitions[i][-1][-2:]=[float(reward[aid]),bool(done)]
                    if done:
                        episodes+=1;metrics.update(match.metrics);metrics['outcome_'+who]+=1
                        nexto_flag=mode_reset(match,gen)
                batch=[]
                for i,trajectory in enumerate(transitions):
                    if trajectory[-1][-1]:bootstrap=0.
                    else:
                        aid=match.our_ids[i];obs=observer.observe(match.state,match.prev)[aid]
                        with torch.no_grad():bootstrap=float(critic(*tensors(obs)).item())
                    gae,returns=discounted_gae([t[4] for t in trajectory],[t[3] for t in trajectory],
                                               [t[5] for t in trajectory],bootstrap)
                    batch.extend((t[0],t[1],t[2],a,r) for t,a,r in zip(trajectory,gae,returns))
                q=torch.from_numpy(np.stack([t[0][0] for t in batch])).float()
                kv=torch.from_numpy(np.stack([t[0][1] for t in batch])).float()
                mask=torch.from_numpy(np.stack([t[0][2] for t in batch])).float()
                acts=torch.tensor([t[1] for t in batch],dtype=torch.long)
                old=torch.tensor([t[2] for t in batch]).float()
                advantages=torch.tensor([t[3] for t in batch]).float()
                returns=torch.tensor([t[4] for t in batch]).float()
                advantages=(advantages-advantages.mean())/(advantages.std(unbiased=False)+1e-6)
                for _ in range(args.epochs):
                    for ix in torch.randperm(len(batch)).split(args.minibatch):
                        logits=actor_logits(learner,q[ix],kv[ix],mask[ix]);dist=Categorical(logits=logits)
                        ratio=torch.exp(dist.log_prob(acts[ix])-old[ix]);clip=ratio.clamp(.85,1.15)
                        objective=-torch.minimum(ratio*advantages[ix],clip*advantages[ix]).mean()
                        with torch.no_grad():ref_logits=actor_logits(anchor,q[ix],kv[ix],mask[ix])
                        kl=F.kl_div(F.log_softmax(logits,-1),F.softmax(ref_logits,-1),reduction='batchmean')
                        loss=objective+args.anchor*kl-.001*dist.entropy().mean()
                        if not torch.isfinite(loss):raise FloatingPointError('Non-finite PPO actor loss')
                        actor_opt.zero_grad();loss.backward();torch.nn.utils.clip_grad_norm_(learner.parameters(),1.);actor_opt.step()
                        critic_pred=critic(q[ix],kv[ix],mask[ix]);critic_loss=F.mse_loss(critic_pred,returns[ix])
                        if not torch.isfinite(critic_loss):raise FloatingPointError('Non-finite PPO critic loss')
                        critic_opt.zero_grad();critic_loss.backward();torch.nn.utils.clip_grad_norm_(critic.parameters(),1.);critic_opt.step()
                controlled_samples+=len(batch)
                checkpoint_save(out,learner,critic,actor_opt,critic_opt,controlled_samples,episodes,metrics,source_hash)
                print(f'[2v2] samples {controlled_samples}/{args.samples} | episodes {episodes} | '
                      f'goals W/L/D={metrics["outcome_ours"]}/{metrics["outcome_them"]}/{metrics["outcome_draw"]} '
                      f'| dual-risk frames={metrics["dual_commit_risk"]} | '
                      f'close-bump-risk frames={metrics["teammate_collision_risk"]} | KL={float(kl):.5f}',flush=True)
                if (run/'STOP_AFTER_ROLLOUT').exists():
                    print('SAFE PAUSE: checkpoint saved. To resume, remove STOP_AFTER_ROLLOUT and use --resume',flush=True)
                    break
        finally:engine.close()
        print('Saved isolated candidate:',out,flush=True)


def evaluate(args):
    from rlgym.rocket_league.sim import RocketSimEngine
    check_protected_source()
    checkpoint=Path(args.run_dir)/'candidate.pt'
    if not checkpoint.exists():raise FileNotFoundError(checkpoint)
    run=Path(args.run_dir).resolve()
    with run_lock(run):
        base=load_actor(SOURCE);candidate=load_actor(SOURCE)
        state=torch.load(checkpoint,map_location='cpu',weights_only=True)
        if state['source_sha']!=SOURCE_HASH:raise RuntimeError('Different Cycle9 baseline')
        candidate.load_state_dict(state['actor'],strict=True)
        frozen=NextoTeacher('cpu').actor;frozen.eval();base.eval();candidate.eval()
        engine=RocketSimEngine(rlbot_delay=False);observer=TeamObserver()
        results={}
        try:
            for name,model in [('Cycle9_baseline',base),('Teamplay_candidate',candidate)]:
                games=Counter();stats=Counter()
                for n in range(args.games):
                    episode_seed=args.seed+n*10007
                    random.seed(episode_seed);np.random.seed(episode_seed%(2**32))
                    scen=['kickoff','grounded','pressure'][n%3]
                    match=SharedPolicy2v2Match(engine,observer,2,2,orange=bool(n%2),scenario=scen,seed=episode_seed)
                    winner='draw'
                    for _ in range(args.episodes):
                        views=observer.observe(match.state,match.prev)
                        cmds=predict(frozen,views,match.their_ids)
                        cmds.update(predict(model,views,match.our_ids))
                        _,done,winner=match.step(cmds,args.episodes)
                        if done:break
                    games[winner]+=1;stats.update(match.metrics)
                    if (n+1)%max(1,args.games//5)==0:
                        print(f'{name}: {n+1}/{args.games} 2v2 seeded episodes',flush=True)
                results[name]={'W':games['ours'],'L':games['them'],'D':games['draw'],
                               'score':round((games['ours']+.5*games['draw'])/args.games,4),
                               'episodes':args.games,'stats':dict(stats),
                               'dual_risk_per_100_episodes':round(stats['dual_commit_risk']*100/args.games,2),
                               'bump_risk_per_100_episodes':round(stats['teammate_collision_risk']*100/args.games,2)}
            atomic_json(run/f'evaluation_seed{args.seed}_n{args.games}.json',{'candidate_sha':sha(checkpoint),
                        'results':results,'episodes_are_not_full_matches':True,
                        'opponents':'two original frozen Nexto model actors',
                        'limits':'heuristic collision/double-commit flags, short first-goal episodes; RLBot full matches required'})
            print(json.dumps(results,indent=2),flush=True)
            print('No automatic promotion. Compare real RLBot 2v2 full matches too.',flush=True)
        finally:engine.close()


def preflight(args):
    from rlgym.rocket_league.sim import RocketSimEngine
    check_protected_source()
    model=load_actor(SOURCE);nexto=NextoTeacher('cpu').actor
    engine=RocketSimEngine(rlbot_delay=False);observer=TeamObserver()
    try:
        for scen in ['kickoff','grounded','pressure']:
            match=SharedPolicy2v2Match(engine,observer,2,2,scenario=scen,seed=args.seed)
            v=observer.observe(match.state,match.prev)
            assert len(v)==4,(len(v),scen)
            for o in v.values():
                assert o[0].shape==(1,32) and o[1].shape==(41,24) and o[2].shape==(41,), 'Bad native model observation shape'
            cmd=predict(nexto,v,match.their_ids);cmd.update(predict(model,v,match.our_ids))
            r,done,winner=match.step(cmd,args.episodes)
            assert len(r)==2 and all(np.isfinite(list(r.values()))), 'Nonfinite rewards'
            print('PASS real RocketSim 2v2:',scen,'native actor, both teammates active, two Nextos, physics step',flush=True)
    finally:engine.close()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['preflight','train','eval'])
    p.add_argument('--run-dir',type=Path,default=DEFAULT_RUN)
    p.add_argument('--samples',type=int,default=8192,help='Cumulative learner-car samples; 2 each physics decision')
    p.add_argument('--rollout',type=int,default=128,help='World steps per PPO rollout')
    p.add_argument('--epochs',type=int,default=2)
    p.add_argument('--minibatch',type=int,default=64)
    p.add_argument('--episodes',type=int,default=330,help='Decision horizon (~22s per episode)')
    p.add_argument('--games',type=int,default=40,help='Evaluation episodes for EACH policy')
    p.add_argument('--lr',type=float,default=1e-6)
    p.add_argument('--anchor',type=float,default=.08)
    p.add_argument('--seed',type=int,default=20261010)
    p.add_argument('--resume',action='store_true')
    a=p.parse_args();torch.set_num_threads(2)
    if a.games<4 or a.epochs<1 or a.anchor<0: p.error('Invalid evaluation/training parameters')
    # One process-scoped lock for the whole preflight/training/evaluation.
    # A paused AFK process has released this lock; an active one has not.
    with no_simultaneous_afk():
        if a.command=='preflight':preflight(a)
        elif a.command=='train':train(a)
        else:evaluate(a)

if __name__=='__main__':main()
