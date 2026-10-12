import importlib.util
from pathlib import Path
import sys, json
import pytest
ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location('slater_nexto_tick_eval_v038b',ROOT/'slater_nexto_tick_eval_v038b.py')
# The eval imports scheduler at module scope; add build to path for isolated unit tests.
sys.path.insert(0,str(ROOT))
mod=importlib.util.module_from_spec(SPEC);sys.modules[SPEC.name]=mod;SPEC.loader.exec_module(mod)

def test_report_create_only(tmp_path):
    (tmp_path/'data'/'isolated').mkdir(parents=True)
    f=mod.outpath(tmp_path,'data/isolated/test01.json')
    f.write_text('{}')
    with pytest.raises(FileExistsError):mod.outpath(tmp_path,'data/isolated/test01.json')
    with pytest.raises(ValueError):mod.outpath(tmp_path,'data/vendor/nexto-model.json')
    with pytest.raises(ValueError):mod.outpath(tmp_path,'../escape.json')

def test_valid_provenance_gate(tmp_path):
    d=tmp_path/'data'/'isolated';d.mkdir(parents=True)
    a={'test':'eight_ticks_batch_vs_eight_single_ticks','passed':True,'blocks_checked':12,
       'max_abs_error':0.,'nexto_script_sha':mod.KICKOFF_SHA}
    b={'test':'same_state_reference_nexto_vs_teamobserver','allclose':True,'fail_count':0,
       'pass_count':528,'action_disagreement_count':0,
       'reference_nexto_obs_sha256':mod.KNOWN_OBS_SHA}
    (d/'a.json').write_text(json.dumps(a));(d/'b.json').write_text(json.dumps(b))
    assert mod.gate(tmp_path,'data/isolated/a.json','eight_ticks_batch_vs_eight_single_ticks','passed')['test']==a['test']
    assert mod.gate(tmp_path,'data/isolated/b.json','same_state_reference_nexto_vs_teamobserver','allclose')['test']==b['test']
    a['max_abs_error']=0.4
    (d/'a.json').write_text(json.dumps(a))
    with pytest.raises(ValueError):mod.gate(tmp_path,'data/isolated/a.json','eight_ticks_batch_vs_eight_single_ticks','passed')

def test_trace_contains_all_scripted_ticks():
    report=mod.trace(n=175)
    assert report['script_applied']==168
    assert report['script_sha']==mod.KICKOFF_SHA
    assert report['control_trace'][0]['tick']==0
    stop=mod.trace(n=60,ball_move_tick=24)
    assert stop['script_applied']==24
    assert stop['interrupted']>0

def test_one_tick_adapter_stops_on_observed_contact(monkeypatch):
    import types
    import numpy as np
    class Physics:
        def __init__(self,xyz):self.position=np.asarray(xyz,dtype=float)
    class Car:
        def __init__(self,team,y):
            self.team_num=team
            self.physics=Physics([0,y,17])
            self.ball_touches=0
    class Ball:
        def __init__(self):self.position=np.array([0.,0.,93.])
    class State:
        def __init__(self):
            self.ball=Ball()
            self.cars={'blue-0':Car(0,-4608),'orange-0':Car(1,4608)}
            self.goal_scored=False
    class Engine:
        def __init__(self,state):self.state=state;self.calls=0
        def step(self,commands,shared):
            self.calls+=1
            assert all(a.shape==(1,8) for a in commands.values())
            for c in self.state.cars.values():c.ball_touches=0
            if self.calls==4:
                self.state.cars['blue-0'].ball_touches=1
                self.state.ball.position[1]=50
            return self.state
    class Base:
        def __init__(self):
            self.state=State();self.engine=Engine(self.state)
            self.student_side='blue';self.t=0;self.total_reward=0.;self.touches=0
            self.opponent_touches=0;self.max_steps=20
            self.previous={};self.obs=None;self.observer=object();self.opponent=None
    fake_old=types.ModuleType('slater_nexto_kickoff_v037a')
    fake_old.sample_nexto_action=lambda *args,**kwargs:5
    fake_base=types.ModuleType('slater_cycle9_native_ppo_v025')
    fake_base.ACTION_REPEAT=8
    fake_base.read_obs=lambda *args,**kwargs:(np.ones((1,1),dtype=np.float32),)
    monkeypatch.setitem(sys.modules,'slater_nexto_kickoff_v037a',fake_old)
    monkeypatch.setitem(sys.modules,'slater_cycle9_native_ppo_v025',fake_base)
    wrapped=mod.TickNextoEnv.__new__(mod.TickNextoEnv)
    wrapped.base_env=Base()
    wrapped.actions=np.repeat(np.array([[1,0,0,0,0,0,1,0]],dtype=np.float32),90,axis=0)
    wrapped.mode='nexto_stock_tick';wrapped.device='cpu'
    wrapped.scheduler=mod.NextoV4Clock(hardcoded=True,stochastic=True)
    wrapped.kickoff_pause_proxy=True
    wrapped.script_control_blocks=0;wrapped.ticks_stepped=0
    _,_,done,info=wrapped.step(4)
    assert not done
    assert wrapped.base_env.engine.calls==8
    assert info['script_physics_ticks']==4
    assert info['stochastic_neural_inferences']>0
    assert info['student_touches']==1
    assert not info['kickoff_pause_proxy']
    assert wrapped.base_env.previous['orange-0'].shape==(8,)
