import json,sys
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import skillforge_search
from skillforge_imitation import Specialist, train, load_policy


def test_cem_requires_independent_holdout_and_writes_only_given_folder(tmp_path,monkeypatch):
    import skillforge_core
    class Sim:
        def close(self):pass
    monkeypatch.setattr(skillforge_search,'Simulator',Sim)
    def fake_rollout(sim,seed,parameters,**kw):
        # First population never actually succeeds; search must not fake success.
        m=SimpleNamespace(success=False,fitness=.2,reason='no_dodge',
            valid_spawn=True,boost_free=True,dodge_detected=False)
        return m,[(list(np.zeros(19)),list(np.zeros(8)))] if kw.get('frames') else []
    monkeypatch.setattr(skillforge_search,'rollout',fake_rollout)
    monkeypatch.setattr(skillforge_search,'output_metrics',lambda m:m.__dict__)
    a=SimpleNamespace(out=tmp_path/'case',population=3,generations=2,
         training_seeds=4,holdout_seeds=5,seed=6,variant='forward',
         difficulty='near',max_ticks=30,minimum_holdout_success=0.5)
    result=skillforge_search.search(a)
    assert result['holdout_wins']==0
    assert result['eligible_for_imitation'] is False
    assert not (a.out/'verified_demonstrations.json').exists()
    assert json.loads((a.out/'discovery.json').read_text())['holdout_total']==5
    with pytest.raises(FileExistsError):skillforge_search.search(a)


def test_bc_refuses_missing_evidence(tmp_path):
    folder=tmp_path/'lab';folder.mkdir()
    (folder/'discovery.json').write_text(json.dumps({'eligible_for_imitation':False}))
    a=SimpleNamespace(path=folder,epochs=1,minimum_trajectories=8,seed=1,batch=4)
    with pytest.raises(RuntimeError,match='failed holdout'):train(a)


def test_bc_trains_from_verified_demonstrations_only(tmp_path):
    folder=tmp_path/'lab';folder.mkdir()
    (folder/'discovery.json').write_text(json.dumps({'eligible_for_imitation':True,
          'variant':'forward'}))
    demos={'examples':[]}
    for seed in range(10):
        frames=[]
        for t in range(8):
            inp=np.zeros(19,dtype=float); inp[-1]=t/110.
            act=np.zeros(8,dtype=float);act[2]=-1 if t==2 else 1 if t==3 else 0
            act[5]=1 if t==2 else 0
            frames.append((inp.tolist(),act.tolist()))
        demos['examples'].append({'seed':seed,'trajectory':frames})
    (folder/'verified_demonstrations.json').write_text(json.dumps(demos))
    a=SimpleNamespace(path=folder,epochs=2,minimum_trajectories=8,seed=1,batch=64)
    train(a)
    checkpoint=folder/'specialist_experimental.pt'
    assert checkpoint.is_file()
    c=load_policy(checkpoint)(np.zeros(19,dtype=np.float32))
    assert c.shape==(8,) and np.all(c[[0,1,3,4,6,7]]==0)
    with pytest.raises(FileExistsError):train(a)
