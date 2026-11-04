from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import numpy as np
import torch

from .core import ROOT, ACTIONS, CONTRACT, OBS_SIZE, atomic_json, nearest_action, sha256
from .environment import ArenaEnv
from .models import save_ppo, FrozenActor
from .teachers import make_opponent, controls_for_ticks, BOT_NAMES
from .training import load_config, new_model, prepare_config


def save_npz(path,**arrays):
    path=Path(path)
    if path.exists(): raise FileExistsError(f'Choose a fresh output path: {path}')
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(suffix='.npz',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f:
            np.savez_compressed(f,**arrays)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp,path)
    finally:
        if os.path.exists(temp): os.unlink(temp)


def collect(args):
    cfg=prepare_config(load_config(args.config),replay_bank=args.replay_bank)
    torch.set_num_threads(cfg['threads'])
    env=ArenaEnv(cfg,opponent=args.opponent)
    names=[n.strip() for n in args.teacher.split(',')]
    if not names or set(names)-set(BOT_NAMES): raise ValueError('Unknown demonstration teacher')
    teachers={n:make_opponent(n) for n in names}
    # Teachers are inference-only. No teacher parameters join the student's optimizer.
    for policy in teachers.values():
        for value in vars(policy).values():
            if isinstance(value,torch.nn.Module):
                value.eval()
                for parameter in value.parameters(): parameter.requires_grad_(False)
    selector=np.random.default_rng(args.seed+100003)
    order=list(selector.permutation(names))
    balanced=getattr(args,'balanced_teachers',False)
    teacher_name=str(order[0]) if balanced else names[int(selector.integers(len(names)))]
    teacher=teachers[teacher_name]
    observations=[]
    actions=[]
    groups=[]
    errors=[]
    teacher_ids=[]
    scenario_ids=[]
    rewards=[]
    returns=[]
    return_complete=[]
    episode_rewards=[]
    episode_rows=[]
    scenario_names=list(cfg['curriculum']['weights'])
    skipped=0
    mixed_windows=0
    kept_by_teacher={n:0 for n in names}
    episode=0
    attempted=0
    stopped=False
    stop_path=getattr(args,'stop_path',None)
    progress=getattr(args,'on_progress',None)
    student=FrozenActor(args.student_model) if getattr(args,'student_model',None) else None
    prefix_decisions=0
    prefix_episodes=0
    obs,_=env.reset(seed=args.seed)
    def finish_returns(complete):
        values=np.zeros(len(episode_rewards),dtype=np.float32);future=0.
        for j in range(len(episode_rewards)-1,-1,-1):
            future=episode_rewards[j]+cfg['ppo']['gamma']*future;values[j]=future
        for row,step in episode_rows:
            returns[row]=float(values[step]);return_complete[row]=bool(complete)
        episode_rewards.clear();episode_rows.clear()
    def start_teacher():
        nonlocal obs,prefix_decisions,prefix_episodes,episode
        if student is not None and selector.random()<.25:
            prefix_episodes+=1
            for _ in range(int(selector.integers(1,61))):
                obs,_,terminal,truncated,_=env.step(student.action(obs))
                prefix_decisions+=1
                if terminal or truncated:
                    episode+=1;obs,_=env.reset();break
                if stop_path and Path(stop_path).exists(): break
        teacher.reset(env.state,env.agent,np.random.default_rng(args.seed+episode))
    try:
        start_teacher()
        for i in range(args.samples):
            if stop_path and Path(stop_path).exists(): stopped=True;break
            commands=controls_for_ticks(teacher,env.state)
            command=commands[0]
            index=nearest_action(command)
            error=float(np.max(np.abs(command-ACTIONS[index])))
            # Never silently relabel a different jump/boost/handbrake.
            constant=bool(np.all(commands==command))
            matches=constant and error<=.3 and np.array_equal(command[5:],ACTIONS[index,5:])
            decision_obs=obs.copy() if matches else None
            obs,reward,terminal,truncated,_=env.step_controls(commands)
            attempted+=1
            if matches:
                observations.append(decision_obs)
                actions.append(index)
                groups.append(episode)
                teacher_ids.append(names.index(teacher_name))
                scenario_ids.append(scenario_names.index(env.scenario))
                errors.append(error)
                kept_by_teacher[teacher_name]+=1
                rewards.append(float(reward));returns.append(0.);return_complete.append(False)
                episode_rows.append((len(actions)-1,len(episode_rewards)))
            else:
                skipped+=1
                mixed_windows+=not constant
            episode_rewards.append(float(reward))
            if terminal or truncated:
                finish_returns(True)
                episode+=1
                obs,_=env.reset()
                teacher_name=str(order[episode%len(order)]) if balanced else names[int(selector.integers(len(names)))]
                teacher=teachers[teacher_name]
                start_teacher()
            if (i+1)%1000==0:
                print(f'Teacher decisions {i+1}/{args.samples}; kept {len(actions)}, episodes {episode}',flush=True)
                if progress: progress(attempted,len(actions))
    except KeyboardInterrupt:
        stopped=True
        print('Stopped collection; saving the samples already collected.',flush=True)
    finally:
        finish_returns(False)
        env.close()
    if not actions:
        if stopped: return dict(stopped=True,samples=0,attempted_decisions=attempted,prefix_decisions=prefix_decisions)
        raise ValueError('No compatible teacher actions were collected')
    save_npz(args.out,obs=np.asarray(observations,dtype=np.float32),actions=np.asarray(actions,dtype=np.int64),
             episode=np.asarray(groups,dtype=np.int64),teacher_id=np.asarray(teacher_ids,dtype=np.int16),
             scenario_id=np.asarray(scenario_ids,dtype=np.int16),reward=np.asarray(rewards,dtype=np.float32),
             return_to_go=np.asarray(returns,dtype=np.float32),return_complete=np.asarray(return_complete,dtype=bool))
    summary=dict(kind='simulator_teacher_controls',contract=CONTRACT,teacher=args.teacher,
        opponent=args.opponent,samples=len(actions),skipped_quantization=skipped-mixed_windows,
        skipped_mid_window_change=mixed_windows,kept_by_teacher=kept_by_teacher,
        completed_episodes=episode,groups=len(set(groups)),max_control_error=max(errors),
        dataset_sha256=sha256(args.out),replay_bank=cfg['env']['replay_bank'],seed=args.seed,
        teacher_names=names,scenario_names=scenario_names,attempted_decisions=attempted,stopped=stopped,
        prefix_decisions=prefix_decisions,prefix_episodes=prefix_episodes,
        reward_signal='NovaForge shared simulator reward; not the original teachers training reward',
        reward_mean=float(np.mean(rewards)),complete_return_fraction=float(np.mean(return_complete)),
        note='Labels are controls actually applied by the teacher in RocketSim, not replay-inferred inputs.')
    atomic_json(str(args.out)+'.json',summary)
    print(json.dumps(summary,indent=2))
    return summary


def split_by_episode(groups,seed=90210):
    unique=np.unique(groups)
    if len(unique)<2: raise ValueError('Need at least two demonstration episodes for a held-out split; collect more')
    rng=np.random.default_rng(seed)
    rng.shuffle(unique)
    validation_groups=unique[:max(1,int(np.ceil(.2*len(unique))))]
    validation=np.isin(groups,validation_groups)
    return np.flatnonzero(~validation),np.flatnonzero(validation)


def pretrain(args):
    meta=json.loads(Path(str(args.dataset)+'.json').read_text())
    if meta.get('contract')!=CONTRACT or meta.get('dataset_sha256')!=sha256(args.dataset):
        raise ValueError('Dataset contract or hash mismatch')
    with np.load(args.dataset,allow_pickle=False) as data:
        obs=data['obs'].copy()
        labels=data['actions'].copy()
        groups=data['episode'].copy()
    if (obs.ndim!=2 or obs.shape[1]!=OBS_SIZE or not np.isfinite(obs).all() or
        labels.shape!=(len(obs),) or groups.shape!=(len(obs),) or
        not np.issubdtype(labels.dtype,np.integer) or np.any(labels<0) or np.any(labels>=len(ACTIONS))):
        raise ValueError('Invalid imitation dataset')
    if Path(args.out).exists(): raise FileExistsError('Choose a fresh BC model filename')
    train_ids,val_ids=split_by_episode(groups,args.seed)
    cfg=load_config(args.config)
    cfg['workers']=1
    cfg['device']=args.device
    torch.set_num_threads(cfg['threads'])
    torch.manual_seed(args.seed)
    env=ArenaEnv(cfg,opponent='scripted')
    model=new_model(cfg,env)
    optimizer=model.policy.optimizer
    for pg in optimizer.param_groups: pg['lr']=args.lr
    rng=np.random.default_rng(args.seed)
    history=[]
    def validate():
        total=correct=0
        loss_sum=0.
        model.policy.set_training_mode(False)
        with torch.no_grad():
            for start in range(0,len(val_ids),512):
                ids=val_ids[start:start+512]
                x=torch.as_tensor(obs[ids],device=model.device)
                y=torch.as_tensor(labels[ids],device=model.device)
                logits=model.policy.get_distribution(x).distribution.logits
                loss_sum+=torch.nn.functional.cross_entropy(logits,y,reduction='sum').item()
                correct+=(logits.argmax(-1)==y).sum().item()
                total+=len(ids)
        return dict(loss=loss_sum/total,accuracy=correct/total)
    before=validate()
    try:
        for epoch in range(args.epochs):
            model.policy.set_training_mode(True)
            rng.shuffle(train_ids)
            for start in range(0,len(train_ids),256):
                ids=train_ids[start:start+256]
                x=torch.as_tensor(obs[ids],device=model.device)
                y=torch.as_tensor(labels[ids],device=model.device)
                logits=model.policy.get_distribution(x).distribution.logits
                loss=torch.nn.functional.cross_entropy(logits,y)
                optimizer.zero_grad()
                loss.backward()
                torch.nn.utils.clip_grad_norm_(model.policy.parameters(),.5)
                optimizer.step()
            record=dict(epoch=epoch+1,validation=validate())
            history.append(record)
            print(json.dumps(record),flush=True)
    finally:
        save_ppo(model,args.out,initialization='behavioral_cloning',teacher=meta['teacher'])
        env.close()
    report=dict(before=before,after=validate(),history=history,training_samples=len(train_ids),
        validation_samples=len(val_ids),split='disjoint episode IDs',dataset_sha256=sha256(args.dataset),
        model_sha256=sha256(args.out),seed=args.seed,
        note='Validation action accuracy does not establish match strength. Evaluate the trained policy.')
    atomic_json(str(args.out)+'.bc-report.json',report)
    print(f'BC model saved: {args.out}; held-out accuracy {report["after"]["accuracy"]:.3f}')


def usable_reset(state):
    if len(state.cars)!=2 or {c.team_num for c in state.cars.values()}!={0,1} or state.goal_scored:
        return False
    if not np.isfinite(state.ball.position).all(): return False
    x,y,z=state.ball.position
    if abs(x)>4020 or abs(y)>5000 or not 85<z<1950: return False
    for c in state.cars.values():
        if c.is_demoed: return False
        x,y,z=c.physics.position
        if abs(x)>4100 or abs(y)>5100 or not 8<z<2000: return False
    return True


def replay_import(args):
    from rlgym_tools.rocket_league.replays.parsed_replay import ParsedReplay
    from rlgym_tools.rocket_league.replays.convert import replay_to_rlgym
    from rlgym_tools.rocket_league.misc.serialize import serialize_game_state
    source=Path(args.source)
    files=sorted(source.glob('*.replay')) if source.is_dir() else [source]
    if not files or any(not f.exists() for f in files): raise FileNotFoundError('No replay files found')
    frames=[]
    sources=[]
    rejected=0
    for replay_file in files:
        print(f'Parsing {replay_file}; 1v1 states only',flush=True)
        replay=ParsedReplay.load(replay_file,carball_path=args.carball)
        if len(replay.player_dfs)!=2:
            print('Skipped: this release needs 1v1 replays.',flush=True)
            continue
        sources.append(dict(file=replay_file.name,sha256=sha256(replay_file)))
        for i,frame in enumerate(replay_to_rlgym(replay,interpolation='rocketsim')):
            if i%args.stride: continue
            state=frame.state
            if not usable_reset(state):
                rejected+=1
                continue
            state.tick_count=0
            row=serialize_game_state(state)
            if not np.isfinite(row).all():
                rejected+=1
                continue
            frames.append(row)
            if len(frames)>=args.max_states: break
        if len(frames)>=args.max_states: break
    if not frames: raise ValueError('No usable 1v1 replay states survived parsing/filtering')
    save_npz(args.out,states=np.stack(frames))
    atomic_json(str(args.out)+'.json',dict(kind='replay_reset_bank',parser='rlgym-tools 2.6.5',
        states=len(frames),rejected=rejected,sources=sources,sha256=sha256(args.out),
        stride_frames=args.stride,labels='none; reconstructed replay controls are not used for BC'))
    print(f'Saved {len(frames)} replay starting states. Use --replay-bank {args.out} with collect or train.')
