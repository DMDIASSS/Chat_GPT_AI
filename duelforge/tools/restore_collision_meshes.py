"""Restore only Soccar mesh data from the official, checksum-pinned package."""
import hashlib,io,json,os,shutil,sys,tarfile,tempfile,time,urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
URL='https://files.pythonhosted.org/packages/99/21/b87ef7ebb0d76e654753349a4f343068d08e1a9eaffd9c77c0593b43668f/rlgym-rocket-league-2.0.1.tar.gz'
ARCHIVE_SHA256='3be8e9d2f1cfb6514e0e3d455fb33ff95e26eb7c399f819fff0258025cf4d501'
PREFIX='rlgym-rocket-league-2.0.1/rlgym/rocket_league/sim/collision_meshes/soccar/'

def atomic_json(path,value):
    fd,tmp=tempfile.mkstemp(prefix=path.name+'.',dir=path.parent)
    try:
        with os.fdopen(fd,'w',encoding='utf8') as f:
            json.dump(value,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def download():
    print('Downloading official RLGym asset archive (about 79 kB); no packages are installed.',flush=True)
    request=urllib.request.Request(URL,headers={'User-Agent':'DuelForge-mesh-recovery/1'})
    with urllib.request.urlopen(request,timeout=30) as response:
        result=response.read(1024*1024+1)
    if len(result)>1024*1024:raise ValueError('Unexpected asset archive size; recovery stopped')
    return result

def restore(root=ROOT,archive=None):
    root=Path(root).resolve();hint=root/'local_paths.json'
    # Parse before making changes; malformed settings are never overwritten.
    settings=json.loads(hint.read_text(encoding='utf-8-sig')) if hint.is_file() else {}
    if not isinstance(settings,dict):raise ValueError('local_paths.json must be an object; existing file preserved')
    payload=download() if archive is None else archive
    if hashlib.sha256(payload).hexdigest()!=ARCHIVE_SHA256:
        raise ValueError('Official package checksum differs; no assets/settings were replaced')
    files={}
    with tarfile.open(fileobj=io.BytesIO(payload),mode='r:gz') as bundle:
        # Whitelist exact members; do not execute setup.py or extract paths.
        for i in range(16):
            name=f'mesh_{i}.cmf';members=[m for m in bundle.getmembers() if m.name==PREFIX+name]
            if len(members)!=1 or not members[0].isfile() or not 0<members[0].size<2*1024*1024:
                raise ValueError('Expected Soccar asset missing or invalid: '+name)
            files[name]=bundle.extractfile(members[0]).read()
    assets=root/'assets';assets.mkdir(exist_ok=True)
    target=assets/'collision_meshes';stamp=str(time.time_ns());backup=None
    stage=Path(tempfile.mkdtemp(prefix='.mesh_restore_',dir=assets))
    try:
        (stage/'soccar').mkdir()
        for name,data in files.items():(stage/'soccar'/name).write_bytes(data)
        unchanged=target.is_dir() and all((target/'soccar'/n).is_file() and (target/'soccar'/n).read_bytes()==b for n,b in files.items())
        if not unchanged:
            if target.exists():
                backup=assets/('collision_meshes.before_restore_'+stamp);os.rename(target,backup)
            try:os.rename(stage,target)
            except BaseException:
                if backup is not None and not target.exists():os.rename(backup,target)
                raise
        if hint.exists():shutil.copy2(hint,root/('local_paths.before_mesh_restore_'+stamp+'.json'))
        settings['meshes']=str(target);atomic_json(hint,settings)
        result={'status':'restored','mesh_root':str(target),'soccar_mesh_count':16,'package':'rlgym-rocket-league==2.0.1',
            'source':URL,'archive_sha256':ARCHIVE_SHA256,
            'mesh_sha256':{n:hashlib.sha256(b).hexdigest() for n,b in files.items()},
            'previous_asset_folder':str(backup) if backup is not None else None,
            'training_started':False,'checkpoints_modified':False,'packages_installed':False}
        atomic_json(root/'collision_mesh_repair.json',result)
        print('MESHES_RESTORED: 16 verified Soccar files at',target,flush=True)
        print('PATH_UPDATED:',hint,flush=True)
        print('No training started; checkpoints, Torch and CUDA were untouched. Run 63_START_NO_BOOST_FLIP.bat again.',flush=True)
        return result
    finally:
        if stage.exists():shutil.rmtree(stage)

if __name__=='__main__':
    try:restore()
    except Exception as ex:
        print('MESH_RECOVERY_FAILED:',type(ex).__name__,str(ex),flush=True)
        print('Keep this output. You can also restore the deleted collision_meshes folder from the Windows Recycle Bin.',flush=True)
        sys.exit(1)
