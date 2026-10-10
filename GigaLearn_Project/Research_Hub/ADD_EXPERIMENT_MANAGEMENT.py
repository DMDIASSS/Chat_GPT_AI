"""Non-destructive, version-checked GUI installer for Rename/Delete/Restore controls.

Rewrites only recognized segments of existing Research Hub v1 hub_app.py. Backs up
before replacing. It does not touch hub_core.py, C++ source, or experiments.
"""
from __future__ import annotations
import ast
from datetime import datetime, timezone
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parent
TARGET=ROOT/'hub_app.py'
MOD=ROOT/'hub_experiment_management.py'
MARKER='from hub_experiment_management import ('

HEADER_OLD='from tkinter import ttk, filedialog, messagebox'
HEADER_NEW='from tkinter import ttk, filedialog, messagebox, simpledialog'
MODULE_ANCHOR='from hub_tournament import save_schedule,standings_from_csv\n'
MODULE_LINE='from hub_experiment_management import (rename_experiment, archive_experiment, list_trashed_experiments, restore_trashed_experiment, trash_folder)\n'
BUTTON_ANCHOR="    self.button(r,'View selected C++ log',self.show_exp_log)\n"
BUTTONS="    self.button(r,'Rename selected',self.rename_exp)\n    self.button(r,'Delete selected',self.delete_exp)\n    self.button(r,'Restore from Trash',self.restore_exp)\n"
HELP_OLD="    ttk.Label(p,text='Do NOT delete a running experiment folder. Safe stop creates request_safe_stop.flag; patched C++ saves after PPO iteration.').pack(anchor='w',padx=18,pady=5)"
HELP_NEW="    ttk.Label(p,text='Delete moves experiments to recoverable Trash. Rename/Delete are disabled for live or pending-safe-stop runs.').pack(anchor='w',padx=18,pady=5)"
METHOD_ANCHOR=' def create_evolution(self):\n'
METHODS=''' def rename_exp(self):
    try:name=self.selected()
    except Exception as e:messagebox.showwarning('Select experiment',str(e));return
    value=simpledialog.askstring('Rename experiment','New experiment name:',initialvalue=name,parent=self.root)
    if value is None:return
    if not value.strip():messagebox.showwarning('Invalid name','Enter a nonempty experiment name.');return
    from hub_core import slug
    try:actual=slug(value.strip())
    except Exception as e:messagebox.showerror('Invalid name',str(e));return
    if not messagebox.askyesno('Confirm rename',f'Rename {name} to {actual}?\\n\\nAll checkpoints remain intact. Existing external references to the old path may need updating.'):
       return
    self.execute(lambda: 'Renamed '+name+' to '+rename_experiment(name,value))

 def delete_exp(self):
    try:name=self.selected()
    except Exception as e:messagebox.showwarning('Select experiment',str(e));return
    if not messagebox.askyesno('Move experiment to Trash',f'Move {name} and ALL its checkpoints into the recoverable Research Hub Trash?\\n\\nYou can restore it later. Running experiments cannot be moved.',icon='warning'):
       return
    confirm=simpledialog.askstring('Confirm archive',f'Type {name} to confirm moving it into Trash:',parent=self.root)
    if confirm!=name:
       if confirm is not None:messagebox.showinfo('Cancelled','Experiment name did not match; nothing changed.')
       return
    self.execute(lambda: 'Moved '+name+' to Trash: '+str(archive_experiment(name)))

 def restore_exp(self):
    items=list_trashed_experiments()
    if not items:
       messagebox.showinfo('Research Hub Trash','Trash is empty.');return
    prompt='Choose an archive to restore by entering its NUMBER:\\n\\n'+'\\n'.join(f'{i+1}. {a["name"]} — {a["archived_utc"]}' for i,a in enumerate(items[:20]))
    num=simpledialog.askinteger('Restore experiment',prompt,parent=self.root,minvalue=1,maxvalue=min(20,len(items)))
    if num is None:return
    item=items[num-1]
    if not messagebox.askyesno('Confirm restore',f'Restore {item["name"]} from Trash?\\nExisting experiments will never be overwritten.'):
       return
    self.execute(lambda: 'Restored '+restore_trashed_experiment(item['archive_id']))

'''


def patch_source(raw:bytes)->tuple[bytes,bool]:
    text=raw.decode('utf-8-sig')
    if MARKER in text:
        if text.count(MARKER)!=1 or ' def rename_exp(self):' not in text or ' def delete_exp(self):' not in text:
            raise RuntimeError('Partially installed GUI patch: inspect hub_app.py; nothing overwritten.')
        return raw,False
    # Preserve CRLF or LF line endings.
    endings='\r\n' if b'\r\n' in raw else '\n'
    text=text.replace('\r\n','\n')
    edits=[(HEADER_OLD,HEADER_NEW),(MODULE_ANCHOR,MODULE_ANCHOR+MODULE_LINE),(BUTTON_ANCHOR,BUTTON_ANCHOR+BUTTONS),(HELP_OLD,HELP_NEW),(METHOD_ANCHOR,METHODS+METHOD_ANCHOR)]
    for old,new in edits:
        if text.count(old)!=1:
            raise RuntimeError('Unsupported hub_app.py version; expected exactly one: '+old[:80])
        text=text.replace(old,new,1)
    ast.parse(text)
    if endings=='\r\n':text=text.replace('\n','\r\n')
    return text.encode('utf-8-sig' if raw.startswith(b'\xef\xbb\xbf') else 'utf-8'),True


def main():
    if not TARGET.is_file() or not MOD.is_file():
        print('ERROR: Add-on must be extracted into GigaLearn_Project\\Research_Hub.')
        return 1
    try:
        raw=TARGET.read_bytes()
        patched,changed=patch_source(raw)
    except (SyntaxError,UnicodeError,RuntimeError,OSError) as e:
        print('ERROR:',e)
        print('No files were changed. Please upload hub_app.py for an exact integration.')
        return 1
    if not changed:
        print('Rename/Delete/Restore already installed. Nothing to change.')
        return 0
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ_%f')
    backup=ROOT / ('hub_app.py.before_experiment_management_'+stamp+'.bak')
    temp=ROOT / ('hub_app.py.management_'+stamp+'.partial')
    try:
        with backup.open('xb') as f:
            f.write(raw);f.flush();os.fsync(f.fileno())
        with temp.open('xb') as f:
            f.write(patched);f.flush();os.fsync(f.fileno())
        os.replace(temp,TARGET)
    except Exception as e:
        temp.unlink(missing_ok=True)
        print('ERROR applying GUI update:',e)
        return 1
    print('SUCCESS: Installed Rename selected, Delete selected, Restore from Trash.')
    print('Original app backup:',backup)
    print('No C++ rebuild. No experiments, checkpoints, or model weights changed.')
    print('Close and reopen Research Hub to see the buttons.')
    return 0


if __name__=='__main__':sys.exit(main())
