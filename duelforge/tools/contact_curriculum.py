"""Windows entry point using the already selected DuelForge runtime."""
import argparse,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

def main():
    p=argparse.ArgumentParser()
    p.add_argument('command',choices=['start','pause','watch','evaluate','export','report','profile'])
    p.add_argument('--steps',type=int,default=5_000_000)
    p.add_argument('--games',type=int,default=200)
    p.add_argument('--seconds',type=float,default=100)
    a=p.parse_args()
    from duelforge import acquisition_experiment as experiment
    if a.command=='pause':return experiment.pause()
    if a.command=='report':return experiment.report()
    if a.command=='profile':
        from duelforge.acquisition_profile import profile
        return profile()
    if a.command=='start':
        import torch
        if not torch.cuda.is_available():raise RuntimeError('CUDA required for this launcher; run 32_INSTALL_CUDA_RUNTIME.bat first. No CPU fallback or model reset.')
        return experiment.start(steps=a.steps)
    folder=experiment.active()
    if a.command=='watch':
        from duelforge.watch import watch
        return watch(folder,seconds=a.seconds,scene=-2)
    if a.command=='evaluate':
        from duelforge.evaluate import evaluate
        return evaluate(folder,games_per_context=a.games,seconds=a.seconds,contexts=['match'])
    if a.command=='export':
        from duelforge.export import export
        return export(folder)

if __name__=='__main__':main()
