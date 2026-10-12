"""Immutable native Nexto checkpoint -> separate RLBot v4 bot. Offline only.

The exporter never changes input .pt files or an existing export folder.
Use --list to enumerate known native actor checkpoints. Non-commercial Nexto terms apply.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile

ROOT=Path(__file__).resolve().parent
SOURCE=ROOT/'vendor'/'nexto'/'nexto-model.pt'
DEFAULT=ROOT/'data'/'autoleague'/'backups'/'20261008T224518_775472Z_cycle0009_steps000008192_candidate.pt'
TEMPLATE=ROOT/'rlbot_v4_template'
OUTPUT=ROOT/'data'/'rlbot_exports'
REQUIRED=('bot.py','agent.py','nexto_obs.py','appearance.cfg','nexto_logo.png','NEXT0_UPSTREAM_LICENSE.txt')

def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()

def discover():
 locations=[ROOT/'data'/'autoleague',ROOT/'data'/'afk_improved',ROOT/'data'/'native_nexto',ROOT/'data'/'mechanics']
 paths=[]
 for base in locations:
  if base.exists():paths.extend(base.rglob('*.pt'))
 paths=[p for p in paths if 'rlbot_exports' not in p.parts and p.resolve()!=SOURCE.resolve()]
 return sorted(set(paths),key=lambda p:str(p).lower())

def validate_name(name):
 if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,59}',name):raise ValueError('Name must be 1..60 ASCII letters, digits, _ or -')
 return name

def model_from_checkpoint(path):
 import torch
 if not SOURCE.is_file():raise FileNotFoundError(f'Bundled Nexto base model missing: {SOURCE}')
 model=torch.jit.load(str(SOURCE),map_location='cpu')
 if path is not None:
  data=torch.load(str(path),map_location='cpu',weights_only=True)
  if not isinstance(data,dict) or 'actor' not in data: raise ValueError('Not a native Nexto actor checkpoint')
  model.load_state_dict(data['actor'],strict=True)
 model.eval()
 return model

def kickoff_settings(source, scripted):
 # Require the known Nexto wrapper and both configurable constructor defaults.
 if scripted and 'self.maybe_do_kickoff(packet, ticks_elapsed)' not in source:
  raise ValueError('RLBot template lacks the scripted kickoff controller')
 for key,value in [('hardcoded_kickoffs',scripted),('stochastic_kickoffs',False)]:
  source,count=re.subn(r'\b'+key+r'\s*=\s*(True|False)\b',key+'='+str(value),source)
  if count!=1:raise ValueError(f'Expected one {key} constructor setting; found {count}')
 return source

def export(checkpoint,name,output=None,*,scripted_kickoff=False):
 import torch
 if checkpoint is not None and (Path(checkpoint).is_dir() or Path(checkpoint).suffix.lower()==".lt"):
  from export_native_rlbot_v4 import export_native
  return export_native(checkpoint,name,output,scripted_kickoff=scripted_kickoff)
 name=validate_name(name);output=Path(OUTPUT if output is None else output).resolve()
 origin=None if checkpoint is None else Path(checkpoint).resolve()
 if origin is not None and not origin.is_file():raise FileNotFoundError(origin)
 if origin is not None and origin==SOURCE.resolve():raise ValueError('Use --original for the original model')
 for item in REQUIRED:
  if not (TEMPLATE/item).is_file():raise FileNotFoundError(f'Need RLBot template from previous Camera/RLBot addon: {TEMPLATE/item}')
 model=model_from_checkpoint(origin)
 original_checksum=sha(origin) if origin else sha(SOURCE)
 output.mkdir(parents=True,exist_ok=True)
 target=output/name
 if target.exists():raise FileExistsError(f'Export already exists: {target}. Use a new export name.')
 # Work in temp folder inside same disk; rename only once fully verified.
 tmp=Path(tempfile.mkdtemp(prefix='.export_partial_',dir=output))
 try:
  for f in REQUIRED:shutil.copy2(TEMPLATE/f,tmp/f)
  torch.jit.save(model,str(tmp/'nexto-model.pt'))
  loaded=torch.jit.load(str(tmp/'nexto-model.pt'),map_location='cpu')
  expected=model.state_dict();actual=loaded.state_dict()
  for key in expected:
   if not torch.equal(expected[key],actual[key]):raise RuntimeError(f'Weight mismatch after export: {key}')
  b=kickoff_settings((tmp/'bot.py').read_text(encoding='utf8'),scripted_kickoff)
  (tmp/'bot.py').write_text(b,encoding='utf8')
  (tmp/'requirements.txt').write_text('rlbot==1.*\nrlgym-compat==1.0.2\nnumpy\ntorch\n',encoding='utf8')
  (tmp/'bot.cfg').write_text(f'''[Locations]
looks_config = ./appearance.cfg
python_file = ./bot.py
requirements_file = ./requirements.txt
logo_file = ./nexto_logo.png
name = {name}
maximum_tick_rate_preference = 120

[Details]
developer = Chat GPT AI project and Necto/Nexto contributors
description = Experimental native Nexto policy, local/offline; not commercial
language = python
tags = 1v1
''',encoding='utf8')
  (tmp/'EXPORT_INFO.json').write_text(json.dumps({'format':'RLBot v4 legacy','name':name,'source':str(origin) if origin else 'original Nexto',
       'source_sha256':original_checksum,'torchscript_sha256':sha(tmp/'nexto-model.pt'),
       'hardcoded_kickoffs':scripted_kickoff,'stochastic_kickoffs':False,'online_play_supported':False},indent=2),encoding='utf8')
  (tmp/'README_IMPORT.txt').write_text('RLBot v4 only (not RLBot v5). Use bot.cfg with compatible RLBot 4 Python environment.\n'
       'Avoid online matchmaking. Nexto derived weights/code non-commercial CC BY-NC-SA 4.0.\n'
       'RLBot v5 requires an independent port; do not rename bot.cfg to bot.toml.\n',encoding='utf8')
  if origin and sha(origin)!=original_checksum:raise RuntimeError('Source checkpoint changed during export')
  tmp.rename(target)
  print('SUCCESS: exported bot at',target,flush=True)
  print('RLBot v4 configuration:',target/'bot.cfg',flush=True)
  return target
 except BaseException:
  shutil.rmtree(tmp,ignore_errors=True)
  raise

def main():
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--checkpoint',type=Path,default=None)
 parser.add_argument('--scripted-kickoff',action='store_true',help='Enable Nexto scripted kickoff controller')
 parser.add_argument('--original',action='store_true')
 parser.add_argument('--list',action='store_true')
 parser.add_argument('--name',default='AFK_Cycle9')
 args=parser.parse_args()
 if args.list:
  for p in discover():print(p.relative_to(ROOT))
  return
 if args.original and args.checkpoint:parser.error('Choose checkpoint or --original, not both')
 export(None if args.original else (args.checkpoint or DEFAULT),args.name,scripted_kickoff=args.scripted_kickoff)
if __name__=='__main__':main()
