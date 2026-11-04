import json
from pathlib import Path
import tomllib
import zipfile

import pytest
import torch

from nova import packaging
from nova.core import OBS_SIZE,ACTIONS,check_model,write_model_meta
from nova.models import FrozenActor


def actor_file(path,outputs=len(ACTIONS),metadata=True):
    actor=torch.jit.trace(torch.nn.Linear(OBS_SIZE,outputs).eval(),torch.zeros(1,OBS_SIZE))
    torch.jit.save(actor,str(path))
    if metadata: write_model_meta(path,timesteps=1234)
    return path


def test_pt_packager_preserves_actor_and_emits_valid_launch_configuration(tmp_path,monkeypatch):
    monkeypatch.setattr(packaging,'ROOT',tmp_path)
    source=actor_file(tmp_path/'student.pt')
    before=source.read_bytes()
    toml,archive=packaging.make_package(source,'Student "Copy"',weights_format='pt')
    config=tomllib.loads(toml.read_text())
    assert config['settings']['name']=='Student "Copy"'
    assert config['settings']['hivemind']
    assert '..\\..\\.venv\\Scripts\\python.exe' in config['settings']['run_command']
    assert '../../.venv/bin/python' in config['settings']['run_command_linux']
    assert (toml.parent/'policy.pt').read_bytes()==before==source.read_bytes()
    assert check_model(toml.parent/'policy.pt')['timesteps']==1234
    runtime=(toml.parent/'bot.py').read_text();compile(runtime,'bot.py','exec')
    assert repr(config['settings']['agent_id']) in runtime
    with zipfile.ZipFile(archive) as z:
        assert z.testzip() is None
        assert {Path(n).name for n in z.namelist()}=={'policy.pt','policy.pt.json','bot.py','bot.bot.toml','README.txt'}
    # Repeat conversion creates a distinct package instead of overwriting one.
    other,_=packaging.make_package(source,'Student "Copy"')
    assert other!=toml and toml.exists()


def test_pt_packager_requires_contract_declaration_when_metadata_is_missing(tmp_path,monkeypatch):
    monkeypatch.setattr(packaging,'ROOT',tmp_path)
    source=actor_file(tmp_path/'bare.pt',metadata=False)
    with pytest.raises(ValueError,match='metadata is missing'):packaging.make_package(source)
    toml,_=packaging.make_package(source,assume_novaforge=True)
    assert check_model(toml.parent/'policy.lt')


def test_pt_packager_rejects_wrong_interface_and_tampered_actor(tmp_path,monkeypatch):
    monkeypatch.setattr(packaging,'ROOT',tmp_path)
    wrong=actor_file(tmp_path/'other_bot.pt',outputs=90,metadata=False)
    with pytest.raises(ValueError,match='276'):packaging.make_package(wrong,assume_novaforge=True)
    source=actor_file(tmp_path/'modified.pt')
    with source.open('ab') as f:f.write(b'changed')
    with pytest.raises(ValueError,match='hash mismatch'):packaging.make_package(source)


def test_lt_export_from_full_checkpoint_preserves_policy_and_v5_runtime(tmp_path,monkeypatch,cfg):
    from argparse import Namespace
    import numpy as np
    from nova.environment import ArenaEnv
    from nova.training import new_model
    from nova.models import save_ppo
    from nova.evaluation import Student
    monkeypatch.setattr(packaging,'ROOT',tmp_path)
    torch.set_num_threads(1)
    env=ArenaEnv(cfg,opponent='scripted')
    try:
        model=new_model(cfg,env);path=tmp_path/'checkpoint.zip';save_ppo(model,path)
        packaging.export_v5(Namespace(model=str(path),name='LT Student'))
        lt=next((tmp_path/'exports').glob('*/policy.lt'))
        config=tomllib.loads((lt.parent/'bot.bot.toml').read_text())
        assert check_model(lt)['weights_format']=='libtorch_torchscript'
        assert "'policy.lt'" in (lt.parent/'bot.py').read_text()
        actor=torch.jit.load(str(lt));student=Student(lt)
        for side in (0,1):
            obs,_=env.reset(seed=700+side)
            assert student.action(obs)==int(model.predict(obs,deterministic=True)[0])
            with torch.inference_mode():
                expected=model.policy.get_distribution(torch.as_tensor(obs[None,:])).distribution.logits
                actual=actor(torch.as_tensor(obs[None,:]))
                torch.testing.assert_close(torch.log_softmax(actual,dim=-1),expected,rtol=1e-6,atol=1e-6)
    finally:env.close()
