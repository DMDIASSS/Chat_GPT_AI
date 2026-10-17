"""Patch exported replay bots' boost mapping without touching private weights."""
from pathlib import Path
import argparse
import json
import os
import shutil
import tempfile
from slater_v041_core import sha256

ROOT=Path(__file__).resolve().parent
RUNTIME_FILES={'policy.pt','tokens.npy','bot.py','replay_rlbot_core.py','replay_nexto_obs.py'}


def repair(folder,*,scripted_kickoff=False):
    folder=Path(folder).resolve();info=folder/'EXPORT_INFO.json'
    metadata=json.loads(info.read_text(encoding='utf8'))
    if metadata.get('format')!='replay-chunk-rlbot-v4-v1':raise ValueError('This is not a replay-model RLBot export')
    hashes=metadata.get('runtime_sha256',{})
    if set(hashes)!=RUNTIME_FILES:raise ValueError('Unexpected export file manifest')
    for name,digest in hashes.items():
        if sha256(folder/name)!=digest:raise ValueError('Export file changed: '+name+'. Re-export with a new name rather than patching this folder.')
    sources={'bot.py':(ROOT/'replay_rlbot_agent.py').read_bytes(),
             'replay_rlbot_core.py':(ROOT/'replay_rlbot_core.py').read_bytes()}
    if scripted_kickoff:
        settings=json.loads((folder/'runtime.json').read_text(encoding='utf8'))
        settings['scripted_kickoff']=True
        sources['runtime.json']=json.dumps(settings,indent=2).encode('utf8')
    if all((folder/name).read_bytes()==raw for name,raw in sources.items()):
        print('ALREADY UP TO DATE:',folder,flush=True);return folder
    protected={name:sha256(folder/name) for name in ('policy.pt','tokens.npy')}
    originals={name:(folder/name).read_bytes() for name in (*sources,'EXPORT_INFO.json')}
    temporary=Path(tempfile.mkdtemp(prefix='.boost_xy_patch_',dir=folder));written=[]
    try:
        for name,raw in sources.items():
            (temporary/name).write_bytes(raw)
            if name in RUNTIME_FILES:metadata['runtime_sha256'][name]=sha256(temporary/name)
        if scripted_kickoff:metadata['scripted_kickoff']=True
        metadata['boost_mapping_patch']='XY positions; canonical training heights retained'
        (temporary/'EXPORT_INFO.json').write_text(json.dumps(metadata,indent=2),encoding='utf8')
        for name in originals:
            backup=folder/(name+'.before_boost_xy_fix')
            if not backup.exists():backup.write_bytes(originals[name])
        for name in originals:
            os.replace(temporary/name,folder/name);written.append(name)
        if protected!={name:sha256(folder/name) for name in protected}:raise RuntimeError('Private model/vocabulary changed during repair')
    except BaseException:
        for name in reversed(written):
            restore=temporary/(name+'.restore');restore.write_bytes(originals[name]);os.replace(restore,folder/name)
        raise
    finally:shutil.rmtree(temporary,ignore_errors=True)
    print('REPAIRED:',folder/'bot.cfg',flush=True)
    print('Model and tokens unchanged. Restart RLBot and load the same bot.cfg.',flush=True)
    return folder


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--folder',type=Path,default=ROOT/'data/rlbot_exports/ReplayScratch01')
    parser.add_argument('--scripted-kickoff',action='store_true')
    args=parser.parse_args(argv);repair(args.folder,scripted_kickoff=args.scripted_kickoff)


if __name__=='__main__':
    try:main()
    except (ValueError,RuntimeError,OSError) as error:print('STOPPED:',str(error),flush=True);raise SystemExit(1)
