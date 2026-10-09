"""Download and summarize a small number of public 1v1 replays once."""
import os
from pathlib import Path
from league_replays import ReplayWorker

if __name__=='__main__':
    root=Path(__file__).resolve().parent
    if not os.getenv('BALLCHASING_TOKEN'):
        raise SystemExit('Set BALLCHASING_TOKEN for this terminal session first; see README_AUTOLEAGUE.md.')
    w=ReplayWorker(root,root/'data'/'autoleague',3600,3)
    w._job()
