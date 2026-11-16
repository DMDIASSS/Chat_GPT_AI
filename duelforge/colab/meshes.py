"""Locate Soccar collision meshes already available in this Linux environment."""
from pathlib import Path
import argparse, json, os, site, sys
ROOT=Path(__file__).resolve().parents[1]

def find():
    paths=[]
    for key in ('DUELFORGE_MESHES','ATTENTIONFORGE_MESHES','REPLICAR_MESHES'):
        if os.environ.get(key): paths.append(Path(os.environ[key]).expanduser())
    locations=ROOT/'local_paths.json'
    if locations.exists():
        try:
            v=json.loads(locations.read_text()).get('meshes')
            if v: paths.append(Path(v))
        except (OSError, ValueError): pass
    for p in (ROOT,ROOT.parent,Path('/content'),Path('/content/drive/MyDrive'),Path.home()):
        for part in ('collision_meshes','assets/collision_meshes','third_party/collision_meshes'):
            paths.append(p/part)
    for base in [*site.getsitepackages(),site.getusersitepackages(),*sys.path]:
        if not base:continue
        b=Path(base)
        paths.extend([b/'rlgym/rocket_league/sim/collision_meshes',b/'rlgym_rocket_league/sim/collision_meshes'])
    for p in dict.fromkeys(paths):
        if p.is_dir() and list(p.glob('soccar/*.cmf')):
            return p.resolve()
    return None

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--save',action='store_true')
    args=parser.parse_args()
    p=find()
    if not p:
        print('SOCCAR_MESHES_NOT_FOUND: needs rlgym-rocket-league or DUELFORGE_MESHES',file=sys.stderr)
        raise SystemExit(2)
    if args.save:
        (ROOT/'local_paths.json').write_text(json.dumps({'meshes':str(p)},indent=2)+'\n')
    print('SOCCAR_MESHES:',p)
if __name__=='__main__':main()
