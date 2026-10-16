from pathlib import Path
import json
import shutil

import pytest
import torch

import slater_mechanics_trainer as trainer
from round_robin_evaluator import weight_digest


def test_real_update_rollback_is_the_state_loaded_on_resume(tmp_path,monkeypatch):
    repository=Path(trainer.__file__).resolve().parent
    source=repository/'vendor/nexto/nexto-model.pt'
    if not source.is_file():pytest.skip('Needs the original Nexto actor')
    root=tmp_path/'repo';root.mkdir()
    (root/'vendor/nexto').mkdir(parents=True)
    shutil.copyfile(source,root/'vendor/nexto/nexto-model.pt')
    for name in ('slater_mechanics_trainer.py','slater_mechanics_core.py',
                 'slater_mechanics_env.py','slater_mechanics_eval.py','slater_ppo.py',
                 'slater_cycle9_native_ppo_v025.py','slater_nexto_scheduler_v038b.py',
                 'afk_team_research.py','mechanics_scenarios.py','nexto_teacher.py',
                 'vendor/nexto/nexto_obs.py','slater_v041_worker.py'):
        shutil.copyfile(repository/name,root/name)
    cfg=dict(trainer.DEFAULT_CONFIG,run_name='persistence',n_envs=2,
             steps_per_env=32,epochs=1,minibatch=32,eval_every=1,
             mastery_seeds=12,retention_seeds=4,retention_seconds=8,episode_seconds=3)
    baseline=weight_digest(trainer.load_actor(root,source).state_dict())
    beginnings=[];collect=trainer.collect_batched
    def recording_collect(actor,*args):
        beginnings.append(weight_digest(actor.state_dict()))
        return collect(actor,*args)
    monkeypatch.setattr(trainer,'collect_batched',recording_collect)
    monkeypatch.setattr(trainer,'evaluate_stage',lambda *a,**kw:{'records':[]})
    monkeypatch.setattr(trainer,'retention_check',lambda *a,**kw:{'passed':False})
    run=trainer.train(root,cfg,source,updates_override=1)
    progress=json.loads((run/'progress.json').read_text())
    saved=torch.load(root/progress['latest_path'],weights_only=True)
    raw=torch.load(run/'update_000001.pt',weights_only=True)
    assert weight_digest(raw['actor'])!=baseline  # an actual PPO actor update
    assert weight_digest(saved['actor'])==baseline
    assert saved['actor_optimizer']['state']=={}
    assert progress['total_updates']==1 and progress['trusted_path'] is None
    monkeypatch.setattr(trainer,'retention_check',lambda *a,**kw:{'passed':True})
    trainer.train(root,cfg,source,resume=True,updates_override=1)
    progress=json.loads((run/'progress.json').read_text())
    assert beginnings==[baseline,baseline]
    assert progress['total_updates']==2 and progress['decisions']==128
    assert progress['trusted_path'].endswith('update_000002.pt')
    with pytest.raises(RuntimeError,match='configuration/models changed'):
        trainer.train(root,dict(cfg,actor_lr=2e-5),source,resume=True,updates_override=1)
