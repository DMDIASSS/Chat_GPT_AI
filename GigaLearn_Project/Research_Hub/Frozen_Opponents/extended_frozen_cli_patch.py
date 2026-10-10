"""Safe, idempotent extension to frozen_cli.py: optional checkpoint frequency and random seed.
Never edits C++ sources/checkpoints. Known-source anchors required, with backup.
"""
from pathlib import Path
import os
import sys

HERE=Path(__file__).resolve().parent
TARGET=HERE/'frozen_cli.py'
BACKUP=HERE/'frozen_cli.py.before_extended_rotation_v1.bak'
MARK='GL_EXTENDED_SAVE_CONFIG_V1'


def modify(source):
    if MARK in source:return source
    required=(
        "'GL_HUB_SAVE_EVERY':'4096',",
        "'GL_HUB_SEED':'734891',",
        "p.add_argument('--games',type=int,default=4)",
        'def run(args):',
        'FROZEN_WORKER_SUBPROCESS_V1',
        'FROZEN_DLL_BUILD_GUARD_V1',
    )
    for val in required:
        if source.count(val)!=1:
            raise RuntimeError('Unexpected frozen_cli.py source. Refusing patch for '+repr(val))
    source=source.replace("'GL_HUB_SAVE_EVERY':'4096',",
        "'GL_HUB_SAVE_EVERY':str(args.save_every), # "+MARK,1)
    source=source.replace("'GL_HUB_SEED':'734891',", "'GL_HUB_SEED':str(args.run_seed),",1)
    source=source.replace('def run(args):','''def run(args):
    if args.save_every < 8192 or args.save_every > 262144 or args.save_every % 4096:
        raise ValueError('Checkpoint interval must be a 4096-multiple between 8192 and 262144')
    if not 1 <= args.run_seed <= 2000000000:
        raise ValueError('Seed must be 1..2000000000')''',1)
    source=source.replace("p.add_argument('--games',type=int,default=4)",
        "p.add_argument('--games',type=int,default=4)\n    p.add_argument('--save-every',type=int,default=32768)\n    p.add_argument('--run-seed',type=int,default=734891)",1)
    compile(source,str(TARGET),'exec')
    return source


def install():
    if not TARGET.is_file():raise FileNotFoundError('Missing '+str(TARGET))
    orig=TARGET.read_text(encoding='utf-8-sig')
    updated=modify(orig)
    if updated==orig:
        print('PASS: Extended checkpoint controls already installed.')
        return
    if BACKUP.exists():
        if BACKUP.read_text(encoding='utf-8-sig')!=orig:
            raise RuntimeError('Original backup conflicts. Stopping rather than overwriting.')
    else:
        BACKUP.write_bytes(TARGET.read_bytes())
    tmp=TARGET.with_name('frozen_cli.py.extended_tmp')
    try:
        tmp.write_text(updated,encoding='utf-8')
        os.replace(tmp,TARGET)
    finally:
        tmp.unlink(missing_ok=True)
    print('PASS: Extended checkpoint interval/seed options installed; CLI backed up at',BACKUP)

if __name__=='__main__':
    try:install()
    except Exception as e:
        print('ERROR:',e,file=sys.stderr);raise SystemExit(1)
