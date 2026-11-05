"""Export launcher diagnostics and source/portable v5 configurations."""
from __future__ import annotations
import argparse
import json
import logging
from pathlib import Path
import sys


def write_launchers(stage,python,agent_id,body='breakout',learned=False,fusion=False):
    stage=Path(stage)
    variants=[('',body)] if learned else [('',body),('.octane','octane')]
    for suffix,hitbox in variants:
        car=22 if hitbox=='breakout' else 23
        loadout='loadout'+suffix+'.toml'
        (stage/loadout).write_text('[blue_loadout]\ncar_id = '+str(car)+'\n[orange_loadout]\ncar_id = '+str(car)+'\n')
        for portable in (False,True):
            name='bot'+suffix+('.portable' if portable else '')+'.bot.toml'
            # Local exports work immediately; portable variants use their own venv.
            win='"'+('.venv\\Scripts\\python.exe' if portable else str(python))+'" run_triad.py --body '+hitbox
            linux='"'+('.venv/bin/python' if portable else str(python))+'" run_triad.py --body '+hitbox
            text='[settings]\nname = '+json.dumps('TriadBot '+('four-expert Fusion selector' if fusion else ('learned selector' if learned else 'random experts'))+' '+hitbox+(' portable' if portable else ''))+'\n'
            text+='agent_id = '+json.dumps(agent_id+suffix+('.portable' if portable else ''))+'\n'
            text+='run_command = '+json.dumps(win)+'\nrun_command_linux = '+json.dumps(linux)+'\n'
            text+='loadout_file = '+json.dumps(loadout)+'\nhivemind = true\n\n[details]\n'
            text+='developer = "NovaForge user; original models credited under assets"\n'
            text+='description = '+json.dumps('Chronos + GalactusV2 + Ripple v1.1'+(' + frozen local Fusion.' if fusion else '.')+' Fixed body; '+('four' if fusion else 'three')+' frozen experts.')+'\nlanguage = "python"\ntags = ["1v1"]\n'
            (stage/name).write_text(text)


def main(agent_id,body='breakout'):
    parser=argparse.ArgumentParser();parser.add_argument('--diagnose',action='store_true');parser.add_argument('--body',choices=['breakout','octane'],default=body)
    args=parser.parse_args()
    ROOT=Path(__file__).resolve().parents[1]
    path=ROOT/'startup.log'
    logging.basicConfig(level=logging.INFO,handlers=[logging.FileHandler(path,encoding='utf8'),logging.StreamHandler()],force=True)
    log=logging.getLogger('triad-startup')
    log.info('TRIAD_START Python=%s Body=%s',sys.executable,args.body)
    try:
        from .triad import TriadClock,run_live
        selector=ROOT/'selector.pt' if (ROOT/'selector.pt').exists() else None
        if args.diagnose:
            clock=TriadClock(selector_path=selector,body=args.body)
            log.info('TRIAD_DIAGNOSE_PASS: experts=%s; selector=%s',clock.names,bool(clock.gate));return
        run_live(agent_id,selector,args.body)
    except BaseException:
        log.exception('TRIAD_START_FAILED');raise
