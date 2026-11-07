"""Independent direct actors, v5 TOML/loadout, and native-timed live driver."""
from __future__ import annotations

from contextlib import chdir
import json
import hashlib
import logging
import os
from pathlib import Path
import shutil
import sys
import tempfile
import time
import uuid
import zipfile

import numpy as np
import torch

from .core import ROOT, check_model, sha256
from .forge_models import DirectController, context, CORE, TABLE, build_features, native_action_mask, contract,check_actor


class LiveDriver:
    def __init__(self,path):
        self.controller=DirectController(path);self.reset()
    def reset(self):
        self.previous=np.zeros(8,np.float32);self.held=np.zeros(8,np.float32);self.pending=None;self.last_query=None
        if self.controller.forecast:self.controller.forecast.reset()
    def controls(self,state,agent,rng,score,remaining):
        frame=int(state.tick_count)
        if self.pending is not None and frame>=self.pending[0]:
            self.held=self.pending[1].copy();self.pending=None
        if self.last_query is None or frame-self.last_query>=8:
            pred=self.controller.forecast.samples(state) if self.controller.forecast else None
            obs,mirror=build_features(state,agent,self.previous,rng,self.controller.kind,pred)
            obs=np.concatenate((obs,context(state,agent,score,remaining)))
            with torch.inference_mode():logits=self.controller.network(torch.from_numpy(obs)[None,:])[0].numpy()
            if logits.shape!=(90,) or not np.isfinite(logits).all():raise ValueError('Invalid live actor output')
            mask=native_action_mask(state.cars[agent]);planned=TABLE[int(np.where(mask,logits,-np.inf).argmax())].copy()
            if mirror:planned[[1,3,4]]*=-1
            self.previous=planned;self.pending=(frame+7,planned);self.last_query=frame
        return self.held.copy()


def create_live_bot(agent_id,actor):
    from rlbot.managers.hivemind import Hivemind
    from rlbot.flat import ControllerState,MatchPhase
    from rlgym_compat import GameState
    class ForgeBot(Hivemind):
        def __init__(self):
            super().__init__(agent_id);torch.set_num_threads(1)
            self.driver=None;self.rng=np.random.default_rng(271031);self.last_frame=None
        def initialize(self):
            self.driver=LiveDriver(actor);self.state=GameState.create_compat_game_state(self.field_info,self.match_config)
            self._logger.info('FORGE_READY: %s direct actor, %s, 1v1, no privileged inputs',self.driver.controller.kind,self.driver.controller.hitbox)
        def get_outputs(self,packet):
            if len(packet.players)!=2 or not packet.balls or len(self.indices)!=1:return {i:ControllerState() for i in self.indices}
            frame=int(packet.match_info.frame_num)
            if self.last_frame is not None and frame<self.last_frame:
                self.state=GameState.create_compat_game_state(self.field_info,self.match_config);self.driver.reset()
            self.last_frame=frame;self.state.update(packet)
            if packet.match_info.match_phase not in (MatchPhase.Active,MatchPhase.Kickoff):
                self.driver.reset();return {i:ControllerState() for i in self.indices}
            index=next(iter(self.indices));agent=packet.players[index].player_id;team=packet.players[index].team
            scores={t.team_index:t.score for t in packet.teams or []}
            controls=self.driver.controls(self.state,agent,self.rng,scores.get(team,0)-scores.get(1-team,0),packet.match_info.game_time_remaining)
            return {index:ControllerState(*[float(v) for v in controls[:5]],*[bool(v) for v in controls[5:]])}
    return ForgeBot()


def boot(default_agent):
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--diagnose',action='store_true');args=parser.parse_args()
    logging.basicConfig(level=logging.INFO,handlers=[logging.FileHandler('startup.log',encoding='utf8'),logging.StreamHandler()],force=True)
    try:
        actor=ROOT/'actor.lt'
        if args.diagnose:
            controller=DirectController(actor)
            with torch.inference_mode():assert controller.network(torch.zeros(1,CORE[controller.kind]+3)).shape==(1,90)
            logging.info('FORGE_DIAGNOSE_PASS family=%s actor_sha256=%s',controller.kind,sha256(actor));return
        agent=os.environ.get('RLBOT_AGENT_ID',default_agent)
        create_live_bot(agent,actor).run(wants_match_communications=False,wants_ball_predictions=False)
    except BaseException:
        logging.exception('FORGE_START_FAILED');raise


def export_actor_bundle(actor,destination_parent,label='retained champion'):
    from .forge_league import read
    actor=Path(actor).resolve();family=read(str(actor)+'.json')['contract']['family'];meta=check_actor(actor,family);body=meta['contract']['hitbox']
    parent=Path(destination_parent);parent.mkdir(parents=True,exist_ok=True)
    source_id=hashlib.sha256(b''.join(p.read_bytes() for p in sorted((ROOT/'nova').glob('*.py')))+(ROOT/'requirements.txt').read_bytes()).hexdigest()[:6]
    stem='Forge_'+family+'_'+meta['sha256'][:10]+'_'+source_id
    destination=parent/stem
    if destination.exists():
        if sha256(destination/'actor.lt')!=meta['sha256']:raise ValueError('Existing export was modified')
        for row in (destination/'MANIFEST.sha256').read_text().splitlines():
            digest,name=row.split('  ',1);target=(destination/name).resolve()
            if not target.is_relative_to(destination.resolve()) or sha256(target)!=digest:raise ValueError('Existing export manifest mismatch')
        print('FORGE_EXPORT_EXISTS:',destination/'bot.bot.toml',flush=True);return destination
    with tempfile.TemporaryDirectory(dir=parent) as tmp:
        stage=Path(tmp)/stem;stage.mkdir()
        shutil.copytree(ROOT/'nova',stage/'nova',ignore=shutil.ignore_patterns('__pycache__'))
        for name in ('requirements.txt','THIRD_PARTY.md','teachers.lock.json'):shutil.copy2(ROOT/name,stage/name)
        for name in ('chronos','galactus'):
            folder=ROOT/'assets'/name
            for notice in folder.glob('*'):
                if notice.is_file() and (notice.suffix.lower() in ('.md','.txt') or notice.name.upper().startswith('LICENSE')):
                    target=stage/'notices'/name/notice.name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(notice,target)
        for suffix in ('lt','pt'):
            shutil.copy2(actor,stage/('actor.'+suffix));shutil.copy2(str(actor)+'.json',stage/('actor.'+suffix+'.json'))
        agent_id='DMDIASSS/'+stem
        (stage/'run_forge.py').write_text('from nova.forge_export import boot\nif __name__=="__main__":boot('+repr(agent_id)+')\n')
        (stage/'loadout.toml').write_text('[blue_loadout]\ncar_id = '+str(22 if body=='breakout' else 23)+'\n[orange_loadout]\ncar_id = '+str(22 if body=='breakout' else 23)+'\n')
        for portable in (False,True):
            win='.venv\\Scripts\\python.exe' if portable else sys.executable
            linux='.venv/bin/python' if portable else sys.executable
            text='[settings]\nname = '+json.dumps('Forge '+family+' '+label+(' portable' if portable else ''))+'\n'
            text+='agent_id = '+json.dumps(agent_id+('.portable' if portable else ''))+'\n'
            text+='run_command = '+json.dumps('"'+win+'" run_forge.py')+'\nrun_command_linux = '+json.dumps('"'+linux+'" run_forge.py')+'\n'
            text+='loadout_file = "loadout.toml"\nhivemind = true\n\n[details]\ndeveloper = "NovaForge; original models credited in THIRD_PARTY.md"\n'
            text+='description = "Independent trained '+family+' family actor. '+body+'; 1v1; no mind reading at runtime."\nlanguage = "python"\ntags = ["1v1"]\n'
            (stage/('bot.portable.bot.toml' if portable else 'bot.bot.toml')).write_text(text)
        (stage/'DIAGNOSE.bat').write_text('@echo off\ncd /d "%~dp0"\n"'+sys.executable+'" run_forge.py --diagnose\npause\n')
        (stage/'INSTALL.bat').write_text('@echo off\ncd /d "%~dp0"\npy -3.11 -m venv .venv\nif errorlevel 1 goto failed\n".venv\\Scripts\\python.exe" -m pip install torch==2.9.1 --index-url https://download.pytorch.org/whl/cpu\nif errorlevel 1 goto failed\n".venv\\Scripts\\python.exe" -m pip install -r requirements.txt\nif errorlevel 1 goto failed\necho INSTALLED - import bot.portable.bot.toml in RLBot v5.\npause\nexit /b 0\n:failed\necho INSTALL_FAILED\npause\nexit /b 1\n')
        (stage/'README.txt').write_text('Import bot.bot.toml on this PC. On another PC run INSTALL.bat, then import bot.portable.bot.toml.\nactor.lt and actor.pt are identical TorchScript archives of the complete actor, requiring this loader and the sidecar contract. They are not native split POLICY/SHARED_HEAD files. TOML describes the launcher; it is not converted neural weights. No critic, private opponent information, selector or team coordination is exported. 1v1 only. Body: '+body+'.\nExport role: '+label+'\nOriginal checkpoint ancestry and source notices are recorded beside the actor and in THIRD_PARTY.md. No measured strength gain is implied by exporting.\n')
        files=sorted(p for p in stage.rglob('*') if p.is_file())
        (stage/'MANIFEST.sha256').write_text(''.join(sha256(p)+'  '+p.relative_to(stage).as_posix()+'\n' for p in files))
        archive=Path(tmp)/(stem+'.zip')
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
            for p in sorted(stage.rglob('*')):
                if p.is_file():z.write(p,stem+'/'+p.relative_to(stage).as_posix())
        stage.replace(destination);archive.replace(parent/(stem+'.zip'))
    print('FORGE_EXPORT_READY:',destination/'bot.bot.toml',flush=True);return destination


def export(name):
    from .forge_league import run_path,champion,PROJECT
    run=run_path(name)
    return [export_actor_bundle(champion(run,family),PROJECT/'exports'/name) for family in ('chronos','galactus')]


def watch(name,family,label='retained',opponent=None):
    from filelock import FileLock
    from .forge_league import run_path,champion,read
    from .forge_env import ForgeEnv
    from .forge_eval import action
    from .viewer import prepare_viewer,learner_first_state
    opponent=opponent or ('galactus' if family=='chronos' else 'chronos')
    if opponent not in ('chronos','galactus'):raise ValueError('Watch opponent must be chronos or galactus')
    run=run_path(name);cfg=read(run/'config.json');actor_path=champion(run,family)
    actor=torch.jit.load(str(actor_path),map_location='cpu').eval();torch.set_num_threads(1)
    body=check_actor(actor_path,family)['contract']['hitbox']
    lock=ROOT/'work/rlviser-watch.lock';lock.parent.mkdir(parents=True,exist_ok=True)
    with FileLock(str(lock),timeout=0),chdir(ROOT):
        prepare_viewer(mode='auto')
        from rlgym.rocket_league.rlviser import RLViserRenderer
        env=ForgeEnv(cfg,family,[dict(name=opponent)],profile='match',side=0,scenario='kickoff')
        renderer=RLViserRenderer(tick_rate=15)
        try:
            obs,_=env.reset(seed=271031)
            opponent_body='breakout' if opponent=='chronos' else 'octane'
            print(f'WATCH: blue/car 1 = {label} {family} actor ({body}); orange = original {opponent} ({opponent_body}). FOV110 distance270 pitch-4 ballcam. Ctrl+C stops.',flush=True)
            while True:
                started=time.monotonic();obs,_,terminal,_,info=env.step(action(actor,obs,family))
                renderer.render(learner_first_state(env.arena.state,env.arena.agent),{})
                if terminal:print('MATCH:',info,flush=True);obs,_=env.reset()
                time.sleep(max(0,1/15-(time.monotonic()-started)))
        except KeyboardInterrupt:pass
        finally:
            try:renderer.close()
            finally:env.close()
