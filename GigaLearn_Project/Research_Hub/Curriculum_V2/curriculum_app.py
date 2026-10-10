"""Tk desktop front-end for guarded multi-stage GigaLearn research."""
import json,subprocess,sys,threading,queue,pathlib,tkinter as tk
from tkinter import ttk, filedialog,messagebox
import curriculum_core as core

ROOT=pathlib.Path(__file__).resolve().parent
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('GigaLearn · Curriculum Control v1 (research)')
        self.geometry('1040x720');self.configure(bg='#131b28')
        self.q=queue.Queue();self.busy=False
        style=ttk.Style(self);style.theme_use('clam');style.configure('TFrame',background='#131b28')
        style.configure('TLabel',background='#131b28',foreground='#eef2f7',font=('Segoe UI',10))
        style.configure('TButton',padding=9,font=('Segoe UI',10))
        style.configure('Treeview',rowheight=32,background='#182335',fieldbackground='#182335',foreground='#eff2f7')
        style.configure('Treeview.Heading',background='#33455c',foreground='white')
        wrap=ttk.Frame(self,padding=18);wrap.pack(fill='both',expand=True)
        ttk.Label(wrap,text='GIGALEARN / CURRICULUM CONTROL',font=('Segoe UI',21,'bold')).pack(anchor='w')
        ttk.Label(wrap,text='Replays → Verified TAS → Nexto/Cycle9/Wavedash → Mechanics → Multiplayer → Heldout gates',font=('Segoe UI',10)).pack(anchor='w',pady=(4,12))
        self.tabs=ttk.Notebook(wrap);self.tabs.pack(fill='both',expand=True)
        self.overview=ttk.Frame(self.tabs,padding=12);self.pipeline=ttk.Frame(self.tabs,padding=12);self.logging=ttk.Frame(self.tabs,padding=12)
        for tab,name in ((self.overview,'Readiness'),(self.pipeline,'Replay / TAS'),(self.logging,'Activity')):self.tabs.add(tab,text=name)
        self.tree=ttk.Treeview(self.overview,columns=('stage','status','description'),show='headings',height=6)
        for col,width in [('stage',200),('status',100),('description',635)]:self.tree.heading(col,text=col.title());self.tree.column(col,width=width)
        self.tree.pack(fill='x')
        for st in core.stage_states():self.tree.insert('','end',values=(st['name'],st['status'],st['description']))
        btns=ttk.Frame(self.overview);btns.pack(fill='x',pady=12)
        ttk.Button(btns,text='Check project',command=lambda:self.schedule(['check'])).pack(side='left',padx=4)
        ttk.Button(btns,text='Show stage gates',command=lambda:self.schedule(['stages'])).pack(side='left',padx=4)
        ttk.Button(btns,text='Verify all-stage readiness',command=lambda:self.schedule(['run-all'])).pack(side='left',padx=4)
        ttk.Label(self.overview,text='Blocked stages remain blocked until matching teacher/TAS adapters are validated.\nThis tool never promotes checkpoints automatically.').pack(anchor='w',pady=12)
        self.replays=tk.StringVar(value=str(core.PARENT/'data/replays'))
        self.dataset=tk.StringVar(value='')
        self.tas=tk.StringVar(value=str(core.PARENT/'data/tas'))
        self.seed=tk.StringVar(value='')
        self.epochs=tk.StringVar(value='4')
        self.checkpoint=tk.StringVar(value='')
        self.branch_name=tk.StringVar(value='replay_foundation_01')
        for row,(text,var,action) in enumerate((('Human .replay folder',self.replays,self.choose_replays),('Extracted dataset folder',self.dataset,self.choose_dataset),('TAS .data folder',self.tas,self.choose_tas),('Optional 1v1 GigaLearn checkpoint seed',self.seed,self.choose_seed))):
            ttk.Label(self.pipeline,text=text).grid(row=row,column=0,sticky='w',padx=4,pady=7)
            ttk.Entry(self.pipeline,textvariable=var,width=68).grid(row=row,column=1,sticky='ew',padx=4)
            ttk.Button(self.pipeline,text='Browse',command=action).grid(row=row,column=2,padx=4)
        self.pipeline.columnconfigure(1,weight=1)
        ttk.Label(self.pipeline,text='Replay BC epochs').grid(row=4,column=0,sticky='w',pady=10)
        ttk.Entry(self.pipeline,textvariable=self.epochs,width=8).grid(row=4,column=1,sticky='w')
        actions=ttk.Frame(self.pipeline);actions.grid(row=5,column=0,columnspan=3,sticky='w',pady=14)
        ttk.Button(actions,text='1  Extract replay examples',command=self.extract).pack(side='left',padx=4)
        ttk.Button(actions,text='2  Audit TAS (no training)',command=self.audit).pack(side='left',padx=4)
        ttk.Button(actions,text='3  Train replay BC policy',command=self.train).pack(side='left',padx=4)
        ttk.Button(actions,text='Open Research Hub for PPO',command=self.open_hub).pack(side='left',padx=4)
        ttk.Label(self.pipeline,text='Successful replay-trained GigaLearn checkpoint').grid(row=7,column=0,sticky='w',pady=7)
        ttk.Entry(self.pipeline,textvariable=self.checkpoint,width=68).grid(row=7,column=1,sticky='ew')
        ttk.Button(self.pipeline,text='Browse',command=self.choose_checkpoint).grid(row=7,column=2)
        ttk.Label(self.pipeline,text='New Research Hub experiment name').grid(row=8,column=0,sticky='w',pady=7)
        ttk.Entry(self.pipeline,textvariable=self.branch_name,width=40).grid(row=8,column=1,sticky='w')
        ttk.Button(self.pipeline,text='4  Create isolated 1v1 branch',command=self.branch).grid(row=9,column=0,columnspan=2,sticky='w',pady=7)
        ttk.Label(self.pipeline,text='Replay training uses reconstructed human actions; TAS requires verified per-frame states.\nNexto/Cycle9/Wavedash opponent bridge is not yet compatible with this C++ policy.\nNew .lt checkpoints are isolated; create a new Research Hub 1v1 experiment from them after evaluation.',font=('Segoe UI',10)).grid(row=6,column=0,columnspan=3,sticky='w',pady=15)
        self.log=tk.Text(self.logging,background='#0b1220',foreground='#d9e8ff',insertbackground='white',font=('Consolas',10),wrap='word')
        self.log.pack(fill='both',expand=True)
        self.after(120,self.poll)
    def choose_replays(self):self.replays.set(filedialog.askdirectory(initialdir=self.replays.get()) or self.replays.get())
    def choose_dataset(self):self.dataset.set(filedialog.askdirectory() or self.dataset.get())
    def choose_tas(self):self.tas.set(filedialog.askdirectory() or self.tas.get())
    def choose_seed(self):self.seed.set(filedialog.askdirectory() or self.seed.get())
    def choose_checkpoint(self):self.checkpoint.set(filedialog.askdirectory() or self.checkpoint.get())
    def branch(self):
        if not self.checkpoint.get():messagebox.showerror('Missing checkpoint','Select a numbered replay BC checkpoint directory.');return
        self.schedule(['branch-to-hub','--checkpoint',self.checkpoint.get(),'--name',self.branch_name.get()])
    def note(self,text):self.q.put(text+'\n')
    def schedule(self,args):
        if self.busy:messagebox.showwarning('Busy','Another operation is running.');return
        self.busy=True;self.tabs.select(self.logging)
        def worker():
            self.note('COMMAND: '+repr(args))
            cmdpy=sys.executable
            if args and args[0]=='extract-replays':
                # Prefer the repaired project environment for rlgym-tools;
                # the standalone GUI interpreter may not contain replay parsers.
                venv=core.PARENT/'.venv/Scripts/python.exe'
                if venv.is_file() and venv.stat().st_size>0:
                    try:
                        q=subprocess.run([str(venv),'-c','import rlgym_tools'],
                            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=12)
                        if q.returncode==0:cmdpy=str(venv)
                    except (OSError,subprocess.SubprocessError):pass
            cmd=[str(cmdpy),str(ROOT/'curriculum_cli.py')]+args
            try:
                proc=subprocess.Popen(cmd,cwd=ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,encoding='utf8',errors='replace')
                for line in proc.stdout:self.q.put(line)
                code=proc.wait();self.note('EXIT CODE: '+str(code))
            except Exception as ex:self.note('FAILED: '+str(ex))
            self.q.put('__DONE__')
        threading.Thread(target=worker,daemon=True).start()
    def poll(self):
        try:
            while True:
                entry=self.q.get_nowait()
                if entry=='__DONE__':self.busy=False
                else:self.log.insert('end',entry);self.log.see('end')
        except queue.Empty:pass
        self.after(120,self.poll)
    def extract(self):
        output=ROOT/'run_data'/core.new_id();self.dataset.set(str(output))
        self.schedule(['extract-replays','--input',self.replays.get(),'--output',str(output)])
    def audit(self):self.schedule(['audit-tas','--input',self.tas.get(),'--output',str(ROOT/'results'/('tas_audit_'+core.new_id()+'.json'))])
    def train(self):
        if not self.dataset.get():messagebox.showerror('Missing dataset','Extract replay examples first.');return
        try:epochs=int(self.epochs.get())
        except ValueError:messagebox.showerror('Invalid epochs','Enter a whole number.');return
        cmd=['train-replays','--dataset',self.dataset.get(),'--epochs',str(epochs)]
        if self.seed.get():cmd+=['--seed-checkpoint',self.seed.get()]
        self.schedule(cmd)
    def open_hub(self):
        import subprocess
        py=core.PARENT/'.venv/Scripts/python.exe'
        if not py.is_file() or py.stat().st_size==0:py=pathlib.Path(sys.executable)
        app=core.HUB/'hub_app.py'
        if not app.is_file():messagebox.showerror('Missing Hub','hub_app.py missing');return
        subprocess.Popen([str(py),str(app)],cwd=core.HUB)
if __name__=='__main__':App().mainloop()
