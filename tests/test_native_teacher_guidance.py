import numpy as np
import pytest
from nexto_teacher import nexto_actions
from slater_native_actor import action_mask
from slater_native_teacher_guidance import project_controls


def car(ground=True,boost=50):
    return dict(ground=ground,boost=boost,flipped=False,double_jumped=False,air_time=0,world_contact=False,contact_normal=[0,0,0])


def test_ground_projection_keeps_throttle_and_boost_from_aerial_teacher_action():
    table=nexto_actions();c=car();mask=action_mask(c)
    source=next(i for i,a in enumerate(table) if not mask[i] and a[0]==1 and a[6]==1 and a[1]==0 and a[5]==0 and a[7]==0)
    p=np.zeros(90);p[source]=1;target=project_controls(p,c);chosen=table[target.argmax()]
    assert target.sum()==pytest.approx(1) and np.all(target[~mask]==0)
    assert chosen[0]==1 and chosen[6]==1 and chosen[5]==0 and np.all(chosen[2:5]==0)
    assert target[8]==0


def test_projection_preserves_feasible_actions_and_total_mass():
    c=car();mask=action_mask(c);p=np.zeros(90);p[mask]=np.arange(1,mask.sum()+1);p/=p.sum()
    assert np.allclose(project_controls(p,c),p)
    rng=np.random.default_rng(1);p=rng.random(90)
    for c in [car(),car(False),car(boost=0),car(False,0)]:
        y=project_controls(p,c);assert y.sum()==pytest.approx(1) and not np.any(y[~action_mask(c)])


def test_projection_rejects_invalid_teacher_signals():
    for p in [np.zeros(90),np.full(90,np.nan),np.ones(89),-np.ones(90)]:
        with pytest.raises(ValueError):project_controls(p,car())


def test_grounded_focus_starts_match_native_flat_orientation():
    from rlgym.rocket_league.sim import RocketSimEngine
    from rlgym.rocket_league.state_mutators import FixedTeamSizeMutator,KickoffMutator
    from slater_focus_evaluation import setup
    engine=RocketSimEngine(rlbot_delay=False)
    try:
        for side in ['blue','orange']:
            s=engine.create_base_state();FixedTeamSizeMutator(blue_size=1,orange_size=1).apply(s,{});KickoffMutator().apply(s,{})
            ours=side+'-0';enemy=('orange' if side=='blue' else 'blue')+'-0'
            setup(s,'touch_warmup',ours,enemy,42,0)
            for c in s.cars.values():assert np.allclose(c.physics.rotation_mtx[:,2],[0,0,1]) and c.on_ground
    finally:engine.close()


def test_teacher_is_frozen_and_evaluated_without_changing_weights(tmp_path,monkeypatch):
    import torch
    import slater_native_teacher_guidance as module
    model=torch.nn.Linear(2,2);model.train();teacher=tmp_path/'teacher.pt';teacher.write_bytes(b'checkpoint identity')
    before={k:v.clone() for k,v in model.state_dict().items()}
    monkeypatch.setattr(module,'load',lambda path:model)
    frozen=module.FrozenTeacher(teacher)
    assert frozen.actor is model and not model.training and all(not p.requires_grad for p in model.parameters())
    assert all(torch.equal(v,before[k]) for k,v in model.state_dict().items())


def test_guided_continuation_preserves_latest_source_and_resume_pins_it(tmp_path):
    import json
    from slater_native_focus_curriculum import continuation_source
    old=tmp_path/'old';old.mkdir();new=tmp_path/'new';new.mkdir();source=tmp_path/'11152448';source.mkdir()
    for name in ['POLICY.lt','SHARED_HEAD.lt','CRITIC.lt','RUNNING_STATS.json','POLICY_OPTIM.lt','SHARED_HEAD_OPTIM.lt','CRITIC_OPTIM.lt']:(source/name).write_bytes(b'identity fixture')
    (old/'status.json').write_text(json.dumps(dict(status='RUNNING',latest=str(source))))
    with pytest.raises(ValueError,match='Pause the old'):continuation_source(new,old)
    (old/'status.json').write_text(json.dumps(dict(status='PAUSED',latest=str(source))))
    assert continuation_source(new,old)==str(source)
    (new/'protocol.json').write_text(json.dumps(dict(source=dict(path=str(source)))))
    (old/'status.json').write_text(json.dumps(dict(status='RUNNING',latest='different_source')))
    assert continuation_source(new,old)==str(source)
