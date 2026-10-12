import json
from pathlib import Path
import sys
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from slater_v036_build_verify import verify, MODES, NEXTO_SHA
from slater_v036_analyze import analyze
from slater_v036_telemetry import note


def test_all_modes_have_verified_weights_and_flags():
    result=verify(ROOT/'data/rlbot_exports/slater_v036_nexto_modes')
    assert len(result)==4
    assert {v['nexto_sha256'] for v in result.values()}=={NEXTO_SHA}
    assert {(v['hardcoded_kickoffs'],v['stochastic_kickoffs']) for v in result.values()}=={(False,False),(False,True),(True,False),(True,True)}


def test_name_configs_and_safe_code():
    for name in MODES:
        p=ROOT/'data/rlbot_exports/slater_v036_nexto_modes'/name
        assert name.replace('_',' ') in (p/'bot.cfg').read_text()
        assert '_v036_note(self, packet' in (p/'bot.py').read_text()


def test_analyzer_finished_and_incomplete(tmp_path):
    p=tmp_path/'a.jsonl'
    events=[{'type':'metadata','mode':'Nexto_NN_Greedy','team':0,'index':0},
            {'type':'kickoff_start','t':10,'kickoff':1},
            {'type':'first_touch','t':11,'player_index':0,'kickoff':1},
            {'type':'score_change','t':20,'score':[1,0]},
            {'type':'match_end','t':30,'score':[2,1]}]
    p.write_text('\n'.join(map(json.dumps,events)))
    r=analyze([p]); v=r['modes']['Nexto_NN_Greedy']
    assert v['completed_matches']==1 and v['wins']==1 and v['first_touch_nexto']==1
    p2=tmp_path/'b.jsonl'
    p2.write_text('\n'.join(map(json.dumps,events[:-1])))
    r=analyze([p2]); v=r['modes']['Nexto_NN_Greedy']
    assert v['completed_matches']==0 and v['win_rate'] is None


def test_read_only_telemetry_no_action_override(tmp_path,monkeypatch):
    import slater_v036_telemetry as m
    monkeypatch.setattr(m,'__file__',str(tmp_path/'logger.py'))
    vec=lambda x=0,y=0,z=0: SimpleNamespace(x=x,y=y,z=z)
    car=SimpleNamespace(physics=SimpleNamespace(location=vec(12,3,17),velocity=vec(30,0,0)),boost=33)
    ball=SimpleNamespace(physics=SimpleNamespace(location=vec(0,0,93),velocity=vec()),latest_touch=SimpleNamespace(time_seconds=-1,player_index=-1))
    ctl=SimpleNamespace(throttle=1,steer=0,pitch=0,yaw=0,roll=0,jump=False,boost=True,handbrake=False)
    bot=SimpleNamespace(index=0,team=0,controls=ctl)
    packet=SimpleNamespace(game_info=SimpleNamespace(seconds_elapsed=0.,is_kickoff_pause=True,is_match_ended=False),game_ball=ball,game_cars=[car],teams=[SimpleNamespace(score=0),SimpleNamespace(score=0)])
    for i in range(9):
        packet.game_info.seconds_elapsed=i/120
        note(bot,packet,'Nexto_NN_Greedy')
    assert ctl.throttle==1 and ctl.boost is True
    log=list((tmp_path/'kickoff_logs_v036').glob('*.jsonl'))
    assert len(log)==1
    events=[json.loads(line) for line in log[0].read_text().splitlines()]
    assert events[0]['type']=='metadata'
    assert 'kickoff_start' in [x['type'] for x in events]
    assert 'snapshot' in [x['type'] for x in events]


def test_telemetry_scores_and_end(tmp_path,monkeypatch):
    import slater_v036_telemetry as m
    monkeypatch.setattr(m,'__file__',str(tmp_path/'logger.py'))
    vec=lambda: SimpleNamespace(x=0,y=0,z=0)
    car=SimpleNamespace(physics=SimpleNamespace(location=vec(),velocity=vec()),boost=22)
    ball=SimpleNamespace(physics=SimpleNamespace(location=vec(),velocity=vec()),latest_touch=SimpleNamespace(time_seconds=0,player_index=0))
    ctl=SimpleNamespace(throttle=0,steer=0,pitch=0,yaw=0,roll=0,jump=False,boost=False,handbrake=False)
    bot=SimpleNamespace(index=0,team=0,controls=ctl)
    gi=SimpleNamespace(seconds_elapsed=0,is_kickoff_pause=True,is_match_ended=False)
    pkt=SimpleNamespace(game_info=gi,game_ball=ball,game_cars=[car],teams=[SimpleNamespace(score=0),SimpleNamespace(score=0)])
    note(bot,pkt,'Nexto_Stock')
    gi.seconds_elapsed=4;gi.is_kickoff_pause=False;ball.latest_touch.time_seconds=2
    note(bot,pkt,'Nexto_Stock')
    pkt.teams[0].score=1;gi.seconds_elapsed=6
    note(bot,pkt,'Nexto_Stock')
    gi.seconds_elapsed=300;gi.is_match_ended=True
    note(bot,pkt,'Nexto_Stock')
    r=analyze([bot._v036_log]); s=r['sessions'][0]
    assert s['finished'] and s['nexto_first_touches']==1 and s['score_blue_orange']==[1,0]
