"""Stationary-target curriculum using the installed DuelForge runtime."""
import argparse,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

def main():
 p=argparse.ArgumentParser()
 p.add_argument('command',choices=['start','pause','watch-held','watch-match','report','evaluate','export'])
 p.add_argument('--steps',type=int,default=500_000);p.add_argument('--seconds',type=float,default=120)
 p.add_argument('--games',type=int,default=200);p.add_argument('--headless',action='store_true')
 a=p.parse_args();root=ROOT/'runs/held01';folder=root/'03_trajectory'
 if a.command=='pause':
  if not root.is_dir():raise FileNotFoundError('Start 56 first; no stationary run exists')
  (root/'STOP').write_text('pause requested\n');print('HELD_PAUSE_REQUESTED: completed PPO update will be saved.',flush=True);return
 from duelforge import held_experiment as experiment
 if a.command=='start':
  import torch
  if not torch.cuda.is_available():raise RuntimeError('CUDA required; select your working CUDA runtime. No CPU fallback or model reset.')
  os.environ['DUELFORGE_DEVICE']='cuda';os.environ['DUELFORGE_WANDB_EXTERNAL']='1'
  experiment.setup(root,root/'baseline.pt' if root.exists() else experiment.source_checkpoint())
  if os.name=='nt':
   subprocess.Popen([sys.executable,'-u',str(ROOT/'tools/wandb_sidecar.py'),'--root',str(root)],
                    cwd=ROOT,creationflags=subprocess.CREATE_NEW_CONSOLE)
   print('W&B runs in its own uploader window; Ctrl+C there closes upload only. Resumes reuse that run.',flush=True)
  return experiment.start(root,steps=a.steps)
 if not (folder/'latest.pt').is_file():raise FileNotFoundError('Run 56 first. No other model will be opened.')
 if a.command=='report':return experiment.report(root)
 if a.command.startswith('watch'):
  from duelforge.watch import watch
  return watch(folder,seconds=a.seconds,opponent='self' if a.command=='watch-held' else 'initial',
               scene=-2,headless=a.headless,held_drills=a.command=='watch-held')
 if a.command=='evaluate':
  from duelforge.evaluate import evaluate
  result=evaluate(folder,games_per_context=a.games,seconds=100,contexts=['match'])
  experiment.report(root);return result
 if a.command=='export':
  from duelforge.export import export
  return export(folder)

if __name__=='__main__':main()
