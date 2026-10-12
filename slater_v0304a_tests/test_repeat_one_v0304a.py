import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import pytest
import slater_stochastic_benchmark_v0304a as m


def dummy_game(policy, side, seed, reg, ot):
    w=policy!='original'
    return dict(seed=seed,side=side,goals_for=int(w),goals_against=0,goal_diff=int(w),
                outcome=int(w),draw=not w,decisions=reg,touches=10,opponent_touches=5,
                kickoffs=1,first_kickoff_signature='s'+str(seed),overtime=False,goal_events=[])


def test_repeats_one_core_evaluator():
    result=m.evaluate_stochastic(dummy_game,['original','u60'],3,1,123,300,0)
    assert len(result['records'])==12
    assert result['overall']['u60']['matches']==6
    assert result['paired_vs_original']['u60']['win_rate']['num_seed_pairs']==3


def test_main_allows_repeat_one_and_writes_readonly_json(monkeypatch, tmp_path):
    import slater_stochastic_benchmark_v0304a as m
    original_path=tmp_path/'original.pt'; original_path.write_bytes(b'original')
    checkpoint=tmp_path/'candidate.pt'; checkpoint.write_bytes(b'candidate')
    def protected_paths(root): return original_path, root/'nexto-model.pt', 'original_sha'
    def checked_candidate(filename,root,sha,ns):
        assert filename == str(checkpoint)
        return checkpoint,{'meta':{'nexto_sha':ns},'global_updates':60}
    monkeypatch.setattr(m.workers,'protected_paths',protected_paths)
    monkeypatch.setattr(m.heldout,'checked_candidate',checked_candidate)
    monkeypatch.setattr(m.base,'sha256',lambda p:'candidate_sha')
    monkeypatch.setattr(m.base,'check_output',lambda a,root,ext:Path(a))
    monkeypatch.setattr(m.workers,'request_subprocess',lambda root,script,paths,policy,side,seed,reg,ot:dummy_game(policy,side,seed,reg,ot))
    out=tmp_path/'report.json'
    monkeypatch.setattr(sys,'argv',['benchmark','--checkpoint',str(checkpoint),'--seeds','2','--repeats','1','--regulation-seconds','20','--overtime-seconds','0','--out',str(out)])
    m.main()
    result=json.loads(out.read_text())
    assert result['repeats']==1 and result['seeds']==2
    assert len(result['records']) == 8
    assert checkpoint.read_bytes() == b'candidate'
    assert original_path.read_bytes() == b'original'


def test_main_rejects_zero_repeats(monkeypatch,tmp_path):
    monkeypatch.setattr(sys,'argv',['benchmark','--checkpoint','fake.pt','--seeds','2','--repeats','0','--out',str(tmp_path/'unused.json')])
    with pytest.raises(SystemExit) as exc:m.main()
    assert exc.value.code == 2
