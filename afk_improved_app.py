"""AFK Improved local Windows desktop control center. Python 3.11/Tkinter (no web accounts).
Designed to be installed by extracting files over the existing Chat_GPT_AI project.
Training uses the EXISTING AutoLeague script in an isolated experiment directory.
"""
from __future__ import annotations
import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import ttk, messagebox, simpledialog, filedialog

import afk_improved_core as core
from afk_v2_device import available_devices,validate_device

ROOT=core.ROOT
PYTHON=ROOT/'.venv'/'Scripts'/'python.exe'
if not PYTHON.is_file():PYTHON=Path(sys.executable)

class ControlCenter(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('AFK Improved v2.3 Research · Rocket League AI')
        self.geometry('1180x800')
        self.minsize(830,580)
        self.configure(bg='#141921')
        self.queue=queue.Queue()
        self.jobs={}  # independent tasks; training and replay downloads may coexist
        self.devices,self.device_info=available_devices()
        if 'cuda:0' in self.devices:
            self.device_info += (' | NOTE: bundled Nexto JIT contains fixed CPU operations. '
                                 'Training automatically falls back to CPU until safely ported.')
        self.camera=None
        self.models=[]
        self._style()
        self._build()
        self.refresh_all()
        self.after(350,self._poll)
        self.protocol('WM_DELETE_WINDOW',self._close)

    def _style(self):
        sty=ttk.Style(self)
        if 'clam' in sty.theme_names():sty.theme_use('clam')
        sty.configure('.',background='#161d27',foreground='#ebeff5',font=('Segoe UI',10))
        sty.configure('TFrame',background='#161d27')
        sty.configure('TLabel',background='#161d27',foreground='#e2e8f0')
        sty.configure('TButton',padding=(12,7),background='#314153',foreground='#f6f8fa')
        sty.map('TButton',background=[('active','#435b72')])
        sty.configure('TNotebook',background='#141921')
        sty.configure('TNotebook.Tab',padding=(17,10),background='#263243',foreground='#dae6f4')
        sty.map('TNotebook.Tab',background=[('selected','#354c64')])
        sty.configure('Treeview',background='#1b2531',foreground='#dce7f3',fieldbackground='#1b2531',rowheight=27)
        sty.map('Treeview',background=[('selected','#375570')])
        sty.configure('Treeview.Heading',background='#253647',foreground='#eaf1f7')
        # Windows Clam defaults are white entry backgrounds even with a dark app.
        sty.configure('TEntry',fieldbackground='#233245',background='#233245',foreground='#f4f7fb',
                      insertcolor='#f4f7fb',bordercolor='#46617b',padding=5)
        sty.map('TEntry',fieldbackground=[('disabled','#29313a'),('readonly','#233245')],
                foreground=[('disabled','#97a6bb'),('readonly','#f4f7fb')])
        sty.configure('TCombobox',fieldbackground='#233245',background='#233245',foreground='#f4f7fb',
                      arrowcolor='#e2e8f0',selectbackground='#314b66',selectforeground='#f4f7fb',padding=4)
        sty.map('TCombobox',fieldbackground=[('readonly','#233245'),('disabled','#29313a')],
                foreground=[('readonly','#f4f7fb'),('disabled','#97a6bb')],
                selectbackground=[('readonly','#233245')],selectforeground=[('readonly','#f4f7fb')])
        self.option_add('*TCombobox*Listbox.background','#1b2531')
        self.option_add('*TCombobox*Listbox.foreground','#f4f7fb')
        self.option_add('*TCombobox*Listbox.selectBackground','#314b66')
        self.option_add('*TCombobox*Listbox.selectForeground','#ffffff')

    def _section(self,parent,title,text=''):
        p=ttk.Frame(parent,padding=(18,16));p.pack(fill='x')
        ttk.Label(p,text=title,font=('Segoe UI',14,'bold')).pack(anchor='w')
        if text:ttk.Label(p,text=text,wraplength=1000).pack(anchor='w',pady=(7,2))
        return p

    def _line_buttons(self,parent,buttons):
        bar=ttk.Frame(parent)
        bar.pack(fill='x',pady=(8,6))
        for label,fn in buttons:ttk.Button(bar,text=label,command=fn).pack(side='left',padx=(0,10))
        return bar

    def _build(self):
        head=ttk.Frame(self,padding=(24,16));head.pack(fill='x')
        ttk.Label(head,text='AFK IMPROVED',font=('Segoe UI',21,'bold')).pack(side='left')
        ttk.Label(head,text='Cycle 9 lineage · protected originals · local control center',font=('Segoe UI',10)).pack(side='right')
        self.tabs=ttk.Notebook(self);self.tabs.pack(fill='both',expand=True,padx=16,pady=(0,12))
        pages={}
        for name in ('Overview','Training','Models & Backups','Reports','Replays','Replay + TAS Learning','Versatile Trainer','Aggressive Research','Team modes','Mechanics Lab','Viewer & RLBot','Logs'):
            p=ttk.Frame(self.tabs);self.tabs.add(p,text=name);pages[name]=p
        self.overview=pages['Overview'];self.training=pages['Training'];self.modelpage=pages['Models & Backups']
        self.reportspage=pages['Reports'];self.replays=pages['Replays'];self.learnpage=pages['Replay + TAS Learning'];self.versatilepage=pages['Versatile Trainer'];self.researchpage=pages['Aggressive Research'];self.team=pages['Team modes'];self.mechanics=pages['Mechanics Lab'];self.viewer=pages['Viewer & RLBot'];self.logs=pages['Logs']
        self._make_overview();self._make_training();self._make_models();self._make_reports();self._make_replays();self._make_learning();self._make_versatile();self._make_research();self._make_team_modes();self._make_mechanics();self._make_viewer();self._make_logs()
        self.footer=tk.StringVar(value='Ready — nothing is started automatically')
        ttk.Label(self,textvariable=self.footer,padding=(22,8)).pack(fill='x')

    def _make_overview(self):
        p=self._section(self.overview,'Verified first, train second',
            'Primary line: Cycle 9 (50f34d4a…). AutoLeague main champion is not altered. '
            'The experimental best only changes after an additional independent benchmark.')
        self.state_text=tk.StringVar(value='Checking project…')
        ttk.Label(p,textvariable=self.state_text,justify='left',wraplength=950,font=('Consolas',10)).pack(anchor='w',pady=14)
        self._line_buttons(p,[('Refresh status',self.refresh_all),('Validate protected files',self.check_files),
                             ('Back up champion + state + Cycle 9',self.backup_files),
                             ('Open experiment directory',lambda:self.open_folder(core.DATA))])
        p=self._section(self.overview,'What this app does — and does not',
            'Runs the existing native Nexto PPO/AutoLeague self-play in its own data folder. '
            'Archives backup checkpoints; keeps a separately verified best. '
            'It does NOT guarantee improvement. Multi-car and replay learning are isolated research; TAS-to-policy learning is not enabled.')
        ttk.Label(p,text='GigaLearn C++ is a research migration track. The Python engine stays active until a '
                  'compatible policy port and fair measured speed comparison are proven.',wraplength=930).pack(anchor='w',pady=6)

    def _make_training(self):
        p=self._section(self.training,'Training controls',
            'One-click safe start/pause/resume. Reopening Start resumes the existing isolated league. '
            'Pause takes effect after the current PPO cycle is saved and evaluated.')
        self.cycles=tk.StringVar(value='0');self.hours=tk.StringVar(value='2');self.device=tk.StringVar(value='cpu')
        self.eval_games=tk.StringVar(value='40');self.segment=tk.StringVar(value='8192')
        row=ttk.Frame(p);row.pack(fill='x',pady=8)
        for title,variable,width in [('Hours (0 = unlimited)',self.hours,10),('Cycles (0 = unlimited)',self.cycles,10),
                                     ('Eval games',self.eval_games,10),('Steps per cycle',self.segment,11)]:
            part=ttk.Frame(row);part.pack(side='left',padx=(0,22));ttk.Label(part,text=title).pack(anchor='w');
            ttk.Entry(part,textvariable=variable,width=width).pack(anchor='w',pady=4)
        dev=ttk.Combobox(row,textvariable=self.device,values=self.devices,state='readonly',width=9)
        dev.pack(side='left',padx=(0,10))
        ttk.Label(p,text=self.device_info,wraplength=970).pack(anchor='w',pady=(3,9))
        self._line_buttons(p,[('Check hashes',self.run_preflight),('RocketSim preflight',self.run_sim_preflight),('Start or resume',self.start_training),
                             ('Request safe pause',self.pause_training),('Open status JSON',lambda:self.open_file(core.STATUS))])
        p=self._section(self.training,'Live experiment state')
        self.traininfo=tk.StringVar(value='Not running')
        ttk.Label(p,textvariable=self.traininfo,wraplength=950,justify='left',font=('Consolas',10)).pack(anchor='w',pady=8)
        ttk.Label(p,text='A paused run is not a failed run. The same checkpoints are used again next time.',wraplength=900).pack(anchor='w')

    def _make_models(self):
        p=self._section(self.modelpage,'Models & backups',
            'Select a checkpoint to inspect its SHA-256, make an archival copy, or evaluate it against Nexto. '
            'Training always starts from the protected Cycle 9 lineage, not the selected row.')
        self._line_buttons(p,[('Refresh list',self.refresh_models),('Show SHA-256',self.show_model_hash),
                             ('Copy selected model safely',self.copy_model),('Evaluate vs Nexto',self.eval_model),
                             ('Open all data',lambda:self.open_folder(ROOT/'data'))])
        holder=ttk.Frame(self.modelpage,padding=(18,4));holder.pack(fill='both',expand=True)
        self.tree=ttk.Treeview(holder,columns=('path','size','date'),show='headings',selectmode='browse')
        self.tree.heading('path',text='Checkpoint');self.tree.heading('size',text='Size (MB)');self.tree.heading('date',text='Modified')
        self.tree.column('path',width=700);self.tree.column('size',width=110,anchor='e');self.tree.column('date',width=165)
        ys=ttk.Scrollbar(holder,orient='vertical',command=self.tree.yview);self.tree.configure(yscrollcommand=ys.set)
        ys.pack(side='right',fill='y');self.tree.pack(fill='both',expand=True)

    def _make_reports(self):
        p=self._section(self.reportspage,'Evaluation reports — never overwrite a checkpoint',
            'Browse tournament, finishing, original AutoLeague, and AFK Improved evaluation JSON files. '
            'A tournament ranking is not proof of full five-minute superiority. Team lab results are experimental.')
        self._line_buttons(p,[('Refresh reports',self.refresh_reports),
            ('Open selected report',self.open_selected_report),
            ('Open AFK reports folder',lambda:self.open_folder(core.DATA/'reports'))])
        holder=ttk.Frame(self.reportspage,padding=(18,4));holder.pack(fill='both',expand=True)
        self.reporttree=ttk.Treeview(holder,columns=('name','verdict','date'),show='headings',selectmode='browse')
        self.reporttree.heading('name',text='Report');self.reporttree.heading('verdict',text='Decision / status');self.reporttree.heading('date',text='Modified')
        self.reporttree.column('name',width=700);self.reporttree.column('verdict',width=190)
        self.reporttree.column('date',width=155)
        self.reporttree.pack(fill='both',expand=True)
        self.reporttree.bind('<Double-1>',lambda event:self.open_selected_report())
        self.report_items=[]
        self.refresh_reports()

    def refresh_reports(self):
        if not hasattr(self,'reporttree'):return
        folders=[core.DATA/'learning'/'reports',core.DATA/'reports',core.LEAGUE/'reports',ROOT/'data'/'autoleague'/'reports',
                 ROOT/'data'/'finishing_lab'/'reports',ROOT/'benchmark_reports',
                 ROOT/'model_tournament_reports',ROOT/'data'/'scenario_diagnostics']
        files=[]
        for folder in folders:
            if folder.is_dir():files.extend(folder.glob('*.json'))
        files=sorted(set(files),key=lambda p:p.stat().st_mtime,reverse=True)[:500]
        self.report_items=files
        self.reporttree.delete(*self.reporttree.get_children())
        for i,p in enumerate(files):
            data=core.read_json(p,{}) or {}
            verdict=str(data.get('verdict',data.get('kind',data.get('status','—'))))[:36]
            relative=str(p.relative_to(ROOT)) if ROOT in p.parents else str(p)
            mod=datetime.fromtimestamp(p.stat().st_mtime).strftime('%Y-%m-%d %H:%M')
            self.reporttree.insert('', 'end',iid=str(i),values=(relative,verdict,mod))

    def open_selected_report(self):
        rows=self.reporttree.selection()
        if rows:self.open_file(self.report_items[int(rows[0])])
        else:messagebox.showinfo('Select report','Select a report row first.')

    def _make_replays(self):
        p=self._section(self.replays,'Ballchasing replay collection',
            'Suggested source: ranked 1v1. Ballchasing API documents GC1+ filter, not exact GC3/SSL. '
            'Download with documented filters; curate GC3/SSL examples separately. '
            'Approximate human replay-to-native action learning is available separately under Replay + TAS Learning.')
        self.maxreplays=tk.StringVar(value='50');self.rank=tk.StringVar(value='gc-plus');self.replay_workers=tk.StringVar(value='2')
        self.afterdate=tk.StringVar(value='2024-01-01');self.beforedate=tk.StringVar(value='2026-10-09')
        row=ttk.Frame(p);row.pack(fill='x',pady=12)
        ttk.Label(row,text='Maximum new files:').pack(side='left');ttk.Entry(row,textvariable=self.maxreplays,width=8).pack(side='left',padx=10)
        ttk.Label(row,text='Rank filter:').pack(side='left');ttk.Combobox(row,textvariable=self.rank,
            values=['gc-plus'],state='readonly',width=10).pack(side='left',padx=10)
        dates=ttk.Frame(p);dates.pack(fill='x')
        ttk.Label(dates,text='Replay after:').pack(side='left');ttk.Entry(dates,textvariable=self.afterdate,width=12).pack(side='left',padx=(8,20))
        ttk.Label(dates,text='Before:').pack(side='left');ttk.Entry(dates,textvariable=self.beforedate,width=12).pack(side='left',padx=(8,20))
        ttk.Label(row,text='Download workers (1–3):').pack(side='left',padx=(15,5))
        ttk.Combobox(row,textvariable=self.replay_workers,values=['1','2','3'],state='readonly',width=3).pack(side='left')
        self._line_buttons(p,[('Pause downloads',self.pause_replays),('Test Ballchasing access',lambda:self.replay_download(True)),
                             ('Resume/download',lambda:self.replay_download(False)),
                             ('Refresh search for new',lambda:self.replay_download(False,refresh=True)),
                             ('Audit downloaded replays',self.audit_replays),
                             ('Open replay folder',lambda:self.open_folder(ROOT/'data'/'replays'))])
        ttk.Label(p,text='Ballchasing search = GC1 and above, NOT verified GC3/SSL. Your API token is requested privately or taken from BALLCHASING_TOKEN. '
                  'It is never saved to the project. Raw replay files contain states, not reliable controller inputs.',
                  wraplength=930).pack(anchor='w',pady=10)

    def _make_research(self):
        p=self._section(self.researchpage,'Aggressive PPO Research · separate experiments',
            'Larger PPO policy changes from the untouched Cycle 9: control, explore, aggressive, radical. '
            'Each checkpoint has its own isolated folder and held-out Nexto/1v1 comparison. '
            'No automatic promotion. Run AFTER Replay/TAS Learning finishes; no simultaneous training.')
        ttk.Label(p,text='This aggressive PPO branch remains native 1v1 CPU training; the separate Team modes tab has experimental multi-car training.',
                  wraplength=950).pack(anchor='w',pady=(5,6))
        self._line_buttons(p,[
            ('Check research preflight',lambda:self.research_start('check')),
            ('Train variants and compare',lambda:self.research_start('run')),
            ('Request pause',lambda:self.research_start('pause')),
            ('Resume experiment',lambda:self.research_start('resume')),
        ])
        self._line_buttons(p,[
            ('Complete held-out evaluations',lambda:self.research_start('evaluate')),
            ('Show research status',lambda:self.research_start('status')),
            ('Open branch checkpoints',lambda:self.open_folder(core.DATA/'aggressive_research')),
        ])
        ttk.Label(p,text='Candidate with highest short-run win rate is NOT automatically the best bot. '
                  'Compare against untouched Cycle 9 on fresh matched seeds before selecting a checkpoint.',
                  wraplength=960).pack(anchor='w',pady=12)

    def research_start(self,cmd):
        if cmd=='run' and not messagebox.askyesno('Start aggressive research',
              'Start up to four isolated PPO experiments, some intentionally unstable?\n'
              'This can take hours. Only start when Replay Learning and all other trainers are finished.'):
            return
        args=[str(PYTHON),str(ROOT/'afk_aggressive_research.py'),cmd]
        if cmd in ('run','resume','evaluate'): args.extend(['--radical','--eval-games','120'])
        if cmd=='pause':
            try:
                subprocess.run(args,cwd=ROOT,check=True,creationflags=(subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0))
                self.log('Aggressive Research pause requested. Wait for current full branch to finish.')
            except Exception as ex:messagebox.showerror('Pause failed',str(ex))
        else:self._spawn('Aggressive Research '+cmd,args,category=('research_check' if cmd in ('check','status') else 'research'))

    def _make_learning(self):
        p=self._section(self.learnpage,'Native Replay + TAS Learning · guarded experiment',
            'Build selective 1v1 replay demonstrations, fine-tune an isolated copy of Cycle 9, '
            'then compare against Nexto and untouched Cycle 9. Reconstructed replay controls are approximate. '
            'TAS .data files are audited, NOT fed into training until input and physics alignment is verified.')
        self.learn_replays=tk.StringVar(value=str(ROOT/'data'/'replays'))
        self.learn_tas=tk.StringVar(value=str(ROOT/'data'/'tas'))
        self.learn_limit=tk.StringVar(value='60000')
        self.learn_games=tk.StringVar(value='200')
        for label,variable in [('Replay folder',self.learn_replays),('TAS folder (audit only)',self.learn_tas)]:
            row=ttk.Frame(p);row.pack(fill='x',pady=5)
            ttk.Label(row,text=label,width=25).pack(side='left')
            ttk.Entry(row,textvariable=variable,width=80).pack(side='left',padx=8)
        row=ttk.Frame(p);row.pack(fill='x',pady=6)
        ttk.Label(row,text='Maximum training samples').pack(side='left',padx=(0,7))
        ttk.Entry(row,textvariable=self.learn_limit,width=12).pack(side='left',padx=(0,24))
        ttk.Label(row,text='Competitive verification games').pack(side='left',padx=(0,7))
        ttk.Entry(row,textvariable=self.learn_games,width=8).pack(side='left')
        self._line_buttons(p,[('One-click: build → train → verify',self.learn_pipeline),
                              ('Audit TAS .data',self.learn_audit_tas),
                              ('Build replay dataset',self.learn_build),
                              ('Train protected copy',self.learn_train)])
        self._line_buttons(p,[('Read-only competitive verify',self.learn_verify),
                              ('Request safe pause',self.learn_pause),
                              ('Clear pause for next run',self.learn_unpause),
                              ('Open experiment files',lambda:self.open_folder(core.DATA/'learning'))])
        p=self._section(self.learnpage,'Replay learning experiments · independent hyperparameter branches',
            'Your first run rejected a candidate because its policy changed too much. Start with a smaller '
            'learning-rate branch and preserve the cached replay dataset. Offline validation is NOT game superiority.')
        self._line_buttons(p,[('Check cached replay data',lambda:self.replay_sweep_start('check')),
                              ('Train 1 isolated replay candidate',lambda:self.replay_sweep_start('train')),
                              ('Show sweep reports',lambda:self.replay_sweep_start('summary')),
                              ('Verify replay candidate vs Nexto',lambda:self.replay_sweep_start('verify'))])
        p=self._section(self.learnpage,'Training safeguards and current status',
            'Original champion/Cycle 9 untouched. Replay-level holdout, uncertainty filtering, '
            'balanced sampling, tiny update steps, KL/action-drift checks and validation early stopping. '
            'A better replay imitation score is NOT proof of better gameplay; acceptance still needs RocketSim. '
            'The app never promotes this candidate automatically.')
        self.learning_info=tk.StringVar(value='No learning run has been started')
        ttk.Label(p,textvariable=self.learning_info,wraplength=940,justify='left',font=('Consolas',10)).pack(anchor='w',pady=7)

    def _make_versatile(self):
        p=self._section(self.versatilepage,'Versatile hybrid trainer',
            'Continue a chosen native checkpoint with mixed 1v1/2v2 PPO practice and confidence-filtered replay learning. '
            'All frozen opponents use scripted kickoff. Fresh match confirmation chooses the saved champion; '
            'every raw candidate remains available. Stop other training jobs before starting this trainer.')
        default=ROOT/'data/isolated/mechanics_curriculum/selected7_mechanics01/update_000180.pt'
        if not default.is_file():default=ROOT/'data/autoleague/backups/20261008T224518_775472Z_cycle0009_steps000008192_candidate.pt'
        self.versatile_source=tk.StringVar(value=str(default))
        self.versatile_dataset=tk.StringVar(value=str(ROOT/'data/isolated/versatile_data01'))
        self.versatile_inputs=tk.StringVar(value=str(ROOT/'data/replays'))
        self.versatile_run=tk.StringVar(value='versatile01');self.versatile_cycles=tk.StringVar(value='3')
        self.versatile_use_data=tk.BooleanVar(value=True)
        for label,var in [('Source checkpoint',self.versatile_source),('Replay / aligned capture folder',self.versatile_inputs),('Prepared dataset folder',self.versatile_dataset)]:
            row=ttk.Frame(p);row.pack(fill='x',pady=4)
            ttk.Label(row,text=label,width=28).pack(side='left')
            ttk.Entry(row,textvariable=var,width=75).pack(side='left',padx=8)
        ttk.Button(p,text='Browse source checkpoint…',command=self.pick_versatile_source).pack(anchor='w')
        ttk.Checkbutton(p,text='Include prepared replay demonstrations and training replay starts',variable=self.versatile_use_data).pack(anchor='w',pady=6)
        row=ttk.Frame(p);row.pack(fill='x',pady=4)
        for label,var in [('Run name',self.versatile_run),('Cycles this session',self.versatile_cycles)]:
            ttk.Label(row,text=label).pack(side='left',padx=7);ttk.Entry(row,textvariable=var,width=20).pack(side='left')
        self._line_buttons(p,[('Install replay dependencies',lambda:self._spawn('Replay dependencies',[str(PYTHON),'-m','pip','install','-r',str(ROOT/'requirements-slater-versatile.txt')],category='versatile_install')),
                             ('Prepare / reuse dataset',lambda:self.versatile_action('prepare')),
                             ('Preflight',lambda:self.versatile_action('preflight'))])
        self._line_buttons(p,[('Smoke test (new run name)',lambda:self.versatile_action('smoke')),
                             ('Start new run',lambda:self.versatile_action('start')),
                             ('Resume saved run',lambda:self.versatile_action('resume')),
                             ('Request safe pause',lambda:self.versatile_action('pause'))])
        self._line_buttons(p,[('Show saved status',lambda:self.versatile_action('status')),
                             ('Open run / reports',self.open_versatile_run),
                             ('Export saved champion',self.export_versatile_champion),
                             ('Read guide',lambda:self.open_file(ROOT/'SLATER_VERSATILE_README.md'))])
        ttk.Label(p,text='Default: 20 PPO updates per cycle; 3 cycles per session. Stops after 3 unconfirmed cycles. '
                  'Smoke needs a separate run name. Resume uses its saved source, data and configuration. '
                  'Legacy TAS .data files lack aligned game states and are not training inputs.',wraplength=920).pack(anchor='w',pady=10)

    def pick_versatile_source(self):
        value=filedialog.askopenfilename(parent=self,title='Choose checkpoint to continue',initialdir=str(ROOT/'data'),filetypes=[('Native Nexto checkpoint','*.pt')])
        if value:self.versatile_source.set(value)

    def versatile_action(self,part):
        name=self.versatile_run.get().strip()
        if not name or not name.replace('_','').replace('-','').isalnum() or len(name)>50:
            messagebox.showerror('Invalid run name','Use letters/digits/_/-; maximum 50 characters');return
        try:
            cycles=int(self.versatile_cycles.get())
            if not 1<=cycles<=100:raise ValueError()
        except ValueError:messagebox.showerror('Invalid cycles','Choose 1..100 cycles');return
        args=[str(PYTHON),'-u',str(ROOT/'slater_versatile_trainer.py'),part,'--run',name]
        if part=='prepare':args+=['--inputs',self.versatile_inputs.get(),'--out',self.versatile_dataset.get()]
        if part in ('start','smoke','preflight'):
            args+=['--source',self.versatile_source.get()]
            if self.versatile_use_data.get():args+=['--dataset',self.versatile_dataset.get()]
        if part in ('start','resume'):args+=['--cycles',str(cycles)]
        self._spawn('Versatile '+part,args,category='versatile_control' if part in ('pause','status','preflight') else 'versatile')

    def open_versatile_run(self):
        from slater_versatile_trainer import run_path
        self.open_folder(run_path(self.versatile_run.get().strip()))

    def export_versatile_champion(self):
        from slater_versatile_trainer import run_path
        doc=core.read_json(run_path(self.versatile_run.get().strip())/'selected.json',{})
        if not doc.get('checkpoint'):messagebox.showerror('No saved champion','Start a versatile run first.');return
        if core.hash_file(Path(doc['checkpoint']))!=doc['sha256']:messagebox.showerror('Changed checkpoint','Saved champion hash differs');return
        self.rl_checkpoint.set(doc['checkpoint']);self.rl_scripted_kickoff.set(True);self.export_rlbot()

    def _learning_cmd(self,part):
        return [str(PYTHON),str(ROOT/'afk_replay_tas_learning.py'),part]

    def _learn_valid(self):
        try:
            samples=int(self.learn_limit.get());games=int(self.learn_games.get())
            if not (1500<=samples<=500000 and 100<=games<=2000):
                raise ValueError('Samples must be 1500–500000; verification games 100–2000')
            return samples,games
        except ValueError as e:
            messagebox.showerror('Invalid learning parameters',str(e));return None

    def learn_pipeline(self):
        nums=self._learn_valid()
        if nums is None:return
        if not messagebox.askyesno('Run isolated replay learning',
                 'This can take a long time. Replay actions are reconstructed APPROXIMATELY. '
                 'The experiment will NEVER replace the champion or Cycle 9 automatically. Continue?'):return
        from pathlib import Path
        # Leave TAS files out of the training input. Their audit, when available, runs independently.
        cmd=self._learning_cmd('pipeline')+['--replays',self.learn_replays.get(),'--tas-folder',self.learn_tas.get(),
                   '--max-samples',str(nums[0]),'--games',str(nums[1])]
        self._spawn('Replay learning pipeline',cmd,category='learning')

    def learn_audit_tas(self):
        self._spawn('TAS input audit',self._learning_cmd('tas-audit')+[self.learn_tas.get()],category='learning')

    def learn_build(self):
        nums=self._learn_valid()
        if nums is not None:
            self._spawn('Native replay dataset',self._learning_cmd('build')+
                        [self.learn_replays.get(),'--max-samples',str(nums[0])],category='learning')

    def learn_train(self):
        if not messagebox.askyesno('Isolated training',
                'Train a copy of Cycle 9 using approximate replay actions? No auto-promotions.'):return
        self._spawn('Conservative replay BC',self._learning_cmd('train'),category='learning')

    def learn_verify(self):
        nums=self._learn_valid()
        if nums is not None:
            self._spawn('Replay candidate vs Nexto and Cycle 9',self._learning_cmd('verify')+
                        ['--games',str(nums[1])],category='learning')

    def learn_pause(self):
        path=core.DATA/'learning'/'learning.pause'
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text('pause at a safe training epoch boundary\n',encoding='utf8')
        self.log('Learning safe pause requested. Do not close until current epoch finishes.')

    def learn_unpause(self):
        if self.jobs.get('learning') and self.jobs['learning'].poll() is None:
            messagebox.showerror('Learning active','Wait for the learner to stop before clearing pause.')
            return
        (core.DATA/'learning'/'learning.pause').unlink(missing_ok=True)
        self.log('Learning pause cleared. You can start a new run.')

    def replay_sweep_start(self,command):
        if command=='train' and not messagebox.askyesno('Try isolated replay learning',
            'Train a separate policy copy using the existing replay dataset (CPU, may take a while)?\n'
            'This WILL NOT replace Cycle 9 and may reject its candidate again.'):
            return
        cmd=[str(PYTHON),str(ROOT/'afk_replay_sweep.py'),command]
        if command=='train':cmd+=['--trials','1','--epochs','2']
        if command=='verify':cmd+=['--name','small_step','--games','80']
        self._spawn('Replay research '+command,cmd,category='learning')

    def _make_team_modes(self):
        p=self._section(self.team,'Multi-car RocketSim research · isolated checkpoints',
            'True variable team sizes, shared-policy teammates, frozen Nexto opponents and padded entity attention. '
            'New PPO branches are research-only: not automatically promoted, and must be benchmarked. '
            'The real installed RocketSim environment needs preflight validation first.')
        self.team_ours=tk.StringVar(value='1');self.team_them=tk.StringVar(value='2')
        self.team_scenario=tk.StringVar(value='kickoff');self.team_steps=tk.StringVar(value='512')
        self.team_lr=tk.StringVar(value='1.2e-5');self.team_seed=tk.StringVar(value='20261010')
        row=ttk.Frame(p);row.pack(fill='x',pady=9)
        for label,var,values in [('Our players',self.team_ours,['1','2','3']),('Opponents',self.team_them,['1','2','3']),
                                  ('Scenario',self.team_scenario,['kickoff','grounded','pressure'])]:
            f=ttk.Frame(row);f.pack(side='left',padx=(0,18));ttk.Label(f,text=label).pack(anchor='w')
            ttk.Combobox(f,textvariable=var,values=values,state='readonly',width=12).pack(anchor='w',pady=4)
        row=ttk.Frame(p);row.pack(fill='x',pady=8)
        for label,var in [('Controlled samples',self.team_steps),('Actor LR',self.team_lr),('Seed',self.team_seed)]:
            f=ttk.Frame(row);f.pack(side='left',padx=(0,22));ttk.Label(f,text=label).pack(anchor='w')
            ttk.Entry(f,textvariable=var,width=13).pack(anchor='w',pady=4)
        self._line_buttons(p,[('Run real simulator preflight',lambda:self.team_start('preflight')),
                              ('Train isolated team candidate',lambda:self.team_start('train')),
                              ('Evaluate chosen team checkpoint',self.team_evaluate),
                              ('Open team checkpoints',lambda:self.open_folder(core.DATA/'team_research'))])
        ttk.Label(p,text='The opponent is an independent frozen Nexto policy; teammates share the evolving policy. '
                  'This does NOT yet include special role assignments, tactical kickoff curriculum, '
                  'contextual demo rewards, full five-minute match evaluation, or automatic skill merging.',wraplength=1000).pack(anchor='w',pady=9)

    def team_start(self,command):
        try:
            ours=int(self.team_ours.get());them=int(self.team_them.get())
            steps=int(self.team_steps.get());seed=int(self.team_seed.get());rate=float(self.team_lr.get())
            if not (1<=ours<=3 and 1<=them<=3 and 2<=ours+them<=6 and 1<=steps<=1000000 and 0<rate<=.001):
                raise ValueError('Team sizes 1–3, valid total 2–6, steps 1–1,000,000 and rate <= 0.001 required')
        except ValueError as e:messagebox.showerror('Invalid team experiment',str(e));return
        if command=='train' and not messagebox.askyesno('Experimental multi-car training',
                f'Train an isolated {ours}v{them} candidate (CPU), using {steps} controlled samples?\n'
                'This is unverified research and may make the bot worse. Original checkpoints stay intact.'):
            return
        args=[str(PYTHON),str(ROOT/'afk_team_research.py'),command,'--ours',str(ours),'--them',str(them),
              '--scenario',self.team_scenario.get(),'--steps',str(steps),'--lr',str(rate),'--seed',str(seed)]
        self._spawn(f'Team {ours}v{them} {command}',args,category='team')

    def team_evaluate(self):
        selected=filedialog.askopenfilename(parent=self,title='Select isolated team candidate .pt',
               initialdir=str(core.DATA/'team_research'),filetypes=[('Native Nexto checkpoint','*.pt')])
        if not selected:return
        try:
            ours=int(self.team_ours.get());them=int(self.team_them.get());seed=int(self.team_seed.get())
        except ValueError as e:messagebox.showerror('Invalid team settings',str(e));return
        args=[str(PYTHON),str(ROOT/'afk_team_research.py'),'evaluate',
              '--ours',str(ours),'--them',str(them),'--candidate',selected,
              '--scenario','mixed','--games','60','--seed',str(seed+99991)]
        self._spawn(f'Team {ours}v{them} held-out evaluation',args,category='team')

    def _make_mechanics(self):
        p=self._section(self.mechanics,'Mechanics experiments · dedicated PPO stages',
            'Runs the EXISTING mechanics_train.py on a protected Cycle 9 copy. Separate checkpoint per '
            'stage, with a held-out mechanics test available. This does not inject a 120Hz wall-dash controller.')
        self.mechanic_stage=tk.StringVar(value='wavedash');self.mechanic_steps=tk.StringVar(value='512')
        self.mechanic_seed=tk.StringVar(value='20261010')
        row=ttk.Frame(p);row.pack(fill='x',pady=9)
        ttk.Label(row,text='Stage').pack(side='left',padx=(0,7))
        ttk.Combobox(row,textvariable=self.mechanic_stage,width=18,state='readonly',
            values=['recovery','wavedash','kickoff','aerial_touch','air_dribble','flip_reset','double_tap',
                    'ground_pinch','wall_pinch','ceiling_touch']).pack(side='left',padx=(0,22))
        ttk.Label(row,text='Steps').pack(side='left');ttk.Entry(row,textvariable=self.mechanic_steps,width=10).pack(side='left',padx=9)
        ttk.Label(row,text='Seed').pack(side='left');ttk.Entry(row,textvariable=self.mechanic_seed,width=14).pack(side='left',padx=9)
        self._line_buttons(p,[('Train isolated skill',lambda:self.mechanic_start('train')),
                              ('Evaluate skill',lambda:self.mechanic_start('evaluate')),
                              ('Open mechanics checkpoints',lambda:self.open_folder(core.DATA/'skill_research'))])
        ttk.Label(p,text='Wall-dashing specifically requires a future per-physics-tick controller; '
                  'the current 8-tick Nexto actions cannot reliably perform all dash sequences.',wraplength=1000).pack(anchor='w',pady=9)

    def mechanic_start(self,command):
        try:
            steps=int(self.mechanic_steps.get());seed=int(self.mechanic_seed.get())
            if not 1<=steps<=1000000:raise ValueError('Steps must be 1..1,000,000')
        except ValueError as e:messagebox.showerror('Invalid skill settings',str(e));return
        stage=self.mechanic_stage.get();source=ROOT/'data'/'autoleague'/'backups'/'20261008T224518_775472Z_cycle0009_steps000008192_candidate.pt'
        ckpt=core.DATA/'skill_research'/stage/f'seed{seed}_steps{steps}.pt'
        if command=='train':
            if ckpt.exists():messagebox.showerror('Already exists','This experiment checkpoint already exists. Change seed/steps; no overwrites.');return
            if not messagebox.askyesno('Train isolated skill',f'Train {stage} (research only), no promotion?'):return
            args=[str(PYTHON),str(ROOT/'mechanics_train.py'),'--stage',stage,'--source',str(source),
                  '--checkpoint',str(ckpt),'--steps',str(steps),'--seed',str(seed),'--device','cpu']
        else:
            if not ckpt.exists():messagebox.showinfo('No candidate','Train this exact stage/seed/steps first.');return
            args=[str(PYTHON),str(ROOT/'mechanics_evaluate.py'),'--stage',stage,'--source',str(source),
                  '--candidate',str(ckpt),'--episodes','30','--seed',str(seed+499),
                  '--opponent','nexto','--competitive']
        self._spawn(f'Mechanic {stage} {command}',args,category='mechanics')

    def _make_viewer(self):
        p=self._section(self.viewer,'Windowed RocketSim camera',
            'Uses an optional pywebview window (Edge WebView2 on Windows), not a browser tab. '
            'C toggles ball cam, Tab switches cars, H hides camera controls. '
            'The viewer is a simplified physics rendering, not Rocket League assets.')
        self.view_model=tk.StringVar(value='Cycle 9');self.view_opponent=tk.StringVar(value='nexto')
        row=ttk.Frame(p);row.pack(fill='x',pady=(10,5))
        ttk.Combobox(row,textvariable=self.view_model,values=['Cycle 9','Champion','Verified best'],
                     state='readonly',width=16).pack(side='left',padx=(0,12))
        ttk.Combobox(row,textvariable=self.view_opponent,values=['nexto','self','champion'],
                     state='readonly',width=13).pack(side='left',padx=(0,12))
        self._line_buttons(p,[('Launch viewer in window',self.launch_viewer),
                             ('Stop viewer',self.stop_viewer),
                             ('Install window viewer support',self.install_webview)])
        p=self._section(self.viewer,'RLBot export',
            'Existing v4 exporter included in your project. RLBot v5 requires a separately validated adapter.')
        self.rl_checkpoint=tk.StringVar(value=str(ROOT/'data'/'autoleague'/'backups'/
                         '20261008T224518_775472Z_cycle0009_steps000008192_candidate.pt'))
        row=ttk.Frame(p);row.pack(fill='x',pady=6)
        ttk.Label(row,text='Checkpoint').pack(side='left',padx=(0,8))
        ttk.Entry(row,textvariable=self.rl_checkpoint,width=83).pack(side='left',padx=(0,8))
        ttk.Button(row,text='Browse…',command=self.pick_rl_checkpoint).pack(side='left')
        ttk.Button(row,text='Native folder…',command=self.pick_native_rl_checkpoint).pack(side='left')
        self.rl_scripted_kickoff=tk.BooleanVar(value=True)
        ttk.Checkbutton(p,text='Scripted Nexto kickoff (ON by default)',
                        variable=self.rl_scripted_kickoff).pack(anchor='w',pady=4)
        self._line_buttons(p,[('Export selected model to RLBot v4',self.export_rlbot),
                             ('Export original Nexto',lambda:self.export_rlbot(original=True)),
                             ('Open exports',lambda:self.open_folder(ROOT/'data'/'rlbot_exports'))])
        p=self._section(self.viewer,'C++ / GigaLearn research',
            'Separate GigaLearn_Project/ folder contains C++ build bootstrap and an independent training workspace. '
            'Native Nexto .pt checkpoints are NOT directly loadable by the upstream C++ policy.')
        self._line_buttons(p,[('Open GigaLearn project',lambda:self.open_folder(ROOT/'GigaLearn_Project')),('Read migration plan',lambda:self.open_file(ROOT/'AFK_IMPROVED_GIGALEARN.md'))])

    def _make_logs(self):
        p=self._section(self.logs,'Process output',
            'Live logs are shown here while the desktop app runs. Training also writes a persistent runner.log.')
        bar=self._line_buttons(p,[('Open runner.log',lambda:self.open_file(core.DATA/'runner.log')),
                                  ('Open evaluation reports',lambda:self.open_folder(core.DATA/'reports'))])
        txtframe=ttk.Frame(self.logs,padding=(16,4));txtframe.pack(fill='both',expand=True)
        self.output=tk.Text(txtframe,background='#0d1420',foreground='#cfe7e0',insertbackground='#fff',
                            font=('Consolas',10),wrap='word',state='disabled')
        self.output.pack(fill='both',expand=True)

    def log(self,msg):
        self.output.configure(state='normal');self.output.insert('end',str(msg).rstrip()+'\n')
        if float(self.output.index('end-1c').split('.')[0])>3500:self.output.delete('1.0','500.0')
        self.output.see('end');self.output.configure(state='disabled')

    def _spawn(self,name,args,env=None,category=None,show_logs=True):
        category=category or name
        existing=self.jobs.get(category)
        if existing and existing.poll() is None:
            messagebox.showwarning('Already running',f'{category} is already running.');return False
        if args[1] not in ('-m','/c') and not Path(args[1]).is_file():
            messagebox.showerror('Missing script',str(args[1]));return False
        kwargs={'cwd':ROOT,'stdout':subprocess.PIPE,'stderr':subprocess.STDOUT,
                'stdin':subprocess.DEVNULL,'env':env or os.environ.copy(),
                'text':True,'encoding':'utf-8','errors':'replace','bufsize':1}
        if os.name=='nt':kwargs['creationflags']=subprocess.CREATE_NO_WINDOW
        try:job=subprocess.Popen(args,**kwargs)
        except Exception as exc:messagebox.showerror('Launch failed',str(exc));return False
        self.jobs[category]=job
        self.log(f'\n==== {name} [{category}] · {datetime.now().strftime("%H:%M:%S")} ====')
        if show_logs:self.tabs.select(self.logs)
        def read():
            for line in job.stdout:self.queue.put(('log',f'[{category}] {line}'))
            self.queue.put(('exit',name,category,job.wait()))
        threading.Thread(target=read,daemon=True).start()
        return True

    def run_preflight(self):
        self._spawn('Preflight',[str(PYTHON),str(ROOT/'afk_improved_runner.py'),'--check'],category='preflight')

    def run_sim_preflight(self):
        self._spawn('RocketSim preflight',[str(PYTHON),str(ROOT/'auto_league.py'),
                    '--source',str(core.CYCLE9),'--data-dir',str(core.LEAGUE),
                    '--preflight','--no-replays'],category='preflight')

    def check_files(self):
        try:
            hashes=core.verify_starting_files()
            messagebox.showinfo('Verified','Protected files verified:\n'+ '\n'.join(f'{Path(k).name}: {v[:16]}' for k,v in hashes.items()))
        except Exception as exc:messagebox.showerror('Preflight failed',str(exc))

    def start_training(self):
        try:
            cycles=int(self.cycles.get());hours=float(self.hours.get());eval_games=int(self.eval_games.get());segment=int(self.segment.get())
            if not (0<=cycles<=100000 and 0<=hours<=168 and 20<=eval_games<=2000 and 96<=segment<=65536):
                raise ValueError('Hours: 0–168 (0=unlimited); cycles: 0–100000; eval games: 20–2000; steps: 96–65536')
        except Exception as exc:messagebox.showerror('Invalid values',str(exc));return
        try: validate_device(self.device.get(),self.devices)
        except ValueError as exc:messagebox.showerror('Device unavailable',str(exc));return
        if not messagebox.askyesno('Start protected training','Start/resume Cycle 9 training in data/afk_improved/league?\nMain champion is never written.'):return
        cmd=[str(PYTHON),str(ROOT/'afk_improved_runner.py'),'--cycles',str(cycles),'--hours',str(hours),
             '--eval-games',str(eval_games),'--segment-decisions',str(segment),'--device',self.device.get()]
        self._spawn('AFK training',cmd,category='training')

    def pause_training(self):
        core.DATA.mkdir(parents=True,exist_ok=True)
        core.STOP_REQUEST.write_text('pause after current cycle\n',encoding='utf-8')
        self.log('Safe pause requested. Do not force-close until cycle finishes.')
        self.footer.set('Pause requested — training finishes its current saved cycle first')

    def backup_files(self):
        try:out=core.checkpoint_snapshot();messagebox.showinfo('Backup created',str(out));self.refresh_models()
        except Exception as exc:messagebox.showerror('Backup failed',str(exc))

    def refresh_all(self):
        raw=core.read_json(core.STATUS,{}) or {};phase=raw.get('phase','not started')
        league=core.read_json(core.LEAGUE/'league_state.json',{}) or {}
        best=core.read_json(core.BEST_STATE,{}) or {}
        bestsha=best.get('sha256','not saved')
        disk='unknown'
        try:
            import shutil
            disk=f'{shutil.disk_usage(ROOT).free/1024**3:.1f} GB free'
        except OSError:pass
        summary=f'Runner: {phase}\nExperimental league cycle: {league.get("cycle", "not initialized")}    Promotions: {league.get("promotions",0)}\nVerified best: {bestsha[:16]}    ({best.get("status","not initialized")})\nDisk: {disk}\nLast update: {raw.get("updated_utc","not started")}'
        self.state_text.set(summary);self.traininfo.set(summary)
        if hasattr(self,'learning_info'):
            lreport=core.read_json(core.DATA/'learning'/'training_report.json',{}) or {}
            lmanifest=core.read_json(core.DATA/'learning'/'dataset_manifest.json',{}) or {}
            self.learning_info.set(f'Dataset: {lmanifest.get("frames",0)} samples from {lmanifest.get("unique_replays",0)} replays; '
                f'candidate epoch: {lreport.get("best_epoch",0)}; '
                f'competition verified: {lreport.get("competition_verified",False)}; '
                f'candidate exists: {(core.DATA/"learning"/"replay_candidate.pt").exists()}')
        self.refresh_models()

    def refresh_models(self):
        self.models=core.inventory()
        self.tree.delete(*self.tree.get_children())
        for i,obj in enumerate(self.models):self.tree.insert('', 'end', iid=str(i),values=(obj['path'],f'{obj["bytes"]/1048576:.1f}',obj['modified']))

    def _selected(self):
        s=self.tree.selection()
        if not s:messagebox.showinfo('Select checkpoint','Click a model in the list first.');return None
        return self.models[int(s[0])]['path']

    def show_model_hash(self):
        selected=self._selected()
        if selected is not None:
            try:messagebox.showinfo('Checkpoint SHA256',selected+'\n\n'+core.hash_file(ROOT/selected))
            except Exception as e:messagebox.showerror('Error',str(e))

    def copy_model(self):
        selected=self._selected()
        if selected:
            try:path=core.safe_copy_selected(selected);messagebox.showinfo('Copy verified',str(path));self.refresh_models()
            except Exception as exc:messagebox.showerror('Copy failed',str(exc))

    def eval_model(self):
        selected=self._selected()
        if selected:
            self._spawn('Read-only vs Nexto',[str(PYTHON),str(ROOT/'native_nexto.py'),'--mode','eval',
                                              '--checkpoint',str(ROOT/selected),'--games','40','--eval-decisions','750','--device','cpu'],category='evaluation')

    def replay_download(self,list_only,refresh=False):
        try:
            count=int(self.maxreplays.get());assert 1<=count<=1000
        except Exception:messagebox.showerror('Invalid count','Choose 1..1000 new files');return
        token=os.environ.get('BALLCHASING_TOKEN','').strip()
        if not token:token=simpledialog.askstring('Ballchasing API token','Token is not saved or displayed:',show='*',parent=self)
        if not token:return
        env=os.environ.copy();env['BALLCHASING_TOKEN']=token
        args=[str(PYTHON),str(ROOT/'download_ballchasing.py'),'--playlist','ranked-duels',
              '--rank',self.rank.get(),'--max-files',str(count),
              '--after',self.afterdate.get(),'--before',self.beforedate.get()]
        if list_only:args.append('--list-only')
        if refresh:args.append('--refresh-search')
        args += ['--workers',self.replay_workers.get(),'--pause-file',str(core.DATA/'replay.pause')]
        if not list_only and not (self.jobs.get('replay') and self.jobs['replay'].poll() is None):
            (core.DATA/'replay.pause').unlink(missing_ok=True)
        self._spawn('Replay API '+('preview' if list_only else 'download'),args,env=env,category='replay')

    def pause_replays(self):
        core.DATA.mkdir(parents=True,exist_ok=True)
        (core.DATA/'replay.pause').write_text('pause at next completed replay batch',encoding='utf-8')
        self.log('Replay pause requested. In-flight downloads will finish safely.')

    def audit_replays(self):
        self._spawn('Replay catalog',[str(PYTHON),str(ROOT/'afk_replay_audit.py')],category='audit')

    def launch_viewer(self):
        if self.camera and self.camera.poll() is None:
            messagebox.showinfo('Viewer','Viewer is already open');return
        checkpoint={'Cycle 9':core.CYCLE9,'Champion':core.MAIN_CHAMPION,'Verified best':core.BEST}[self.view_model.get()]
        if not checkpoint.is_file():messagebox.showerror('Missing model',str(checkpoint));return
        try:
            viewer_kwargs={'cwd':ROOT}
            if os.name=='nt':viewer_kwargs['creationflags']=subprocess.CREATE_NO_WINDOW
            self.camera=subprocess.Popen([str(PYTHON),str(ROOT/'rl_camera_server.py'),'--window',
                         '--checkpoint',str(checkpoint),'--opponent',self.view_opponent.get()],**viewer_kwargs)
            self.footer.set('Viewer launched in a separate window')
        except Exception as ex:messagebox.showerror('Viewer failed',str(ex))

    def stop_viewer(self):
        if self.camera and self.camera.poll() is None:
            self.camera.terminate();self.camera=None
            self.footer.set('Viewer stopped')

    def install_webview(self):
        if messagebox.askyesno('Install optional viewer','Install pywebview into project virtual environment?\nRequires internet; no changes to your models.'):
            self._spawn('Install pywebview',[str(PYTHON),'-m','pip','install','pywebview'])

    def pick_rl_checkpoint(self):
        name=filedialog.askopenfilename(parent=self,title='Choose native Nexto actor .pt checkpoint',
            initialdir=str(ROOT/'data'),filetypes=[('PyTorch native checkpoints','*.pt'),('All files','*.*')])
        if name:self.rl_checkpoint.set(name)

    def pick_native_rl_checkpoint(self):
        name=filedialog.askdirectory(parent=self,title='Select numbered native checkpoint folder (contains POLICY.lt)',
            initialdir=str(ROOT/'data'/'isolated'/'gigalearn_native'/'runs'))
        if name:self.rl_checkpoint.set(name)

    def export_rlbot(self,original=False):
        path=None if original else Path(self.rl_checkpoint.get())
        if path is not None and not path.exists():messagebox.showerror('Missing checkpoint',str(path));return
        name=simpledialog.askstring('RLBot v4 export name','Unique export folder name (letters/numbers/_/-):',
                    initialvalue=('Original_Nexto' if original else path.stem[:38]),parent=self)
        if not name:return
        import re
        if not re.fullmatch('[A-Za-z0-9][A-Za-z0-9_-]{0,59}',name):
            messagebox.showerror('Invalid name','Letters/digits/_/- only, maximum 60 characters');return
        if not messagebox.askyesno('Export separate RLBot v4 bot',
                f'Copy {"original Nexto" if original else str(path)} into an isolated RLBot v4 bot named {name}?\n'
                f'Scripted kickoff: {"ON" if self.rl_scripted_kickoff.get() else "OFF"}.\n'
                'No existing exports or checkpoints are overwritten.'):
            return
        args=[str(PYTHON),str(ROOT/'export_rlbot_v4.py'),'--name',name]
        if self.rl_scripted_kickoff.get():args.append('--scripted-kickoff')
        args+=['--original'] if original else ['--checkpoint',str(path)]
        self._spawn('RLBot v4 export',args,category='export')

    def open_folder(self,p):
        p=Path(p);p.mkdir(parents=True,exist_ok=True)
        if os.name=='nt':os.startfile(p)
        else:messagebox.showinfo('Path',str(p))

    def open_file(self,p):
        p=Path(p)
        if not p.exists():messagebox.showinfo('Not created yet',str(p));return
        if os.name=='nt':os.startfile(p)
        else:messagebox.showinfo('Path',str(p))

    def _poll(self):
        for _ in range(100):
            try:entry=self.queue.get_nowait()
            except queue.Empty:break
            if entry[0]=='log':self.log(entry[1])
            if entry[0]=='exit':
                _,name,category,code=entry
                self.log(f'==== {name} [{category}] exited, code {code} ====')
                self.footer.set(f'{name} finished with exit code {code}')
                self.jobs.pop(category,None);self.refresh_all()
        # Refresh current status every ~3.5 seconds without scanning thousands of files
        if not hasattr(self,'_ticks'):self._ticks=0
        self._ticks+=1
        if self._ticks%10==0:
            st=core.read_json(core.STATUS,{}) or {}
            self.traininfo.set(f'Phase: {st.get("phase","not started")}; last completed cycle: {st.get("completed_cycle","—")}; updated {st.get("updated_utc","—")}')
        self.after(350,self._poll)

    def _close(self):
        active=[k for k,v in self.jobs.items() if v.poll() is None]
        if active:
            messagebox.showwarning('Processes running','Still running: '+', '.join(active)+'.\nPause training/downloads and wait until they exit before closing.')
            return
        self.stop_viewer();self.destroy()

if __name__=='__main__':ControlCenter().mainloop()
