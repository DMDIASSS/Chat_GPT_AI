import argparse,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

def main():
 p=argparse.ArgumentParser();p.add_argument('command',choices=['start','watch','report','export','evaluate','pause']);p.add_argument('--updates',type=int,default=300);a=p.parse_args()
 from duelforge import jump_bootstrap
 root=ROOT/'runs/jump01';folder=root/'03_trajectory'
 if a.command=='start':
  import torch
  if not torch.cuda.is_available():raise RuntimeError('Use the existing verified CUDA runtime')
  return jump_bootstrap.start(updates=a.updates)
 if a.command=='pause':
  if root.is_dir():(root/'STOP').write_text('pause requested')
  return
 if a.command=='report':return jump_bootstrap.report(root)
 if a.command=='watch':
  from duelforge.watch import watch
  return watch(folder,scene=6)
 if a.command=='export':
  from duelforge.export import export
  return export(folder)
 if a.command=='evaluate':
  from duelforge.evaluate import evaluate
  return evaluate(folder,games_per_context=200,seconds=100,contexts=['match'])

if __name__=='__main__':main()
