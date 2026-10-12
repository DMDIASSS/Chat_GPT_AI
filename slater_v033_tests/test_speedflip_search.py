from pathlib import Path
from types import SimpleNamespace
import sys
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import slater_speedflip_search_v033 as s


def params():
    return {'start':22,'held':7,'released':4,'dodge':2,'cancel':30,
            'diag':.72,'airroll':.68,'correction':0,'first_pitch':0.,'correction_pitch':0.}


def test_speedflip_action_has_two_distinct_jump_edges_and_dodge_yaw():
    a=s.macro(params())
    assert a.shape==(240,8)
    assert np.all(a[22:29,5]==1)
    assert np.all(a[29:33,5]==0)
    assert np.all(a[33:35,5]==1)
    assert np.all(a[33:35,2]==-1)
    assert np.all(a[33:35,3]<0)
    assert np.all(a[35:65,2]==1)
    assert np.all(a[:,6]==1)
    assert np.isfinite(a).all()


def test_mirrored_macro_and_no_out_of_bounds():
    left=s.macro(params(),side=-1);right=s.macro(params(),side=1)
    assert np.array_equal(left[:,3],-right[:,3])
    assert np.array_equal(left[:,4],-right[:,4])
    assert np.array_equal(left[:,5],right[:,5])
    with pytest.raises(ValueError):s.macro(params(),side=0)
    with pytest.raises(ValueError):s.macro(params(),ticks=99)


def test_seed_partition_and_reproducible_search_config():
    x=s.seed_list(777,3);y=s.seed_list(777,3,holdout=True)
    assert len(set(x))==3 and set(x).isdisjoint(y)
    from random import Random
    assert s.random_params(Random(123))==s.random_params(Random(123))
    with pytest.raises(ValueError):s.seed_list(777,21)


def fake_run(prog,*,ground=True,alignment=1.,upright=1.,speed=2300.):
    return {'metrics':{'144':{'forward_progress':prog*.5},
                       '192':{'forward_progress':prog*.78},
                       '240':{'forward_progress':prog,'on_ground':ground,
                              'alignment':alignment,'upright_z':upright,'forward_speed':speed}}}


def test_qualification_rejects_ungrounded_unaligned_and_slow_macros():
    baseline=fake_run(3000)
    assert s.qualified(fake_run(3100),baseline)
    assert not s.qualified(fake_run(3020),baseline)
    assert not s.qualified(fake_run(3500,ground=False),baseline)
    assert not s.qualified(fake_run(3500,alignment=.5),baseline)
    assert not s.qualified(fake_run(3500,upright=-1),baseline)
    assert not s.qualified(fake_run(3500,speed=500),baseline)
    assert s.score(fake_run(3500),baseline)>s.score(fake_run(2000,ground=False),baseline)


def test_report_creatonly_guard(tmp_path):
    good=tmp_path/'data'/'isolated'/'speed.json'
    assert s.checked_out(str(good),tmp_path)==good
    good.parent.mkdir(parents=True);good.write_text('{}')
    with pytest.raises(FileExistsError):s.checked_out(str(good),tmp_path)
    with pytest.raises(ValueError):s.checked_out(str(tmp_path/'overwritten.pt'),tmp_path)
    with pytest.raises(ValueError):s.checked_out(str(tmp_path/'any.json'),tmp_path)


def test_search_mock_physics_prefers_best_then_validates_new_seeds(monkeypatch):
    def fake_physics(frames,seed):
        # Encodes larger progress if any jump; never depends on run order.
        progressed=3100 if (frames[:,5]>.5).any() else 3000
        return {'seed':seed,**fake_run(progressed)}
    monkeypatch.setattr(s,'run_physics',fake_physics)
    result=s.search(3,[1,2],[100,101],17)
    assert result['validated'] and result['holdout_progress_gain_uu']==[100.,100.]
    assert result['train_count']==2 and len(result['heldout_candidate'])==2
