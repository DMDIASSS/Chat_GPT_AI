"""Prepare, verify 3v3 coverage, then train a separate fresh imitation run."""
from pathlib import Path
import argparse
import subprocess
import sys
from audit_replay_mix import audit

ROOT=Path(__file__).resolve().parent


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run',default='replay_mixed3v3_02')
    parser.add_argument('--dataset',type=Path,default=ROOT/'data/isolated/replay_imitation/dataset_mixed3v3_02')
    parser.add_argument('--inputs',nargs='+',default=[str(ROOT/'data/replays'/name)
        for name in ('ranked-duels','ranked-doubles','ranked-standard')])
    args,extra=parser.parse_known_args(argv)
    common=['--run',args.run,'--dataset',str(args.dataset),'--inputs',*args.inputs,*extra]
    prepare=subprocess.run([sys.executable,'-u','-m','replay_il.launch','prepare',*common],cwd=ROOT)
    if prepare.returncode:return prepare.returncode
    audit(args.dataset)
    return subprocess.run([sys.executable,'-u','-m','replay_il.launch','run',*common],cwd=ROOT).returncode


if __name__=='__main__':
    try:raise SystemExit(main())
    except (ValueError,RuntimeError,OSError) as error:print('STOPPED:',str(error),flush=True);raise SystemExit(1)
