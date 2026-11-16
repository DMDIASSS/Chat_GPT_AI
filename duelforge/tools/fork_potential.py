"""Create a named ablation from a paused trained parent; never train implicitly."""
import argparse,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from duelforge.potential_experiment import fork_potential
p=argparse.ArgumentParser();p.add_argument('--source',default='duel02');p.add_argument('--run',required=True);p.add_argument('--intercept-weight',type=float,default=.8);p.add_argument('--threat-weight',type=float,default=.2);p.add_argument('--shaping-weight',type=float,default=.5);p.add_argument('--temperature',type=float,default=.6);a=p.parse_args()
for name in (a.source,a.run):
    if Path(name).name!=name or name in ('.','..'):p.error('Use simple run names')
fork_potential(ROOT/'runs'/a.source,ROOT/'runs'/a.run,{'intercept_weight':a.intercept_weight,'threat_weight':a.threat_weight,'shaping_weight':a.shaping_weight,'temperature':a.temperature})
print('FORK_READY:',a.run,'; no training started. Use your selected runtime to run: run.py train --run',a.run,'--minutes 60')
