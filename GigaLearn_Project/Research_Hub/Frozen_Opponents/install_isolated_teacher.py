"""Install frozen teacher process isolation without touching native code or models."""
from __future__ import annotations
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
MAIN=HERE/'frozen_nexto_bridge.py'
SHIM=HERE/'frozen_nexto_bridge_isolated.py'
CORE=HERE/'frozen_nexto_worker_core.py'
CLI=HERE/'frozen_cli.py'
WORKER=HERE/'frozen_nexto_worker_main.py'
MARK='FROZEN_WORKER_SUBPROCESS_V1'


def patch_cli(code):
    if MARK in code:return code
    a="'GL_FROZEN_SITE_PACKAGES':str(BASE/'.venv/Lib/site-packages'),"
    if code.count(a)!=1:raise RuntimeError('Could not find known v1 environment setup in frozen_cli.py')
    code=code.replace(a,a+"\n            'GL_FROZEN_PYTHON_EXE':sys.executable,",1)
    a="        if not env.get('GIGALEARN_MESHES'):"
    if code.count(a)!=1:raise RuntimeError('Could not find known v1 mesh setup in frozen_cli.py')
    code=code.replace(a,
        "        # "+MARK+": subprocess must receive the project wheel packages.\n"
        "        env['PYTHONPATH'] = str(BASE / '.venv/Lib/site-packages') + os.pathsep + env.get('PYTHONPATH','')\n"+a,1)
    a="        with logfile.open('a',encoding='utf-8') as log:"
    if code.count(a)!=1:raise RuntimeError('Could not find v1 subprocess log anchor')
    code=code.replace(a,"        fatal_seen = False\n"+a,1)
    a="                for line in proc.stdout:\n                    log.write(line);"
    if code.count(a)!=1:raise RuntimeError('Could not find v1 stdout log anchor')
    code=code.replace(a,"                for line in proc.stdout:\n                    if 'RG FATAL ERROR:' in line or 'Exception thrown during main learner loop:' in line:\n                        fatal_seen = True\n                    log.write(line);",1)
    a='                rc=proc.wait()'
    if code.count(a)!=1:raise RuntimeError('Could not find v1 exit code capture')
    code=code.replace(a,"                rc=proc.wait()\n        if fatal_seen:\n            rc = rc or 95\n            print('ERROR: Trainer reported a fatal error; checkpoint cannot be marked successful')",1)
    a="        if int(last.name)<=old_step:"
    if code.count(a)==1:
        code=code.replace(a,
            "        if int(last.name) < old_step + args.steps:\n"
            "            raise RuntimeError('No checkpoint reached requested new student steps; training did not complete')\n"
            +a,1)
    compile(code,'frozen_cli.py','exec')
    return code


def install():
    for file in (MAIN,SHIM,CLI,WORKER):
        if not file.is_file():raise FileNotFoundError('Missing file: '+str(file))
    original=MAIN.read_text(encoding='utf-8-sig')
    if 'FROZEN_WORKER_ISOLATION_V1' not in original:
        if 'class FrozenRotation' not in original or 'from nexto_obs import' not in original or 'import torch' not in original:
            raise RuntimeError('Unexpected installed frozen_nexto_bridge.py; refusing unsafe replacement')
        if CORE.exists():
            if CORE.read_text(encoding='utf-8-sig')!=original:
                raise RuntimeError('Existing worker core conflicts with installed bridge; do not overwrite')
        else:
            CORE.write_bytes(MAIN.read_bytes())
        backup=HERE/'frozen_nexto_bridge.py.before_worker_isolation_v1.bak'
        if not backup.exists(): backup.write_bytes(MAIN.read_bytes())
        elif backup.read_bytes()!=MAIN.read_bytes():raise RuntimeError('Old backup differs; refusing overwrite')
        updated=SHIM.read_text(encoding='utf-8')
        compile(updated,'frozen_nexto_bridge.py','exec')
        MAIN.write_text(updated,encoding='utf-8')
        print('Installed subprocess-only frozen teacher bridge; original teacher core preserved')
    else:
        if not CORE.exists():raise RuntimeError('Worker core missing; refusing partial install')
        print('Teacher subprocess bridge already installed')
    original_cli=CLI.read_text(encoding='utf-8-sig')
    updated_cli=patch_cli(original_cli)
    if updated_cli!=original_cli:
        cli_backup=HERE/'frozen_cli.py.before_worker_isolation_v1.bak'
        if not cli_backup.exists():cli_backup.write_bytes(CLI.read_bytes())
        elif cli_backup.read_bytes()!=CLI.read_bytes():raise RuntimeError('CLI backup differs; refusing overwrite')
        CLI.write_text(updated_cli,encoding='utf-8')
        print('Installed fail-closed launcher checks; CLI backup preserved')
    else: print('Launcher subprocess patch already installed')
    print('PASS: No GigaLearn C++ rebuild necessary. No model/checkpoint files touched.')

if __name__=='__main__':
    try:install()
    except Exception as e:
        print('ERROR:',e,file=sys.stderr);sys.exit(1)
