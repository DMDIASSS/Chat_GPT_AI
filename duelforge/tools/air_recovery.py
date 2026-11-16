import argparse,sys,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

def main():
    p=argparse.ArgumentParser();p.add_argument('command',choices=['start','pause','watch','report','evaluate','export']);p.add_argument('--steps',type=int,default=500000);a=p.parse_args()
    from duelforge import air_experiment
    root=ROOT/'runs/air01';folder=root/'03_trajectory'
    if a.command=='pause':
        if not root.is_dir():raise FileNotFoundError('Air experiment not created')
        (root/'STOP').write_text('pause requested')
        if folder.is_dir():(folder/'STOP').write_text('pause requested')
        return
    if a.command=='start':
        import torch
        if not torch.cuda.is_available():raise RuntimeError('CUDA runtime required; no CPU fallback')
        os.environ['DUELFORGE_WANDB_EXTERNAL']='1';return air_experiment.start(steps=a.steps)
    if a.command=='report':return air_experiment.report(root)
    if a.command=='watch':
        from duelforge.watch import watch
        return watch(folder,scene=6)
    if a.command=='evaluate':
        from duelforge.evaluate import evaluate
        return evaluate(folder,games_per_context=200,seconds=100,contexts=['match'])
    if a.command=='export':
        from duelforge.export import export
        return export(folder)

if __name__=='__main__':main()
