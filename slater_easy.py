"""Small Windows launcher for the existing native-attention champion campaign.

Does not implement PPO, change rewards, edit checkpoints, or bypass campaign gates.
Importing this module never imports torch or launches any training.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import webbrowser

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / 'data/isolated/mechanics_curriculum/selected7_mechanics01/update_000180.pt'
NEXTO = ROOT / 'vendor/nexto/nexto-model.pt'
CAMPAIGNS = ROOT / 'data/isolated/champion_campaigns'
EASY = ROOT / 'data/isolated/easy_console'
VENV = ROOT / '.venv/Scripts/python.exe'


def valid_name(value):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,40}', value):
        raise ValueError('Run name must contain 1-40 ASCII letters, digits, _ or -')
    return value


def json_file(path, fallback=None):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (ValueError, OSError):
        return fallback


def working_paths(run):
    run = valid_name(run)
    return CAMPAIGNS / run, EASY / run


def check_install(source):
    required = {'Python environment': VENV, 'Update180 source': Path(source),
                'Original Nexto rival': NEXTO,
                'Native attention trainer': ROOT / 'slater_native_attention.py',
                'Champion campaign': ROOT / 'slater_champion_campaign.py',
                'Compiled native attention exe': ROOT / 'data/isolated/native_attention/build/SlaterAttentionNative.exe',
                'Transfer audit': ROOT / 'slater_transfer_diagnose.py'}
    return {k: {'exists': p.is_file(), 'path': str(p)} for k, p in required.items()}


def prepare_config(run: str, mode='1v1'):
    """Use the repository's real configuration schema, not a hand-made substitute."""
    from slater_champion_campaign import default_config, validate_config
    campaign, easy_dir = working_paths(run)
    if campaign.exists():
        raise FileExistsError('Campaign already exists; use Resume rather than Start: ' + str(campaign))
    if easy_dir.exists():
        raise FileExistsError('Easy-run folder exists; choose a fresh run ID: ' + str(easy_dir))
    cfg = default_config()
    cfg.update(cycles=8, branch_updates=100, chunk_updates=20,
               max_minutes=240., min_disk_gb=5., confirm_seeds=16,
               confirm_seconds=120., routines=['match','defense','recovery','air-control','boost','wall-reset'])
    if mode == '1v1':
        cfg['formats'] = ['1v1']
        cfg['mode_weights'] = {'1v1': 1.}
    elif mode != 'balanced':
        raise ValueError('mode must be 1v1 or balanced')
    cfg = validate_config(cfg)
    easy_dir.mkdir(parents=True)
    target = easy_dir / 'campaign_config.json'
    with target.open('x', encoding='utf-8') as f:
        json.dump(cfg, f, indent=2)
    return target


def cmd_for(command, *, run, source=None, config=None):
    """Argv list avoids nested Windows shell quoting bugs."""
    if command not in ('run','resume','pause','status'):
        raise ValueError('Not a campaign command')
    argv = [str(VENV), '-u', str(ROOT / 'slater_champion_campaign.py'), command,
            '--run', valid_name(run)]
    if command == 'run':
        if source is None or config is None:
            raise ValueError('New campaigns require an explicit source and config')
        argv += ['--source', str(Path(source).resolve()), '--config', str(config)]
    return argv


def spawn(argv, log_path, *, hidden=False):
    """Launch independently. stdout/stderr go to durable logs, not a GUI pipe."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open('a', encoding='utf-8') as stream:
        flags = 0
        if os.name == 'nt':
            flags = subprocess.CREATE_NO_WINDOW if hidden else subprocess.CREATE_NEW_CONSOLE
        proc = subprocess.Popen([str(x) for x in argv], cwd=str(ROOT),
                                stdin=subprocess.DEVNULL, stdout=stream,
                                stderr=subprocess.STDOUT, creationflags=flags,
                                close_fds=True)
    return proc.pid


def start(run, source=SOURCE, *, mode='1v1', monitor=True):
    state = check_install(source)
    missing = [label for label, value in state.items() if not value['exists']]
    if missing:
        raise FileNotFoundError('Preflight failed: ' + ', '.join(missing))
    if os.name != 'nt':
        raise RuntimeError('Start is intended for the owner\'s Windows/Python/CUDA installation; no simulated model substitution')
    config = prepare_config(run, mode)
    _, easy_dir = working_paths(run)
    pid = spawn(cmd_for('run', run=run, source=source, config=config), easy_dir / 'training.log')
    (easy_dir / 'launcher.json').write_text(json.dumps({'pid':pid,'started':time.time(),
                            'source':str(Path(source).resolve()),'mode':mode},indent=2),encoding='utf-8')
    if monitor:
        spawn([VENV, '-u', ROOT / 'slater_easy_monitor.py', 'follow', '--run', run],
              easy_dir / 'monitor.log', hidden=True)
    return pid


def resume(run, *, monitor=True):
    if os.name != 'nt':
        raise RuntimeError('Resume requires the Windows training installation')
    campaign, easy_dir = working_paths(run)
    if not (campaign / 'protocol.json').is_file():
        raise FileNotFoundError('No compatible saved campaign; cannot resume an uninitialized run')
    if not VENV.is_file():
        raise FileNotFoundError('Missing .venv/Scripts/python.exe')
    pid = spawn(cmd_for('resume',run=run),easy_dir / 'training.log')
    if monitor:
        spawn([VENV,'-u',ROOT/'slater_easy_monitor.py','follow','--run',run],
              easy_dir/'monitor.log', hidden=True)
    return pid


def pause(run):
    campaign, easy_dir = working_paths(run)
    if not (campaign / 'protocol.json').is_file():
        raise FileNotFoundError('No campaign to pause')
    if not VENV.is_file():
        raise FileNotFoundError('Missing project Python .venv')
    result = subprocess.run(cmd_for('pause',run=run),cwd=str(ROOT),
                            capture_output=True,text=True,timeout=30)
    if result.returncode:
        raise RuntimeError(result.stderr[-2000:])
    return 'Pause requested. Wait for PAUSED; do not force-close a running PPO update.'


def status(run):
    campaign, easy_dir = working_paths(run)
    progress = json_file(campaign / 'progress.json', {}) or {}
    selected = json_file(campaign / 'selected.json', {}) or {}
    telemetry = json_file(ROOT/'data/isolated/easy_monitor'/run/'bridge_state.json',{}) or {}
    active = progress.get('active') or {}
    return {
        'run':run,'status':progress.get('status','NOT_STARTED'),
        'phase':progress.get('phase','-'),'cycle':progress.get('cycle',0),
        'training_updates':progress.get('train_updates',0),
        'evaluation_games':progress.get('evaluation_games',0),
        'promotions':progress.get('promotions',0),
        'routine':progress.get('routine') or active.get('routine') or '-',
        'experiment_champion':selected.get('actor_path') or progress.get('champion') or 'Original source',
        'playing_model_unchanged':selected.get('playing_model_unchanged',True),
        'wandb_mode':telemetry.get('mode','not_started'),
        'wandb_url':telemetry.get('url'),
        'last_wandb_sync':telemetry.get('last_sync'),
        'log':str(easy_dir/'training.log'),
        'campaign_folder':str(campaign),
    }


def gui(run='slater_easy01'):
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    root=tk.Tk();root.title('Slater | AI Training');root.geometry('740x515');root.minsize(660,475)
    root.configure(bg='#f5f6f8')
    frame=ttk.Frame(root,padding=24);frame.pack(fill='both',expand=True)
    ttk.Label(frame,text='Slater Training',font=('Segoe UI',21,'bold')).pack(anchor='w')
    ttk.Label(frame,text='Your protected attention model • Private champion selection • Live progress').pack(anchor='w',pady=(0,18))
    opts=ttk.Frame(frame);opts.pack(fill='x')
    ttk.Label(opts,text='Campaign').grid(row=0,column=0,sticky='w')
    run_var=tk.StringVar(value=run)
    ttk.Entry(opts,textvariable=run_var,width=22).grid(row=1,column=0,sticky='w',padx=(0,12))
    ttk.Label(opts,text='Focus').grid(row=0,column=1,sticky='w')
    mode_var=tk.StringVar(value='1v1')
    ttk.Combobox(opts,textvariable=mode_var,values=('1v1','balanced'),width=13,state='readonly').grid(row=1,column=1,sticky='w')
    ttk.Label(opts,text='Strongest model (original checkpoint; never overwritten)').grid(row=2,column=0,columnspan=3,sticky='w',pady=(16,2))
    source_var=tk.StringVar(value=str(SOURCE))
    ttk.Entry(opts,textvariable=source_var,width=74).grid(row=3,column=0,columnspan=2,sticky='ew')
    def browse():
        name=filedialog.askopenfilename(title='Select trained update180 actor',filetypes=[('PyTorch checkpoint','*.pt'),('All files','*.*')])
        if name:source_var.set(name)
    ttk.Button(opts,text='Browse',command=browse).grid(row=3,column=2,padx=(8,0))
    opts.columnconfigure(0,weight=1)
    buttons=ttk.Frame(frame);buttons.pack(anchor='w',pady=18)
    info=tk.StringVar(value='Press Check first. Start always creates a NEW isolated campaign.')
    def call(fn):
        try:
            message=fn()
            if message:info.set(str(message))
        except Exception as exc:
            messagebox.showerror('Slater',str(exc))
        refresh()
    ttk.Button(buttons,text='Check',command=lambda:call(lambda: '\n'.join(
        ('OK  ' if x['exists'] else 'MISSING  ')+k for k,x in check_install(source_var.get()).items()))).pack(side='left',padx=(0,8))
    ttk.Button(buttons,text='Start new',command=lambda:call(lambda:f'Started campaign process {start(run_var.get(),Path(source_var.get()),mode=mode_var.get())}')).pack(side='left',padx=(0,8))
    ttk.Button(buttons,text='Resume',command=lambda:call(lambda:f'Resumed campaign process {resume(run_var.get())}')).pack(side='left',padx=(0,8))
    ttk.Button(buttons,text='Pause safely',command=lambda:call(lambda:pause(run_var.get()))).pack(side='left')
    ttk.Label(frame,textvariable=info,wraplength=675,foreground='#555').pack(anchor='w',pady=(0,8))
    status_label=ttk.Label(frame,text='Campaign status',font=('Segoe UI',12,'bold'))
    status_label.pack(anchor='w')
    content=tk.Text(frame,wrap='word',height=10,background='#fff',foreground='#222',relief='flat',font=('Consolas',10))
    content.pack(fill='both',expand=True,pady=(8,8));content.configure(state='disabled')
    foot=ttk.Frame(frame);foot.pack(fill='x')
    def open_folder():
        folder=working_paths(run_var.get())[0]
        if folder.is_dir():os.startfile(folder)
        else:messagebox.showinfo('Slater','No campaign reports yet')
    def open_wandb():
        url=status(run_var.get()).get('wandb_url')
        if url and url.startswith('https://'):webbrowser.open(url)
        else:messagebox.showinfo('Slater','Log in with wandb locally; online run link appears after monitoring connects.')
    ttk.Button(foot,text='Open reports',command=lambda:call(open_folder)).pack(side='left')
    ttk.Button(foot,text='Open W&B dashboard',command=lambda:call(open_wandb)).pack(side='left',padx=8)
    ttk.Label(foot,text='Refreshes every 5 seconds',foreground='#777').pack(side='right')
    def refresh():
        try:
            d=status(run_var.get())
            display=(f"State: {d['status']}   Phase: {d['phase']}   Cycle: {d['cycle']}\n"
                     f"Routine: {d['routine']}    Updates: {d['training_updates']}\n"
                     f"Evaluated games: {d['evaluation_games']}    Confirmed promotions: {d['promotions']}\n\n"
                     f"Experiment champion: {d['experiment_champion']}\n\n"
                     f"W&B: {d['wandb_mode']}\nDashboard: {d['wandb_url'] or 'Local logs available; no online run yet'}\n"
                     f"Training log: {d['log']}\n")
            content.configure(state='normal');content.delete('1.0','end');content.insert('1.0',display);content.configure(state='disabled')
        except (ValueError,OSError):
            pass
    def tick():
        refresh();root.after(5000,tick)
    tick();root.mainloop()


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=('gui','check','start','resume','pause','status','audit','monitor'))
    p.add_argument('--run',default='slater_easy01',type=valid_name)
    p.add_argument('--source',type=Path,default=SOURCE)
    p.add_argument('--target',type=Path)
    p.add_argument('--mode',choices=('1v1','balanced'),default='1v1')
    p.add_argument('--no-monitor',action='store_true')
    a=p.parse_args(argv)
    if a.command=='gui':gui(a.run)
    elif a.command=='check':print(json.dumps(check_install(a.source),indent=2))
    elif a.command=='start':print('TRAINING_PID',start(a.run,a.source,mode=a.mode,monitor=not a.no_monitor))
    elif a.command=='resume':print('TRAINING_PID',resume(a.run,monitor=not a.no_monitor))
    elif a.command=='pause':print(pause(a.run))
    elif a.command=='status':print(json.dumps(status(a.run),indent=2))
    elif a.command=='audit':
        from slater_transfer_diagnose import main as audit
        return audit(['--source',str(a.source)]+(['--target',str(a.target)] if a.target else []))
    elif a.command=='monitor':
        from slater_easy_monitor import main as monitoring
        return monitoring(['follow','--run',a.run])
    return 0


if __name__=='__main__':
    sys.exit(main())
