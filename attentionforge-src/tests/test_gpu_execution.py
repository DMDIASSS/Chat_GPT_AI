import copy,json
from pathlib import Path
import numpy as np
import pytest
import torch
from attentionforge.model import ActorCritic
from attentionforge.runtime import config,save_checkpoint,sha
from attentionforge.execution import compile_checked,make_optimizer,configure_optimizer,checked_step,optimizer_probe,select_model_execution
from attentionforge.gpu_profile import fork_checkpoint,model_hash,recent_phase


def test_script_preserves_checkpoint_outputs_gradients_and_parameter_identity():
    torch.set_num_threads(1);torch.manual_seed(617)
    eager=ActorCritic();reference=copy.deepcopy(eager);script=compile_checked(eager)
    x=torch.randn(5,43,40);x[:,:,39]=torch.randint(0,7,(5,43));x[:,0,39]=1
    legal=torch.ones(5,90,dtype=torch.bool);legal[:,3]=False
    a,v=reference(x,legal);b,z=script(x,legal);torch.testing.assert_close(a,b);torch.testing.assert_close(v,z)
    (a[:,0].sum()+v.square().mean()).backward();(b[:,0].sum()+z.square().mean()).backward()
    for (n,p),(m,q) in zip(reference.named_parameters(),script.named_parameters()):assert n==m;torch.testing.assert_close(p.grad,q.grad,rtol=3e-4,atol=2e-6)
    eager.load_state_dict(reference.state_dict());assert list(eager.state_dict())==list(script.state_dict())


def test_optimizer_resume_keeps_moments_and_step_values():
    torch.set_num_threads(1);c=config();a=ActorCritic();o,_=make_optimizer(a,c,torch.device('cpu'))
    x=torch.zeros(2,43,40);x[:,0,39]=1;l=torch.ones(2,90,dtype=torch.bool)
    a(x,l)[1].sum().backward();o.step();saved=copy.deepcopy(o.state_dict());saved['param_groups'][0]['fused']=True;saved['param_groups'][0]['foreach']=False
    b=copy.deepcopy(a);p,name=make_optimizer(b,c,torch.device('cpu'));p.load_state_dict(saved);configure_optimizer(p,torch.device('cpu'),name)
    for (old,orig),(new,dest) in zip(o.state.items(),p.state.items()):
        for key in ('step','exp_avg','exp_avg_sq'):torch.testing.assert_close(orig[key],dest[key])
    o.zero_grad();p.zero_grad();a(x,l)[1].sum().backward();b(x,l)[1].sum().backward();o.step();p.step()
    for old,new in zip(a.parameters(),b.parameters()):torch.testing.assert_close(old,new)


def test_checked_step_rejects_bad_kl_without_changing_weights_or_adam_state():
    m=torch.nn.Linear(2,1);o=torch.optim.Adam(m.parameters());before=copy.deepcopy(m.state_dict())
    loss=m(torch.ones(3,2)).square().mean();accepted,_=checked_step(loss,torch.tensor(.2),m,o,.5,.025)
    assert not accepted and not o.state
    for k,v in m.state_dict().items():torch.testing.assert_close(v,before[k])


def test_checked_step_rejects_nonfinite_gradient_before_optimizer_update():
    p=torch.nn.Parameter(torch.tensor([0.]));m=torch.nn.ParameterList([p]);o=torch.optim.Adam(m.parameters())
    # Finite value with an infinite derivative.
    loss=p.sqrt().sum()
    with pytest.raises(FloatingPointError):checked_step(loss,torch.tensor(0.),m,o,.5,.025)
    torch.testing.assert_close(p,torch.tensor([0.]));assert not o.state


def test_cpu_execution_selection_is_eager_and_does_not_change_weights():
    c=config();m=ActorCritic();before=model_hash(m.state_dict());actual,name,rows=select_model_execution(m,c,torch.device('cpu'))
    assert actual is m and name=='eager' and not rows;assert model_hash(m.state_dict())==before


def test_gpu_fork_preserves_parent_model_counters_moments_and_history(tmp_path):
    source=tmp_path/'parent';source.mkdir();c=config(Path(__file__).resolve().parents[1]/'laptop_config.json');m=ActorCritic(**c['network']);o=torch.optim.Adam(m.parameters());sum(p.square().sum() for p in m.parameters()).backward();o.step()
    payload={'model':m.state_dict(),'optimizer':o.state_dict(),'config':c,'learning_transitions':2200000,'updates':36,'history':['old.pt'],'history_scores':{'old.pt':.4},'wandb_id':'parent-run','python_rng':None,'numpy_rng':None,'torch_rng':torch.get_rng_state()}
    (source/'history').mkdir();save_checkpoint(source/'history/old.pt',{'model':m.state_dict()});save_checkpoint(source/'baseline.pt',{'model':m.state_dict()});save_checkpoint(source/'latest.pt',payload)
    before=sha(source/'latest.pt');record=fork_checkpoint(source,tmp_path/'child',payload,512,'eager',{'probe':True})
    child=torch.load(tmp_path/'child/latest.pt',weights_only=False);assert sha(source/'latest.pt')==before;assert model_hash(child['model'])==model_hash(payload['model'])
    assert child['learning_transitions']==2200000 and child['updates']==36 and child['wandb_id'] is None
    assert child['config']['ppo']['batch_size']==512 and payload['config']['ppo']['batch_size']==256
    assert sha(source/'history/old.pt')==sha(tmp_path/'child/history/old.pt')
    for key,original in payload['optimizer']['state'].items():
        for field in ('step','exp_avg','exp_avg_sq'):torch.testing.assert_close(child['optimizer']['state'][key][field],original[field])
    with pytest.raises(FileExistsError):fork_checkpoint(source,tmp_path/'child',payload,1024,'eager',{})


def test_phase_reader_uses_recorded_learner_count_and_collection_time(tmp_path):
    c=config();c['n_envs']=128
    row={'speed/collection_seconds':3.3,'league/opponent':'old.pt'};(tmp_path/'metrics.jsonl').write_text(json.dumps(row)+'\n')
    seconds,samples=recent_phase(tmp_path,c);assert seconds==3.3 and samples==57344


@pytest.mark.skipif(not torch.cuda.is_available(),reason='CUDA GPU unavailable in this environment')
def test_actual_cuda_fused_adam_and_scripted_forward():
    device=torch.device('cuda');c=config();m=ActorCritic().to(device);o,name=make_optimizer(m,c,device);assert name in ('adam_fused','adam_foreach')
    j=compile_checked(m);x=torch.zeros(4,43,40,device=device);x[:,0,39]=1;l=torch.ones(4,90,dtype=torch.bool,device=device)
    out,v=j(x,l);accepted,_=checked_step(v.square().mean(),torch.zeros((),device=device),j,o,.5,.025);assert accepted


def test_training_failure_does_not_overwrite_checkpoint_with_failed_update(tmp_path,monkeypatch):
    from test_contracts import has_meshes
    if not has_meshes():pytest.skip('Local Soccar collision meshes required')
    import importlib
    t=importlib.import_module('attentionforge.train');c=config();c['n_envs']=2;c['ppo']['steps']=4;c['ppo']['batch_size']=4;c['wandb']['enabled']=False
    writes=[];original=t.save_checkpoint
    def record(path,payload):
        original(path,payload);writes.append(sha(path))
    def fail(*args,**kwargs):raise FloatingPointError('injected failure before optimizer step')
    monkeypatch.setattr(t,'save_checkpoint',record);monkeypatch.setattr(t,'checked_step',fail)
    with pytest.raises(FloatingPointError):t.train(c,tmp_path/'run',max_updates=1)
    assert len(writes)==1 and sha(tmp_path/'run/latest.pt')==writes[0]
    assert json.loads((tmp_path/'run/status.json').read_text())['state']=='error'
