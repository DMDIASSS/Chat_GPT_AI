from pathlib import Path
import importlib.util
import hashlib
import json
import subprocess
from types import SimpleNamespace
import pytest


def load():
    path=Path(__file__).resolve().parents[1]/'GigaLearn_Project/Native_Backend/native_setup.py'
    spec=importlib.util.spec_from_file_location('native_setup_test',path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def test_zero_exit_without_completion_is_not_success():
    m=load()
    with pytest.raises(ValueError):m.parse_log('RG FATAL ERROR: failed')
    with pytest.raises(ValueError):m.parse_log('Collection Steps/Second: 100\nOverall Steps/Second: 50\n')


def test_pause_before_first_collection_reports_saved_progress_without_fake_throughput(tmp_path):
    m=load();message='SLATER_GIGA_COMPLETE iterations=10 timesteps=8192'
    result=m.process_result(message,0,tmp_path/'log',allow_empty_pause=True)
    assert result['paused_before_collection'] and result['total_timesteps']==8192
    assert 'Collection Steps/Second' not in result
    with pytest.raises(RuntimeError):m.process_result(message,0,tmp_path/'log')


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


def test_tool_prefers_venv_over_system_cmake(tmp_path,monkeypatch):
    m=load();python=tmp_path/'python';cmake=tmp_path/'cmake';cmake.write_text('venv tool')
    monkeypatch.setattr(m.sys,'executable',str(python));monkeypatch.setattr(m.shutil,'which',lambda name:'/system/cmake')
    assert m.tool('cmake')==str(cmake)


def test_cuda_gpu_capability_populates_both_architecture_settings(monkeypatch):
    m=load();monkeypatch.delenv('TORCH_CUDA_ARCH_LIST',raising=False)
    torch=SimpleNamespace(version=SimpleNamespace(cuda='12.6'),cuda=SimpleNamespace(
        is_available=lambda:True,device_count=lambda:2,get_device_capability=lambda i:(7,5)))
    args,env=m.cuda_configuration(torch)
    assert args==['-DCMAKE_CUDA_ARCHITECTURES=75']
    assert env['TORCH_CUDA_ARCH_LIST']=='7.5'


def test_cuda_explicit_override_and_cpu_build(monkeypatch):
    m=load();monkeypatch.setenv('TORCH_CUDA_ARCH_LIST','7.5;8.6+PTX')
    args,env=m.cuda_configuration(SimpleNamespace(version=SimpleNamespace(cuda='12.6')))
    assert args==['-DCMAKE_CUDA_ARCHITECTURES=75;86']
    assert env['TORCH_CUDA_ARCH_LIST']=='7.5;8.6+PTX'
    assert m.cuda_configuration(SimpleNamespace(version=SimpleNamespace(cuda=None)))[0]==[]


def test_cuda_missing_gpu_requests_architecture(monkeypatch):
    m=load();monkeypatch.delenv('TORCH_CUDA_ARCH_LIST',raising=False)
    torch=SimpleNamespace(version=SimpleNamespace(cuda='12.6'),cuda=SimpleNamespace(is_available=lambda:False))
    with pytest.raises(ValueError,match='TORCH_CUDA_ARCH_LIST'):m.cuda_configuration(torch)


@pytest.mark.parametrize('exit_code',[-1073741515,3221225781])
def test_missing_dll_exit_is_not_hidden_by_empty_metrics(exit_code):
    m=load()
    with pytest.raises(RuntimeError,match='0xC0000135') as caught:m.process_result('',exit_code,Path('failed.log'))
    assert 'DLL was not found' in str(caught.value) and 'failed.log' in str(caught.value)
    assert 'No valid Collection' not in str(caught.value)


def test_zero_exit_failure_includes_native_output_and_log():
    m=load()
    with pytest.raises(RuntimeError) as caught:m.process_result('RG FATAL ERROR: missing meshes',0,Path('failed.log'))
    assert 'missing meshes' in str(caught.value) and 'failed.log' in str(caught.value)


def test_windows_runtime_path_contains_native_torch_and_python_dlls(tmp_path,monkeypatch):
    import torch
    m=load();build=tmp_path/'build';(build/'giga').mkdir(parents=True)
    monkeypatch.setenv('PATH','existing-path')
    env=m.runtime_environment(build/'SlaterGigaNative.exe',tmp_path/'pause.flag',windows=True)
    paths=env['PATH'].split(';')
    assert str(build) in paths and str(build/'giga') in paths
    assert str(Path(torch.__file__).resolve().parent/'lib') in paths
    assert str(Path(m.sys.base_prefix)) in paths and paths[-1]=='existing-path'
    assert env['SLATER_GL_PAUSE_FILE']==str(tmp_path/'pause.flag')


def windows_library_fixture(tmp_path):
    (tmp_path/'giga').mkdir()
    (tmp_path/'SlaterGigaNative.exe').write_bytes(b'executable')
    library=tmp_path/'giga/GigaLearnCPP.dll';library.write_bytes(b'current library')
    shadow=tmp_path/'GigaLearnCPP.dll';shadow.write_bytes(b'stale library')
    return library,shadow


def test_library_repair_verifies_source_and_repeats_without_replacing(tmp_path,monkeypatch):
    m=load();library,shadow=windows_library_fixture(tmp_path)
    original_exe=(tmp_path/'SlaterGigaNative.exe').read_bytes()
    m.sync_library(tmp_path,windows=True)
    assert shadow.read_bytes()==library.read_bytes()==b'current library'
    assert (tmp_path/'SlaterGigaNative.exe').read_bytes()==original_exe
    assert not list(tmp_path.glob('.GigaLearnCPP-*.tmp'))
    def cannot_copy(*args):raise AssertionError('matching library must not be replaced')
    monkeypatch.setattr(m.shutil,'copyfile',cannot_copy)
    m.sync_library(tmp_path,windows=True)


def test_library_repair_locked_destination_preserves_old_copy(tmp_path,monkeypatch):
    m=load();library,shadow=windows_library_fixture(tmp_path)
    def locked(*args):raise PermissionError('DLL in use')
    monkeypatch.setattr(m.os,'replace',locked)
    with pytest.raises(RuntimeError,match='Stop native training/evaluation'):m.sync_library(tmp_path,windows=True)
    assert shadow.read_bytes()==b'stale library' and library.read_bytes()==b'current library'
    assert not list(tmp_path.glob('.GigaLearnCPP-*.tmp'))


def test_library_repair_source_change_is_not_installed(tmp_path,monkeypatch):
    m=load();library,shadow=windows_library_fixture(tmp_path);copyfile=m.shutil.copyfile
    def changing_copy(src,dst):
        copyfile(src,dst);Path(src).write_bytes(b'concurrent build')
    monkeypatch.setattr(m.shutil,'copyfile',changing_copy)
    with pytest.raises(ValueError,match='changed during repair'):m.sync_library(tmp_path,windows=True)
    assert shadow.read_bytes()==b'stale library'
    assert not list(tmp_path.glob('.GigaLearnCPP-*.tmp'))


def test_library_repair_missing_build_preserves_old_copy(tmp_path):
    m=load();library,shadow=windows_library_fixture(tmp_path);library.unlink()
    with pytest.raises(ValueError,match='Complete native'):m.sync_library(tmp_path,windows=True)
    assert shadow.read_bytes()==b'stale library'


def test_build_refreshes_library_even_when_cmake_has_no_work(tmp_path,monkeypatch):
    m=load();library,shadow=windows_library_fixture(tmp_path)
    monkeypatch.setattr(m,'tool',lambda name:name)
    monkeypatch.setattr(m,'cuda_configuration',lambda torch:([],{}))
    monkeypatch.setattr(m,'python_paths',lambda:('python.lib','include'))
    calls=[]
    # A successful no-op build never executes the executable's POST_BUILD hook.
    monkeypatch.setattr(m,'command',lambda args,**kwargs:calls.append(args))
    original_sync=m.sync_library
    monkeypatch.setattr(m,'sync_library',lambda folder:original_sync(folder,windows=True))
    m.build(tmp_path/'source',tmp_path,2)
    assert len(calls)==2 and '--build' in calls[-1]
    assert shadow.read_bytes()==library.read_bytes()==b'current library'


def test_binary_identity_still_rejects_stale_library(tmp_path):
    m=load();(tmp_path/'giga').mkdir()
    name='GigaLearnCPP.dll' if m.os.name=='nt' else 'libGigaLearnCPP.so'
    (tmp_path/('SlaterGigaNative.exe' if m.os.name=='nt' else 'SlaterGigaNative')).write_bytes(b'executable')
    (tmp_path/'giga'/name).write_bytes(b'current');(tmp_path/name).write_bytes(b'stale')
    with pytest.raises(ValueError,match='Stale native library'):m.binary_identity(tmp_path)


@pytest.mark.parametrize('code,marker',[(1,'SLATER_TEACHER_REFRESH_COMPLETE timesteps=100'),(0,''),(0,'SLATER_TEACHER_REFRESH_COMPLETE timesteps=99')])
def test_teacher_refresh_requires_success_and_exact_saved_checkpoint(tmp_path,monkeypatch,code,marker):
    m=load();monkeypatch.setattr(m.subprocess,'Popen',lambda *args,**kwargs:SimpleNamespace(stdout=[marker+'\n'],wait=lambda:code))
    profile=dict(device='cpu',width=256,depth=3,threads=1,players=1,teacher_bank='bank.bin',teacher_epochs=3)
    with pytest.raises(RuntimeError,match='Teacher refresh failed'):
        m.refresh_teacher(tmp_path/'SlaterGigaNative',profile,tmp_path,{},tmp_path/'training.log',100,tmp_path/'meshes')
    assert (tmp_path/'training.log').exists()
