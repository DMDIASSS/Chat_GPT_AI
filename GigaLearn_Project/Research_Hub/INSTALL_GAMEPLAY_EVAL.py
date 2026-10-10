"""Guarded UI integration; preserve user's current Research Hub + other hotfixes."""
from pathlib import Path
from datetime import datetime,timezone
import shutil

HERE=Path(__file__).resolve().parent
APP=HERE/'hub_app.py'

def install():
    if not APP.is_file():raise RuntimeError('Existing hub_app.py missing; install Research Hub first')
    src=APP.read_text(encoding='utf-8-sig')
    if 'install_evaluation_tab(self)' in src:
        return 'Already installed; no files modified.'
    marker='self.create_overview();self.create_experiments();self.create_evolution();self.create_replays();self.create_bridge();self.create_logs()'
    if src.count(marker)!=1:raise RuntimeError('UI structure changed; upload current hub_app.py for a compatible patch')
    backup=APP.with_name('hub_app.before_gameplay_eval_'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.bak')
    shutil.copy2(APP,backup)
    src=src.replace(marker,marker+'\n    from hub_eval_ui import install_evaluation_tab\n    install_evaluation_tab(self)',1)
    APP.write_text(src,encoding='utf8')
    return 'Gameplay Eval tab installed. Backup: '+str(backup)
if __name__=='__main__':print(install())
