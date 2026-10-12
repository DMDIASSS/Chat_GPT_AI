import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pytest
import slater_human_input_v035 as m


def test_accepts_valid_packet():
    r = m.make_record({'t':'input','throttle':1},42,'2026-01-01')
    assert r['data']['throttle'] == 1 and r['recv_monotonic_ns'] == 42


def test_rejects_bad_packet():
    with pytest.raises(ValueError):
        m.make_record({'t':'poll'},42,'')


def test_refuses_existing(tmp_path):
    p = tmp_path / 'old.jsonl'
    p.write_text('hi')
    with pytest.raises(FileExistsError):
        m.safe_output(str(p))


def test_refuses_wrong_extension(tmp_path):
    with pytest.raises(ValueError):
        m.safe_output(str(tmp_path/'a.pt'))


def test_summary(tmp_path):
    p = tmp_path/'input.jsonl'
    rows = [
        {'recv_monotonic_ns':1000000000,'data':{'t':'settings'}},
        {'recv_monotonic_ns':1000000000,'data':{'t':'input','onGround':1,'holdBoost':1,'jump':0,'dodgeT':0,'vel':[3,4,0]}},
        {'recv_monotonic_ns':1010000000,'data':{'t':'input','onGround':0,'holdBoost':0,'jump':1,'dodgeT':0.1,'vel':[0,0,0]}},
        {'recv_monotonic_ns':1020000000,'data':{'t':'input','onGround':0,'holdBoost':1,'jump':1,'dodgeT':0.2,'vel':[0,0,0]}},
        {'recv_monotonic_ns':1030000000,'data':{'t':'input','onGround':1,'holdBoost':1,'jump':0,'dodgeT':0,'vel':[0,0,0]}},
    ]
    p.write_text('\n'.join(json.dumps(x) for x in rows)+'\n')
    r = m.parse_capture(p)
    assert r['input_frames']==4 and r['settings_messages']==1
    assert r['dodge_starts_detected']==1
    assert r['observed_rate_hz']==100
    assert r['boost_held_fraction']==0.75


def test_corrupted_line(tmp_path):
    p=tmp_path/'bad.jsonl'
    p.write_text('{bad}\n')
    assert m.parse_capture(p)['corrupt_records']==1
