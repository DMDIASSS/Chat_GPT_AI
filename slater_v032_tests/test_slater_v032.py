from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import json
import numpy as np
import pytest
import slater_kickoff_heldout_v032 as m
import slater_kickoff_audit_v032 as a

def row(policy, episode, win, *, rep=0):
    return {'policy':policy,'episode':episode,'repeat':rep,'seed':11+episode,'side':'blue' if episode%2==0 else 'orange',
            'mode':'nexto','kickoff_signature':'start'+str(episode),'outcome':win,
            'first_touch':'student' if win>0 else 'opponent','fake_takeover_proxy':False,
            'fake_attempted':False,'final_ball_progress':win*100.0}

def test_summary():
    o=m.summarize([row('x',0,1),row('x',1,-1),row('x',2,0)])
    assert o['games']==3 and o['wins']==1 and o['losses']==1 and o['draws']==1
    assert o['mean_ball_progress_uu']==0

def test_paired_bootstrap_exact_difference():
    old=[row('original_u60',i,-1) for i in range(12)]
    new=[row('candidate',i,1) for i in range(12)]
    stats=m.seeded_stats({'original_u60':old,'candidate':new},1,samples=100)
    assert stats['deltas']['win']['delta']==1
    assert stats['deltas']['win']['bootstrap_95ci']==[1.,1.]
    assert stats['paired_count']==12

def test_pair_rejects_start_mismatch():
    old=[row('original_u60',0,-1)];new=[row('candidate',0,1)]
    new[0]['kickoff_signature']='wrong'
    with pytest.raises(RuntimeError,match='START_STATE_MISMATCH'):
        m.seeded_stats({'original_u60':old,'candidate':new},42,samples=5)

def test_report_path_guard():
    with TemporaryDirectory() as td:
        root=Path(td);safe=root/'data'/'isolated';safe.mkdir(parents=True)
        assert m.checked_destination(safe/'new.json',root)==(safe/'new.json').resolve()
        with pytest.raises(ValueError):m.checked_destination(root/'champion.json',root)
        (safe/'old.json').write_text('data')
        with pytest.raises(FileExistsError):m.checked_destination(safe/'old.json',root)

def test_audit_disjoint_splits():
    with TemporaryDirectory() as td:
        root=Path(td)
        for split,sha in [('train','a'*64),('validation','b'*64),('test','c'*64)]:
            folder=root/split;folder.mkdir()
            np.savez_compressed(folder/f'{sha[:14]}_kickoff000.npz',replay_sha=np.array(sha),
                                source_period=np.int64(0),split=np.array(split),
                                blue_position=np.array([0.,-2000.,17.]),orange_position=np.array([0.,2000.,17.]),
                                ball_position=np.array([0.,0.,93.]))
        d=a.audit(root)
        assert d['safe_for_heldout'] and d['by_split']['test']['scenarios']==1
        # Same replay SHA appearing in a different split must be detected.
        f=root/'validation'/'bbbbbbbbbbbbbb_kickoff000.npz'
        f.unlink()
        np.savez_compressed(f,replay_sha=np.array('a'*64),source_period=np.int64(1),
                            split=np.array('validation'),blue_position=np.zeros(3),
                            orange_position=np.zeros(3),ball_position=np.zeros(3))
        assert not a.audit(root)['safe_for_heldout']
