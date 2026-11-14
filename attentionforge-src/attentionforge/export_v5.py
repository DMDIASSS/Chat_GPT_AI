"""Add a real TorchScript .lt reader and RLBot v5 launch configuration."""
from pathlib import Path
import json,sys,hashlib
from .runtime import ROOT

def write(out,frozen):
    import shutil
    out=Path(out);frozen.save(str(out/'actor.lt'))
    digest=hashlib.sha256((out/'actor.lt').read_bytes()).hexdigest()
    agent_id='DMDIASSS/AttentionSkills_'+out.name+'_'+digest[:12]
    (out/'runtime_v5.json').write_text(json.dumps({'agent_id':agent_id,'actor_sha256':digest},indent=2))
    shutil.copy2(ROOT/'attentionforge/rlbot5_agent.py',out/'run_v5.py')
    (out/'loadout.toml').write_text('[blue_loadout]\ncar_id = 23\n[orange_loadout]\ncar_id = 23\n')
    for portable in (False,True):
        python='.venv_v5\\Scripts\\python.exe' if portable else sys.executable
        command='"'+python+'" run_v5.py'
        data='[settings]\nname = "AttentionForge Skills"\nagent_id = '+json.dumps(agent_id)+'\nrun_command = '+json.dumps(command)+'\nrun_command_linux = '+json.dumps(('".venv_v5/bin/python" run_v5.py') if portable else command)+'\nloadout_file = "loadout.toml"\nhivemind = true\n\n[details]\ndeveloper = "DM Dias"\ndescription = "Learned attention policy. Octane. Training is currently 1v1."\nlanguage = "python"\ntags = ["1v1"]\n'
        (out/('bot.portable.bot.toml' if portable else 'bot.bot.toml')).write_text(data)
    code='''from pathlib import Path
import sys,subprocess,venv,site
root=Path(__file__).resolve().parent
venv.EnvBuilder(with_pip=True).create(root/'.venv_v5')
exe=root/'.venv_v5'/('Scripts/python.exe' if sys.platform=='win32' else 'bin/python')
paths=[p for p in sys.path if 'site-packages' in p and Path(p).is_dir()]
location=subprocess.check_output([str(exe),'-c','import site; print(site.getsitepackages()[0])'],text=True).strip()
# Reuse the selected Torch/NumPy stack via .pth; SDK install stays isolated.
Path(location,'attention_runtime.pth').write_text('\\n'.join(paths)+'\\n')
probe=subprocess.run([str(exe),'-c','import torch,numpy'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
if probe.returncode:
    subprocess.run([str(exe),'-m','pip','install','torch==2.9.1','--index-url','https://download.pytorch.org/whl/cpu'],check=True)
subprocess.run([str(exe),'-m','pip','install','rlbot==2.0.0b56'],check=True)
print('READY: import bot.portable.bot.toml. Original training environment unchanged.')
'''
    (out/'install_v5.py').write_text(code)
    (out/'INSTALL_V5.bat').write_text('@echo off\ncd /d "%~dp0"\nif exist "'+sys.executable+'" (\n"'+sys.executable+'" install_v5.py\n) else (\npy -3.11 install_v5.py\n)\nif errorlevel 1 echo INSTALL_FAILED\npause\n')
    (out/'DIAGNOSE_V5.bat').write_text('@echo off\ncd /d "%~dp0"\nif exist .venv_v5\\Scripts\\python.exe (\n".venv_v5\\Scripts\\python.exe" run_v5.py --diagnose\n) else (\n"'+sys.executable+'" run_v5.py --diagnose\n)\npause\n')
    (out/'README_EXPORT.md').write_text('RLBot v5: bot.bot.toml uses the exporting Python. It needs rlbot==2.0.0b56. If missing or a different SDK is installed, run INSTALL_V5.bat then import bot.portable.bot.toml; the isolated SDK environment reuses the existing Torch stack.\n\nactor.lt is TorchScript read by run_v5.py, not a GigaLearn binary format. actor.pt + bot.cfg is the separate RLBot v4 wrapper. Install v4 in a separate environment; the v4 and v5 SDKs share a package name. Models use Octane, 120Hz physics, eight-tick decisions and one-tick action delay. Do not train while running RLBot.\n\nSource/export logits and packet adapter/clock are checked automatically. A live Rocket League connection still requires local verification. startup.log records v5 initialization. No scripted kickoff or hidden controller replaces the model.\n')
