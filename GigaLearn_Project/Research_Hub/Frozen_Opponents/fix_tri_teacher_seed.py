"""Hotfix: preserve --seed=checkpoint for frozen_cli create, use --run-seed for PPO.

No model files, GigaLearn sources, or checkpoint paths are edited.  This intentionally
refuses unknown script versions and checks every file before making any changes.
"""
from __future__ import annotations
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parent
SOURCES = ('frozen_cli.py', 'extended_rotation.py', 'extended_frozen_cli_patch.py')
SUFFIX = '.before_run_seed_hotfix_v1.bak'


def replace_once(src: str, old: str, new: str, name: str) -> str:
    if src.count(old) != 1:
        raise RuntimeError(f'{name}: expected exactly one occurrence of {old!r}, got {src.count(old)}; refusing to edit')
    return src.replace(old, new, 1)


def all_or_none(src: str, old: tuple[str, ...], new: tuple[str, ...], name: str) -> bool:
    original = [src.count(x) for x in old]
    fixed = [src.count(x) for x in new]
    if all(n == 0 for n in original) and all(n == 1 for n in fixed):
        return True
    if not all(n == 1 for n in original) or not all(n == 0 for n in fixed):
        raise RuntimeError(f'{name}: unexpected or partially edited seed arguments (before={original}, after={fixed}). Refusing.')
    return False


def rewrite_frozen(src: str) -> str:
    name = 'frozen_cli.py'
    for anchor in ('GL_EXTENDED_SAVE_CONFIG_V1', 'FROZEN_WORKER_SUBPROCESS_V1', 'FROZEN_DLL_BUILD_GUARD_V1',
                   "p.add_argument('--seed',type=Path,help='Exact GigaLearn 1v1 checkpoint directory to copy, never modified')"):
        if src.count(anchor) != 1:
            raise RuntimeError(f'{name}: unexpected script version, missing/duplicated {anchor!r}')
    originals = (
        'if not 1 <= args.seed <= 2000000000:',
        "'GL_HUB_SEED':str(args.seed),",
        "p.add_argument('--seed',type=int,default=734891)",
    )
    fixed = (
        'if not 1 <= args.run_seed <= 2000000000:',
        "'GL_HUB_SEED':str(args.run_seed),",
        "p.add_argument('--run-seed',type=int,default=734891)",
    )
    if all_or_none(src, originals, fixed, name):
        return src
    for old, new in zip(originals, fixed):
        src = replace_once(src, old, new, name)
    return src


def rewrite_rotation(src: str) -> str:
    name = 'extended_rotation.py'
    if src.count('GIGALEARN_EXTENDED_TRI_TEACHER_V1') != 1:
        raise RuntimeError(f'{name}: unexpected script version')
    orig = "'--save-every',str(save_every),'--seed',str(seed)]"
    fixed = "'--save-every',str(save_every),'--run-seed',str(seed)]"
    if all_or_none(src, (orig,), (fixed,), name):
        return src
    return replace_once(src, orig, fixed, name)


def rewrite_patcher(src: str) -> str:
    name = 'extended_frozen_cli_patch.py'
    if src.count("MARK='GL_EXTENDED_SAVE_CONFIG_V1'") != 1:
        raise RuntimeError(f'{name}: unexpected patcher version')
    orig = (
        'if not 1 <= args.seed <= 2000000000:',
        "'GL_HUB_SEED':str(args.seed)",
        "p.add_argument('--seed',type=int,default=734891)",
    )
    fixed = (
        'if not 1 <= args.run_seed <= 2000000000:',
        "'GL_HUB_SEED':str(args.run_seed)",
        "p.add_argument('--run-seed',type=int,default=734891)",
    )
    if all_or_none(src, orig, fixed, name):
        return src
    for old,new in zip(orig,fixed):
        src = replace_once(src, old, new, name)
    return src


TRANSFORMS = {'frozen_cli.py': rewrite_frozen,
              'extended_rotation.py': rewrite_rotation,
              'extended_frozen_cli_patch.py': rewrite_patcher}


def install(root: Path = ROOT):
    changes = []
    # Do all checks before altering any file, so unknown sources leave everything untouched.
    for filename in SOURCES:
        path = root / filename
        if not path.is_file():
            raise FileNotFoundError(f'Missing {path}; extract previous 1M package first')
        before = path.read_text(encoding='utf-8-sig')
        after = TRANSFORMS[filename](before)
        compile(after, str(path), 'exec')
        changes.append((path, path.read_bytes(), after))
    backups = []
    temps = []
    try:
        for path, original_bytes, after in changes:
            if after == original_bytes.decode('utf-8-sig'):
                continue
            backup = path.with_name(path.name + SUFFIX)
            if backup.exists():
                if backup.read_bytes() != original_bytes:
                    # A patch may have partially applied on a previous run, in
                    # which case its backup should remain immutable.
                    raise RuntimeError(f'Existing backup differs from source: {backup}; inspect manually')
            else:
                with backup.open('xb') as handle:
                    handle.write(original_bytes)
                backups.append(backup)
        for path, original_bytes, after in changes:
            if after == original_bytes.decode('utf-8-sig'):
                continue
            temp = path.with_name(path.name + '.run_seed_hotfix_tmp')
            if temp.exists():
                raise RuntimeError(f'Stale patch temp file: {temp}')
            with temp.open('x', encoding='utf-8') as handle:
                handle.write(after)
            temps.append(temp)
        for path, original_bytes, after in changes:
            if after == original_bytes.decode('utf-8-sig'):
                continue
            os.replace(path.with_name(path.name + '.run_seed_hotfix_tmp'), path)
    finally:
        for temp in temps:
            temp.unlink(missing_ok=True)
    edited = [path.name for path, data, after in changes if after != data.decode('utf-8-sig')]
    print('SUCCESS: Resolved --seed conflict. Fixed:', ', '.join(edited) if edited else '(already fixed)')
    print('Retained checkpoint-create --seed PATH; PPO uses --run-seed INTEGER.')
    print('No models, saved checkpoints, or C++ files were modified.')
    return edited


if __name__ == '__main__':
    try:
        install()
    except Exception as error:
        print('ERROR: hotfix aborted:',error,file=sys.stderr)
        sys.exit(1)
