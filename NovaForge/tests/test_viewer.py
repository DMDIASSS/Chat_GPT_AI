from argparse import Namespace
import hashlib
import io
import json
from pathlib import Path

import pytest
import torch

from nova import viewer
from nova.environment import ArenaEnv
from nova.models import save_ppo
from nova.training import new_model


def test_find_viewer_recognizes_parent_rilviser_spelling_and_explicit_path(tmp_path):
    root=tmp_path/'chat_gpt_ai/novaforge';root.mkdir(parents=True)
    known=root.parent/'rilviser.exe';known.write_bytes(b'MZexisting')
    (root/'rlviser.exe').write_bytes(b'MZother')
    assert viewer.find_viewer(root)==known.resolve()
    corrected=root.parent/'rlviser.exe';corrected.write_bytes(b'MZcorrect-name')
    assert viewer.find_viewer(root)==corrected.resolve()
    assert viewer.find_viewer(root,root/'rlviser.exe')==(root/'rlviser.exe').resolve()
    with pytest.raises(FileNotFoundError):viewer.find_viewer(root,tmp_path/'missing.exe')


def test_existing_viewer_is_copied_without_moving_original_and_camera_follows_car(tmp_path):
    root=tmp_path/'chat_gpt_ai/novaforge';root.mkdir(parents=True)
    original=root.parent/'rilviser.exe';original.write_bytes(b'MZstock-viewer')
    (root/'settings.txt').write_text('fps_limit=90\nball_cam=false\ncamera_state="Spectator"\n')
    result=viewer.prepare_viewer(root,mode='existing',platform_name='win32')
    assert result==root/'rlviser.exe'
    assert original.read_bytes()==result.read_bytes()==b'MZstock-viewer'
    text=(root/'settings.txt').read_text()
    assert 'camera_state={"TrackCar":1}' in text and 'ball_cam=true' in text
    assert 'fps_limit=90' in text and 'camera_fov=' not in text
    assert list((root/'viewer/backups').glob('settings_*.txt'))


def test_checked_camera_download_is_installed_and_cached(tmp_path,monkeypatch):
    monkeypatch.setattr(viewer,'ensure_camera_sender',lambda:None)
    root=tmp_path/'novaforge';root.mkdir()
    (root/'rlviser.exe').write_bytes(b'MZold')
    binary=b'MZcamera-custom';digest=hashlib.sha256(binary).hexdigest()
    url='https://github.com/DMDIASSS/Chat_GPT_AI/releases/download/test/rlviser.exe'
    (root/'viewer.lock.json').write_text(json.dumps({'windows':{'url':url,'sha256':digest}}))
    calls=[]
    def response(value,timeout):calls.append(value);return io.BytesIO(binary)
    monkeypatch.setattr(viewer.urllib.request,'urlopen',response)
    path=viewer.prepare_viewer(root,platform_name='win32')
    assert path.read_bytes()==binary and calls==[url]
    settings=(root/'settings.txt').read_text()
    for line in ['camera_fov=110','camera_distance=270','camera_height=100','camera_pitch=-4','ball_cam=true']:
        assert line in settings
    assert list((root/'viewer/backups').glob('rlviser-*.exe'))
    viewer.prepare_viewer(root,platform_name='win32')
    assert calls==[url]
    assert json.loads((root/'viewer/last_setup.json').read_text())['requested_camera']['shake'] is False


def test_camera_sender_upgrades_legacy_before_native_import(monkeypatch):
    version=['0.6.13'];calls=[]
    monkeypatch.setattr(viewer.importlib.metadata,'version',lambda name:version[0])
    monkeypatch.delitem(viewer.sys.modules,'rlviser_py',raising=False)
    def install(command,check):calls.append(command);version[0]='0.6.14'
    monkeypatch.setattr(viewer.subprocess,'run',install)
    viewer.ensure_camera_sender()
    assert calls[0][0]==viewer.sys.executable and calls[0][-1]=='rlviser-py==0.6.14'
    viewer.ensure_camera_sender();assert len(calls)==1


def test_camera_sender_refuses_loaded_incompatible_extension(monkeypatch):
    monkeypatch.setattr(viewer.importlib.metadata,'version',lambda name:'0.6.13')
    monkeypatch.setitem(viewer.sys.modules,'rlviser_py',object())
    monkeypatch.setattr(viewer.subprocess,'run',lambda *a,**k:pytest.fail('Must not replace a loaded native DLL'))
    with pytest.raises(RuntimeError,match='already loaded'):viewer.ensure_camera_sender()
    monkeypatch.setattr(viewer.importlib.metadata,'version',lambda name:'0.6.14')
    monkeypatch.setitem(viewer.sys.modules,'rlviser_py',Namespace(__version__='0.6.13'))
    with pytest.raises(RuntimeError,match='already loaded'):viewer.ensure_camera_sender()


@pytest.mark.parametrize('wrong_digest,binary',[(True,b'MZcorrect-format'),(False,b'not-an-executable')])
def test_viewer_download_rejects_bad_digest_or_non_executable(tmp_path,monkeypatch,wrong_digest,binary):
    monkeypatch.setattr(viewer.urllib.request,'urlopen',lambda *a,**k:io.BytesIO(binary))
    path=tmp_path/'viewer.exe';path.write_bytes(b'MZkeep')
    digest='0'*64 if wrong_digest else hashlib.sha256(binary).hexdigest()
    with pytest.raises(ValueError):viewer.download_checked('https://github.com/DMDIASSS/Chat_GPT_AI/releases/download/test/viewer.exe',path,digest)
    assert path.read_bytes()==b'MZkeep'
    assert not list(tmp_path.glob('*.download'))


def test_offline_camera_setup_falls_back_to_existing_viewer_honestly(tmp_path,monkeypatch,capsys):
    root=tmp_path/'novaforge';root.mkdir()
    (root.parent/'rilviser.exe').write_bytes(b'MZstock')
    (root/'viewer.lock.json').write_text(json.dumps({'windows':{'url':'unused','sha256':'a'*64}}))
    def unavailable(*a,**k):raise OSError('offline')
    monkeypatch.setattr(viewer,'download_checked',unavailable)
    path=viewer.prepare_viewer(root,platform_name='win32')
    assert path.read_bytes()==b'MZstock'
    assert 'not the full 110/270/-4 preset' in capsys.readouterr().out
    assert not json.loads((root/'viewer/last_setup.json').read_text())['full_camera_preset']


@pytest.mark.parametrize('side',[0,1])
def test_rendered_car_one_is_learner_without_mutating_simulator(cfg,side):
    env=ArenaEnv(cfg,opponent='scripted',side=side)
    try:
        env.reset(seed=98)
        env.state.cars={env.other:env.state.cars[env.other],env.agent:env.state.cars[env.agent]}
        before=list(env.state.cars)
        rendered=viewer.learner_first_state(env.state,env.agent)
        assert list(rendered.cars)[0]==env.agent
        assert list(env.state.cars)==before
        assert rendered.cars[env.agent] is env.state.cars[env.agent]
    finally:env.close()


def test_watch_prepares_viewer_and_closes_renderer_on_interrupt(tmp_path,cfg,monkeypatch):
    import rlgym.rocket_league.rlviser as adapter
    from nova import evaluation
    torch.set_num_threads(1)
    env=ArenaEnv(cfg,opponent='scripted')
    try:
        model=new_model(cfg,env);path=tmp_path/'model.zip';save_ppo(model,path)
    finally:env.close()
    config=tmp_path/'cfg.json';config.write_text(json.dumps(cfg))
    calls=[]
    monkeypatch.setattr(viewer,'prepare_viewer',lambda **kwargs:calls.append(('prepare',kwargs)))
    class FakeRenderer:
        def __init__(self,tick_rate):self.count=0;calls.append(('init',tick_rate))
        def render(self,state,shared):
            self.count+=1
            if self.count==2:raise KeyboardInterrupt
        def close(self):calls.append(('close',None))
    monkeypatch.setattr(adapter,'RLViserRenderer',FakeRenderer)
    evaluation.watch(Namespace(model=str(path),config=str(config),opponent='scripted',scenario='kickoff',
        seconds=.15,seed=55,viewer_mode='auto',viewer_exe=None))
    assert [x[0] for x in calls]==['prepare','init','close']
