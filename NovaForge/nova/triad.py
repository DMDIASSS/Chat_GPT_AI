"""Three frozen experts, one age/repetition-weighted controller per decision."""
from __future__ import annotations
from collections import Counter,deque
import json
from pathlib import Path
import shutil
import tempfile
import time
import uuid
import zipfile
import numpy as np
import torch
from .core import ROOT,sha256
from .giga_teachers import TABLE,build_features,native_action_mask

NAMES=('chronos','galactus','ripple')


class FairSelector:
    def __init__(self,seed=271,window=60):
        self.rng=np.random.default_rng(seed);self.recent=deque(maxlen=window)
        self.ages=np.zeros(3,dtype=np.int64);self.counts=np.zeros(3,dtype=np.int64);self.last=None
    def probabilities(self):
        repeats=np.bincount(list(self.recent),minlength=3)
        scores=(1+np.minimum(self.ages,1000)/4.)**.75/(1+repeats)**.5
        if self.last is not None:scores[self.last]*=.35
        return scores/scores.sum()
    def choose(self):
        choice=int(self.rng.choice(3,p=self.probabilities()))
        self.ages+=1;self.ages[choice]=0;self.counts[choice]+=1
        self.recent.append(choice);self.last=choice
        return choice
    def status(self):
        return dict(last=NAMES[self.last] if self.last is not None else None,
            selections=dict(zip(NAMES,map(int,self.counts))),waiting_decisions=dict(zip(NAMES,map(int,self.ages))),
            next_probabilities=dict(zip(NAMES,map(float,self.probabilities()))))


class TriadClock:
    def __init__(self,seed=271):
        from .chronos_fusion import TeacherFusion
        self.teacher=TeacherFusion();self.selector=FairSelector(seed);self.reset()
    def reset(self):
        self.previous=np.zeros(8,np.float32);self.held=np.zeros(8,np.float32)
        self.pending=None;self.next_decision=None;self.last_frame=None;self.initialized=False
    def controls(self,state,agent,rng):
        frame=int(state.tick_count)
        if self.last_frame is not None and frame<self.last_frame:self.reset()
        self.last_frame=frame
        if not self.initialized:
            self.teacher.reset(state,agent,rng);self.initialized=True
        if self.pending is not None and frame>=self.pending[0]:
            self.held=self.pending[1].copy();self.pending=None
        if self.next_decision is None or frame>=self.next_decision:
            obs,mirror=build_features(state,agent,self.previous,rng,'chronos')
            experts=self.teacher.distributions(state,self.previous,obs,mirror)
            selected=self.selector.choose();mask=native_action_mask(state.cars[agent])
            command=TABLE[int(np.where(mask,experts[selected],-np.inf).argmax())].copy()
            if mirror:command[[1,3,4]]*=-1
            self.previous=command.copy();self.pending=(frame+7,command);self.next_decision=frame+8
        return self.held.copy()


class TriadPolicy:
    def __init__(self):self.clock=TriadClock()
    def reset(self,state,agent,rng):self.agent=agent;self.rng=rng;self.clock.reset()
    def controls_for_ticks(self,state,ticks=4):
        if ticks!=4:raise ValueError('Triad simulator uses four-tick calls')
        controls=self.clock.controls(state,self.agent,self.rng)
        result=np.repeat(controls[None,:],4,axis=0)
        if self.clock.pending is not None:
            due,command=self.clock.pending
            if due<int(state.tick_count)+4:
                result[max(0,due-int(state.tick_count)):]=command
                self.clock.held=command.copy();self.clock.pending=None
        return result


def run_live(agent_id):
    from rlbot.managers.hivemind import Hivemind
    from rlbot.flat import ControllerState,MatchPhase
    from rlgym_compat import GameState
    class TriadBot(Hivemind):
        def __init__(self):
            super().__init__(agent_id);torch.set_num_threads(1)
            self.clock=TriadClock();self.rng=np.random.default_rng(271);self.last_frame=None;self.last_log=-10000
        def initialize(self):self.create_state()
        def create_state(self):self.state=GameState.create_compat_game_state(self.field_info,self.match_config)
        def get_outputs(self,packet):
            if len(packet.players)!=2 or not packet.balls or len(self.indices)!=1:
                return {i:ControllerState() for i in self.indices}
            frame=int(packet.match_info.frame_num)
            if self.last_frame is not None and frame<self.last_frame:
                self.create_state();self.clock.reset();self.last_log=-10000
            self.last_frame=frame;self.state.update(packet)
            if packet.match_info.match_phase not in (MatchPhase.Active,MatchPhase.Kickoff):
                self.clock.reset();return {i:ControllerState() for i in self.indices}
            index=next(iter(self.indices));agent=packet.players[index].player_id
            controls=self.clock.controls(self.state,agent,self.rng)
            if frame-self.last_log>=600:
                self._logger.info('Triad selection: %s',json.dumps(self.clock.selector.status()));self.last_log=frame
            return {index:ControllerState(*[float(v) for v in controls[:5]],*[bool(v) for v in controls[5:]])}
    TriadBot().run()


def check():
    from .teachers import fetch_teachers
    from .chronos import ChronosEnv
    from .training import load_config
    fetch_teachers(['chronos','galactus','ripple']);torch.set_num_threads(1)
    cfg=load_config(ROOT/'configs/chronos.json');env=ChronosEnv(cfg,opponent='scorer',scenario='kickoff')
    try:
        env.reset(seed=271);policy=TriadPolicy();policy.reset(env.arena.state,env.arena.agent,np.random.default_rng(271))
        for _ in range(30):
            controls=policy.controls_for_ticks(env.arena.state)
            assert controls.shape==(4,8) and np.isfinite(controls).all()
            env.arena.step_controls(controls)
        print('TRIAD_CHECK_PASS',json.dumps(policy.clock.selector.status()))
    finally:env.close()


def watch():
    from filelock import FileLock
    from .viewer import prepare_viewer,learner_first_state
    from .training import load_config
    from .environment import ArenaEnv
    from .teachers import fetch_teachers
    fetch_teachers(['chronos','galactus','ripple']);torch.set_num_threads(1)
    lock=ROOT/'work/rlviser-watch.lock';lock.parent.mkdir(parents=True,exist_ok=True)
    with FileLock(str(lock),timeout=0):
        prepare_viewer(mode='auto')
        from rlgym.rocket_league.rlviser import RLViserRenderer
        cfg=load_config(ROOT/'configs/chronos.json');env=ArenaEnv(cfg,opponent='chronos',scenario='kickoff')
        renderer=RLViserRenderer(tick_rate=30);policy=TriadPolicy();last_log=0.
        try:
            env.reset(seed=271);policy.reset(env.state,env.agent,np.random.default_rng(271))
            while True:
                start=time.monotonic();_,_,term,trunc,_=env.step_controls(policy.controls_for_ticks(env.state))
                renderer.render(learner_first_state(env.state,env.agent),{})
                if time.monotonic()-last_log>3:
                    print(json.dumps(policy.clock.selector.status()),flush=True);last_log=time.monotonic()
                if term or trunc:env.reset();policy.reset(env.state,env.agent,np.random.default_rng(271))
                time.sleep(max(0,1/30-(time.monotonic()-start)))
        except KeyboardInterrupt:pass
        finally:
            try:renderer.close()
            finally:env.close()


def export():
    from .teachers import fetch_teachers,verify_teacher
    fetch_teachers(['chronos','galactus','ripple'])
    parent=ROOT.parent/'triadbot/exports';parent.mkdir(parents=True,exist_ok=True)
    stem='TriadBot_'+uuid.uuid4().hex[:8];destination=parent/stem
    with tempfile.TemporaryDirectory(dir=parent) as temp:
        stage=Path(temp)/stem;stage.mkdir()
        shutil.copytree(ROOT/'nova',stage/'nova',ignore=shutil.ignore_patterns('__pycache__'))
        for name in ('requirements.txt','teachers.lock.json','THIRD_PARTY.md'):shutil.copy2(ROOT/name,stage/name)
        for name in NAMES:shutil.copytree(verify_teacher(name),stage/'assets'/name)
        agent_id='DMDIASSS/'+stem
        (stage/'run_triad.py').write_text('from nova.triad import run_live\nif __name__=="__main__":run_live('+repr(agent_id)+')\n')
        win=json.dumps('".venv\\Scripts\\python.exe" run_triad.py');linux=json.dumps('".venv/bin/python" run_triad.py')
        (stage/'bot.bot.toml').write_text('[settings]\nname = "TriadBot random experts"\nagent_id = '+json.dumps(agent_id)+'\nrun_command = '+win+'\nrun_command_linux = '+linux+'\nhivemind = true\n\n[details]\ndeveloper = "NovaForge user; models credited to original authors"\ndescription = "Three frozen models with age/repetition weighted selection. Experimental timing/action projections."\nlanguage = "python"\ntags = ["1v1"]\n')
        (stage/'INSTALL.bat').write_text('@echo off\ncd /d "%~dp0"\npy -3.11 -m venv .venv\nif errorlevel 1 goto failed\n".venv\\Scripts\\python.exe" -m pip install torch==2.9.1 --index-url https://download.pytorch.org/whl/cpu\nif errorlevel 1 goto failed\n".venv\\Scripts\\python.exe" -m pip install -r requirements.txt\nif errorlevel 1 goto failed\necho TRIAD_INSTALLED - add bot.bot.toml in RLBot v5.\npause\nexit /b 0\n:failed\necho INSTALL_FAILED\npause\nexit /b 1\n')
        (stage/'README.txt').write_text('Portable personal runtime export. Run INSTALL.bat with Python 3.11 x64, then import bot.bot.toml into RLBot v5 for offline 1v1. Three original networks remain separate; this is not one merged .pt/.lt.\nOne model controls each 8-tick decision. Waiting models gain probability; recent/frequent selections lose probability. Selection statistics print to the bot log. All models stay frozen.\nRipple 276->90 projection and its held-control queue approximation can lose skills. Switching experts can disrupt mechanics; no strength gain is claimed.\nOriginal teacher notices and hashes are preserved under assets and THIRD_PARTY.md. No new redistribution license is granted.\n')
        files=sorted(p for p in stage.rglob('*') if p.is_file())
        (stage/'MANIFEST.sha256').write_text(''.join(sha256(p)+'  '+p.relative_to(stage).as_posix()+'\n' for p in files))
        archive=Path(temp)/(stem+'.zip')
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
            for p in sorted(stage.rglob('*')):
                if p.is_file():z.write(p,stem+'/'+p.relative_to(stage).as_posix())
        stage.replace(destination);archive.replace(parent/(stem+'.zip'))
    print('TRIAD_EXPORT_READY:',destination/'bot.bot.toml',flush=True)


def league():
    from .teachers import fetch_teachers
    from .chronos_fusion import TeacherFusion
    from .chronos_league import match_suite,match_summary
    from .chronos_guard import paired_statistics
    from .training import load_config
    from .core import atomic_json
    fetch_teachers(['chronos','galactus','ripple','nexto']);torch.set_num_threads(1)
    class RandomExpert:
        def __init__(self):self.teacher=TeacherFusion();self.selector=FairSelector()
        def bind(self,env):
            self.env=env;self.selector=FairSelector(271)
            self.teacher.reset(env.arena.state,env.arena.agent,np.random.default_rng(271))
        def action(self,obs):
            env=self.env;choices=self.teacher.distributions(env.arena.state,env.previous,obs[:225],env.mirror)
            return int(choices[self.selector.choose()].argmax())
    candidate=RandomExpert()
    class Original:
        def action(self,obs):
            with torch.inference_mode():logits=candidate.teacher.chronos(torch.from_numpy(obs[:225])[None,:])[0].numpy()
            return int(np.where(obs[225:]>0,logits,-np.inf).argmax())
    parent=ROOT.parent/'triadbot/reports';parent.mkdir(parents=True,exist_ok=True)
    rows,baseline=match_suite(load_config(ROOT/'configs/chronos.json'),candidate,Original(),2,60,77130001,parent/'STOP')
    output=parent/f'TriadBot_wdl_{uuid.uuid4().hex[:8]}.json'
    atomic_json(output,dict(kind='triad_timed_matches',summary=match_summary(rows),baseline_summary=match_summary(baseline),
        statistics=paired_statistics(rows,baseline),trials=rows,baseline_trials=baseline,
        note='Compared with original Chronos; timed simulator matches, no goal pauses/overtime.'))
    print('TRIAD_WDL_READY:',output)
