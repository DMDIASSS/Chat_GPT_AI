"""Export a completed Freestyle checkpoint as a real RLBot v5 bot."""
from __future__ import annotations
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import zipfile

from slater_v041_core import read_json,sha256

ROOT=Path(__file__).resolve().parent
RUNS=ROOT/'data/isolated/freestyle/runs'
OUTPUT=ROOT/'data/rlbot_v5_exports'
TEMPLATE=ROOT/'freestyle_rlbot_v5'


def checkpoints(run):
    result=[]
    for path in (Path(run)/'checkpoints').glob('*'):
        if not path.is_dir() or not path.name.isdigit():continue
        try:
            marker=read_json(path/'FREESTYLE_COMPLETE.json',{})
            state=read_json(path/'FREESTYLE_STATE.json',{})
        except (OSError,json.JSONDecodeError):continue
        if not marker or marker.get('schema')!=1 or any(marker.get(k)!=state.get(k)for k in ('update','timesteps','source_sha')):continue
        if type(marker.get('update'))is not int or not (path/'POLICY.lt').is_file():continue
        result.append((marker['update'],path,state))
    return sorted(result,key=lambda x:x[0])


def load_actor(checkpoint, config):
    import torch
    torch.set_num_threads(1)
    archive=torch.jit.load(str(Path(checkpoint)/'POLICY.lt'),map_location='cpu')
    layers=[];size=512
    for _ in range(config['depth']):
        layers += [torch.nn.Linear(size,config['width']),torch.nn.LayerNorm(config['width']),torch.nn.ReLU()]
        size=config['width']
    layers.append(torch.nn.Linear(size,94))
    actor=torch.nn.Sequential(*layers).eval()
    actor.load_state_dict(archive.state_dict(),strict=True)
    # Every tensor must transfer exactly; never silently fit an unrelated actor.
    assert all(torch.equal(v,actor.state_dict()[k])for k,v in archive.state_dict().items())
    return actor


def export(run='freestyle_rewards02', *, update=None, checkpoint=None, name=None, scripted=True, output=None):
    import torch
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}',run):raise ValueError('Invalid Freestyle run name')
    source=RUNS/run;protocol=read_json(source/'protocol.json',{})
    if protocol.get('schema')!='slater-freestyle-v1':raise ValueError('Select an existing Freestyle run')
    choices=checkpoints(source)
    if checkpoint is not None:
        requested=Path(checkpoint)
        if requested.name=='POLICY.lt':requested=requested.parent
        chosen=next((x for x in choices if x[1].resolve()==requested.resolve()),None)
    elif update is not None:chosen=next((x for x in choices if x[0]==update),None)
    else:chosen=choices[-1]if choices else None
    if chosen is None:raise FileNotFoundError('No matching completed checkpoint. Use --list to see saved updates.')
    number,folder,state=chosen
    if state.get('reward_version')!=2:raise ValueError('This runtime supports Freestyle reward version 2 checkpoints')
    config=read_json(source/'config.json');backend=protocol['identity']['backend_sha']
    for filename in ('FreestyleObs.h','FreestyleActions.h','FreestyleRewards.h','FreestyleCurriculum.h'):
        if backend.get(filename)!=sha256(ROOT/'GigaLearn_Project/Freestyle'/filename):
            raise ValueError('Checkpoint observation/history source differs: '+filename)
    name=name or f'Freestyle_u{number:06d}_{"Scripted" if scripted else "Learned"}_'+datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S_%f')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,95}',name):raise ValueError('Use a name containing letters, numbers, _ or -')
    destination=Path(output or OUTPUT)/name
    if destination.exists()or destination.with_suffix('.zip').exists():raise FileExistsError('Export already exists; choose another name')
    destination.parent.mkdir(parents=True,exist_ok=True)
    before=sha256(folder/'POLICY.lt')
    marker_before=sha256(folder/'FREESTYLE_COMPLETE.json')
    actor=load_actor(folder,config)
    from freestyle_rlbot_v5.runtime import ACTIONS,STAGES,OBS_SCHEMA,ACTION_SCHEMA
    settings={'agent_id':'dmdias/freestyle-'+name.lower().replace('_','-'),
        'update':number,'stage':STAGES.index(state['stage']),'difficulty':state['difficulty'],
        'episode_seconds':config['max_episode_seconds'],'tick_skip':config['tick_skip'],
        'action_delay':config['action_delay'],'scripted_kickoff':bool(scripted),
        'diagnostic_capture':True,
        'reward_timings':config['rewards'],'observation_schema':OBS_SCHEMA,'action_schema':ACTION_SCHEMA}
    with tempfile.TemporaryDirectory(prefix='.freestyle-v5-',dir=destination.parent)as temp:
        staging=Path(temp)
        for filename in ('runtime.py','live.py','bot.py','install_runtime.py','diagnose.py','live_audit.py'):
            shutil.copyfile(TEMPLATE/filename,staging/filename)
        traced=torch.jit.trace(actor,torch.zeros(1,512))
        traced.save(str(staging/'policy.pt'))
        portable=torch.jit.load(str(staging/'policy.pt'),map_location='cpu').eval()
        generator=torch.Generator().manual_seed(8810271)
        observations=torch.randn(96,512,generator=generator).clamp(-4,4)
        masks=torch.rand(96,94,generator=generator)>.25;masks[:,0]=True
        with torch.inference_mode():
            expected=actor(observations);actual=portable(observations)
        error=float((expected-actual).abs().max())
        identical=bool(torch.equal(expected.masked_fill(~masks,-1e10).argmax(1),actual.masked_fill(~masks,-1e10).argmax(1)))
        if error>1e-5 or not identical:raise RuntimeError('Portable policy verification failed')
        (staging/'runtime.json').write_text(json.dumps(settings,indent=2),encoding='utf-8')
        (staging/'loadout.toml').write_text('[blue_loadout]\nteam_color_id = 29\ncustom_color_id = 0\ncar_id = 23\n\n[orange_loadout]\nteam_color_id = 69\ncustom_color_id = 0\ncar_id = 23\n',encoding='utf-8')
        (staging/'bot.toml').write_text(
            '#:schema https://rlbot.org/schemas/agent.json\n[settings]\n'+
            'name = '+json.dumps(name)+'\nagent_id = '+json.dumps(settings['agent_id'])+'\n'+
            'loadout_file = "loadout.toml"\nroot_dir = ""\n'+
            'run_command = ".\\\\.venv\\\\Scripts\\\\python.exe bot.py"\n'+
            'run_command_linux = "./.venv/bin/python bot.py"\n'+
            '[details]\ndescription = "Freestyle scratch policy, flat512/stall94, RLBot v5."\n'+
            'developer = "DMDIASSS"\nlanguage = "Python"\ntags = []\n',encoding='utf-8')
        # Bootstrap only the small SDK in a separate venv. Torch is read from
        # the existing training installation; it is never upgraded or replaced.
        (staging/'python_source.json').write_text(json.dumps({'python':sys.executable},indent=2),encoding='utf-8')
        executable='"'+str(sys.executable).replace('%','%%')+'"'
        (staging/'INSTALL.bat').write_text('@echo off\nsetlocal DisableDelayedExpansion\ncd /d "%~dp0"\n'+
            executable+' -u install_runtime.py\nset "BOT_EXIT=%ERRORLEVEL%"\npause\nendlocal & exit /b %BOT_EXIT%\n',encoding='utf-8')
        (staging/'DIAGNOSE.bat').write_text('@echo off\ncd /d "%~dp0"\n.venv\\Scripts\\python.exe -u diagnose.py\n'+
            'set "BOT_EXIT=%ERRORLEVEL%"\npause\nexit /b %BOT_EXIT%\n',encoding='utf-8')
        (staging/'AUDIT_LIVE.bat').write_text('@echo off\ncd /d "%~dp0"\n.venv\\Scripts\\python.exe -u live_audit.py\n'+
            'set "BOT_EXIT=%ERRORLEVEL%"\npause\nexit /b %BOT_EXIT%\n',encoding='utf-8')
        (staging/'README_IMPORT.txt').write_text(
            'Run INSTALL.bat once, then import this folder bot.toml in RLBot v5.\n'+
            'The exported model is policy.pt. Training checkpoints are unchanged.\n'+
            'SDK uses a separate .venv; inference is on CPU and reads existing Torch.\n'+
            'Requires the original project Python/Torch installation on this PC.\n'+
            'Kickoff script: '+str(scripted)+'. Edit runtime.json to change it.\n'+
            'Standard Soccar only, 1..6 cars. Trained in solo drills; match strength is unverified.\n'+
            'Wheel-contact/reset evidence is masked, as in training dropout episodes.\n'+
            'Live jump timers and reward-chain history are reconstructed from packets.\n'+
            'These reconstructed histories and timing are not exact simulator state.\n'+
            'Use 120 physics packets/second where possible. Review RLBot logs if startup fails.\n'+
            'Local diagnostics record at most 45 seconds/3600 callbacks. Play then end\n'+
            'the match and run AUDIT_LIVE.bat. Reports/capture are in diagnostics/.\n'+
            'Set diagnostic_capture=false in runtime.json to disable packet recording.\n',encoding='utf-8')
        manifest={'source_checkpoint':str(folder),'source_policy_sha256':before,'update':number,
            'portable_policy_sha256':sha256(staging/'policy.pt'),'observation_schema':OBS_SCHEMA,'action_schema':ACTION_SCHEMA,
            'scripted_kickoff':scripted,'parameter_tensors_identical':True,'portable_test_states':96,
            'portable_max_logit_error':error,'portable_actions_identical':identical,
            'live_state':'privileged mask zero; observable timers/history reconstructed',
            'rlbot_sdk':'2.0.0b56','flatbuffers':'0.19.0'}
        manifest['runtime_files_sha256']={filename:sha256(staging/filename)for filename in ('runtime.py','live.py','bot.py','live_audit.py')}
        (staging/'EXPORT_INFO.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
        if sha256(folder/'POLICY.lt')!=before or sha256(folder/'FREESTYLE_COMPLETE.json')!=marker_before:
            raise RuntimeError('Input checkpoint changed during export; retry after its save completes')
        shutil.copytree(staging,destination)
    with zipfile.ZipFile(destination.with_suffix('.zip'),'w',zipfile.ZIP_DEFLATED)as archive:
        for path in sorted(destination.rglob('*')):
            if path.is_file():archive.write(path,name+'/'+path.relative_to(destination).as_posix())
    print('FREESTYLE_V5_EXPORT',json.dumps({'folder':str(destination),'bot_toml':str(destination/'bot.toml'),**manifest}),flush=True)
    return destination


def gui(initial_run='freestyle_rewards02'):
    import tkinter as tk
    from tkinter import ttk,messagebox,filedialog
    root=tk.Tk();root.title('Export Freestyle to RLBot v5');root.geometry('620x240')
    run=tk.StringVar(value=initial_run);update=tk.StringVar(value='latest');script=tk.BooleanVar(value=True)
    ttk.Label(root,text='Freestyle run').pack(anchor='w',padx=12);ttk.Entry(root,textvariable=run,width=60).pack(padx=12)
    ttk.Label(root,text='Saved update number, or latest').pack(anchor='w',padx=12);ttk.Entry(root,textvariable=update,width=60).pack(padx=12)
    ttk.Checkbutton(root,text='Scripted kickoff ON',variable=script).pack(anchor='w',padx=12,pady=10)
    def perform():
        try:
            path=export(run.get(),update=None if update.get().strip().lower()=='latest'else int(update.get()),scripted=script.get())
            messagebox.showinfo('Export complete','Run INSTALL.bat in:\n'+str(path)+'\nThen import bot.toml in RLBot v5.')
            if os.name=='nt':os.startfile(path)
        except Exception as exc:messagebox.showerror('Export failed',str(exc))
    ttk.Button(root,text='Export model',command=perform).pack(pady=8);root.mainloop()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',default='freestyle_rewards02')
    p.add_argument('--update',type=int);p.add_argument('--checkpoint',type=Path);p.add_argument('--name')
    p.add_argument('--learned-kickoff',action='store_true');p.add_argument('--list',action='store_true');p.add_argument('--gui',action='store_true')
    a=p.parse_args()
    if a.gui:gui(a.run)
    elif a.list:print(json.dumps([{'update':n,'checkpoint':str(f),'stage':s['stage'],'difficulty':s['difficulty']}for n,f,s in checkpoints(RUNS/a.run)],indent=2))
    else:export(a.run,update=a.update,checkpoint=a.checkpoint,name=a.name,scripted=not a.learned_kickoff)


if __name__=='__main__':main()
