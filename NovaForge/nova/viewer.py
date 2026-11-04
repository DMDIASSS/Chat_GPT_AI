"""Find RLViser and prepare the checked camera build before its native auto-launch."""
from __future__ import annotations

import copy
from datetime import datetime,timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import sys
import subprocess
import tempfile
import urllib.request

from .core import ROOT,atomic_json,sha256

CAMERA=dict(fov=110.,distance=270.,height=100.,pitch=-4.,ball_cam=True,shake=False)
CAMERA_SENDER_VERSION='0.6.14'


def ensure_camera_sender():
    """The camera viewer uses FlatBuffers; 0.6.13 uses the incompatible legacy wire format."""
    try:version=importlib.metadata.version('rlviser-py')
    except importlib.metadata.PackageNotFoundError:version=None
    loaded=sys.modules.get('rlviser_py')
    loaded_version=getattr(loaded,'__version__',None)
    if loaded_version is not None and loaded_version!=CAMERA_SENDER_VERSION:
        raise RuntimeError('The incompatible RLViser sender is already loaded. Close this console, run 31_SETUP_RLVISER.bat, then start viewing again.')
    if version==CAMERA_SENDER_VERSION:return
    command=[sys.executable,'-m','pip','install','--disable-pip-version-check','--only-binary=:all:',
        '--no-deps','--index-url','https://pypi.org/simple','rlviser-py=='+CAMERA_SENDER_VERSION]
    if 'rlviser_py' in sys.modules:
        raise RuntimeError('The incompatible RLViser sender is already loaded. Close this console, run 31_SETUP_RLVISER.bat, then start viewing again.')
    print(f'Updating the viewer sender from {version or "missing"} to {CAMERA_SENDER_VERSION} to match the camera protocol.',flush=True)
    try:subprocess.run(command,check=True)
    except (OSError,subprocess.CalledProcessError):
        raise RuntimeError('Viewer sender update failed. Run .venv\\Scripts\\python.exe -m pip install --only-binary=:all: rlviser-py==0.6.14, then retry. Viewing has not started.') from None
    if importlib.metadata.version('rlviser-py')!=CAMERA_SENDER_VERSION:
        raise RuntimeError('Viewer sender version is still incompatible; restart after installing rlviser-py==0.6.14.')


def find_viewer(root=ROOT,explicit=None):
    root=Path(root)
    if explicit:
        path=Path(explicit).expanduser().resolve()
        if not path.is_file():raise FileNotFoundError(f'RLViser executable not found: {path}')
        return path
    names=('rlviser.exe','rilviser.exe','rlviser-x86_64-pc-windows-msvc.exe','rlviser')
    for folder in (root.parent,root,root/'viewer'):
        for name in names:
            path=folder/name
            if path.is_file():return path.resolve()
    return None


def download_checked(url,destination,digest,size_limit=160*1024*1024):
    if not url.startswith('https://github.com/DMDIASSS/Chat_GPT_AI/releases/download/'):
        raise ValueError('Viewer download must use the pinned NovaForge GitHub release')
    if len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):raise ValueError('Missing pinned viewer SHA256')
    destination=Path(destination);destination.parent.mkdir(parents=True,exist_ok=True)
    fd,temp=tempfile.mkstemp(dir=destination.parent,suffix='.download')
    total=0;hasher=hashlib.sha256();next_notice=8*1024*1024
    try:
        with os.fdopen(fd,'wb') as f:
            with urllib.request.urlopen(url,timeout=30) as response:
                while True:
                    chunk=response.read(1024*1024)
                    if not chunk:break
                    total+=len(chunk)
                    if total>size_limit:raise ValueError('Viewer download exceeded size limit')
                    f.write(chunk);hasher.update(chunk)
                    if total>=next_notice:
                        print(f'RLViser download: {total//(1024*1024)} MiB',flush=True);next_notice+=8*1024*1024
            f.flush();os.fsync(f.fileno())
        if hasher.hexdigest()!=digest:raise ValueError('Viewer download SHA256 mismatch')
        with open(temp,'rb') as f:
            if f.read(2)!=b'MZ':raise ValueError('Viewer download is not a Windows executable')
        os.replace(temp,destination)
    finally:
        if os.path.exists(temp):os.unlink(temp)
    return destination


def configure_camera(root=ROOT,full_camera=True):
    root=Path(root);path=root/'settings.txt';values={}
    if path.exists():
        for line in path.read_text(encoding='utf8').splitlines():
            if '=' in line:
                key,value=line.split('=',1);values[key]=value
    values.update(ball_cam='true',camera_state='{"TrackCar":1}',paused='false',allow_rendering='true',packet_smoothing='1')
    values.setdefault('fps_limit','60');values.setdefault('uncap_fps','false')
    if full_camera:
        values.update(camera_fov='110',camera_distance='270',camera_height='100',camera_pitch='-4')
    else:
        for key in ('camera_fov','camera_distance','camera_height','camera_pitch'):values.pop(key,None)
    content=''.join(f'{key}={value}\n' for key,value in values.items())
    if path.exists() and path.read_text(encoding='utf8')!=content:
        backup=root/'viewer/backups'/f'settings_{datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")}.txt'
        backup.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,backup)
    fd,temp=tempfile.mkstemp(dir=root,suffix='.settings.tmp')
    try:
        with os.fdopen(fd,'w',encoding='utf8') as f:f.write(content);f.flush();os.fsync(f.fileno())
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)
    return path


def prepare_viewer(root=ROOT,explicit=None,mode='auto',platform_name=None):
    root=Path(root);platform_name=platform_name or sys.platform
    if mode=='manual':return None
    found=find_viewer(root,explicit)
    if found:print(f'Found RLViser: {found}',flush=True)
    if platform_name!='win32':
        raise RuntimeError('Automatic camera-build setup currently supports Windows. Use --viewer-mode manual with your Linux viewer.')
    manifest_path=root/'viewer.lock.json'
    manifest=json.loads(manifest_path.read_text()) if manifest_path.exists() else {}
    asset=manifest.get('windows',{});digest=asset.get('sha256','')
    canonical=root/'rlviser.exe';full_camera=False;selected=None
    for path in (canonical,found):
        if path and path.is_file() and len(digest)==64 and sha256(path)==digest:
            selected=path;full_camera=True;break
    if selected is None and mode=='auto':
        if len(digest)!=64:raise RuntimeError('The pinned camera viewer manifest is missing. Update NovaForge or use --viewer-mode existing.')
        cached=root/'viewer/bin'/f'rlviser-{digest[:12]}.exe'
        try:
            if not cached.is_file() or sha256(cached)!=digest:
                print('Downloading the checked camera viewer once; your existing viewer is preserved.',flush=True)
                download_checked(asset['url'],cached,digest)
            selected=cached;full_camera=True
        except (OSError,ValueError) as error:
            if not found:raise RuntimeError(f'Camera viewer setup failed ({type(error).__name__}); install RLViser or retry with Internet access.') from None
            print(f'Camera viewer download unavailable ({type(error).__name__}); using your existing viewer. Stock RLViser supports ballcam/follow, but not the full 110/270/-4 preset.',flush=True)
            selected=found
    if selected is None:selected=found
    if selected is None:raise FileNotFoundError('RLViser was not found. Put rilviser.exe or rlviser.exe in chat_gpt_ai, or run viewer-setup online.')
    if full_camera:ensure_camera_sender()
    if selected.resolve()!=canonical.resolve():
        if canonical.exists() and sha256(canonical)!=sha256(selected):
            backup=root/'viewer/backups'/f'rlviser-{sha256(canonical)[:12]}.exe'
            backup.parent.mkdir(parents=True,exist_ok=True)
            if not backup.exists():shutil.copyfile(canonical,backup)
        if not canonical.exists() or sha256(canonical)!=sha256(selected):
            fd,temporary=tempfile.mkstemp(dir=root,suffix='.viewer.tmp');os.close(fd)
            try:
                shutil.copyfile(selected,temporary)
                with open(temporary,'r+b') as f:f.flush();os.fsync(f.fileno())
                os.replace(temporary,canonical)
            except PermissionError:
                raise RuntimeError('Close the previous RLViser window once, then retry; Windows is holding the old executable open.') from None
            finally:
                if os.path.exists(temporary):os.unlink(temporary)
    configure_camera(root,full_camera)
    atomic_json(root/'viewer/last_setup.json',dict(executable=str(canonical),full_camera_preset=full_camera,
        requested_camera=CAMERA,launch='rlviser-py first-frame startup',follow_render_car=1))
    print('RLViser ready: ballcam on learner; '+('FOV 110, distance 270, height 100, pitch -4, no added shake.' if full_camera else 'stock camera geometry.'),flush=True)
    return canonical


def learner_first_state(state,agent):
    """RLViser assigns IDs by iteration order; car 1 must always be the learner."""
    rendered=copy.copy(state)
    rendered.cars={agent:state.cars[agent],**{key:value for key,value in state.cars.items() if key!=agent}}
    return rendered


def setup_command(args):
    prepare_viewer(explicit=args.exe,mode=args.mode)
