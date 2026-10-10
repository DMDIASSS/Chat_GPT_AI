"""GigaLearn research workspace control: source stays within this folder.

No native Nexto checkpoint conversion is claimed. Never mutates parent data.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[1]
PARENT=ROOT.parent
UPSTREAM=ROOT/'upstream'
OUT=ROOT/'checkpoints'
REPORTS=ROOT/'reports'

def digest(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for c in iter(lambda:f.read(1048576),b''):h.update(c)
 return h.hexdigest()

def inventory():
 all_paths=[]
 for folder in [PARENT/'data'/'autoleague',PARENT/'data'/'afk_improved',PARENT/'data'/'native_nexto',PARENT/'data'/'mechanics']:
  if folder.exists():all_paths.extend(folder.rglob('*.pt'))
 records=[{'relative_path':str(p.relative_to(PARENT)), 'bytes':p.stat().st_size,'sha256':digest(p)} for p in all_paths]
 REPORTS.mkdir(parents=True,exist_ok=True)
 (REPORTS/'parent_native_model_inventory.json').write_text(json.dumps({'read_only':True,'policy_compatibility':'NOT COMPATIBLE with GigaLearn C++ native policy','models':records},indent=2),encoding='utf8')
 print(f'Indexed {len(records)} parent project checkpoints READ ONLY into reports/parent_native_model_inventory.json')

def check():
 print('GigaLearn workspace:',ROOT)
 print('Parent project:',PARENT)
 print('Original Cycle9 found:',(PARENT/'data'/'autoleague'/'backups'/'20261008T224518_775472Z_cycle0009_steps000008192_candidate.pt').exists())
 print('C++ upstream present:',(UPSTREAM/'src'/'ExampleMain.cpp').is_file())
 print('Meshes configured:',bool(os.environ.get('GIGALEARN_MESHES')))
 print('git installed:',shutil.which('git') or 'NO')
 print('cmake installed:',shutil.which('cmake') or 'NO')
 print('nvcc installed:',shutil.which('nvcc') or 'NO (CUDA toolkit may still be installed but not on PATH)')
 print('GigaLearn native CPP cannot directly use Nexto .pt actors. C++ training starts its own NEW policy.')
 inventory()

def clone():
 if UPSTREAM.exists():
  print('Already have upstream checkout; skip re-clone. Update manually if desired.');return
 if not shutil.which('git'):raise RuntimeError('Install Git for Windows')
 subprocess.run(['git','clone','--recurse-submodules','https://github.com/ZealanL/GigaLearnCPP-Leak.git',str(UPSTREAM)],check=True,cwd=ROOT)
 print('Fetched archived upstream into',UPSTREAM)

def patch():
 """Make a copy of main TU; never edit external repo or original checkpoint.

Hard fails when expected upstream version differs; do not apply corrupted blind patches.
"""
 src=UPSTREAM/'src'/'ExampleMain.cpp'
 if not src.is_file():raise FileNotFoundError('Run GL_1_GET_SOURCE.bat first')
 text=src.read_text(encoding='utf-8-sig')
 signature='RocketSim::Init("C:\\\\Users\\\\admin\\\\source\\\\repos\\\\RLArenaCollisionDumper\\\\collision_meshes");'
 # Avoid assuming a particular private username in the example.
 text,n=re.subn(r'RocketSim::Init\("C:\\\\Users.*?collision_meshes"\);',
                'const char* meshes = std::getenv("GIGALEARN_MESHES");\n\tif (!meshes || !*meshes) { std::cerr << "Set GIGALEARN_MESHES first\\\\n"; return EXIT_FAILURE; }\n\tRocketSim::Init(meshes);',text,count=1)
 if n!=1:raise RuntimeError('Unexpected source: did not find original RocketSim::Init hardcoded meshes. No file changed.')
 if '#include <cstdlib>' not in text:text='#include <cstdlib>\n#include <iostream>\n#include <algorithm>\n'+text
 required=['cfg.deviceType = LearnerDeviceType::GPU_CUDA;', 'int playersPerTeam = 1;','cfg.numGames = 256;',"int tsPerItr = 50'000;"]
 if not all(x in text for x in required):raise RuntimeError('Unexpected GigaLearn example revision; no changes made. Please upload ExampleMain.cpp')
 # Configurable research only; don't promise baseline policy interoperability.
 text=text.replace('int playersPerTeam = 1;',
 '''int playersPerTeam = 1;
    if (const char* e = std::getenv("GIGALEARN_PLAYERS_PER_TEAM"))
        playersPerTeam = std::max(1, std::min(3, std::atoi(e)));''')
 text=text.replace('cfg.numGames = 256;', 'cfg.numGames = 32; // Conservative starting RAM load')
 text=text.replace("int tsPerItr = 50'000;", "int tsPerItr = 5'000;")
 text=text.replace("cfg.ppo.miniBatchSize = 50'000;", "cfg.ppo.miniBatchSize = 5'000;")
 # Reward hacking countermeasures: remove score for uncontrolled repeated bumps and touches.
 text=text.replace('{ new StrongTouchReward(20, 100), 60 },','{ new StrongTouchReward(20, 100), 1.0f },')
 text=text.replace('{ new ZeroSumReward(new BumpReward(), 0.5f), 20 },','// Removed demo/bump farming reward; test tactical bumps by goals instead')
 text=text.replace('{ new ZeroSumReward(new DemoReward(), 0.5f), 80 },','// Demo reward removed to discourage farmed explosions')
 text=text.replace('{ new PickupBoostReward(), 10.f },','{ new PickupBoostReward(), 0.1f },')
 text=text.replace('{ new SaveBoostReward(), 0.2f },','{ new SaveBoostReward(), 0.05f },')
 text=text.replace('{ new VelocityPlayerToBallReward(), 4.f },','{ new VelocityPlayerToBallReward(), 0.5f },')
 text=text.replace('{ new AirReward(), 0.25f },','{ new AirReward(), 0.02f },')
 text=text.replace('{ new FaceBallReward(), 0.25f },','{ new FaceBallReward(), 0.05f },')
 text=text.replace('{ new ZeroSumReward(new VelocityBallToGoalReward(), 1), 2.0f },','{ new ZeroSumReward(new VelocityBallToGoalReward(), 1), 2.0f },')
 tgt=UPSTREAM/'src'/'ExampleMain.cpp'
 backup=ROOT/'cache'/'ExampleMain.original.cpp'
 backup.parent.mkdir(parents=True,exist_ok=True)
 if backup.exists():raise FileExistsError('Patch already applied/backup exists. Refusing repeat: '+str(backup))
 shutil.copy2(tgt,backup)
 tmp=tgt.with_suffix('.cpp.partial');tmp.write_text(text,encoding='utf-8');os.replace(tmp,tgt)
 print('Applied conservative research patch to isolated upstream source, backup in cache.')

def main():
 parser=argparse.ArgumentParser();parser.add_argument('command',choices=['check','clone','patch'])
 args=parser.parse_args();{'check':check,'clone':clone,'patch':patch}[args.command]()
if __name__=='__main__':main()
