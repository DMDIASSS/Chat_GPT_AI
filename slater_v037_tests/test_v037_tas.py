import sys,struct
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
import pytest
import slater_tas_phases_v037 as m


def test_tas_frames_and_phases(tmp_path):
    frames=[(0,[0.]*7)]*20+[(3,[.8]+[0.]*6)]*50+[(3,[0.]*7)]*40
    path=tmp_path/'controller.data'
    raw=struct.pack('<II',1,len(frames))+b''.join(m.REC.pack(mask,*v) for mask,v in frames)+bytes(128)
    path.write_bytes(raw)
    report=m.analyze_file(path)
    assert report['frames']==110
    assert report['phases'][0]['start_frame']==0
    assert report['phases'][-1]['end_frame_exclusive']==110
    assert sum(p['frames'] for p in report['phases'])==110
    assert not report['ready_for_behavior_cloning']


def test_tas_bad_bytes_rejected(tmp_path):
    path=tmp_path/'bad.data';path.write_bytes(bytes(3))
    with pytest.raises(ValueError):m.read_raw(path)


def test_labels_are_tentative():
    assert m.tentative_label('nice flip reset.data')=='flip_reset_demo'
    assert m.tentative_label('2 player tas.data').startswith('multi_actor_named_demo')
