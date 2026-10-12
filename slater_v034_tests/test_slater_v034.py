from pathlib import Path
import sys
from types import SimpleNamespace
import numpy as np
import pytest
import torch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import slater_parity_v034 as parity
import slater_rlbot_copy_v034 as copier
import slater_rlbot_capture_v034 as telemetry


def sample_obs():
    return (np.zeros((1,32),np.float32), np.zeros((41,24),np.float32), np.ones((41,),np.float32))


def test_canonical_obs_unbatched_and_batched():
    obs=sample_obs()
    assert tuple(x.shape for x in parity.canonical_obs(obs)) == parity.EXPECTED_SHAPES
    assert tuple(x.shape for x in parity.canonical_obs([a[None] for a in obs])) == parity.EXPECTED_SHAPES
    with pytest.raises(ValueError):parity.canonical_obs([np.zeros(32),obs[1],obs[2]])
    obs=list(sample_obs());obs[0][0,0]=np.nan
    with pytest.raises(ValueError):parity.canonical_obs(obs)


def test_action_table_catches_reordering():
    a=np.zeros((90,8),np.float32);b=a.copy()
    assert parity.compare_actions(a,b)['identical']
    b[55,7]=1
    d=parity.compare_actions(a,b)
    assert not d['identical'] and d['mismatched_ids']==[55]
    assert not parity.compare_actions(a,np.zeros((89,8)))['identical']


def test_parameter_mismatch_and_matching():
    a=torch.nn.Linear(2,3);b=torch.nn.Linear(2,3)
    b.load_state_dict(a.state_dict())
    assert parity.model_state_diff(a,b)['identical']
    with torch.no_grad():b.weight[0,0]+=1
    assert parity.model_state_diff(a,b)['different']==['weight']


class FakePolicy(torch.nn.Module):
    def forward(self,x):
        q,kv,mask=x
        return q.new_ones((q.shape[0],90)) * q[:,0,0:1], None


def test_inference_comparison_and_classifier():
    actor=FakePolicy()
    result=parity.compare_inference(actor,actor,sample_obs())
    assert result['top_action_same'] and result['allclose_1e-5'] and result['max_abs_logit_diff']==0
    assert 'LIVE_OBS_NOT_TESTED' in parity.classify_report({'identical':True},{'identical':True},[result],0)
    assert 'FAIL_ACTION_TABLE' == parity.classify_report({'identical':True},{'identical':False},[result],0)


def test_file_output_isolated_create_only(tmp_path):
    root=tmp_path;(root/'data'/'isolated').mkdir(parents=True)
    fp=parity.check_output('data/isolated/new.json',root)
    assert fp.parent==(root/'data'/'isolated')
    fp.touch()
    with pytest.raises(FileExistsError):parity.check_output('data/isolated/new.json',root)
    with pytest.raises(ValueError):parity.check_output('elsewhere.json',root)
    with pytest.raises(ValueError):parity.check_output('../evil.json',root)


def sample_bot():
    return 'import numpy as np\nclass Nexto:\n    def get_output(self, packet):\n        obs = self.obs_builder.build_obs(player, self.game_state, self.action)\n        self.action, weights = self.agent.act(obs, beta)\n'


def test_bot_copy_only_modifies_new_destination(tmp_path):
    root=tmp_path;(root/'data'/'isolated').mkdir(parents=True)
    src=root/'original';src.mkdir()
    files={'bot.py':sample_bot(),'agent.py':'pass\n','nexto_obs.py':'pass\n','bot.cfg':'pass\n','nexto-model.pt':'a'}
    for name,content in files.items():(src/name).write_text(content)
    (root/'slater_parity_v034.py').write_text('pass\n')
    module=root/'slater_rlbot_capture_v034.py';module.write_text('pass\n')
    dst=root/'data'/'isolated'/'slater_v034_test'
    assert copier.clone_bot(src,dst,root,module)==dst
    assert (src/'bot.py').read_text()==sample_bot()
    assert (dst/'nexto-model.pt').read_text()=='a'
    assert '_slater_v034_capture(self, obs,' in (dst/'bot.py').read_text()
    with pytest.raises(FileExistsError):copier.clone_bot(src,dst,root,module)
    assert (dst/'bot.py').is_file()


def test_instrument_fails_closed():
    with pytest.raises(ValueError):copier.instrument_source('something unexpected')
    with pytest.raises(ValueError):copier.instrument_source(sample_bot().replace('self.agent.act','self.agent.method'))


def test_capture_bounded_create_only(tmp_path,monkeypatch):
    monkeypatch.setattr(telemetry,'__file__',str(tmp_path/'slater_rlbot_capture_v034.py'))
    monkeypatch.setenv('SLATER_V034_EVERY','2')
    monkeypatch.setenv('SLATER_V034_LIMIT','1')
    location=SimpleNamespace(x=1.,y=2.,z=3.)
    packet=SimpleNamespace(game_info=SimpleNamespace(seconds_elapsed=2.,is_kickoff_pause=False),
        game_cars=[SimpleNamespace(physics=SimpleNamespace(location=location))],
        game_ball=SimpleNamespace(physics=SimpleNamespace(location=location)))
    bot=SimpleNamespace(index=0,team=0)
    for _ in range(5):telemetry.capture_decision(bot,sample_obs(),np.zeros(8),np.zeros(8),packet)
    assert len(list((tmp_path/'capture_v034').glob('capture_*.npz')))==1
    inputs,meta,n=parity.capture_inputs(tmp_path/'capture_v034')
    assert n==1 and meta[0]['team']==0 and len(inputs)==1


def test_opponent_constructor_defaults(tmp_path):
    p=tmp_path/'bot.py'
    p.write_text('class Nexto:\n def __init__(self, beta=1, hardcoded_kickoffs=True, stochastic_kickoffs=False): pass\n')
    d=parity.opponent_defaults(p)
    assert d['defaults']['hardcoded_kickoffs'] is True
    assert 'defaults' in d['status']
