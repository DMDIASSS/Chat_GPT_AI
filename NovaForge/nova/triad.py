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
import sys
import numpy as np
import torch
from .core import ROOT,sha256
from .giga_teachers import TABLE,build_features,native_action_mask

NAMES=('chronos','galactus','ripple')


class FairSelector:
    def __init__(self,seed=271,window=60,names=NAMES):
        self.names=tuple(names);self.n=len(names)
        self.rng=np.random.default_rng(seed);self.recent=deque(maxlen=window)
        self.ages=np.zeros(self.n,dtype=np.int64);self.counts=np.zeros(self.n,dtype=np.int64);self.last=None
    def probabilities(self):
        repeats=np.bincount(list(self.recent),minlength=self.n)
        scores=(1+np.minimum(self.ages,1000)/4.)**.75/(1+repeats)**.5
        if self.last is not None:scores[self.last]*=.35
        return scores/scores.sum()
    def choose(self):
        choice=int(self.rng.choice(self.n,p=self.probabilities()))
        self.record(choice)
        return choice
    def record(self,choice):
        self.ages+=1;self.ages[choice]=0;self.counts[choice]+=1
        self.recent.append(choice);self.last=choice
    def status(self):
        return dict(last=self.names[self.last] if self.last is not None else None,
            selections=dict(zip(self.names,map(int,self.counts))),waiting_decisions=dict(zip(self.names,map(int,self.ages))),
            next_probabilities=dict(zip(self.names,map(float,self.probabilities()))))


class TriadClock:
    def __init__(self,seed=271,selector_path=None,body='breakout'):
        from .triad_selector import teacher_pool
        self.gate=None
        if selector_path is not None:
            from .triad_selector import Gate
            self.gate=Gate(selector_path,body)
        self.names=self.gate.names if self.gate is not None else NAMES
        self.teacher=teacher_pool(self.gate.fusion_path if self.gate is not None else None,self.names)
        self.selector=FairSelector(seed,names=self.names)
        if len(self.names)==6:
            from .six_experts import Clock
            self.native_clock=Clock(self.teacher,self.gate,self.selector.counts)
        self.reset()
    def status(self):
        if self.gate is None:return dict(mode='random',**self.selector.status())
        return dict(mode='learned',last=self.selector.names[self.selector.last] if self.selector.last is not None else None,
            selections=dict(zip(self.selector.names,map(int,self.selector.counts))),**self.gate.status())
    def reset(self):
        self.previous=np.zeros(8,np.float32);self.held=np.zeros(8,np.float32)
        self.pending=None;self.next_decision=None;self.last_frame=None;self.initialized=False
        if self.gate is not None:self.gate.reset()
        if hasattr(self,'native_clock'):self.native_clock.initialized=False
    def controls(self,state,agent,rng):
        frame=int(state.tick_count)
        if self.last_frame is not None and frame<self.last_frame:self.reset()
        self.last_frame=frame
        if hasattr(self,'native_clock'):
            if not self.native_clock.initialized:self.native_clock.reset(state,agent,rng)
            controls=self.native_clock.update(state);self.selector.last=self.native_clock.last_choice
            return controls
        if not self.initialized:
            self.teacher.reset(state,agent,rng);self.initialized=True
        if self.pending is not None and frame>=self.pending[0]:
            self.held=self.pending[1].copy();self.pending=None
        if self.next_decision is None or frame>=self.next_decision:
            obs,mirror=build_features(state,agent,self.previous,rng,'chronos')
            experts=self.teacher.proposals(state,self.previous,obs,mirror)
            if self.gate is None:selected=self.selector.choose()
            else:selected=self.gate.choose(obs);self.selector.record(selected)
            command=experts[selected].copy()
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


def create_live_bot(agent_id,selector_path=None,body='breakout'):
    from rlbot.managers.hivemind import Hivemind
    from rlbot.flat import ControllerState,MatchPhase
    from rlgym_compat import GameState
    class TriadBot(Hivemind):
        def __init__(self):
            super().__init__(agent_id);torch.set_num_threads(1)
            self.clock=None;self.rng=np.random.default_rng(271);self.last_frame=None;self.last_log=-10000
        def initialize(self):
            self._logger.info('Loading pinned frozen experts after connecting')
            self.clock=TriadClock(selector_path=selector_path,body=body);self.create_state()
            self._logger.info('TRIAD_READY: %s selector, %s body, experts=%s','learned' if self.clock.gate else 'fair random',body,self.clock.names)
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
                self._logger.info('Triad selection: %s',json.dumps(self.clock.status()));self.last_log=frame
            return {index:ControllerState(*[float(v) for v in controls[:5]],*[bool(v) for v in controls[5:]])}
    return TriadBot()


def run_live(agent_id,selector_path=None,body='breakout'):
    create_live_bot(agent_id,selector_path,body).run(wants_match_communications=False,wants_ball_predictions=False)


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
        print('TRIAD_CHECK_PASS',json.dumps(policy.clock.status()))
    finally:env.close()


def watch(selector_path=None):
    from contextlib import chdir
    from filelock import Timeout
    if selector_path is not None:
        from .triad_selector import resolve
        selector_path=resolve(selector_path).resolve()
    try:
        # rlviser-py spawns ./rlviser.exe and reads settings.txt from cwd.
        # The second project's launchers start in the sibling triadbot folder.
        with chdir(ROOT):_watch_in_project(selector_path)
    except Timeout as error:
        raise RuntimeError('A NovaForge/Triad viewer session is already running. Stop its watch console with Ctrl+C, close RLViser, then retry.') from error


def _watch_in_project(selector_path=None):
    if selector_path is not None:
        from .triad_selector import selector_meta,SIX_NAMES
        if tuple(selector_meta(selector_path)['contract']['actions'])==SIX_NAMES:
            from .six_selector import watch
            return watch(selector_path)
    from filelock import FileLock
    from .viewer import prepare_viewer,learner_first_state
    from .training import load_config
    from .environment import ArenaEnv
    from .teachers import fetch_teachers
    print('TRIAD_WATCH_START:', 'latest learned selector' if selector_path else 'random expert selection',flush=True)
    print('Viewer working directory:',ROOT,flush=True)
    fetch_teachers(['chronos','galactus','ripple']);torch.set_num_threads(1)
    lock=ROOT/'work/rlviser-watch.lock';lock.parent.mkdir(parents=True,exist_ok=True)
    with FileLock(str(lock),timeout=0):
        prepare_viewer(mode='auto')
        from rlgym.rocket_league.rlviser import RLViserRenderer
        cfg=load_config(ROOT/'configs/chronos.json')
        if selector_path is not None:
            from .triad_selector import selector_meta
            cfg['env']['learner_hitbox']=selector_meta(selector_path)['hitbox']
        env=ArenaEnv(cfg,opponent='chronos',scenario='kickoff')
        renderer=RLViserRenderer(tick_rate=30);policy=TriadPolicy();last_log=0.
        if selector_path is not None:policy.clock=TriadClock(selector_path=selector_path,body=cfg['env'].get('learner_hitbox','breakout'))
        try:
            env.reset(seed=271);policy.reset(env.state,env.agent,np.random.default_rng(271))
            print('RLViser opens on the first frame. Follow car 1 is Triad; opponent is Chronos. Ctrl+C stops viewing.',flush=True)
            while True:
                start=time.monotonic();_,_,term,trunc,_=env.step_controls(policy.controls_for_ticks(env.state))
                renderer.render(learner_first_state(env.state,env.agent),{})
                if time.monotonic()-last_log>3:
                    print(json.dumps(policy.clock.status()),flush=True);last_log=time.monotonic()
                if term or trunc:env.reset();policy.reset(env.state,env.agent,np.random.default_rng(271))
                time.sleep(max(0,1/30-(time.monotonic()-start)))
        except KeyboardInterrupt:pass
        finally:
            try:renderer.close()
            finally:env.close()


def export(selector_path=None,destination_parent=None):
    from .teachers import fetch_teachers,verify_teacher
    parent=Path(destination_parent) if destination_parent is not None else ROOT.parent/'triadbot/exports'
    parent.mkdir(parents=True,exist_ok=True)
    stem='TriadBot_'+uuid.uuid4().hex[:8];destination=parent/stem
    body='breakout'
    names=NAMES
    if selector_path is not None:
        from .triad_selector import resolve,selector_meta
        from .core import check_model
        selector_path=resolve(selector_path);selector_info=selector_meta(selector_path);body=selector_info['hitbox']
        names=tuple(selector_info['contract']['actions'])
        from .triad_selector import Gate
        Gate(selector_path,body) # validate source pins and owned teacher before bundling
    external=[n for n in names if n!='fusion'];fetch_teachers(external)
    with tempfile.TemporaryDirectory(dir=parent) as temp:
        stage=Path(temp)/stem;stage.mkdir()
        shutil.copytree(ROOT/'nova',stage/'nova',ignore=shutil.ignore_patterns('__pycache__'))
        for name in ('requirements.txt','teachers.lock.json','extra_teachers.lock.json','THIRD_PARTY.md'):shutil.copy2(ROOT/name,stage/name)
        for name in external:shutil.copytree(verify_teacher(name),stage/'assets'/name)
        if selector_path is not None:
            shutil.copy2(selector_path,stage/'selector.pt');shutil.copy2(str(selector_path)+'.json',stage/'selector.pt.json')
            if 'fusion_teacher' in selector_info:
                from .triad_selector import fusion_asset
                from .core import write_model_meta
                frozen=fusion_asset(selector_path.parent,selector_info['fusion_teacher']);target=stage/'assets/fusion/actor.pt';target.parent.mkdir(parents=True)
                shutil.copy2(frozen,target);shutil.copy2(str(frozen)+'.json',str(target)+'.json')
                details={k:v for k,v in selector_info.items() if k not in ('contract','sha256','fusion_teacher')}
                write_model_meta(stage/'selector.pt',contract=selector_info['contract'],
                    fusion_teacher=dict(path='assets/fusion/actor.pt',sha256=sha256(target)),**details)
        agent_id='DMDIASSS/'+stem
        (stage/'run_triad.py').write_text('from nova.triad_boot import main\nif __name__=="__main__":main('+repr(agent_id)+', '+repr(body)+')\n')
        from .triad_boot import write_launchers
        write_launchers(stage,sys.executable,agent_id,body,selector_path is not None,
            fusion=selector_path is not None and 'fusion_teacher' in selector_info,names=names)
        (stage/'INSTALL.bat').write_text('@echo off\ncd /d "%~dp0"\npy -3.11 -m venv .venv\nif errorlevel 1 goto failed\n".venv\\Scripts\\python.exe" -m pip install torch==2.9.1 --index-url https://download.pytorch.org/whl/cpu\nif errorlevel 1 goto failed\n".venv\\Scripts\\python.exe" -m pip install -r requirements.txt\nif errorlevel 1 goto failed\necho TRIAD_INSTALLED - add bot.portable.bot.toml in RLBot v5.\npause\nexit /b 0\n:failed\necho INSTALL_FAILED\npause\nexit /b 1\n')
        (stage/'README.txt').write_text('LOCAL: import bot.bot.toml immediately; it uses the exporting Python environment. No INSTALL step is required while that environment stays installed.\nPORTABLE: on another PC run INSTALL.bat, then import bot.portable.bot.toml. Startup diagnostics go to startup.log. DIAGNOSE.bat loads all models without Rocket League.\nDefault body is Breakout. A live car keeps one hitbox while controllers switch; Octane alternatives are generated only for random mode. The learned selector is trained for its fixed body.\nLearned mode selects among three frozen models and commits for 8 decisions (~0.53s). Random mode retains waiting/repetition probabilities. Three models remain separate.\nRipple 276->90 projection and held-control queue approximation can lose skills. No strength gain is claimed. Original notices/hashes are preserved; no new model-license grant is implied.\n')
        if selector_path is not None and 'fusion_teacher' in selector_info:
            with (stage/'README.txt').open('a') as f:f.write('FOUR-EXPERT MODE: this export also contains the hash-locked local Fusion actor under assets/fusion. The four experts stay separate and frozen. The description of three-model mode above applies to the original selector only.\n')
        if len(names)==6:
            (stage/'README.txt').write_text('SIX-EXPERT OCTANE MODE: Chronos, Galactus V2, frozen local Fusion, Ducky, Rain 1v1 and Megabyte. Ripple is not bundled. Native 6/8-tick expert periods; greedy gate commits for 8 decisions. LOCAL: import bot.bot.toml using the exporting Python. PORTABLE: run INSTALL.bat, then import bot.portable.bot.toml. DIAGNOSE.bat checks model loading. startup.log records selection. Ducky V3 prediction uses installed RocketSim instead; no native strength parity claim. Model hashes and original readmes retained under assets.\n')
        (stage/'DIAGNOSE.bat').write_text('@echo off\ncd /d "%~dp0"\n"'+sys.executable+'" run_triad.py --diagnose\npause\n')
        files=sorted(p for p in stage.rglob('*') if p.is_file())
        (stage/'MANIFEST.sha256').write_text(''.join(sha256(p)+'  '+p.relative_to(stage).as_posix()+'\n' for p in files))
        archive=Path(temp)/(stem+'.zip')
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
            for p in sorted(stage.rglob('*')):
                if p.is_file():z.write(p,stem+'/'+p.relative_to(stage).as_posix())
        stage.replace(destination);archive.replace(parent/(stem+'.zip'))
    print('TRIAD_EXPORT_READY:',destination/'bot.bot.toml',flush=True)
    return destination


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
        def world_controls(self,obs):
            env=self.env;choices=self.teacher.proposals(env.arena.state,env.previous,obs[:225],env.mirror)
            return choices[self.selector.choose()]
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
