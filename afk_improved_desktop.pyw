"""No-console GUI launcher. Fatal startup exceptions go to data/afk_improved/gui_errors.log."""
from __future__ import annotations
import sys
from datetime import datetime
from pathlib import Path
from tkinter import Tk, messagebox

ROOT=Path(__file__).resolve().parent

def report_failure(exc_type, exc, trace):
    import traceback
    log=ROOT/'data'/'afk_improved'/'gui_errors.log'
    try:
        log.parent.mkdir(parents=True,exist_ok=True)
        with log.open('a',encoding='utf-8') as fh:
            fh.write('\n'+datetime.now().isoformat()+'\n')
            traceback.print_exception(exc_type,exc,trace,file=fh)
    except OSError:pass
    try:
        window=Tk();window.withdraw()
        messagebox.showerror('AFK Improved failed to start',f'{exc}\n\nDetails: {log}',parent=window)
        window.destroy()
    except Exception:pass
sys.excepthook=report_failure

from afk_improved_app import ControlCenter
ControlCenter().mainloop()
