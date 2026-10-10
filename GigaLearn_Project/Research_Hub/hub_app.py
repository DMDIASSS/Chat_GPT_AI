"""GigaLearn Research Hub — dark, dependency-free Tkinter control app.
Controls a *separate* GigaLearn C++ research workspace. This app is NOT an RLBot exporter.
"""
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
from hub_core import (HERE,PROJECT,PARENT,PRESETS,exp_path,read_json,check_runtime,new_experiment,
 list_experiments,make_plan,start_experiment,request_safe_stop,replay_tas_audit,HubError)
from hub_tournament import save_schedule,standings_from_csv
from hub_experiment_management import (rename_experiment, archive_experiment, list_trashed_experiments, restore_trashed_experiment, trash_folder)

BG='#111923'; PANEL='#1b2735'; FG='#eaf1fa'; MUTED='#a7b6ca'; PRIMARY='#4c93ed'; BORDER='#34475b'; FIELD='#233448'

class App:
 def __init__(self,root):
    self.root=root;root.title('GigaLearn Research Hub v1.0  ·  isolated C++ research')
    root.geometry('1190x765');root.minsize(950,650);root.configure(bg=BG)
    st=ttk.Style(root);st.theme_use('clam')
    st.configure('TFrame',background=BG);st.configure('TLabel',background=BG,foreground=FG,font=('Segoe UI',10))
    st.configure('Muted.TLabel',background=BG,foreground=MUTED,font=('Segoe UI',9))
    st.configure('TNotebook',background=BG,borderwidth=0);st.configure('TNotebook.Tab',background=PANEL,foreground=FG,padding=(13,9),font=('Segoe UI',10))
    st.map('TNotebook.Tab',background=[('selected',FIELD)],foreground=[('selected','#ffffff')])
    st.configure('TButton',background=FIELD,foreground=FG,padding=(11,7),borderwidth=1,font=('Segoe UI',10))
    st.map('TButton',background=[('active',PRIMARY)])
    st.configure('TEntry',foreground=FG,fieldbackground=FIELD,background=FIELD,insertcolor='white',borderwidth=1)
    st.configure('TCombobox',foreground=FG,fieldbackground=FIELD,background=FIELD,arrowcolor='white',selectforeground='white',selectbackground=FIELD)
    st.map('TCombobox',fieldbackground=[('readonly',FIELD)],foreground=[('readonly',FG)])
    st.configure('Treeview',background=PANEL,fieldbackground=PANEL,foreground=FG,rowheight=27,bordercolor=BORDER)
    st.configure('Treeview.Heading',background=FIELD,foreground=FG,font=('Segoe UI',10,'bold'))
    self.q=queue.Queue()
    self.title=tk.Label(root,text='GIGALEARN  /  RESEARCH HUB',bg=BG,fg=FG,font=('Segoe UI',22,'bold'))
    self.title.pack(anchor='w',padx=22,pady=(18,2))
    tk.Label(root,text='GigaLearn PPO variants · checkpoint-safe experiments · AFK/Nexto originals untouched',bg=BG,fg=MUTED,font=('Segoe UI',10)).pack(anchor='w',padx=24,pady=(0,13))
    self.tabs=ttk.Notebook(root);self.tabs.pack(fill='both',expand=True,padx=18,pady=(0,10))
    self.pages={}
    for name in ['Overview','Experiments','Evolution League','Replay + TAS','AFK Bridge','Logs']:
       frame=ttk.Frame(self.tabs);self.pages[name]=frame;self.tabs.add(frame,text=name)
    self.status=tk.StringVar(value='Idle — models and projects protected')
    tk.Label(root,textvariable=self.status,bg=BG,fg=MUTED,anchor='w',font=('Segoe UI',9)).pack(fill='x',padx=22,pady=(0,10))
    self.create_overview();self.create_experiments();self.create_evolution();self.create_replays();self.create_bridge();self.create_logs()
    from hub_eval_ui import install_evaluation_tab
    install_evaluation_tab(self)
    self.refresh();self.root.after(200,self.poll);self.root.after(15000,self.periodic_refresh)

 def text(self,parent,heading,description):
    tk.Label(parent,text=heading,bg=BG,fg=FG,font=('Segoe UI',16,'bold')).pack(anchor='w',padx=18,pady=(16,7))
    tk.Label(parent,text=description,bg=BG,fg=MUTED,font=('Segoe UI',10),justify='left',wraplength=950).pack(anchor='w',padx=19,pady=(0,10))
 def field(self,parent,label,var,width=24):
    ttk.Label(parent,text=label).pack(side='left',padx=(12,4));e=ttk.Entry(parent,textvariable=var,width=width);e.pack(side='left',padx=(0,10));return e
 def button(self,parent,title,cmd):
    b=ttk.Button(parent,text=title,command=cmd);b.pack(side='left',padx=(8,3),pady=6);return b
 def notify(self,msg):self.status.set(msg);self.write_log(msg)
 def write_log(self,msg):
    if hasattr(self,'log'):
       self.log.configure(state='normal');self.log.insert('end',msg+'\n');self.log.see('end');self.log.configure(state='disabled')
 def execute(self,fn):
    def worker():
       try:self.q.put(('ok',fn()))
       except Exception as e:self.q.put(('err',str(e)))
    threading.Thread(target=worker,daemon=True).start()
 def poll(self):
    try:
       while True:
          kind,value=self.q.get_nowait()
          if kind=='ok':self.notify('Complete: '+str(value)[:300]);self.refresh()
          else:self.notify('ERROR: '+value);messagebox.showerror('Research Hub',value)
    except queue.Empty:pass
    self.root.after(300,self.poll)

 def periodic_refresh(self):
    try:self.refresh()
    except Exception as e:self.notify('Refresh warning: '+str(e))
    self.root.after(15000,self.periodic_refresh)

 def create_overview(self):
    p=self.pages['Overview'];self.text(p,'System readiness','Your existing Python 3.11 GigaLearn build is the foundation. Patch and rebuild it once to enable research stages and safe stops.')
    r=ttk.Frame(p);r.pack(fill='x',padx=14,pady=8)
    self.button(r,'Refresh system status',self.refresh)
    self.button(r,'Patch C++ research trainer',lambda:self.execute(self.patch))
    self.button(r,'Build patched C++',lambda:self.execute(self.build))
    self.over=tk.Text(p,wrap='word',height=21,bg=PANEL,fg=FG,insertbackground=FG,relief='flat',padx=14,pady=12,font=('Consolas',10));self.over.pack(fill='both',expand=True,padx=18,pady=7)
    tk.Label(p,text='Patching changes only GigaLearn_Project/upstream C++ source, with backups. Building still needs your MSVC x64 developer environment.',bg=BG,fg=MUTED).pack(anchor='w',padx=19,pady=6)

 def create_experiments(self):
    p=self.pages['Experiments'];self.text(p,'Train isolated policy variants','A C++ experiment has its own working directory and numeric GigaLearn checkpoints. Use safe stop before closing the app.')
    top=ttk.Frame(p);top.pack(fill='x',padx=15)
    self.expname=tk.StringVar(value='defense_1v2_trial_01');self.field(top,'Experiment name',self.expname,27)
    self.preset=tk.StringVar(value='Defense Under Pressure 1v2')
    ttk.Label(top,text='Preset').pack(side='left',padx=(9,4))
    ttk.Combobox(top,textvariable=self.preset,values=list(PRESETS),width=27,state='readonly').pack(side='left')
    r=ttk.Frame(p);r.pack(fill='x',padx=14)
    self.seed=tk.StringVar();self.field(r,'Optional seed checkpoint directory',self.seed,64)
    self.button(r,'Browse',self.pick_seed)
    self.button(r,'Create experiment',self.create_exp)
    r=ttk.Frame(p);r.pack(fill='x',padx=14,pady=(6,1))
    self.button(r,'Start selected',self.run_exp);self.button(r,'Request safe save + stop',self.stop_exp)
    self.button(r,'Refresh experiments',self.refresh)
    self.button(r,'View selected C++ log',self.show_exp_log)
    self.button(r,'Rename selected',self.rename_exp)
    self.button(r,'Delete selected',self.delete_exp)
    self.button(r,'Restore from Trash',self.restore_exp)
    self.tree=ttk.Treeview(p,columns=('name','preset','status','checkpoints','latest','speed'),show='headings',height=13)
    for col,w in [('name',210),('preset',225),('status',130),('checkpoints',110),('latest',135),('speed',110)]:self.tree.heading(col,text=col.title());self.tree.column(col,width=w,anchor='w')
    self.tree.pack(fill='both',expand=True,padx=18,pady=10)
    ttk.Label(p,text='Delete moves experiments to recoverable Trash. Rename/Delete are disabled for live or pending-safe-stop runs.').pack(anchor='w',padx=18,pady=5)

 def rename_exp(self):
    try:name=self.selected()
    except Exception as e:messagebox.showwarning('Select experiment',str(e));return
    value=simpledialog.askstring('Rename experiment','New experiment name:',initialvalue=name,parent=self.root)
    if value is None:return
    if not value.strip():messagebox.showwarning('Invalid name','Enter a nonempty experiment name.');return
    from hub_core import slug
    try:actual=slug(value.strip())
    except Exception as e:messagebox.showerror('Invalid name',str(e));return
    if not messagebox.askyesno('Confirm rename',f'Rename {name} to {actual}?\n\nAll checkpoints remain intact. Existing external references to the old path may need updating.'):
       return
    self.execute(lambda: 'Renamed '+name+' to '+rename_experiment(name,value))

 def delete_exp(self):
    try:name=self.selected()
    except Exception as e:messagebox.showwarning('Select experiment',str(e));return
    if not messagebox.askyesno('Move experiment to Trash',f'Move {name} and ALL its checkpoints into the recoverable Research Hub Trash?\n\nYou can restore it later. Running experiments cannot be moved.',icon='warning'):
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
    prompt='Choose an archive to restore by entering its NUMBER:\n\n'+'\n'.join(f'{i+1}. {a["name"]} — {a["archived_utc"]}' for i,a in enumerate(items[:20]))
    num=simpledialog.askinteger('Restore experiment',prompt,parent=self.root,minvalue=1,maxvalue=min(20,len(items)))
    if num is None:return
    item=items[num-1]
    if not messagebox.askyesno('Confirm restore',f'Restore {item["name"]} from Trash?\nExisting experiments will never be overwritten.'):
       return
    self.execute(lambda: 'Restored '+restore_trashed_experiment(item['archive_id']))

 def create_evolution(self):
    p=self.pages['Evolution League'];self.text(p,'Evolution League','Plan 6–24 small experiments. Tournament brackets are real CSV schedules; match results must be measured, never fabricated.')
    r=ttk.Frame(p);r.pack(fill='x',padx=14)
    self.variants=tk.StringVar(value='12');self.field(r,'Number of variants',self.variants,6)
    self.button(r,'Generate plan',self.plan);self.button(r,'Create planned branches',self.materialize)
    self.button(r,'Create tournament schedule',self.schedule)
    self.button(r,'Read results CSV',self.read_scores)
    self.evo=tk.Text(p,bg=PANEL,fg=FG,font=('Consolas',10),wrap='word',height=22,relief='flat',padx=12,pady=10)
    self.evo.pack(fill='both',expand=True,padx=18,pady=8)
    self.evo.insert('end','1. Generate a reproducible 12-variant plan.\n2. Create independent branches, optionally from a complete GigaLearn checkpoint.\n3. Train branches and request safe stop.\n4. Export/report actual match results through a verified GigaLearn evaluator (still to be built).\n5. Record results, retain diverse winners, test finalists against fixed baselines.\n\nIMPORTANT: Automatic head-to-head GigaLearn and native Nexto model compatibility are NOT implemented. No automatic promotions.\n')

 def create_replays(self):
    p=self.pages['Replay + TAS'];self.text(p,'Human replay and TAS pipeline','The native AFK dataset exists but cannot be loaded directly into GigaLearn PPO. This page audits sources; training is correctly blocked until conversion is validated.')
    self.audit=tk.Text(p,bg=PANEL,fg=FG,font=('Consolas',10),wrap='word',height=20,relief='flat',padx=12,pady=10)
    self.audit.pack(fill='both',expand=True,padx=18,pady=10)
    r=ttk.Frame(p);r.pack(fill='x',padx=14)
    self.button(r,'Audit existing sources',self.audit_replays)
    self.button(r,'Open curriculum plan',lambda:self.open_path(HERE/'docs/CURRICULUM.md'))
    self.audit_replays()

 def create_bridge(self):
    p=self.pages['AFK Bridge'];self.text(p,'Cycle 9 and Wavedash: independent reference bots','These are native Nexto TorchScript .pt checkpoints. GigaLearn .lt training cannot resume or distill them without a compatible adapter. Keep AFK as a separate benchmark/teacher system.')
    self.bridge=tk.Text(p,bg=PANEL,fg=FG,font=('Consolas',10),wrap='word',height=16,relief='flat',padx=12,pady=10)
    self.bridge.pack(fill='both',expand=True,padx=18,pady=10)
    r=ttk.Frame(p);r.pack(fill='x',padx=14)
    self.button(r,'Launch AFK team preflight',lambda:self.legacy('TEAM_0_PREFLIGHT_1v2.bat'))
    self.button(r,'Open AFK model comparison',lambda:self.legacy('RESEARCH_5_EVAL.bat'))
    self.button(r,'AFK model tournament',lambda:self.legacy('MODEL_TOURNAMENT_2_THOROUGH.bat'))
    self.button(r,'AFK Cycle9 RLBot v4 export',lambda:self.legacy('RLBOT_EXPORT_1_ORIGINAL_CYCLE9.bat'))
    self.button(r,'Open parent project',lambda:self.open_path(PARENT))

 def create_logs(self):
    p=self.pages['Logs'];self.text(p,'Research events','Short status messages are shown here. Per-experiment C++ training logs are in Research_Hub/experiments/<name>/reports/training.log')
    self.log=tk.Text(p,bg=PANEL,fg=FG,font=('Consolas',10),wrap='word',relief='flat',padx=13,pady=11,state='disabled')
    self.log.pack(fill='both',expand=True,padx=18,pady=8)

 def pick_seed(self):
    folder=filedialog.askdirectory(title='Select numeric GigaLearn checkpoint folder (e.g. checkpoints/4562496)')
    if folder:self.seed.set(folder)
 def selected(self):
    sel=self.tree.selection()
    if not sel:raise HubError('Select a row in Experiments first')
    return self.tree.item(sel[0],'values')[0]
 def patch(self):
    from hub_cpp_patch import patch
    return patch()
 def build(self):
    if sys.platform!='win32':raise HubError('Windows MSVC x64 developer terminal is required to compile C++')
    bat=HERE/'BUILD_IN_VS2022_DEV_PROMPT.bat'
    # Starts a visible terminal; user can read the true CMake error instead of a silent failure.
    subprocess.Popen(['cmd','/c','start','"Build GigaLearn C++"',str(bat)],cwd=str(PROJECT))
    return 'Build opened in new terminal; read the exit status there.'
 def refresh(self):
    c=check_runtime();lines=[f"Existing GigaLearn binary: {c['binary']}",f"Built binary exists: {c['binary_exists']}",f"Source: {c['source']}",f"Collision meshes: {c['meshes']}",f"Collision meshes exist: {c['meshes_exist']}",'','READ-ONLY AFK MODELS:']
    lines.extend([f"  {m['label']}: {'found' if m['exists'] else 'missing'} · SHA {m['sha256_prefix'] or 'n/a'}" for m in c['models']])
    lines+=['','NOT YET VALIDATED: C++ patched build; native Nexto policy transfer; automated GigaLearn match rankings; TAS direct cloning.','Research source edits require C++ rebuild.']
    self.over.delete('1.0','end');self.over.insert('1.0','\n'.join(lines))
    for t in self.tree.get_children():self.tree.delete(t)
    for m in list_experiments():
       self.tree.insert('', 'end',values=(m['name'],m.get('preset',''),m.get('status',''),m.get('checkpoints',''),m.get('latest',''),m.get('speed','')))
    self.bridge.delete('1.0','end');self.bridge.insert('end','\n'.join(lines[6:])+'\n\nRLBot v4 multi-model exports remain in the existing AFK app.\n')
 def create_exp(self):
    name=self.expname.get().strip();preset=self.preset.get();seed=self.seed.get().strip() or None
    self.execute(lambda:new_experiment(name,preset,seed))
 def run_exp(self):
    try:name=self.selected()
    except Exception as e:messagebox.showwarning('Select experiment',str(e));return
    if not messagebox.askyesno('Start C++ training',f'Start {name}?\n\nIts GigaLearn .lt checkpoints are isolated.\nUse Request Safe Stop before shutting down.'):return
    self.execute(lambda: f'{name} PID={start_experiment(name)}')
 def show_exp_log(self):
    try:
        name=self.selected()
        log=exp_path(name)/'reports/training.log'
        if not log.exists():raise HubError('No training log yet for '+name)
        with log.open('rb') as f:
            f.seek(max(0,log.stat().st_size-48000));raw=f.read()
        self.tabs.select(self.pages['Logs'])
        self.write_log('==== '+name+' ====\n'+raw.decode('utf8',errors='replace')[-40000:])
    except Exception as e:messagebox.showerror('Experiment log',str(e))
 def stop_exp(self):
    try:name=self.selected();self.notify('Safe stop file: '+str(request_safe_stop(name)))
    except Exception as e:messagebox.showerror('Safe stop',str(e))
 def plan(self):
    try:
       data=make_plan(self.seed.get().strip() or None,int(self.variants.get()))
       self.evo.delete('1.0','end');self.evo.insert('end',json.dumps(data,indent=2))
       self.notify(f'Planned {len(data)} branches; nothing trained or deleted')
    except Exception as e:messagebox.showerror('Plan',str(e))
 def materialize(self):
    if not messagebox.askyesno('Create research branches','Create non-overwriting directories for all planned variants?\nThis does not start training.'):return
    def action():
       data=make_plan(self.seed.get().strip() or None,int(self.variants.get()))
       return [str(new_experiment(a['name'],a['preset'],self.seed.get().strip() or None,a['settings'])) for a in data]
    self.execute(action)
 def schedule(self):
    models=[m['name'] for m in list_experiments()]
    if len(models)<2:messagebox.showinfo('Need models','Create at least two experiments first');return
    try:
       path=save_schedule(HERE/'reports/tournament_schedule.csv',models,3)
       self.notify('Tournament schedule created (no match results): '+str(path))
    except Exception as e:messagebox.showerror('Schedule',str(e))
 def read_scores(self):
    fname=filedialog.askopenfilename(title='Select completed results CSV',filetypes=[('CSV results','*.csv')])
    if not fname:return
    try:
       rows=standings_from_csv(fname)
       self.evo.delete('1.0','end');self.evo.insert('end',json.dumps(rows,indent=2))
    except Exception as e:messagebox.showerror('Results validation',str(e))
 def audit_replays(self):
    self.audit.delete('1.0','end');self.audit.insert('end',json.dumps(replay_tas_audit(),indent=2))
 def open_path(self,path):
    path=Path(path)
    if not path.exists():messagebox.showerror('Missing',str(path));return
    if os.name=='nt':os.startfile(str(path))
    else:subprocess.Popen(['xdg-open',str(path)])
 def legacy(self,filename):
    path=PARENT/filename
    if not path.is_file():messagebox.showerror('Missing legacy module','Not found: '+str(path));return
    if not messagebox.askyesno('External AFK module',filename+' runs outside GigaLearn and may run a long evaluation. Launch it?'):return
    if os.name=='nt':subprocess.Popen(['cmd','/c','start', '"AFK Legacy"',str(path)],cwd=PARENT)
    else:messagebox.showinfo('Windows only','This command requires Windows')

if __name__=='__main__':
    root=tk.Tk();App(root);root.mainloop()
