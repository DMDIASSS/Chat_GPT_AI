"""Safely insert a 1v1 defense preset into Research Hub without changing checkpoints."""
from __future__ import annotations
import ast
from datetime import datetime, timezone
from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parent
TARGET = ROOT / 'hub_core.py'
KEY = b"'Defense Fundamentals 1v1':"
ANCHOR = b"    'Defense Under Pressure 1v2':"
PRESET_LINE = b"    'Defense Fundamentals 1v1': {'mode':'defense','blue':1,'orange':1,'lr':0.00010,'entropy':0.030,'setup':'random'},"


def patch(source: bytes) -> tuple[bytes, bool]:
    if KEY in source:
        if source.count(KEY) != 1:
            raise ValueError('Duplicate Defense Fundamentals 1v1 keys detected; edit manually.')
        return source, False
    if source.count(ANCHOR) != 1:
        raise ValueError('Unsupported hub_core.py: expected exactly one existing Defense Under Pressure 1v2 preset; file unchanged.')
    newline = b'\r\n' if b'\r\n' in source else b'\n'
    updated = source.replace(ANCHOR, PRESET_LINE + newline + ANCHOR, 1)
    ast.parse(updated.decode('utf-8-sig'))
    return updated, True


def main() -> int:
    if not TARGET.is_file():
        print('ERROR: Cannot find Research Hub\\hub_core.py next to this script.')
        return 1
    original = TARGET.read_bytes()
    try:
        updated, changed = patch(original)
    except (ValueError, SyntaxError, UnicodeDecodeError) as e:
        print(f'ERROR: {e}')
        return 1
    if not changed:
        print('Defense Fundamentals 1v1 is already available. No changes needed.')
        return 0
    stamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')
    backup = TARGET.with_name(f'hub_core.py.before_defense_1v1_{stamp}.bak')
    temp = TARGET.with_name(f'hub_core.py.defense_1v1_{stamp}.partial')
    try:
        with backup.open('xb') as b:
            b.write(original)
            b.flush()
            os.fsync(b.fileno())
        with temp.open('xb') as f:
            f.write(updated)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, TARGET)
    except Exception as e:
        print(f'ERROR: Could not safely apply patch: {e}')
        try:
            temp.unlink(missing_ok=True)
        except OSError:
            pass
        return 1
    print('SUCCESS: Added Defense Fundamentals 1v1 preset.')
    print('Backup:', backup)
    print('No C++ rebuild needed; no existing experiments or model files changed.')
    print('Close and reopen Research Hub, then choose Defense Fundamentals 1v1.')
    return 0

if __name__ == '__main__':
    sys.exit(main())
