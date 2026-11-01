"""Install RLBot v5 separately; reuse the source project's Torch read-only."""
from pathlib import Path
import importlib.util
import os
import subprocess
import sys
import sysconfig


def main():
    root=Path(__file__).resolve().parent
    if importlib.util.find_spec('torch') is None:
        raise RuntimeError('Run INSTALL.bat using the original project Python, which already has Torch')
    shared_site=Path(sysconfig.get_path('purelib')).resolve()
    environment=root/'.venv'
    if not environment.exists():subprocess.run([sys.executable,'-m','venv',str(environment)],check=True)
    python=environment/('Scripts/python.exe'if os.name=='nt'else'bin/python')
    site=Path(subprocess.check_output([str(python),'-c',"import sysconfig;print(sysconfig.get_path('purelib'))"],text=True).strip())
    # Append the project's installed packages AFTER this venv's packages, so
    # RLBot v5 overrides any v4 SDK while Torch stays in its original location.
    (site/'freestyle_project_torch.pth').write_text(str(shared_site)+'\n',encoding='utf-8')
    subprocess.run([str(python),'-m','pip','install','--disable-pip-version-check',
                    'rlbot==2.0.0b56','numpy>=1.26,<3'],check=True)
    subprocess.run([str(python),'-c',
        "import importlib.metadata as m, torch;from rlbot.managers import Bot;from rlbot.flat import GamePacket;"
        "assert m.version('rlbot')=='2.0.0b56';print('RLBot v5 ready; existing Torch:',torch.__version__)"],check=True)
    subprocess.run([str(python),str(root/'diagnose.py')],check=True)
    print('Install complete. Import '+str(root/'bot.toml')+' in RLBot v5.',flush=True)


if __name__=='__main__':main()
