"""Select and watch real GigaLearn .lt checkpoints using RLViser, read-only."""
from __future__ import annotations
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox
import watch_teacher_core as wc

class WatchApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Actual Nexto / Cycle 9 / Wavedash in RocketSim (read-only)')
        self.geometry('900x590')
        self.minsize(720,480)
        self.q=queue.Queue();self.stop_event=threading.Event();self.worker=None
        self.model_a=tk.StringVar(value='tri_teacher_challenger_01')
        self.model_b=tk.StringVar(value='frozen:nexto')
        self.viewer=tk.StringVar(value='rlviser')
        self.speed=tk.StringVar(value='1.0')
        self.decisions=tk.StringVar(value='900')
        self.mode=tk.StringVar(value='greedy')
        self.gpu=tk.BooleanVar(value=False)
        self.models={}
        wrap=ttk.Frame(self,padding=16);wrap.pack(fill='both',expand=True)
        ttk.Label(wrap,text='WATCH THE REAL FROZEN TEACHERS',font=('Segoe UI',17,'bold')).pack(anchor='w')
        ttk.Label(wrap,text='Student .lt vs frozen .pt teacher with real RocketSim physics. Check driving, steer/boost/jump and touches.').pack(anchor='w',pady=(2,16))
        controls=ttk.Frame(wrap);controls.pack(fill='x')
        ttk.Label(controls,text='Blue / model A').grid(row=0,column=0,sticky='w',padx=4)
        ttk.Label(controls,text='Teacher / model B (real .pt)').grid(row=0,column=1,sticky='w',padx=4)
        self.a=ttk.Combobox(controls,textvariable=self.model_a,state='readonly',width=37)
        self.a.grid(row=1,column=0,sticky='ew',padx=4)
        self.b=ttk.Combobox(controls,textvariable=self.model_b,state='readonly',width=37)
        self.b.grid(row=1,column=1,sticky='ew',padx=4)
        ttk.Button(controls,text='Refresh models',command=self.refresh).grid(row=1,column=2,padx=8)
        controls.grid_columnconfigure(0,weight=1);controls.grid_columnconfigure(1,weight=1)
        opts=ttk.Frame(wrap);opts.pack(fill='x',pady=(16,7))
        ttk.Label(opts,text='Viewer').grid(row=0,column=0,sticky='w',padx=4)
        ttk.Combobox(opts,textvariable=self.viewer,values=['rlviser','rocketsimvis'],width=16,state='readonly').grid(row=1,column=0,padx=4)
        ttk.Label(opts,text='Speed').grid(row=0,column=1,sticky='w',padx=4)
        ttk.Combobox(opts,textvariable=self.speed,values=['0.5','1.0','1.5','2.0','3.0'],width=8,state='readonly').grid(row=1,column=1,padx=4)
        ttk.Label(opts,text='Action mode').grid(row=0,column=2,sticky='w',padx=4)
        ttk.Combobox(opts,textvariable=self.mode,values=['greedy','sample'],width=12,state='readonly').grid(row=1,column=2,padx=4)
        ttk.Label(opts,text='Max decisions / episode').grid(row=0,column=3,sticky='w',padx=4)
        ttk.Entry(opts,textvariable=self.decisions,width=10).grid(row=1,column=3,padx=4)
        ttk.Checkbutton(opts,text='GPU inference',variable=self.gpu).grid(row=1,column=4,padx=8,sticky='w')
        btns=ttk.Frame(wrap);btns.pack(fill='x',pady=12)
        self.startbtn=ttk.Button(btns,text='▶ Watch in RocketSim',command=self.start)
        self.startbtn.pack(side='left',padx=(0,10))
        self.stopbtn=ttk.Button(btns,text='■ Stop',command=self.stop,state='disabled')
        self.stopbtn.pack(side='left')
        ttk.Label(wrap,text='RLViser: Esc closes menu; 1/2 car cameras, 9 director, 0 free, WASD moves camera.').pack(anchor='w')
        ttk.Label(wrap,text='RocketSimVis: open its separate app first; it listens on localhost UDP port 9273.').pack(anchor='w')
        self.output=tk.Text(wrap,height=13,wrap='word',font=('Consolas',9));self.output.pack(fill='both',expand=True,pady=(12,0))
        self.output.configure(state='disabled')
        self.protocol('WM_DELETE_WINDOW',self.close)
        self.refresh();self.after(80,self.poll)

    def log(self,text):self.q.put(str(text))

    def refresh(self):
        self.models=wc.discover()
        keys=list(self.models)
        self.a['values']=keys;self.b['values']=['frozen:nexto','frozen:cycle9','frozen:wavedash']
        if self.model_a.get() not in keys and keys:self.model_a.set(keys[0])

        self.log('Found '+str(len(keys))+' 1v1 models: '+', '.join(keys))
        if not wc.EXE.exists():self.log('Needs C++ build: '+str(wc.EXE))

    def start(self):
        if self.worker is not None and self.worker.is_alive():return
        a=self.models.get(self.model_a.get());b=self.model_b.get()
        if a is None or b not in ('frozen:nexto','frozen:cycle9','frozen:wavedash'):
            messagebox.showerror('Select models','Choose two 1v1 models with checkpoints.');return
        try:
            dec=int(self.decisions.get());speed=float(self.speed.get())
        except ValueError:
            messagebox.showerror('Settings','Speed or decisions is invalid');return
        self.stop_event=threading.Event()
        settings=dict(viewer=self.viewer.get(),speed=speed,sample=self.mode.get()=='sample',
                      decisions=dec,episodes=0,gpu=bool(self.gpu.get()),stop=self.stop_event,log=self.log)
        self.startbtn.configure(state='disabled');self.stopbtn.configure(state='normal')
        self.log('Starting '+self.model_a.get()+' vs '+self.model_b.get())
        def runner():
            try:wc.play(a,b,**settings)
            except Exception as e:self.log('ERROR: '+repr(e))
            finally:self.q.put('__DONE__')
        self.worker=threading.Thread(target=runner,daemon=True);self.worker.start()

    def stop(self):
        self.stop_event.set();self.log('Stopping viewer...')

    def poll(self):
        try:
            for _ in range(100):
                entry=self.q.get_nowait()
                if entry=='__DONE__':
                    self.startbtn.configure(state='normal');self.stopbtn.configure(state='disabled')
                    continue
                self.output.configure(state='normal');self.output.insert('end',entry+'\n')
                self.output.see('end');self.output.configure(state='disabled')
        except queue.Empty:pass
        self.after(80,self.poll)

    def close(self):
        self.stop_event.set();self.destroy()

if __name__=='__main__':WatchApp().mainloop()
