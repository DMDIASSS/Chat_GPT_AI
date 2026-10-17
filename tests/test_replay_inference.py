"""Inference-only algebra must preserve the existing network's outputs."""
import pytest
import torch
from replay_il_inference import InferenceKernel,freeze_kernel
from test_replay_runtime import model_book


@pytest.mark.parametrize('batch',[1,3,64])
@pytest.mark.parametrize('history',[1,4,8])
@pytest.mark.parametrize('frozen',[False,True])
def test_one_query_kernels_match_full_history_and_masked_spatial_encoder(model_book,batch,history,frozen):
    model,_=model_book;original=InferenceKernel(model)
    kernel=freeze_kernel(original) if frozen else original
    generator=torch.Generator().manual_seed(batch*history+56)
    observations=(torch.randn(batch,1,32,generator=generator),torch.randn(batch,41,24,generator=generator),torch.zeros(batch,41))
    observations[2][:,2:6]=-10000.
    features=torch.randn(batch,history,128,generator=generator)
    before={key:tensor.clone() for key,tensor in model.state_dict().items()}
    with torch.inference_mode():
        actual=kernel.encode(observations);expected=model.encoder(observations)
        torch.testing.assert_close(actual,expected,atol=3e-6,rtol=3e-6)
        x=model.project(features)+model.position[:,:history]
        x=model.norm(model.temporal(x,mask=original.causal[:history,:history])[:,-1])
        expected=(model.policy(x),torch.cat([head(x).tanh() for head in model.values],-1))
        actual=kernel.decode(features)
        for a,b in zip(actual,expected):torch.testing.assert_close(a,b,atol=3e-6,rtol=3e-6)
    for key,tensor in model.state_dict().items():torch.testing.assert_close(tensor,before[key],atol=0,rtol=0)


def test_kernel_rejects_incompatible_training_architecture(model_book):
    import copy
    model=copy.deepcopy(model_book[0]);model.temporal.layers[-1].dropout.p=.1
    with pytest.raises(ValueError,match='zero-dropout'):InferenceKernel(model)
