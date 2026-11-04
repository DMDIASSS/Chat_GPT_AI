"""Package supported actors with their runtime: TOML is configuration, not weights."""
from __future__ import annotations

import json
from pathlib import Path
import re
import shutil
import tempfile
import uuid
import zipfile

import torch

from .core import ROOT,CONTRACT,OBS_SIZE,ACTIONS,check_model,write_model_meta,sha256


def inspect_actor(path,assume_novaforge=False):
    path=Path(path).resolve()
    if path.suffix.lower() not in {'.pt','.lt'} or not path.is_file(): raise ValueError('Choose an existing exported TorchScript actor .pt or .lt file')
    sidecar=Path(str(path)+'.json')
    if sidecar.exists():
        check_model(path)
    elif not assume_novaforge:
        raise ValueError('Actor metadata is missing. For a model trained with NovaForge features/actions, '
            'add --assume-novaforge. Other bots need their original observation/action adapter.')
    torch.set_num_threads(1)
    try:
        actor=torch.jit.load(str(path),map_location='cpu').eval()
        with torch.inference_mode():
            for batch in (1,2):
                result=actor(torch.zeros(batch,OBS_SIZE))
                if not torch.is_tensor(result) or result.shape!=(batch,len(ACTIONS)) or not torch.isfinite(result).all():
                    raise ValueError('Actor must return finite [batch,276] logits from [batch,100] NovaForge features')
    except (RuntimeError,TypeError) as error:
        raise ValueError('This is not a supported NovaForge TorchScript actor. '
            'A state_dict checkpoint or another bot architecture needs its training code/adapter; '
            'changing the extension cannot convert it.') from None
    return path


def make_package(model,name=None,assume_novaforge=False,weights_format='lt'):
    if weights_format not in {'pt','lt'}:raise ValueError('Weights format must be pt or lt')
    source=inspect_actor(model,assume_novaforge)
    display=name or source.stem
    if not isinstance(display,str) or not display.strip() or len(display)>80 or any(ord(c)<32 for c in display):
        raise ValueError('Use a nonempty bot name of at most 80 printable characters')
    display=display.strip()
    slug=re.sub(r'[^a-z0-9_-]+','_',display.lower()).strip('_')[:48] or 'imported_bot'
    digest=sha256(source);stem=f'{slug}_{digest[:10]}'
    parent=ROOT/'exports';parent.mkdir(parents=True,exist_ok=True)
    if (parent/stem).exists() or (parent/(stem+'.zip')).exists(): stem+='_'+uuid.uuid4().hex[:6]
    destination=parent/stem;archive=parent/(stem+'.zip')
    agent_id='DMDIASSS/'+stem
    weights_name='policy.'+weights_format
    # These relative paths refer to the package under novaforge/exports/<bot>.
    toml='''#:schema https://rlbot.org/schemas/agent.json
[settings]
name = DISPLAY
agent_id = AGENT
run_command = WINCMD
run_command_linux = LINUXCMD
hivemind = true

[details]
developer = "NovaForge user"
description = "NovaForge TorchScript actor packaged for offline 1v1. Keep this folder inside novaforge/exports."
language = "python"
tags = ["1v1"]
'''
    replacements={'DISPLAY':display,'AGENT':agent_id,
        'WINCMD':'"..\\..\\.venv\\Scripts\\python.exe" bot.py',
        'LINUXCMD':'"../../.venv/bin/python" bot.py'}
    for key,value in replacements.items(): toml=toml.replace('= '+key+'\n','= '+json.dumps(value,ensure_ascii=False)+'\n')
    runtime='''from pathlib import Path
import importlib.util
import sys

project=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(project))
spec=importlib.util.spec_from_file_location('novaforge_packaged_live',project/'rlbot'/'bot.py')
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

if __name__=='__main__':
    module.NovaForge(policy_path=Path(__file__).with_name(WEIGHTS),agent_id=AGENT).run()
'''.replace('AGENT',repr(agent_id)).replace('WEIGHTS',repr(weights_name))
    with tempfile.TemporaryDirectory(prefix='package_',dir=parent) as temporary:
        stage=Path(temporary)/stem;stage.mkdir()
        if weights_format=='lt':
            # A real LibTorch-readable TorchScript archive, reserialized rather than renamed.
            torch.jit.save(torch.jit.load(str(source),map_location='cpu').eval(),str(stage/weights_name))
        else:shutil.copyfile(source,stage/weights_name)
        if sha256(source)!=digest: raise ValueError('Source actor changed during packaging; retry after export finishes')
        with torch.inference_mode():
            example=torch.linspace(-1,1,OBS_SIZE*2).reshape(2,OBS_SIZE)
            expected=torch.jit.load(str(source),map_location='cpu')(example)
            actual=torch.jit.load(str(stage/weights_name),map_location='cpu')(example)
            torch.testing.assert_close(actual,expected,rtol=0,atol=0)
        steps=check_model(source).get('timesteps',0) if Path(str(source)+'.json').exists() else 0
        write_model_meta(stage/weights_name,timesteps=int(steps),initialization='imported_novaforge_actor',source_sha256=digest,
            weights_format='libtorch_torchscript' if weights_format=='lt' else 'torchscript')
        (stage/'bot.py').write_text(runtime,encoding='utf8')
        (stage/'bot.bot.toml').write_text(toml,encoding='utf8')
        (stage/'README.txt').write_text('Keep this folder at novaforge/exports/'+stem+'.\n'
            'In the RLBot v5 GUI add bot.bot.toml and start an offline 1v1.\n'
            'The package uses the enclosing NovaForge .venv, nova modules and rlbot/bot.py.\n'
            'TOML describes how to launch the Python adapter; '+weights_name+' contains the model weights.\n'
            'The .lt export is LibTorch TorchScript for this adapter, not a drop-in Chronos/Galactus architecture.\n'
            'This supports the NovaForge 100-feature / 276-action contract only.\n',encoding='utf8')
        staged_zip=Path(temporary)/'package.zip'
        with zipfile.ZipFile(staged_zip,'w',zipfile.ZIP_DEFLATED) as z:
            for file in sorted(stage.iterdir()): z.write(file,stem+'/'+file.name)
        stage.replace(destination);staged_zip.replace(archive)
    return destination/'bot.bot.toml',archive


def package_actor(args):
    source=args.model
    if not source:
        try:
            import tkinter as tk
            from tkinter.filedialog import askopenfilename
            root=tk.Tk();root.withdraw()
            try: source=askopenfilename(title='Choose a NovaForge exported actor .pt',filetypes=[('TorchScript actor','*.pt')])
            finally: root.destroy()
        except Exception:
            raise RuntimeError('File picker unavailable. Use: python run.py pt-to-toml PATH_TO_ACTOR.pt') from None
        if not source: print('No actor selected.');return
    toml,archive=make_package(source,args.name,args.assume_novaforge,getattr(args,'weights_format','lt'))
    print(f'PT_PACKAGE_READY: {toml}')
    print(f'Package ZIP: {archive}')
    print('Add the .bot.toml to RLBot v5 and start an offline 1v1. Keep its folder inside novaforge/exports.')


def export_v5(args):
    from .training import resolve_model
    from .models import load_ppo,export_actor
    source=resolve_model(args.model)
    if source.suffix in {'.pt','.lt'}:
        toml,archive=make_package(source,args.name)
    else:
        with tempfile.TemporaryDirectory(prefix='v5_actor_') as temporary:
            actor=Path(temporary)/'policy.lt'
            export_actor(load_ppo(source),actor,source_sha256=sha256(source))
            toml,archive=make_package(actor,args.name or 'NovaForge Copy')
    print(f'V5_LT_EXPORT_READY: {toml}')
    print(f'LibTorch weights: {toml.parent/"policy.lt"}')
    print(f'Bot package ZIP: {archive}')
    print('In RLBot v5 add this .bot.toml, select one opponent, and start an offline 1v1.')
