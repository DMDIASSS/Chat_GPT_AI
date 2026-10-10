"""One-time safe patch of Research Hub's already-modified GigaLearn ExampleMain.cpp.
Does NOT modify binary/checkpoints/models/experiment folders. Compile after patching.
Works on the exact Hub v1 PPO minibatch assignment; refuses unknown source.
"""
from pathlib import Path
import os
import sys

HERE=Path(__file__).resolve().parent
MAIN=HERE.parent/'upstream'/'src'/'ExampleMain.cpp'
MARKER=b'AFK_RESEARCH_HUB_PPO_BATCH_FIX_V1'
OLD=b'cfg.ppo.miniBatchSize = std::min(tsPerItr, 2048);'
REPLACEMENT="""// AFK_RESEARCH_HUB_PPO_BATCH_FIX_V1: align effective PPO batch to a whole number of minibatches.
    const int hubMiniBatchSize = std::min(tsPerItr, 2048);
    tsPerItr = (tsPerItr / hubMiniBatchSize) * hubMiniBatchSize;
    cfg.ppo.tsPerItr = tsPerItr;
    cfg.ppo.batchSize = tsPerItr;
    cfg.ppo.miniBatchSize = hubMiniBatchSize;
    std::cout << "[Research Hub] PPO samples/iteration=" << tsPerItr << " minibatch=" << hubMiniBatchSize << std::endl;"""

def patch_bytes(data: bytes):
    if MARKER in data:
        return data,False
    if b'AFK_RESEARCH_HUB_PATCH_V1' not in data:
        raise RuntimeError('Source lacks Research Hub v1 patch. First run HUB_1_PATCH_CPP.bat.')
    if data.count(OLD) != 1:
        raise RuntimeError('Expected exactly one Research Hub minibatch assignment; source left unchanged.')
    for field in [b'cfg.ppo.tsPerItr = tsPerItr;',b'cfg.ppo.batchSize = tsPerItr;']:
        if field not in data:
            raise RuntimeError('Required PPO batch assignment missing; source left unchanged.')
    newline='\r\n' if b'\r\n' in data else '\n'
    replacement=REPLACEMENT.replace('\n',newline).encode('utf8')
    result=data.replace(OLD,replacement,1)
    return result,True

def main():
    if not MAIN.is_file():
        raise RuntimeError('C++ source not found: '+str(MAIN))
    data=MAIN.read_bytes()
    updated,changed=patch_bytes(data)
    if not changed:
        print('PPO batch fix already present. No source changed.')
        return 0
    backup=MAIN.with_name(MAIN.name+'.before_ppo_batch_fix_v1.bak')
    if backup.exists():
        raise RuntimeError('Safety backup already exists, refusing to replace: '+str(backup))
    # Persist backup atomically, never overwrite a prior backup.
    with backup.open('xb') as f:f.write(data)
    temp=MAIN.with_name(MAIN.name+'.ppo_batch_fix_tmp')
    try:
        with temp.open('xb') as f:f.write(updated)
        os.replace(temp,MAIN)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise
    print('FIXED:',MAIN)
    print('Saved original source to:',backup)
    print('The default 5000 steps now aligns safely to 4096 with minibatch 2048.')
    print('Run BUILD_IN_VS2022_DEV_PROMPT.bat in a Visual Studio x64 Developer Prompt.')
    return 0

if __name__=='__main__':
    try:sys.exit(main())
    except Exception as e:
        print('ERROR:',e,file=sys.stderr);sys.exit(1)
