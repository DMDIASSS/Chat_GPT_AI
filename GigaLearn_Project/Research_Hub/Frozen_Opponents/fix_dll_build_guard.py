"""Repair the incorrect EXE timestamp gate for GigaLearnCPP's DLL build.

Only patches the known v1 verify_install() function; preserves other user code.
No C++ source or checkpoint is modified.
"""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
TARGET = HERE / 'frozen_cli.py'
BACKUP = HERE / 'frozen_cli.py.before_dll_build_guard_v1.bak'
MARK = 'FROZEN_DLL_BUILD_GUARD_V1'


def change(code: str) -> str:
    if MARK in code:
        return code
    start = code.find('def verify_install():\n')
    end = code.find('\ndef preflight(', start)
    if start < 0 or end < 0:
        raise RuntimeError('Expected v1 source anchors missing; refusing unsafe patch')
    old = code[start:end]
    required = (
        "EXECUTABLE.stat().st_mtime < learner.stat().st_mtime",
        "'FROZEN_NEXTO_BRIDGE_V1'",
        "def verify_install():",
    )
    if not all(part in old for part in required):
        raise RuntimeError('Unknown version or modified guard; refusing unsafe patch')
    replacement = '''def verify_install():
    # FROZEN_DLL_BUILD_GUARD_V1: Learner.cpp is compiled into GigaLearnCPP.dll,
    # not the launcher executable. Check compiled DLL freshness and embedded code.
    learner = PROJECT / 'upstream/GigaLearnCPP/src/public/GigaLearnCPP/Learner.cpp'
    header = PROJECT / 'upstream/GigaLearnCPP/src/public/GigaLearnCPP/Util/FrozenNextoBridge.h'
    if not learner.is_file() or 'FROZEN_NEXTO_BRIDGE_V1' not in learner.read_text(encoding='utf-8-sig'):
        raise RuntimeError('Run 1_INSTALL.bat first: Learner.cpp is not patched')
    if not header.is_file():
        raise RuntimeError('Missing frozen bridge header; run 1_INSTALL.bat / repair header')
    if not EXECUTABLE.is_file() or EXECUTABLE.stat().st_size == 0:
        raise FileNotFoundError('Run 2_BUILD.bat first: ' + str(EXECUTABLE))
    dll = EXECUTABLE.with_name('GigaLearnCPP.dll')
    if not dll.is_file() or dll.stat().st_size == 0:
        raise FileNotFoundError('Compiled GigaLearnCPP.dll missing; run 2_BUILD.bat: ' + str(dll))
    # Preserve a freshness check, but point it at the actual compiled artifact.
    latest_src = max(learner.stat().st_mtime, header.stat().st_mtime)
    if dll.stat().st_mtime + 2.0 < latest_src:
        raise RuntimeError('Compiled GigaLearnCPP.dll is older than patched source/header; run 2_BUILD.bat')
    # Ensure we didn't pick up an unrelated/stale DLL with a newer timestamp.
    dll_bytes = dll.read_bytes()
    for literal in (b'GL_FROZEN_BRIDGE', b'GL_FROZEN_STOP_AFTER_STEPS', b'GL_FROZEN_STEPS_PER_OPPONENT'):
        if literal not in dll_bytes:
            raise RuntimeError('Compiled GigaLearnCPP.dll lacks frozen teacher code ('
                               + literal.decode('ascii') + '); run 2_BUILD.bat')
    print('PASS: GigaLearnCPP.dll is fresh and contains frozen teacher bridge markers')

'''
    return code[:start] + replacement + code[end:]


def install(target=TARGET, backup=BACKUP):
    if not target.is_file():
        raise FileNotFoundError('Missing frozen_cli.py: ' + str(target))
    original = target.read_text(encoding='utf-8-sig')
    updated = change(original)
    if updated == original:
        print('Already repaired: no changes required')
        return False
    if backup.exists():
        if backup.read_text(encoding='utf-8-sig') != original:
            raise RuntimeError('Existing backup differs; refusing to replace it')
    else:
        backup.write_bytes(target.read_bytes())
    tmp = target.with_name('frozen_cli.py.dll_guard_tmp')
    try:
        tmp.write_text(updated, encoding='utf-8')
        compile(updated, str(target), 'exec')
        tmp.replace(target)
    finally:
        tmp.unlink(missing_ok=True)
    print('SUCCESS: Corrected verification to check GigaLearnCPP.dll, without bypassing source checks')
    print('Backup:', backup)
    return True


if __name__ == '__main__':
    try:
        install()
    except Exception as exc:
        print('ERROR:', exc, file=sys.stderr)
        sys.exit(1)
