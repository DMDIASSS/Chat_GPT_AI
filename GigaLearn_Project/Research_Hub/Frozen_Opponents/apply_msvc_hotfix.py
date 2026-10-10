"""Safe incremental fix for FrozenNextoBridge v1 MSVC shape and action-count bugs.

No third-party Python packages required. Patches ONLY FrozenNextoBridge.h.
Aborts if headers are unfamiliar and preserves individual backups.
"""
from __future__ import annotations
import os
from pathlib import Path
import shutil
import sys

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
TARGETS = [
    HERE / 'FrozenNextoBridge.h',
    PROJECT / 'upstream' / 'GigaLearnCPP' / 'src' / 'public' / 'GigaLearnCPP' / 'Util' / 'FrozenNextoBridge.h',
]

OLD_SHAPE = 'auto payload = py::array_t<float>({static_cast<py::ssize_t>(arenas), 89});'
NEW_SHAPE = ('std::vector<py::ssize_t> payloadShape = {'
             'static_cast<py::ssize_t>(arenas), static_cast<py::ssize_t>(89)};\n'
             '        py::array_t<float> payload(payloadShape);')
OLD_NUM_ACTIONS = 'if (env.state.gameStates.empty() || env.numActions != 90)'
NEW_NUM_ACTIONS = ('if (env.state.gameStates.empty() || env.actionParsers.empty() ||\n'
                   '            env.actionParsers.at(0)->GetActionAmount() != 90)')


def fix_text(source: str) -> str:
    if OLD_SHAPE in source and NEW_SHAPE not in source:
        if source.count(OLD_SHAPE) != 1:
            raise ValueError('ambiguous NumPy shape construction')
        source = source.replace(OLD_SHAPE, NEW_SHAPE, 1)
    elif NEW_SHAPE not in source:
        raise ValueError('unknown NumPy shape construction; refusing replacement')
    if OLD_NUM_ACTIONS in source and NEW_NUM_ACTIONS not in source:
        if source.count(OLD_NUM_ACTIONS) != 1:
            raise ValueError('ambiguous action-count guard')
        source = source.replace(OLD_NUM_ACTIONS, NEW_NUM_ACTIONS, 1)
    elif NEW_NUM_ACTIONS not in source:
        raise ValueError('unknown action-count guard; refusing replacement')
    if source.count('class FrozenNextoBridge') != 1 or source.count('namespace GGL {') != 1:
        raise ValueError('unexpected bridge header identity')
    return source


def apply(targets=TARGETS):
    prepared = []
    for p in targets:
        if not p.is_file():
            raise FileNotFoundError(f'Required header missing: {p}. Run 1_INSTALL.bat first.')
        old = p.read_bytes()
        try:
            s = old.decode('utf-8-sig')
        except UnicodeError as exc:
            raise ValueError(f'File is not UTF-8: {p}') from exc
        fixed = fix_text(s).encode('utf-8')
        backup = p.with_name('FrozenNextoBridge.h.before_msvc_fix_v1.bak')
        if fixed != old and backup.exists() and backup.read_bytes() != old:
            raise FileExistsError(f'Existing backup does not match current source: {backup}')
        prepared.append((p, old, fixed, backup))
    # Validate all target contents before writing either file.
    for p, old, fixed, backup in prepared:
        if fixed == old:
            print('ALREADY FIXED:', p)
            continue
        if not backup.exists():
            shutil.copy2(p, backup)
        tmp = p.with_name(p.name + '.hotfix_tmp')
        if tmp.exists():
            raise FileExistsError(f'Refusing to overwrite temporary file: {tmp}')
        try:
            with open(tmp, 'xb') as out:
                out.write(fixed)
            os.replace(tmp, p)
        finally:
            tmp.unlink(missing_ok=True)
        print('PATCHED:', p)
        print('BACKUP:', backup)
    print('SUCCESS: Fixed pybind11 shape construction + action parser count. Rebuild now.')


if __name__ == '__main__':
    try:
        apply()
    except Exception as exc:
        print('ERROR:', exc, file=sys.stderr)
        raise SystemExit(1)
