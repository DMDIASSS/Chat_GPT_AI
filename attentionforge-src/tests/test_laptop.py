import importlib.util
from pathlib import Path
from types import SimpleNamespace as NS
import numpy as np
import torch
from torch.distributions import Categorical
from attentionforge.runtime import config,batch
from attentionforge.observation import encode,encode_reference
from attentionforge.performance import sample_actions,RolloutStore
from attentionforge.model import ActorCritic
from test_contracts import native

@native
def test_native_encoder_matches_portable_encoder_all_team_sizes():
    rng=np.random.default_rng(1539)
    for team in (1,2,3):
        c=config();c['team_size']=team;e=batch(c,n=3)
        for _ in range(9):
            r=e.step(rng.integers(0,90,(3,team*2),dtype=np.int64));loc=e.pad_locations()
            a,m=encode(r['world'],r['pads'],loc);b,n=encode_reference(r['world'],r['pads'],loc)
            np.testing.assert_allclose(a,b,atol=2e-6,rtol=2e-6);np.testing.assert_array_equal(m,n)

@native
def test_native_simple_rewards_match_existing_rlgym_classes():
    from rlgym.rocket_league.reward_functions import GoalReward
    from rlgym_tools.rocket_league.reward_functions.advanced_touch_reward import AdvancedTouchReward
    from rlgym_tools.rocket_league.reward_functions.velocity_player_to_ball_reward import VelocityPlayerToBallReward
    c=config();c['rewards']={'profile':'rlgym_simple_v1','goal':10.,'approach':1.,'touch':.25,'control_progress':0.};e=batch(c,n=2,kickoffs=True)
    def state(w,t,g=0,touches=(0,0)):
        ball=NS(position=w[0,:3],linear_velocity=w[0,3:6]);cars={j:NS(team_num=j,ball_touches=int(touches[j]),physics=NS(position=w[j+1,:3],linear_velocity=w[j+1,3:6])) for j in range(2)}
        return NS(ball=ball,cars=cars,tick_count=t,goal_scored=g!=0,scoring_team=0 if g>0 else 1)
    # Include a goal and a collision, not only empty random trajectories.
    w=e.observe()['world'];w[0,0,:3]=[0,5100,100];w[0,0,3:6]=[0,1800,0];w[0,1,:3]=[-2000,-3000,17];w[0,2,:3]=[2000,3000,17]
    w[1,0,:3]=[0,0,94];w[1,1,:3]=[-140,0,17];w[1,1,3:6]=[700,0,0];w[1,2,:3]=[2000,3000,17]
    for i in range(2):e.test_state(i,w[i])
    rewards=[];ticks=[0,0];raw=e.observe()
    for i in range(2):
        group=[GoalReward(),VelocityPlayerToBallReward(include_negative_values=False),AdvancedTouchReward(use_touch_count=False)]
        for r in group:r.reset([0,1],state(raw['world'][i],0),{})
        rewards.append(group)
    seen_goal=seen_touch=False
    for _ in range(40):
        raw=e.step(np.full((2,2),8,np.int64))
        for i in range(2):
            ticks[i]+=int(raw['info'][i,7]);g=raw['info'][i,0];hits=raw['info'][i,1:3];s=state(raw['final_world'][i],ticks[i],g,hits)
            vals=[r.get_rewards([0,1],s,{0:bool(raw['terminated'][i]),1:bool(raw['terminated'][i])},{0:bool(raw['truncated'][i]),1:bool(raw['truncated'][i])},{}) for r in rewards[i]]
            expected=[10*vals[0][j]+vals[1][j]+.25*vals[2][j] for j in range(2)]
            np.testing.assert_allclose(raw['rewards'][i],expected,rtol=2e-5,atol=2e-6)
            seen_goal|=bool(g);seen_touch|=bool(np.any(hits))
            if raw['terminated'][i] or raw['truncated'][i]:
                for r in rewards[i]:r.reset([0,1],state(raw['world'][i],ticks[i]),{})
    assert seen_goal and seen_touch

def test_sampler_probabilities_log_probs_and_legal_actions():
    torch.set_num_threads(1);torch.manual_seed(621)
    logits=torch.tensor([[-1.,0.,1.,-1e9]]).expand(60000,-1)
    a,lp=sample_actions(logits);expected=Categorical(logits=logits,validate_args=False)
    torch.testing.assert_close(lp,expected.log_prob(a));assert not (a==3).any()
    np.testing.assert_allclose(torch.bincount(a,minlength=4).numpy()/len(a),logits[0].softmax(-1).numpy(),atol=.008)

def test_cpu_rollout_cache_matches_arrays():
    rng=np.random.default_rng(42);a=rng.normal(size=(12,5)).astype(np.float32);b=rng.integers(0,2,(12,3)).astype(bool);s=RolloutStore([a,b],torch.device('cpu'));idx=np.array([8,2,11,0]);x,y=s.get(s.permutation(idx));np.testing.assert_array_equal(x,a[idx]);np.testing.assert_array_equal(y,b[idx]);assert not s.cached

def test_laptop_model_has_expected_capacity():
    torch.set_num_threads(1);n=ActorCritic(width=256,heads=4,blocks=2)
    assert sum(x.numel() for x in n.parameters())==1091163

def test_attention_fastpath_matches_original_outputs_and_gradients():
    import copy
    from attentionforge.model import QueryBlock
    torch.set_num_threads(1);torch.manual_seed(198)
    old=QueryBlock(64,4);new=copy.deepcopy(old)
    x=torch.randn(7,43,64);q=torch.randn(7,1,64);padding=torch.rand(7,43)<.25;padding[:,0]=False
    def reference(block):
        k=block.knorm(x);a=q+block.attention(block.qnorm(q),k,k,key_padding_mask=padding,need_weights=False)[0]
        return a+block.ff(block.norm(a))
    a=reference(old);b=new(q,x,padding);torch.testing.assert_close(a,b,rtol=2e-5,atol=2e-6)
    a.square().mean().backward();b.square().mean().backward()
    for (name,p),(_,other) in zip(old.named_parameters(),new.named_parameters()):torch.testing.assert_close(p.grad,other.grad,rtol=3e-4,atol=2e-7,msg=name)
