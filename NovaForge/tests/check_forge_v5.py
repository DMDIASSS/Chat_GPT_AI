"""Actual exported processes for both native families; loopback v5, no game UI."""
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import torch
from nova.core import ROOT
from nova.forge_models import DirectActor,save_actor,FAMILIES
from nova.giga_teachers import GigaNetwork
from nova.teachers import verify_teacher

torch.set_num_threads(1)
with tempfile.TemporaryDirectory() as temp:
    for family in FAMILIES:
        actor=DirectActor(family);actor.core.load_state_dict(GigaNetwork(verify_teacher(family),family).state_dict())
        path=save_actor(actor,Path(temp)/(family+'.lt'),family)
        subprocess.run([sys.executable,str(ROOT/'tests/check_triad_v5.py'),'--forge-actor',str(path)],cwd=ROOT,check=True)
print('BOTH_FORGE_FAMILIES_V5_PROCESS_PASS')
