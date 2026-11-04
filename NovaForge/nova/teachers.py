from __future__ import annotations

import importlib.util
import json
import shutil
import urllib.request
from pathlib import Path

import numpy as np
import torch

from .core import ROOT, TICK_SKIP, ACTIONS, as_v1, observe, sha256, atomic_json
from .models import FrozenActor

ASSETS=ROOT/'assets'


def _entries(group):
    return [a for a in json.loads((ROOT/'teachers.lock.json').read_text()) if a['group']==group]


def _patch_nexto(data):
    source=data.decode('utf8')
    source=source.replace('from rlgym_compat.common_values import BLUE_TEAM, ORANGE_TEAM',
                          'from rlgym.rocket_league.common_values import BLUE_TEAM, ORANGE_TEAM')
    source=source.replace('from rlgym_compat.game_state import GameState, PlayerData',
        'from rlgym_tools.rocket_league.v1 import V1GameState as GameState, V1PlayerData as PlayerData')
    return ('# NovaForge modification: import V1 types from rlgym-tools; no feature changes.\n'+source).encode('utf8')


def fetch_teachers(groups):
    """Download immutable upstream files, verify bytes, and preserve notices."""
    import rlgym.rocket_league.sim as sim
    for group in groups:
        if group not in ('nexto','ripple'):
            raise ValueError(f'No verified headless adapter for {group}')
        target=ASSETS/group
        target.mkdir(parents=True,exist_ok=True)
        installed={}
        for entry in _entries(group):
            dst=target/entry['target']
            source_file=target/('upstream_'+entry['target']) if entry['target']=='nexto_obs.py' else dst
            if not source_file.exists() or sha256(source_file)!=entry['sha256']:
                print(f'Downloading {group}/{entry["target"]}',flush=True)
                with urllib.request.urlopen(entry['url'],timeout=120) as response:
                    data=response.read(32*1024*1024+1)
                import hashlib
                if hashlib.sha256(data).hexdigest()!=entry['sha256']:
                    raise ValueError(f'Upstream hash mismatch: {entry["url"]}')
                temp=source_file.with_suffix(source_file.suffix+'.tmp')
                temp.write_bytes(data)
                temp.replace(source_file)
            if entry['target']=='nexto_obs.py':
                dst.write_bytes(_patch_nexto(source_file.read_bytes()))
            installed[dst.name]=sha256(dst)
        if group=='ripple':
            meshes=Path(sim.__file__).parent/'collision_meshes'
            shutil.copytree(meshes,target/'collision_meshes',dirs_exist_ok=True)
        atomic_json(target/'installed.json',installed)
        print(f'{group}: files verified. License/notices: {target}',flush=True)


def verify_teacher(group):
    target=ASSETS/group
    manifest=target/'installed.json'
    if not manifest.exists():
        raise FileNotFoundError(f'{group} assets absent. Run: python run.py fetch-teachers --names {group}')
    installed=json.loads(manifest.read_text())
    expected_names={e['target'] for e in _entries(group)}
    if set(installed)!=expected_names:
        raise ValueError(f'Invalid asset manifest for {group}')
    for entry in _entries(group):
        file=target/entry['target']
        if sha256(file)!=installed[file.name]:
            raise ValueError(f'Modified teacher asset: {file}')
        # Check against the built-in lock too; editing installed.json cannot relabel a model.
        if entry['target']!='nexto_obs.py' and installed[file.name]!=entry['sha256']:
            raise ValueError(f'Teacher identity mismatch: {file}')
        if entry['target']=='nexto_obs.py':
            original=target/'upstream_nexto_obs.py'
            if sha256(original)!=entry['sha256'] or file.read_bytes()!=_patch_nexto(original.read_bytes()):
                raise ValueError('Nexto feature code does not match the pinned import-only adaptation')
    return target


def _module(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Scripted:
    def reset(self,state,agent,rng):
        self.agent=agent
        self.previous=np.zeros(8,dtype=np.float32)
        self.counter=0

    def act(self,state):
        car=state.cars[self.agent]
        delta=state.ball.position-car.physics.position
        angle=np.arctan2(np.dot(delta,car.physics.right),np.dot(delta,car.physics.forward))
        distance=np.linalg.norm(delta)
        steer=float(np.clip(angle*3,-1,1))
        self.counter+=1
        self.previous=np.array([1,steer,0,steer,0,
            car.on_ground and distance<320 and state.ball.position[2]>160 and self.counter%8<3,
            abs(angle)<.2 and distance>700 and car.boost_amount>0,
            abs(angle)>1.5],dtype=np.float32)
        return self.previous.copy()


class Snapshot:
    def __init__(self,path):
        self.actor=FrozenActor(path)
    def reset(self,state,agent,rng):
        self.agent=agent
        self.previous=np.zeros(8,dtype=np.float32)
    def act(self,state):
        self.previous=ACTIONS[self.actor.action(observe(state,self.agent,self.previous))].copy()
        return self.previous.copy()


class Nexto:
    """Pinned Nexto neural policy at 8 ticks. Stock scripted kickoff is not included."""
    def __init__(self):
        path=verify_teacher('nexto')
        self.model=torch.jit.load(str(path/'policy.pt'),map_location='cpu').eval()
        self.obs=_module(path/'nexto_obs.py','nova_nexto_obs').NextoObsBuilder(tick_skip=8)
        from rlgym.rocket_league.action_parsers import LookupTableAction
        self.table=np.asarray(LookupTableAction.make_lookup_table(),dtype=np.float32)
    def reset(self,state,agent,rng):
        self.agent=agent
        self.rng=rng
        self.previous=np.zeros(8,dtype=np.float32)
        self.next_tick=state.tick_count
        self.obs.reset(as_v1(state))
    def act(self,state):
        if state.tick_count>=self.next_tick:
            legacy=as_v1(state)
            own=next(p for p in legacy.players if p.team_num==state.cars[self.agent].team_num)
            obs=self.obs.build_obs(own,legacy,self.previous)
            with torch.inference_mode():
                out=self.model(tuple(torch.as_tensor(x,dtype=torch.float32) for x in obs))
            logits=out[0] if isinstance(out,tuple) else out
            if logits.shape!=(1,90) or not torch.isfinite(logits).all():
                raise ValueError('Nexto logits are invalid')
            self.previous=self.table[int(logits.argmax(-1).item())].copy()
            self.next_tick=state.tick_count+8
        return self.previous.copy()


class Ripple:
    """Upstream obs, action table and six-slot queue, fixed deterministic RL v1.1."""
    def __init__(self):
        path=verify_teacher('ripple')
        import onnxruntime as ort
        options=ort.SessionOptions()
        options.intra_op_num_threads=1
        options.inter_op_num_threads=1
        options.execution_mode=ort.ExecutionMode.ORT_SEQUENTIAL
        self.session=ort.InferenceSession(str(path/'policy.onnx'),options,providers=['CPUExecutionProvider'])
        self.obs_type=_module(path/'obs.py','nova_ripple_obs').RippleObs
        self.parser_type=_module(path/'act.py','nova_ripple_act').RippleAction
        self.queue=np.zeros((6,1,8))
        self.obs=self.obs_type(self.queue)
        self.parser=self.parser_type(self.queue)
    def reset(self,state,agent,rng):
        self.agent=agent
        self.previous=np.zeros(8,dtype=np.float32)
        self.obs.reset(as_v1(state,agent))
    def act(self,state):
        legacy=as_v1(state,self.agent)
        self.obs.pre_step(legacy,controlled_count=1,elapsed_ticks=TICK_SKIP)
        self.obs.prev_prev_actions[:1]=self.previous
        names=('main','others','ball','actions','boosts')
        logits=self.session.run(['logits'],dict(zip(names,self.obs.current_obs)))[0]
        if logits.shape!=(1,276) or not np.isfinite(logits).all():
            raise ValueError('Ripple logits are invalid')
        # The published ONNX graph already reverses side-mirrored action indices.
        self.previous=self.parser.parse_actions(logits.argmax(-1),legacy)[0].astype(np.float32)
        return self.previous.copy()


def make_opponent(name,path=None):
    factories={'scripted':Scripted,'nexto':Nexto,'ripple':Ripple}
    if name=='snapshot': return Snapshot(path)
    if name not in factories:
        raise ValueError(f'Unsupported opponent: {name}')
    return factories[name]()
