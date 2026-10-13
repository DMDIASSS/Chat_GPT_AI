from pathlib import Path
from zipfile import ZipFile
import numpy as np
import torch
import package_update180_continuation as package
from slater_mechanics_eval import load_actor
from slater_mechanics_env import collect_batched
from slater_versatile_env import VersatileCritic, VersatileEnv
from slater_ppo import trust_region_update

ROOT=Path(__file__).resolve().parents[1]

def test_shipped_bundle_contains_exact_training_dependencies():
    with ZipFile(ROOT/'Slater_Update180_Continuation_Update.zip') as z:
        assert package.dependencies(ROOT) <= set(z.namelist())
        for name in package.dependencies(ROOT):
            assert z.read(name)==(ROOT/name).read_bytes(), name
        assert not any(n.endswith(('.pt','.lt','.bin')) for n in z.namelist())

def test_batched_ppo_uses_matching_task_heads_and_configured_anchor():
    torch.set_num_threads(2)
    teacher=load_actor(ROOT,ROOT/'vendor/nexto/nexto-model.pt')
    actor=load_actor(ROOT,ROOT/'vendor/nexto/nexto-model.pt',trainable=True)
    critic=VersatileCritic()
    # This critic intentionally has no forward(x): PPO must use the rollout task.
    envs=[VersatileEnv({'teacher':teacher},task_name=task,max_seconds=1,anchor_weight=.10)
          for task in ('match','ground')]
    try:
        seeds=[71,72];obs=[e.reset(s) for e,s in zip(envs,seeds)]
        rows,*_=collect_batched(actor,critic,envs,obs,seeds,4)
        assert set(rows['task'])=={0,1}
        assert np.allclose(rows['anchor_weight'],.10)
        ao=torch.optim.Adam(actor.parameters(),lr=3e-6)
        co=torch.optim.Adam(critic.parameters(),lr=1e-4)
        result=trust_region_update(actor,teacher,critic,ao,co,rows,1,8,.10,73,target_kl=.005)
        assert result['accepted_actor_epochs']==1
        assert np.isfinite(result['value_loss'])
        assert torch.count_nonzero(critic.heads.weight.grad[:2])>0
        assert torch.count_nonzero(critic.heads.weight.grad[2:])==0
    finally:
        for e in envs:e.close()
