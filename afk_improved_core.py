"""File safety, checkpoint inventory, independent archive helpers for AFK Improved.
No Torch or RocketSim imports; management UI works without simulator dependencies.
"""
from __future__ import annotations
import hashlib
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data' / 'afk_improved'
LEAGUE = DATA / 'league'
CYCLE9 = ROOT/'data'/'autoleague'/'backups'/'20261008T224518_775472Z_cycle0009_steps000008192_candidate.pt'
CYCLE9_SHA = '50f34d4a3723bc2849c97200e8e42969e0cc1d82328473b017505994be1966d2'
MAIN_CHAMPION = ROOT/'data'/'autoleague'/'champion.pt'
MAIN_STATE = ROOT/'data'/'autoleague'/'league_state.json'
STOP_REQUEST = DATA/'pause.request'
STATUS = DATA/'status.json'
BEST = DATA/'best_verified.pt'
BEST_STATE = DATA/'best_verified.json'
LOCK = DATA/'.runner.lock'

def hash_file(path: Path) -> str:
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):
            h.update(chunk)
    return h.hexdigest()

def now():
    return datetime.now(timezone.utc).isoformat()

def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return default

def atomic_json(path, value):
    path=Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.tmp')
    tmp.write_text(json.dumps(value,indent=2,sort_keys=True),encoding='utf-8')
    os.replace(tmp,path)

def atomic_copy(src,dest):
    src,dest=Path(src),Path(dest)
    dest.parent.mkdir(parents=True,exist_ok=True)
    tmp=dest.with_name(dest.name+'.incomplete')
    try:
        shutil.copy2(src,tmp)
        os.replace(tmp,dest)
    finally:tmp.unlink(missing_ok=True)

def protected_paths():
    return (MAIN_CHAMPION,MAIN_STATE,CYCLE9)

def assert_main_league_idle():
    """Fail fast if ordinary AutoLeague has the same lock open.

    Uses the same byte-region OS lock as auto_league.exclusive_league_lock.
    It does not remove or replace another process's lock file.
    """
    lock=MAIN_CHAMPION.parent/'.training.lock'
    lock.parent.mkdir(parents=True,exist_ok=True)
    with lock.open('a+b') as fh:
        fh.seek(0);fh.write(b'0');fh.flush();fh.seek(0)
        if os.name=='nt':
            import msvcrt
            try:msvcrt.locking(fh.fileno(),msvcrt.LK_NBLCK,1)
            except OSError as exc:
                raise RuntimeError('Main AutoLeague is running — pause it before AFK Improved') from exc
            fh.seek(0);msvcrt.locking(fh.fileno(),msvcrt.LK_UNLCK,1)
        else:
            import fcntl
            try:fcntl.flock(fh.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError('Main AutoLeague is running — pause it before AFK Improved') from exc
            fcntl.flock(fh.fileno(),fcntl.LOCK_UN)

def verify_starting_files():
    if not CYCLE9.is_file():
        raise FileNotFoundError(f'Missing Cycle 9 checkpoint: {CYCLE9}')
    actual=hash_file(CYCLE9)
    if actual!=CYCLE9_SHA:
        raise RuntimeError(f'Cycle 9 SHA mismatch: expected {CYCLE9_SHA[:16]}, got {actual[:16]}')
    if not (MAIN_CHAMPION.is_file() and MAIN_STATE.is_file()):
        raise FileNotFoundError('Main champion and league_state.json must be present')
    state=read_json(MAIN_STATE,{})
    if hash_file(MAIN_CHAMPION)!=state.get('champion_sha'):
        raise RuntimeError('Original champion hash differs from main league_state.json')
    return {str(p):hash_file(p) for p in protected_paths()}

def verify_untouched(hashes):
    changed=[p for p,hash_ in hashes.items() if not Path(p).exists() or hash_file(p)!=hash_]
    if changed:
        raise RuntimeError('Protected inputs changed: '+', '.join(changed))

def existing_checkpoint_verified():
    if not BEST.exists():return False
    meta=read_json(BEST_STATE,{})
    return meta.get('sha256')==hash_file(BEST)

def init_best():
    DATA.mkdir(parents=True,exist_ok=True)
    if BEST.exists() or BEST_STATE.exists():
        if not existing_checkpoint_verified():
            raise RuntimeError('Best checkpoint checksum mismatch. Restore manually; refusing overwrite.')
        return False
    if (LEAGUE/'league_state.json').exists() or (LEAGUE/'champion.pt').exists():
        raise RuntimeError('Existing experiment league without best metadata. Manual migration required.')
    atomic_copy(CYCLE9,BEST)
    atomic_json(BEST_STATE,dict(sha256=hash_file(BEST),origin=str(CYCLE9.relative_to(ROOT)) if CYCLE9.is_relative_to(ROOT) else str(CYCLE9),
                                status='baseline_from_tournament',verified_cycle=0,created_utc=now()))
    return True

def inventory(limit=10000):
    roots=[ROOT/'data'/'autoleague',ROOT/'data'/'native_nexto',ROOT/'data'/'mechanics',
           ROOT/'data'/'finishing_lab',ROOT/'data'/'tactical_balance',DATA,
           ROOT/'data'/'checkpoints']
    out=[]
    seen=set()
    for folder in roots:
        if not folder.is_dir():continue
        for p in folder.rglob('*.pt'):
            if p in seen:continue
            seen.add(p)
            if len(out)>=limit:return out
            try:
                s=p.stat()
                out.append({'path':str(p.relative_to(ROOT)),'bytes':s.st_size,
                            'modified':datetime.fromtimestamp(s.st_mtime).strftime('%Y-%m-%d %H:%M')})
            except OSError:pass
    return sorted(out,key=lambda v:v['path'])

def safe_copy_selected(relative_path):
    path=(ROOT/relative_path).resolve()
    if not path.is_file() or path.suffix.lower()!='.pt' or (ROOT/'data').resolve() not in path.parents:
        raise ValueError('Select an existing .pt file inside this project data directory')
    src_sha=hash_file(path)
    out=DATA/'manual_exports'/(path.stem+'_'+src_sha[:12]+'.pt')
    if out.exists():
        if hash_file(out)!=src_sha:raise RuntimeError('Export hash collision')
    else:atomic_copy(path,out)
    return out

def checkpoint_snapshot(paths=None):
    """Immutable backup copies before any optional external mutation. Never deletes originals."""
    if paths is None:assert_main_league_idle()
    paths=tuple(paths or protected_paths())
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=DATA/'manual_backups'/stamp
    if out.exists():raise RuntimeError('Timestamped backup exists; retry in one second')
    out.mkdir(parents=True)
    manifest=[]
    for p in paths:
        p=Path(p)
        if not p.exists():raise FileNotFoundError(p)
        dst=out/p.name
        if dst.exists():dst=out/(p.parent.name+'_'+p.name)
        shutil.copy2(p,dst)
        if hash_file(p)!=hash_file(dst):raise RuntimeError('Backup checksum mismatch')
        manifest.append({'source':str(p),'backup':str(dst),'sha256':hash_file(dst)})
    atomic_json(out/'MANIFEST.json',manifest)
    return out
