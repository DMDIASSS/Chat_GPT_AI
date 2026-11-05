"""Second project; shares the installed NovaForge Python runtime for setup."""
from pathlib import Path
import argparse
import sys
root=Path(__file__).resolve().parents[1]/'novaforge'
if not root.exists():root=Path(__file__).resolve().parents[1]/'NovaForge'
sys.path.insert(0,str(root))
if __name__=='__main__':
    parser=argparse.ArgumentParser(description='TriadBot three frozen experts')
    parser.add_argument('command',choices=['check','watch','export','league']);args=parser.parse_args()
    from nova import triad
    getattr(triad,args.command)()
