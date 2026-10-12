"""Build one isolated RLBot v4 stock Nexto live probe from verified reference files.

The user-provided RLBotPack source is bundled in slater_v038c_source. Original
Nexto weights are copied from vendor/nexto/nexto-model.pt after SHA check.
No originals or protected Slater checkpoints are changed.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import shutil

EXPECTED_BOT_SHA='1d9d4537ee846cbdf670079fde831e4078feb1f8fefb34911399ac4a7bb186d1'
EXPECTED_OBS_SHA='7247046d836059ab4428fb8f08968af1a977cf3228f1462a0235cd7a825362b0'
EXPECTED_MODEL_SHA='bf5343b5eeacac6bf7cdb75dac4a5c14ba0f94d820eae75f00a211b6119d69fa'


def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as fh:
        for chunk in iter(lambda:fh.read(1024*1024),b''):
            h.update(chunk)
    return h.hexdigest()


def instrument(source):
    begin='        if self.update_action and len(self.game_state.players) > self.index:'
    act='            self.action, weights = self.agent.act(obs, beta)'
    end='        return self.controls'
    for anchor in (begin,act,end):
        if source.count(anchor)!=1:
            raise ValueError(f'Unexpected source anchor: {anchor}')
    if 'slater_nexto_probe_v038c' in source:
        raise ValueError('Already instrumented')
    source='from slater_nexto_probe_v038c import capture as _v038c_capture\n'+source
    source=source.replace(begin,
         '        _v038c_was_nn = bool(self.update_action and len(self.game_state.players) > self.index)\n'
         '        _v038c_nn_action = None\n'
         '        _v038c_beta = None\n'+begin)
    source=source.replace(act,act+'\n'
        '            _v038c_nn_action = np.asarray(self.action, dtype=np.float32).copy()\n'
        '            _v038c_beta = float(beta)')
    source=source.replace(end,
        '        try:\n'
        '            _v038c_capture(self, packet, ticks_elapsed, _v038c_was_nn, _v038c_nn_action, _v038c_beta)\n'
        '        except Exception as _v038c_exc:\n'
        '            if not getattr(self, "_v038c_capture_warned", False):\n'
        '                print("SLATER_V038C_CAPTURE_ERROR", repr(_v038c_exc), flush=True)\n'
        '                self._v038c_capture_warned = True\n'
        +end)
    compile(source,'<Nexto instrumented>','exec')
    return source


def build(root, dest, model=None):
    root=root.resolve(); dest=(root/dest).resolve()
    isolation=(root/'data'/'isolated').resolve()
    if dest.parent!=isolation or not dest.name.startswith('slater_v038c_nexto_'):
        raise ValueError('Destination must be a direct child of data/isolated named slater_v038c_nexto_*')
    if dest.exists() or dest.with_name(dest.name+'.partial').exists():
        raise FileExistsError(f'Cannot replace an existing diagnostic folder: {dest}')
    source_dir=Path(__file__).resolve().parent/'slater_v038c_source'
    original_bot=source_dir/'bot.py'; original_obs=source_dir/'nexto_obs.py'
    if sha(original_bot)!=EXPECTED_BOT_SHA or sha(original_obs)!=EXPECTED_OBS_SHA:
        raise RuntimeError('Archived Nexto reference files differ; refusing to create probe')
    model=(root/model).resolve() if model is not None else root/'vendor'/'nexto'/'nexto-model.pt'
    if not model.is_file():
        raise FileNotFoundError(f'Original Nexto model not found: {model}')
    if sha(model)!=EXPECTED_MODEL_SHA:
        raise ValueError('Original Nexto weights SHA mismatch. Do NOT use V60/Cycle9 as the stock Nexto probe.')
    tmp=dest.with_name(dest.name+'.partial')
    dest.parent.mkdir(parents=True,exist_ok=True)
    try:
        shutil.copytree(source_dir,tmp)
        (tmp/'bot.py').write_text(instrument(original_bot.read_text(encoding='utf-8-sig')),encoding='utf-8')
        cfg=(tmp/'bot.cfg').read_text(encoding='utf-8-sig')
        cfg,num=re.subn(r'(?m)^(name\s*=\s*)Nexto\s*$',
                         r'\1Nexto [v038c LIVE PROBE]',cfg,count=1)
        if num!=1:raise RuntimeError('Reference bot config name unexpected')
        (tmp/'bot.cfg').write_text(cfg,encoding='utf-8')
        shutil.copyfile(model,tmp/'nexto-model.pt')
        shutil.copyfile(Path(__file__).resolve().parent/'slater_nexto_probe_v038c.py',tmp/'slater_nexto_probe_v038c.py')
        tmp.rename(dest)
    except BaseException:
        if tmp.exists():shutil.rmtree(tmp)
        raise
    return dest


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out-bot',default='data/isolated/slater_v038c_nexto_live01')
    p.add_argument('--model',default='vendor/nexto/nexto-model.pt',help='original model only; SHA verified')
    a=p.parse_args()
    path=build(Path.cwd(),a.out_bot,a.model)
    print('V038C_REFERENCE_NEXTO_MODEL_SHA',EXPECTED_MODEL_SHA)
    print('V038C_DIAGNOSTIC_FOLDER',path)
    print('V038C_LIVE_CAPTURE_AFTER_PLAYING',path/'capture_v038c')
    print('V038C_EXISTING_BOTS_UNCHANGED')


if __name__=='__main__':main()
