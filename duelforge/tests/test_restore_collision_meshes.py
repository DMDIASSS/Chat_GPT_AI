import importlib.util,json,io,tarfile,hashlib
from pathlib import Path
import pytest

spec=importlib.util.spec_from_file_location('mesh_recovery',Path(__file__).resolve().parents[1]/'tools/restore_collision_meshes.py')
repair=importlib.util.module_from_spec(spec);spec.loader.exec_module(repair)
@pytest.fixture
def archive(monkeypatch):
    buffer=io.BytesIO()
    with tarfile.open(fileobj=buffer,mode='w:gz') as t:
        for i in range(16):
            data=('mesh fixture '+str(i)).encode();entry=tarfile.TarInfo(repair.PREFIX+f'mesh_{i}.cmf');entry.size=len(data)
            t.addfile(entry,io.BytesIO(data))
    payload=buffer.getvalue();monkeypatch.setattr(repair,'ARCHIVE_SHA256',hashlib.sha256(payload).hexdigest());return payload

def test_restore_only_assets_preserves_models_and_other_settings(tmp_path,archive):
    (tmp_path/'runs').mkdir();model=tmp_path/'runs/latest.pt';model.write_bytes(b'protected model')
    old={'meshes':'missing/folder','other_setting':'keep'}
    (tmp_path/'local_paths.json').write_text(json.dumps(old))
    r=repair.restore(tmp_path,archive=archive)
    assert len(list((tmp_path/'assets/collision_meshes/soccar').glob('*.cmf')))==16
    hint=json.loads((tmp_path/'local_paths.json').read_text())
    assert hint['other_setting']=='keep' and hint['meshes']==r['mesh_root']
    assert model.read_bytes()==b'protected model' and not r['training_started']
    assert json.loads(next(tmp_path.glob('local_paths.before_mesh_restore_*.json')).read_text())==old

def test_checksum_failure_preserves_existing_assets_and_settings(tmp_path,archive):
    target=tmp_path/'assets/collision_meshes';target.mkdir(parents=True);(target/'keep').write_bytes(b'old')
    settings=tmp_path/'local_paths.json';settings.write_text('{"other": 1}')
    with pytest.raises(ValueError,match='checksum'):repair.restore(tmp_path,archive=b'bad archive')
    assert (target/'keep').read_bytes()==b'old' and settings.read_text()=='{"other": 1}'

def test_partial_folder_preserved_and_idempotent_complete_restore(tmp_path,archive):
    target=tmp_path/'assets/collision_meshes';target.mkdir(parents=True);(target/'partial').write_bytes(b'recoverable')
    r=repair.restore(tmp_path,archive=archive)
    assert (Path(r['previous_asset_folder'])/'partial').read_bytes()==b'recoverable'
    after=repair.restore(tmp_path,archive=archive)
    assert after['previous_asset_folder'] is None
    assert after['mesh_sha256']==r['mesh_sha256']

def test_malformed_settings_are_never_overwritten(tmp_path,archive):
    path=tmp_path/'local_paths.json';path.write_text('broken settings')
    with pytest.raises(ValueError):repair.restore(tmp_path,archive=archive)
    assert path.read_text()=='broken settings' and not (tmp_path/'assets').exists()
