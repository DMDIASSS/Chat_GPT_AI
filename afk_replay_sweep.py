"""Safe replay BC hyperparameter sweep using the existing cached replay dataset.

Each trial isolated under data/afk_improved/replay_sweeps, no promotion, no overwrite.
Use verify separately after candidate exists. Raw TAS .data is audit-only.
"""
from __future__ import annotations
import argparse
import contextlib
import contextlib
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parent
OLD=ROOT/'data'/'afk_improved'/'learning'
BASE=ROOT/'data'/'afk_improved'/'replay_sweeps'
TRIALS=[('small_step',3e-7,3.0,.030,.83),('moderate_step',6e-7,4.0,.045,.79),('exploration',1.2e-6,6.0,.065,.75)]

def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()

def check():
 files=[OLD/'native_replay_dataset.npz',OLD/'dataset_manifest.json',ROOT/'afk_replay_tas_learning.py']
 for p in files:
  if not p.is_file():raise FileNotFoundError(f'Missing required input: {p}. Run Replay + TAS Learning build first.')
 manifest=json.loads((OLD/'dataset_manifest.json').read_text('utf8'))
 print('Replay dataset:',manifest.get('frames', '?'),'frames; unique replays:',manifest.get('unique_replays','?'))
 print('SHA256 dataset:',sha(files[0]));print('TAS direct training: DISABLED (unverified inputs)')

def snapshot_trial(name):
 dest=BASE/name
 if dest.exists():raise FileExistsError('Trial exists; no overwrites: '+str(dest))
 dest.mkdir(parents=True)
 for filename in ('native_replay_dataset.npz','dataset_manifest.json'):
  source=OLD/filename;target=dest/filename
  try:os.link(source,target)
  except OSError:shutil.copy2(source,target)
 for filename in ('anchor_logits.npy','anchor_meta.json'):
  source=OLD/filename;target=dest/filename
  if source.is_file():
   try:os.link(source,target)
   except OSError:shutil.copy2(source,target)
 return dest


@contextlib.contextmanager
def main_learning_guard():
    """Prevent overlapping standard replay learning and sweep variants on Windows."""
    lock=OLD/'.learning.lock';lock.parent.mkdir(parents=True,exist_ok=True)
    with lock.open('a+b') as f:
        f.seek(0);f.write(b'0');f.flush();f.seek(0)
        if os.name=='nt':
            import msvcrt
            try:msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
            except OSError as e:raise RuntimeError('Ordinary replay training still active; wait for it to finish') from e
        else:
            import fcntl
            try:fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError as e:raise RuntimeError('Ordinary replay training still active') from e
        try:yield
        finally:
            f.seek(0)
            if os.name=='nt':msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
            else:fcntl.flock(f.fileno(),fcntl.LOCK_UN)

def train(n=1,epochs=2):
 check()
 if not 1<=n<=3 or not 1<=epochs<=6:raise ValueError('1–3 branches, 1–6 epochs')
 BASE.mkdir(parents=True,exist_ok=True)
 for name,lr,anchor,kl,agree in TRIALS[:n]:
  directory=snapshot_trial(name)
  args=[sys.executable,str(ROOT/'afk_replay_tas_learning.py'),'train',
        '--epochs',str(epochs),'--batch-size','128','--lr',str(lr),'--anchor',str(anchor),
        '--max-kl',str(kl),'--min-agreement',str(agree),'--patience','1']
  env=os.environ.copy();env['AFK_REPLAY_EXPERIMENT_DIR']=str(directory)
  print('START replay BC:',name,' output:',directory,' lr:',lr,' anchor:',anchor,flush=True)
  logfile=directory/'training_console.log'
  with logfile.open('a',encoding='utf8') as stream:
   stream.write('Command: '+repr(args)+'\n');stream.flush()
   with subprocess.Popen(args,cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                         text=True,encoding='utf-8',errors='replace',bufsize=1) as proc:
    for line in proc.stdout:
     stream.write(line);stream.flush();print('['+name+']',line,end='',flush=True)
    code=proc.wait()
  (directory/'trial_meta.json').write_text(json.dumps({'name':name,'lr':lr,'anchor':anchor,'max_kl':kl,
       'min_agreement':agree,'source_dataset_sha':sha(OLD/'native_replay_dataset.npz'),'exitcode':code},indent=2),encoding='utf8')
  if code: print('WARN: replay branch exited with nonzero status:',code,flush=True)
 summarize()

def summarize():
 BASE.mkdir(parents=True,exist_ok=True)
 items=[]
 for path in sorted(BASE.iterdir()):
  if not path.is_dir():continue
  report=path/'training_report.json';meta=path/'trial_meta.json'
  if report.is_file():
   value=json.loads(report.read_text('utf8'))
   items.append({'trial':path.name,'epoch':value.get('best_epoch'),
                'candidate_exists':(path/'replay_candidate.pt').is_file(),
                'best_metrics':value.get('best'),'status':value.get('status'),
                'checkpoint':str(path/'replay_candidate.pt') if (path/'replay_candidate.pt').is_file() else None})
  else:items.append({'trial':path.name,'status':'no_training_report','candidate_exists':False})
 dest=BASE/'sweep_summary.json';dest.write_text(json.dumps({'trials':items,
       'note':'Offline imitation metrics only. Must run --verify separately; never auto-promote.'},indent=2),encoding='utf8')
 print('Saved sweep summary',dest)
 for item in items:print(item)

def verify(name,games):
 if name not in [t[0] for t in TRIALS]:raise ValueError('Unknown trial')
 directory=BASE/name
 if not (directory/'replay_candidate.pt').is_file():raise FileNotFoundError('No offline accepted candidate in '+str(directory))
 env=os.environ.copy();env['AFK_REPLAY_EXPERIMENT_DIR']=str(directory)
 cmd=[sys.executable,str(ROOT/'afk_replay_tas_learning.py'),'verify','--games',str(games),'--seed','734891']
 print('Independent gameplay check only, no promotion',flush=True)
 subprocess.run(cmd,cwd=ROOT,env=env,check=True)

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('command',choices=['check','train','summary','verify'])
 p.add_argument('--trials',type=int,default=1);p.add_argument('--epochs',type=int,default=2)
 p.add_argument('--name',default='small_step');p.add_argument('--games',type=int,default=80)
 args=p.parse_args()
 if args.command=='check':check()
 elif args.command=='train':
  with main_learning_guard():train(args.trials,args.epochs)
 elif args.command=='summary':summarize()
 elif args.command=='verify':verify(args.name,args.games)
if __name__=='__main__':main()
