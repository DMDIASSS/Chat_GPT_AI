"""Safe rename, archive, and restore of isolated GigaLearn Research Hub experiments.

Renames and archives directories on the same volume. Never touches native AFK weights,
parent models, C++ source, or live training processes. No permanent deletion API.
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from contextlib import contextmanager
import json
import os
import uuid

import hub_core as hub


class ManagementError(hub.HubError):
    """Operation was refused to protect experiments and their checkpoints."""


def _root() -> Path:
    return hub.EXPERIMENTS


def trash_folder() -> Path:
    # Sibling directory in Research_Hub, on the same filesystem as experiments.
    return _root().parent / 'experiment_trash'


def _experiment(name: str) -> Path:
    if name != hub.slug(name):
        raise ManagementError('Select an existing experiment by its exact table name.')
    p = _root() / name
    if p.is_symlink() or not p.is_dir() or not (p / 'experiment.json').is_file():
        raise ManagementError('Experiment directory or metadata missing: ' + name)
    if (p / 'experiment.json').is_symlink():
        raise ManagementError('Refusing a symlinked experiment metadata file.')
    if p.resolve().parent != _root().resolve():
        raise ManagementError('Experiment path escapes the managed experiments directory.')
    return p


def _check_stopped(p: Path) -> None:
    running = p / 'running.json'
    if running.is_symlink():
        raise ManagementError('Untrusted running.json symlink: cannot safely determine process state.')
    if running.exists():
        try:
            pid = hub.read_json(running).get('pid')
        except (OSError, ValueError, TypeError) as e:
            raise ManagementError('Cannot read running.json; refuse rename/delete until inspected.') from e
        if not isinstance(pid, int) or pid < 1:
            raise ManagementError('Invalid running PID; refuse rename/delete until inspected.')
        try:
            alive = hub.is_alive(pid)
        except (OSError, ValueError) as e:
            raise ManagementError('Unable to verify training process has stopped.') from e
        if alive:
            raise ManagementError(f'Training is active (PID {pid}). Request safe save + stop and wait first.')
    if (p / 'request_safe_stop.flag').exists():
        raise ManagementError('A safe-stop request is still pending. Wait for a clean checkpoint save first.')


@contextmanager
def _management_lock(p: Path):
    # Shares the per-experiment lock that hub_core.start_experiment takes when launching.
    lock = p / 'launch.lock'
    try:
        fd = os.open(str(lock), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as e:
        raise ManagementError('Experiment launch or another management operation is in progress.') from e
    try:
        os.write(fd, b'Experiment rename/archive lock\n')
        os.close(fd)
        fd = -1
        _check_stopped(p)
        yield lock
    finally:
        if fd != -1:
            os.close(fd)
        # A directory move changes the lock path; callers must remove the moved lock.
        lock.unlink(missing_ok=True)


def rename_experiment(old_name: str, new_name: str) -> str:
    src = _experiment(old_name)
    new_slug = hub.slug(new_name.strip())
    if src.name == new_slug:
        raise ManagementError('The new experiment name is the same as the current name.')
    dst = _root() / new_slug
    if dst.exists() or dst.is_symlink():
        raise ManagementError('An experiment with that name already exists: ' + new_slug)
    with _management_lock(src):
        if dst.exists() or dst.is_symlink():
            raise ManagementError('Destination was created by another process: ' + new_slug)
        old_meta = hub.read_json(src / 'experiment.json')
        os.rename(src, dst)  # atomic on same filesystem; never merges or overwrites folders
        try:
            meta = dict(old_meta)
            meta['name'] = new_slug
            meta['renamed_from'] = list(meta.get('renamed_from') or []) + [src.name]
            meta['last_renamed_utc'] = hub.now()
            hub.atomic_json(dst / 'experiment.json', meta)
        except Exception:
            # Restore original on disk if metadata cannot be updated.
            os.rename(dst, src)
            raise
        finally:
            (dst / 'launch.lock').unlink(missing_ok=True)
    return new_slug


def archive_experiment(name: str) -> Path:
    src = _experiment(name)
    with _management_lock(src):
        trash = trash_folder()
        trash.mkdir(parents=True, exist_ok=True)
        if trash.is_symlink() or trash.resolve().parent != _root().resolve().parent:
            raise ManagementError('Unsafe Trash path; refusing to move checkpoints.')
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        dst = trash / f'{stamp}__{src.name}__{uuid.uuid4().hex[:10]}'
        if dst.exists() or dst.is_symlink():
            raise ManagementError('Unexpected Trash collision; nothing deleted.')
        os.rename(src, dst)
        try:
            hub.atomic_json(dst / 'trash_record.json', {
                'experiment_name': src.name,
                'archived_utc': hub.now(),
                'original_path': str(src),
                'policy': 'RECOVERABLE; checkpoints and optimizer states are preserved',
            })
        except Exception:
            os.rename(dst, src)
            raise
        finally:
            (dst / 'launch.lock').unlink(missing_ok=True)
    return dst


def list_trashed_experiments() -> list[dict]:
    trash = trash_folder()
    if not trash.is_dir() or trash.is_symlink():
        return []
    out = []
    for p in sorted(trash.iterdir(), reverse=True):
        if p.is_symlink() or not p.is_dir() or not (p / 'trash_record.json').is_file():
            continue
        try:
            rec = hub.read_json(p / 'trash_record.json')
            out.append({'archive_id': p.name, 'name': rec['experiment_name'], 'archived_utc': rec['archived_utc']})
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return out


def restore_trashed_experiment(archive_id: str) -> str:
    if (not archive_id or '/' in archive_id or '\\' in archive_id or archive_id in ('.', '..')):
        raise ManagementError('Invalid Trash archive identifier.')
    trash = trash_folder()
    src = trash / archive_id
    if src.is_symlink() or not src.is_dir() or src.resolve().parent != trash.resolve():
        raise ManagementError('Trash archive missing or invalid.')
    record = hub.read_json(src / 'trash_record.json')
    original_name = record.get('experiment_name')
    if not isinstance(original_name, str) or original_name != hub.slug(original_name):
        raise ManagementError('Trash record has invalid experiment name.')
    dst = _root() / original_name
    if dst.exists() or dst.is_symlink():
        raise ManagementError('Cannot restore: destination experiment exists. Rename it first.')
    if not (src / 'experiment.json').is_file():
        raise ManagementError('Archive metadata is incomplete.')
    if (src / 'running.json').exists():
        # It may contain a stale PID from a stopped process. Do not resume automatically.
        try:
            pid = hub.read_json(src / 'running.json').get('pid')
        except (OSError, ValueError, TypeError) as e:
            raise ManagementError('Unverifiable running.json in Trash; cannot restore.') from e
        if not isinstance(pid,int) or pid<1 or hub.is_alive(pid):
            raise ManagementError('Training process still active or unknown; cannot restore.')
    _root().mkdir(parents=True,exist_ok=True)
    os.rename(src, dst)
    return original_name
