from pathlib import Path
import hashlib
import json
from types import SimpleNamespace as S

import numpy as np
import pytest

from slater_nexto_live_build_v038c import instrument,build,sha,EXPECTED_BOT_SHA,EXPECTED_OBS_SHA
from slater_nexto_live_analyze_v038c import compare,load
from slater_nexto_scheduler_v038b import NextoV4Clock
from slater_nexto_probe_v038c import control_vec,flush,record

SOURCE=Path(__file__).resolve().parents[1]/'slater_v038c_source'


def test_original_source_verification():
    assert sha(SOURCE/'bot.py')==EXPECTED_BOT_SHA
    assert sha(SOURCE/'nexto_obs.py')==EXPECTED_OBS_SHA


def test_instrument_exact_not_double():
    code=(SOURCE/'bot.py').read_text()
    patched=instrument(code)
    assert 'slater_nexto_probe_v038c' in patched
    assert patched.count('_v038c_capture(self')==1
    assert code!=patched
    with pytest.raises(ValueError):instrument(patched)


def test_instrument_fails_for_unsupported():
    with pytest.raises(ValueError):instrument('def get_output(self): return None')


def test_builder_prevents_overwrite(tmp_path,monkeypatch):
    import slater_nexto_live_build_v038c as m
    root=tmp_path
    model=root/'vendor'/'nexto'/'nexto-model.pt'
    model.parent.mkdir(parents=True)
    model.write_bytes(b'fake original for test only')
    monkeypatch.setattr(m,'EXPECTED_MODEL_SHA',sha(model))
    dest=build(root,'data/isolated/slater_v038c_nexto_fake01','vendor/nexto/nexto-model.pt')
    assert dest.is_dir() and (dest/'bot.py').is_file() and (dest/'agent.py').is_file()
    assert 'v038c LIVE PROBE' in (dest/'bot.cfg').read_text()
    assert sha(dest/'nexto-model.pt')==sha(model)
    with pytest.raises(FileExistsError):build(root,'data/isolated/slater_v038c_nexto_fake01','vendor/nexto/nexto-model.pt')


def test_builder_refuses_outside(tmp_path):
    with pytest.raises(ValueError):build(tmp_path,'data/rlbot_exports/V60')


def test_builder_refuses_wrong_weights(tmp_path):
    m=tmp_path/'vendor/nexto/nexto-model.pt';m.parent.mkdir(parents=True);m.write_bytes(b'V60 is forbidden')
    with pytest.raises(ValueError):build(tmp_path,'data/isolated/slater_v038c_nexto_test','vendor/nexto/nexto-model.pt')


def example_trace():
    m=NextoV4Clock(hardcoded=True,stochastic=True)
    rows=[]
    for i in range(175):
        action=np.asarray([1,0,0,0,0,0,1,0],dtype=np.float32)
        was=[]
        def infer(prev,beta):
            was.append(beta)
            return 16,action
        f=m.frame(is_kickoff_pause=True,ball_xy=[0,0],
                  positions=np.array([[0,-4608],[0,4608]]),teams=np.array([0,1]),
                  index=1,infer=infer)
        rows.append({'kind':'frame','packet_index':i,'ticks_elapsed':1,'seconds_elapsed':i/120,
                 'is_kickoff_pause':True,'is_round_active':True,'is_match_ended':False,
                 'ball_xy':[0,0], 'cars':[{'pos':[0,-4608],'team':0},{'pos':[0,4608],'team':1}],
                 'player_index':1,'neural_updated':f.neural_updated,
                 'selected_nn_action':action.tolist() if f.neural_updated else None,
                 'selected_beta':f.beta,'post_action':f.action.tolist(),
                 'controls':f.controls.tolist(),'kickoff_index':f.kickoff_index})
    return {'schema':'slater_nexto_live_v038c_v1','flags':{'hardcoded':True,'stochastic':True,'beta':1,'tick_skip':8}},rows


def test_analyzer_success_synthetic():
    meta,rows=example_trace()
    result=compare(meta,rows)
    assert result['status']=='LIVE_CONTROL_SCHEDULER_PARITY_PASS'
    assert result['script_applied_predicted']==168
    assert result['neural_updates_predicted']==23
    assert not any(result['mismatch_by_field'].values())


def test_analyzer_detects_controller_divergence():
    meta,rows=example_trace()
    rows[44]['controls'][1]=0.125
    result=compare(meta,rows)
    assert result['status']=='LIVE_CONTROL_SCHEDULER_MISMATCH'
    assert result['mismatch_by_field']['final_controls']==1


def test_load_jsonl(tmp_path):
    meta,rows=example_trace()
    p=tmp_path/'capture.jsonl'
    p.write_text(json.dumps(meta)+'\n'+json.dumps(rows[0])+'\n')
    h,r=load(p)
    assert len(r)==1 and h['schema']==meta['schema']


def test_control_vec_and_capture_flush(tmp_path):
    x=S(throttle=1.,steer=-1.,pitch=0.5,yaw=0.,roll=0.,jump=True,boost=False,handbrake=True)
    assert control_vec(x)==[1.,-1.,0.5,0.,0.,1.,0.,1.]
    bot=S(_v038c_file=tmp_path/'trace.jsonl',_v038c_count=0,_v038c_buffer=[],index=0,
          action=np.zeros(8),controls=x,kickoff_index=-1)
    car=S(physics=S(location=S(x=0,y=-4608,z=17)),team=0)
    ball=S(physics=S(location=S(x=0,y=0,z=93)))
    pkt=S(game_info=S(seconds_elapsed=1.,is_kickoff_pause=True,is_round_active=True,is_match_ended=False),
          game_cars=[car],num_cars=1,game_ball=ball)
    record(bot,pkt,1,False,None,None)
    flush(bot)
    assert json.loads(bot._v038c_file.read_text())['kind']=='frame'
