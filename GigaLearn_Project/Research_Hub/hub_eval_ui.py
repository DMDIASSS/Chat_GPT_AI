"""Inject an optional Evaluation tab without replacing existing Research Hub UI patches."""
from tkinter import ttk, messagebox
import tkinter as tk
from hub_eval import candidates, ready, run, show_summary


def install_evaluation_tab(app):
    frame=ttk.Frame(app.tabs)
    app.tabs.add(frame,text='Gameplay Eval')
    app.text(frame,'GigaLearn 1v1 Gameplay Evaluator',
        'Read-only first-goal RocketSim matches. Same seeded kickoff, then swapped teams. '
        'Compares GigaLearn .lt policies only. NOT full five-minute games, Nexto, or 1v2.')
    controls=ttk.Frame(frame);controls.pack(fill='x',padx=14,pady=7)
    names=[]
    picks=[]
    for i,label in enumerate(('Model A','Model B','Model C (optional)')):
        ttk.Label(controls,text=label).pack(side='left',padx=(8,4))
        v=tk.StringVar();names.append(v)
        c=ttk.Combobox(controls,textvariable=v,width=20,state='readonly');c.pack(side='left',padx=(0,6));picks.append(c)
    opts=ttk.Frame(frame);opts.pack(fill='x',padx=14)
    pairs=tk.StringVar(value='4');decisions=tk.StringVar(value='600')
    ttk.Label(opts,text='Paired starts per matchup').pack(side='left',padx=(10,4))
    ttk.Entry(opts,textvariable=pairs,width=6).pack(side='left')
    ttk.Label(opts,text='Decision cap per game').pack(side='left',padx=(12,4))
    ttk.Entry(opts,textvariable=decisions,width=7).pack(side='left')
    result=tk.Text(frame,height=22,wrap='word',font=('Consolas',10),bg='#1b2735',fg='#eaf1fa')
    result.pack(fill='both',expand=True,padx=19,pady=(12,8))
    def put(msg):
        result.delete('1.0','end');result.insert('end',msg)
    def reload():
        available=candidates();found=[x['name'] for x in available]
        for c in picks:c.configure(values=['']+found)
        for i,v in enumerate(names):
            if v.get() not in found:
                preferred=['smoke_balanced_01','shootingv1','defense1v1']
                v.set(preferred[i] if i<len(preferred) and preferred[i] in found else (found[i] if i<len(found) and i<2 else ''))
        return available
    def start():
        selection=[v.get() for v in names if v.get()]
        try:
            amount=int(pairs.get());cap=int(decisions.get())
            if amount<1 or amount>1000 or cap<60 or cap>5000:raise ValueError('Limits out of range')
        except ValueError as e:
            messagebox.showerror('Gameplay Eval','Invalid pairs/decision cap: '+str(e));return
        if len(set(selection))!=len(selection):
            messagebox.showerror('Gameplay Eval','Choose different models');return
        if not messagebox.askyesno('Read-only evaluation',f'Run {len(selection)} model(s), {amount} paired kickoffs per matchup?\nThis may take several minutes. No checkpoints will be changed.'):
            return
        put('Starting evaluation...\nReports will appear under Research_Hub\\evaluations.\n'
            'Training runs should be stopped to make comparison fair.\n')
        app.execute(lambda:'Gameplay evaluation saved: '+str(run(selection,pairs=amount,decisions=cap)))
    def last():put(show_summary())
    row=ttk.Frame(frame);row.pack(fill='x',padx=14,pady=(0,12))
    app.button(row,'Refresh available models',reload)
    app.button(row,'Run paired tournament',start)
    app.button(row,'Show last results',last)
    info=ready()
    put('Evaluation binary: '+info['binary']+'\nBuilt: '+str(info['binary_exists'])+'\n\n'
        'Run EVAL_1_PATCH_CPP.bat and build GigaLearnEval.exe first.\n'
        'Start with 2–4 paired kickoffs, then use 20–40+ for longer comparison.\n'
        'Shot/save event counts are diagnostics, not proof of accuracy or positioning.\n')
    reload()
