import json
import os
from pathlib import Path
import numpy as np
import pytest
import torch

from nova.core import ACTIONS, check_model, observe
from nova.data import save_npz, split_by_episode, usable_reset
from nova.environment import ArenaEnv
from nova.models import export_actor, FrozenActor, save_ppo, load_ppo
from nova.scenarios import Curriculum
from nova.training import new_model, validate_config


@pytest.mark.parametrize('kind',['checkpoint','actor'])
def test_serialized_models_fsync_with_write_access(cfg,tmp_path,monkeypatch,kind):
    """Reproduce Windows' write-access requirement even when running on Linux."""
    real_fsync=os.fsync
    def require_write_access(fd):
        # A zero-byte write changes no file bytes and rejects read-only descriptors.
        os.write(fd,b'')
        return real_fsync(fd)

    torch.set_num_threads(1)
    cfg['ppo'].update(n_steps=16,batch_size=16,n_epochs=1)
    env=ArenaEnv(cfg,opponent='scripted')
    try:
        model=new_model(cfg,env)
        monkeypatch.setattr(os,'fsync',require_write_access)
        obs,_=env.reset(seed=99)
        expected=int(model.predict(obs,deterministic=True)[0])
        if kind=='checkpoint':
            path=tmp_path/'full.zip'
            save_ppo(model,path)
            restored=load_ppo(path)
            assert int(restored.predict(obs,deterministic=True)[0])==expected
        else:
            path=tmp_path/'actor.pt'
            export_actor(model,path)
            assert FrozenActor(path).action(obs)==expected
        assert not list(tmp_path.glob('*.tmp'))
    finally:
        env.close()


def test_full_checkpoint_and_frozen_export_parity(cfg,tmp_path):
    torch.set_num_threads(1)
    cfg['ppo'].update(n_steps=16,batch_size=16,n_epochs=1)
    env=ArenaEnv(cfg,opponent='scripted')
    try:
        model=new_model(cfg,env)
        model.learn(32)
        save_ppo(model,tmp_path/'full.zip')
        export_actor(model,tmp_path/'actor.pt')
        restored=load_ppo(tmp_path/'full.zip')
        actor=FrozenActor(tmp_path/'actor.pt')
        assert restored.num_timesteps==32
        assert len(restored.policy.optimizer.state)>0
        obs,_=env.reset(seed=99)
        for _ in range(10):
            assert int(restored.predict(obs,deterministic=True)[0])==actor.action(obs)
            obs,_,term,trunc,_=env.step(actor.action(obs))
            if term or trunc: obs,_=env.reset()
        old_logits=actor.model(torch.from_numpy(obs)[None,:]).clone()
        with torch.no_grad(): model.policy.action_net.bias.add_(torch.arange(len(ACTIONS)))
        torch.testing.assert_close(old_logits,actor.model(torch.from_numpy(obs)[None,:]))
        # Binary integrity is checked before a modified model is loaded.
        with (tmp_path/'actor.pt').open('ab') as f: f.write(b'changed')
        with pytest.raises(ValueError,match='hash mismatch'): FrozenActor(tmp_path/'actor.pt')
    finally: env.close()


def test_episode_split_has_no_validation_leakage():
    groups=np.repeat(np.arange(10),37)
    a,b=split_by_episode(groups)
    assert len(a)>0 and len(b)>0
    assert set(groups[a]).isdisjoint(set(groups[b]))
    assert len(a)+len(b)==len(groups)
    with pytest.raises(ValueError,match='two'): split_by_episode(np.zeros(50))


def test_replay_reset_bank_roundtrip_in_real_simulator(cfg,tmp_path):
    from rlgym_tools.rocket_league.misc.serialize import serialize_game_state
    env=ArenaEnv(cfg,opponent='scripted',scenario='shot',side=0)
    try:
        env.reset(seed=22)
        original=env.state.ball.position.copy()
        assert usable_reset(env.state)
        row=serialize_game_state(env.state)
    finally: env.close()
    path=tmp_path/'bank.npz'
    save_npz(path,states=np.stack([row,row]))
    cfg['env']['replay_bank']=str(path)
    cfg['curriculum']['weights']={'replay':1}
    replay_env=ArenaEnv(cfg,opponent='scripted',scenario='replay',side=0)
    try:
        replay_env.reset(seed=14)
        np.testing.assert_allclose(replay_env.state.ball.position,original,atol=1e-4)
        obs,_,_,_,_=replay_env.step(17)
        assert np.isfinite(obs).all()
    finally: replay_env.close()
    with pytest.raises(FileExistsError): save_npz(path,states=np.stack([row]))


def test_no_silent_teacher_fallback_and_league_cold_start(cfg):
    cfg['league']['weights']={'history':1}
    env=ArenaEnv(cfg)
    try:
        env.reset(seed=8)
        assert env.opponent_label=='scripted:empty-snapshot-pool'
    finally: env.close()
    cfg['league']['weights']={'unverified_pulsar':1}
    with pytest.raises(ValueError,match='headless'): validate_config(cfg)


def test_curriculum_keeps_practice_diversity():
    c=Curriculum({'shot':1,'aerial':1})
    for _ in range(100):
        c.record('shot',True)
        c.record('aerial',False)
    rng=np.random.default_rng(67)
    counts={n:0 for n in c.weights}
    for _ in range(1000): counts[c.choose(rng)]+=1
    assert 100<counts['shot']<counts['aerial']


def test_recovery_ignores_incomplete_generation_and_recovers_pointer(tmp_path):
    from nova.core import write_model_meta
    from nova.training import recover_checkpoint
    directory=tmp_path/'checkpoints'
    directory.mkdir()
    valid=directory/'step_000000000010.zip'
    valid.write_bytes(b'completed checkpoint bytes')
    write_model_meta(valid,timesteps=10)
    partial=directory/'step_000000000020.zip'
    partial.write_bytes(b'power loss before sidecar completion')
    (tmp_path/'latest.json').write_text('{interrupted pointer')
    assert recover_checkpoint(tmp_path)==valid
    assert json.loads((tmp_path/'latest.json').read_text())['step']==10
