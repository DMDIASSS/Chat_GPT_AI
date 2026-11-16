import json,shutil,sys,time
from pathlib import Path
import numpy as np
import torch
from .runtime import ROOT,model,atomic_json,sha


def export(folder,checkpoint=None):
    folder=Path(folder);actor,ck,path=model(folder,checkpoint=checkpoint);torch.set_num_threads(1)
    out=ROOT/'exports'/f'{folder.name}_{ck["learning_transitions"]:016d}_{ck["_source_sha256"][:10]}'
    if out.exists():raise FileExistsError(f'Existing export preserved: {out}')
    out.mkdir(parents=True);frozen=torch.jit.script(actor.eval());frozen.save(str(out/'actor.pt'));frozen.save(str(out/'actor.lt'))
    rng=np.random.default_rng(55219);x=torch.from_numpy(rng.normal(size=(31,109)).astype(np.float32));legal=torch.from_numpy(rng.random((31,90))>.3);legal[:,8]=True
    with torch.inference_mode():
        a,v=actor(x,legal);b,w=torch.jit.load(str(out/'actor.lt'))(x,legal);c,z=torch.jit.load(str(out/'actor.pt'))(x,legal)
    torch.testing.assert_close(a,b);torch.testing.assert_close(a,c);torch.testing.assert_close(v,w);assert torch.equal(a.argmax(-1),b.argmax(-1))
    for src,dst in [('observation.py','observation.py'),('rlbot5_agent.py','run_v5.py')]:shutil.copy2(ROOT/'duelforge'/src,out/dst)
    atomic_json(out/'model_config.json',ck['config']);identity={'agent_id':'DMDIASSS/DuelForge_'+folder.name+'_'+sha(out/'actor.lt')[:12],'actor_lt_sha256':sha(out/'actor.lt'),'actor_pt_sha256':sha(out/'actor.pt'),'source_checkpoint_sha256':ck['_source_sha256'],'learning_transitions':ck['learning_transitions'],'source_export_logits_max_abs_difference':float((a-b).abs().max()),'action_agreement':1.,'hitbox':'Octane','format':'TorchScript actor.pt and actor.lt, read by the included RLBot v5 Python wrapper; NOT GGL native parameter archives','live_rlbot_match_verified':False}
    atomic_json(out/'identity.json',identity)
    (out/'loadout.toml').write_text('[blue_loadout]\ncar_id = 23\n[orange_loadout]\ncar_id = 23\n')
    for portable in (False,True):
        py='.venv_v5\\Scripts\\python.exe' if portable else sys.executable
        text='[settings]\nname = "DuelForge '+folder.name+'"\nagent_id = '+json.dumps(identity['agent_id'])+'\nrun_command = '+json.dumps('"'+py+'" run_v5.py')+'\nrun_command_linux = '+json.dumps('".venv_v5/bin/python" run_v5.py' if portable else '"'+py+'" run_v5.py')+'\nloadout_file = "loadout.toml"\nhivemind = true\n\n[details]\ndeveloper = "DM Dias"\ndescription = "Fresh learned 1v1 dense policy. Octane. Neural controls only."\nlanguage = "python"\ntags = ["1v1"]\n'
        (out/('bot.portable.bot.toml' if portable else 'bot.bot.toml')).write_text(text)
    script='''from pathlib import Path
import sys,subprocess,venv,struct
root=Path(__file__).resolve().parent
if sys.version_info[:2]!=(3,11) or struct.calcsize('P')!=8:raise RuntimeError('Use 64-bit Python 3.11 for this export')
venv.EnvBuilder(with_pip=True).create(root/'.venv_v5')
exe=root/'.venv_v5'/('Scripts/python.exe' if sys.platform=='win32' else 'bin/python')
paths=[p for p in sys.path if 'site-packages' in p and Path(p).is_dir()]
site=subprocess.check_output([str(exe),'-c','import site;print(site.getsitepackages()[0])'],text=True).strip()
Path(site,'duelforge_runtime.pth').write_text('\\n'.join(paths)+'\\n')
probe=subprocess.run([str(exe),'-c','import torch,numpy'],capture_output=True,text=True)
if probe.returncode:
    print('No usable Torch/NumPy in the selected runtime. Installing CPU inference dependencies into .venv_v5 only.',flush=True)
    subprocess.run([str(exe),'-m','pip','install','torch==2.9.1','--index-url','https://download.pytorch.org/whl/cpu'],check=True)
    subprocess.run([str(exe),'-m','pip','install','numpy>=1.26,<3'],check=True)
subprocess.run([str(exe),'-m','pip','install','rlbot==2.0.0b56'],check=True)
print('READY: import bot.portable.bot.toml into RLBot v5. Existing training runtime unchanged.')
'''
    (out/'install_v5.py').write_text(script)
    (out/'INSTALL_V5.bat').write_text('@echo off\ncd /d "%~dp0"\nif exist "'+sys.executable+'" (\n"'+sys.executable+'" install_v5.py\n) else (\npy -3.11 install_v5.py\n)\nif errorlevel 1 echo INSTALL_FAILED - keep the output above\npause\n')
    (out/'DIAGNOSE_V5.bat').write_text('@echo off\ncd /d "%~dp0"\nif exist .venv_v5\\Scripts\\python.exe (\n".venv_v5\\Scripts\\python.exe" run_v5.py --diagnose\n) else (\necho Run INSTALL_V5.bat first, then retry this diagnostic.\n)\npause\n')
    (out/'README.md').write_text('Run INSTALL_V5.bat once, then import bot.portable.bot.toml into RLBot v5. This installs the v5 SDK in an isolated wrapper environment and reuses an existing Python 3.11 Torch/NumPy stack. On a different PC without Torch, it downloads CPU inference dependencies into .venv_v5 only. Requires 64-bit Python 3.11. No trainer runs alongside the bot. DIAGNOSE_V5.bat checks actor/SDK loading. startup.log records connection errors.\n\nOctane 1v1; 109 features; DF90-v1 mask; eight-tick decisions and seven-tick action delay at 120Hz. actor.lt and actor.pt are TorchScript for this wrapper, not native GGL weight files. RLBot v4 CFG is not included in this prototype. Source/export logits/actions are checked; an actual Rocket League client match still needs local testing.\n')
    print('EXPORT_READY:',out,'; source/PT/LT logits and actions match. Run INSTALL_V5.bat, import bot.portable.bot.toml.',flush=True);return out
