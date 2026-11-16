import copy
import torch
import pytest
from duelforge.runtime import ROOT,config,sha,load
from duelforge.train import train
from duelforge.potential_experiment import fork_potential

def test_objective_fork_preserves_actor_adam_parent_and_baseline(tmp_path):
    c=config();c.update(width=32,n_envs=2,torch_threads=1,device='cpu');c['ppo'].update(steps=8,batch_size=32);c['wandb']['enabled']=False;c['auto_evaluate_every']=10**10
    source=tmp_path/'parent';train(source,c,minutes=1,max_updates=2);h=sha(source/'latest.pt');parent=load(source/'latest.pt');target=tmp_path/'child';fork_potential(source,target);child=load(target/'latest.pt')
    assert sha(source/'latest.pt')==h and sha(target/'initial.pt')==h
    assert child['learning_transitions']==parent['learning_transitions'] and child['config']['predictive']['enabled']
    assert not child['config']['bootstrap']['enabled'] and child['wandb_id'] is None
    assert child['optimizer']['param_groups'][0]['lr']==.00005
    for k in parent['model']:
        if k.startswith('actor.'):torch.testing.assert_close(parent['model'][k],child['model'][k],atol=0,rtol=0)
    assert any(not torch.equal(parent['model'][k],child['model'][k]) for k in parent['model'] if k.startswith('critic.'))
    # Actor has fourteen parameter tensors; critic moments are deliberately reset.
    for idx,state in child['optimizer']['state'].items():
        assert idx<14
        torch.testing.assert_close(state['exp_avg'],parent['optimizer']['state'][idx]['exp_avg'],atol=0,rtol=0)
    train(target,minutes=1,max_updates=1);assert load(target/'latest.pt')['updates']==parent['updates']+1
    with pytest.raises(FileExistsError):fork_potential(source,target)
