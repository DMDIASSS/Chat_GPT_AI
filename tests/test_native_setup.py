from pathlib import Path
import importlib.util
import hashlib
import json
import subprocess
import pytest


def load():
    path=Path(__file__).resolve().parents[1]/'GigaLearn_Project/Native_Backend/native_setup.py'
    spec=importlib.util.spec_from_file_location('native_setup_test',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def test_zero_exit_without_completion_is_not_success():
    m=load()
    with pytest.raises(ValueError):m.parse_log('RG FATAL ERROR: failed')
    with pytest.raises(ValueError):m.parse_log('Collection Steps/Second: 100\nOverall Steps/Second: 50\n')


def test_warm_throughput_parser_counts_agent_decisions():
    m=load();text='Collection Steps/Second: 1,000\nOverall Steps/Second: 500\nCollection Steps/Second: 2,000\nOverall Steps/Second: 800\nSLATER_GIGA_COMPLETE iterations=2 timesteps=4096'
    r=m.parse_log(text)
    assert r['Collection Steps/Second']['warm_median']==2000
    assert r['total_timesteps']==4096 and r['total_iterations']==2


def test_python_headers_and_tools_are_real():
    m=load();library,include=m.python_paths()
    assert library.is_file() and (include/'Python.h').is_file()
    assert Path(m.tool('cmake')).is_file()


def source_fixture(tmp_path,monkeypatch):
    m=load();source=tmp_path/'source';source.mkdir();helper=tmp_path/'helper';helper.mkdir()
    def git(*args):
        return subprocess.check_output(['git','-C',str(source),*args],text=True).strip()
    git('init','-q');git('config','core.autocrlf','false')
    original=b'first\nold\nlast\n';patched=b'first\nnew\nlast\n'
    for name in ('a.h','b.h'):(source/name).write_bytes(original)
    git('add','.');git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','fixture')
    manifest={name:{'original':hashlib.sha256(original).hexdigest(),
                    'patched':hashlib.sha256(patched).hexdigest()} for name in ('a.h','b.h')}
    (helper/'patch_manifest.json').write_text(json.dumps(manifest))
    patch=''
    for name in manifest:
        patch+=f'diff --git a/{name} b/{name}\n--- a/{name}\n+++ b/{name}\n@@ -1,3 +1,3 @@\n first\n-old\n+new\n last\n'
    (helper/'compatibility.patch').write_bytes(patch.encode())
    monkeypatch.setattr(m,'HERE',helper);monkeypatch.setattr(m,'GIGA',git('rev-parse','HEAD'))
    return m,source,original,patched


@pytest.mark.parametrize('already_patched,crlf',[(False,False),(False,True),(True,True)])
def test_known_source_line_endings_apply_and_repeat(tmp_path,monkeypatch,already_patched,crlf):
    m,source,original,patched=source_fixture(tmp_path,monkeypatch)
    text=patched if already_patched else original
    if crlf:text=text.replace(b'\n',b'\r\n')
    for name in ('a.h','b.h'):(source/name).write_bytes(text)
    m.patch_source(source);m.patch_source(source)
    assert all((source/name).read_bytes()==patched for name in ('a.h','b.h'))


@pytest.mark.parametrize('partial',[False,True])
def test_unknown_or_partial_source_preserves_all_bytes(tmp_path,monkeypatch,partial):
    m,source,original,patched=source_fixture(tmp_path,monkeypatch)
    (source/'a.h').write_bytes(original.replace(b'\n',b'\r\n'))
    (source/'b.h').write_bytes(patched if partial else original+b'user edit\n')
    before={p:p.read_bytes() for p in source.glob('*.h')}
    with pytest.raises(ValueError):m.patch_source(source)
    assert all(p.read_bytes()==contents for p,contents in before.items())


def test_git_apply_crlf_output_is_verified_and_normalized(tmp_path,monkeypatch):
    m,source,original,patched=source_fixture(tmp_path,monkeypatch)
    subprocess.run(['git','-C',str(source),'config','core.autocrlf','true'],check=True)
    subprocess.run(['git','-C',str(source),'config','core.eol','crlf'],check=True)
    # Reproduce Windows checkout attributes as well as the global Git setting.
    (source/'.gitattributes').write_bytes(b'*.h text eol=crlf\n')
    for name in ('a.h','b.h'):(source/name).write_bytes(original.replace(b'\n',b'\r\n'))
    m.patch_source(source)
    assert all((source/name).read_bytes()==patched for name in ('a.h','b.h'))
    m.patch_source(source)
