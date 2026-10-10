"""Safe additive exporter for Cycle9 Fusion v1 (RLBot v4 only).

Run from project root after AFK PPO is paused. Creates ONE new standalone bot
folder; never modifies any existing exports or source checkpoints.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parent
THIS=ROOT/'fusion_logic.py'
RUNTIME=ROOT/'fusion_runtime.py'
SOURCE_C9=ROOT/'data'/'autoleague'/'backups'/'20261008T224518_775472Z_cycle0009_steps000008192_candidate.pt'
SOURCE_CHAMP=ROOT/'data'/'autoleague'/'champion.pt'
SOURCE_WAVE=ROOT/'data'/'mechanics'/'wavedash'/'last.pt'
EXPECTED={
    'cycle9':'50f34d4a3723bc2849c97200e8e42969e0cc1d82328473b017505994be1966d2',
    'champion':'c9596e2945ca6997f9ed496d90e89a772e519e4377db9989ef0645f827f6501a',
    'wavedash':None,
}

def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()


def replacements(bot_text, agent_text):
    old='from agent import Agent'
    new=old+'\nfrom fusion_runtime import FusionController'
    if bot_text.count(old)!=1:raise ValueError('Unexpected template: Agent import changed')
    bot_text=bot_text.replace(old,new,1)
    old='        self.agent = Agent()'
    new=old+'\n        self.fusion_controller = FusionController(self.agent)'
    if bot_text.count(old)!=1:raise ValueError('Unexpected template: self.agent setup changed')
    bot_text=bot_text.replace(old,new,1)
    old='self.action, weights = self.agent.act(obs, beta)'
    new='self.action, weights = self.fusion_controller.act(obs, beta, player, teammates, opponents, self.game_state, packet, self)'
    if bot_text.count(old)!=1:raise ValueError('Unexpected template: agent action invocation changed')
    bot_text=bot_text.replace(old,new,1)
    old='    def __init__(self):'
    new="    def __init__(self, model_filename='nexto-model.pt'):"
    if agent_text.count(old)!=1:raise ValueError('Unexpected template: Agent constructor changed')
    agent_text=agent_text.replace(old,new,1)
    old='os.path.join(cur_dir, "nexto-model.pt")'
    new='os.path.join(cur_dir, model_filename)'
    if agent_text.count(old)!=1:raise ValueError('Unexpected template: model filepath changed')
    agent_text=agent_text.replace(old,new,1)
    compile(bot_text,'exported/bot.py','exec')
    compile(agent_text,'exported/agent.py','exec')
    return bot_text,agent_text


def preflight():
    for name,p in [('cycle9',SOURCE_C9),('champion',SOURCE_CHAMP),('wavedash',SOURCE_WAVE)]:
        if not p.is_file():raise FileNotFoundError(f'{name} missing: {p}')
        sha=digest(p)
        if EXPECTED[name] and sha!=EXPECTED[name]:
            raise RuntimeError(f'{name} differs from verified source hash; refusing to export: {sha}')
        print(f'CHECK {name}: {sha[:20]}  {p.relative_to(ROOT)}',flush=True)
    from export_rlbot_v4 import TEMPLATE,REQUIRED,model_from_checkpoint
    for f in REQUIRED:
        if not (TEMPLATE/f).is_file():raise FileNotFoundError('Missing RLBot v4 template file '+str(TEMPLATE/f))
    replacements((TEMPLATE/'bot.py').read_text(encoding='utf8'),(TEMPLATE/'agent.py').read_text(encoding='utf8'))
    for p in (THIS,RUNTIME):
        if not p.is_file():raise FileNotFoundError('Install both Fusion Python modules: '+str(p))
    # Important: preflight verifies that the models really accept native weights.
    for p in (SOURCE_C9,SOURCE_CHAMP,SOURCE_WAVE):
        _=model_from_checkpoint(p)
    print('PREFLIGHT PASSED: all three native policies and template hooks are compatible',flush=True)


def build(name):
    import torch
    from export_rlbot_v4 import export, model_from_checkpoint
    preflight()
    out=ROOT/'data'/'rlbot_exports'/name
    if out.exists():raise FileExistsError('Export already exists (no overwrite): '+str(out))
    created=False
    try:
        folder=export(SOURCE_C9,name)
        created=True
        bot_src=(folder/'bot.py').read_text(encoding='utf8')
        agent_src=(folder/'agent.py').read_text(encoding='utf8')
        bt,ag=replacements(bot_src,agent_src)
        (folder/'bot.py').write_text(bt,encoding='utf8')
        (folder/'agent.py').write_text(ag,encoding='utf8')
        shutil.copy2(THIS,folder/'fusion_logic.py')
        shutil.copy2(RUNTIME,folder/'fusion_runtime.py')
        # TorchScript retains the exact original architecture; no weight averaging.
        for p, filename in ((SOURCE_CHAMP,'champion-model.pt'),(SOURCE_WAVE,'wavedash-model.pt')):
            model=model_from_checkpoint(p)
            torch.jit.save(model,str(folder/filename))
            loaded=torch.jit.load(str(folder/filename),map_location='cpu')
            for k,v in model.state_dict().items():
                if not torch.equal(loaded.state_dict()[k],v):raise RuntimeError('Export parity failed: '+filename)
        record={'format':'RLBot v4','experimental':True,
                'not_trained':True,'teamplay':'heuristic deterministic role selection, not learned',
                'policies':{k:{'source':str(p.relative_to(ROOT)),'sha256':digest(p)}
                    for k,p in [('cycle9',SOURCE_C9),('champion',SOURCE_CHAMP),('wavedash',SOURCE_WAVE)]},
                'sources_immutable':True,'switching':'cycle9 attack; champion open finishing; wavedash own-goal danger; second-man goal-side support'}
        (folder/'FUSION_INFO.json').write_text(json.dumps(record,indent=2),encoding='utf8')
        print('FUSION EXPORTED to:',folder,flush=True)
        print('Import RLBot v4 bot.cfg from:',folder/'bot.cfg',flush=True)
    except BaseException:
        # Delete only newly created Fusion export.  Never delete old models.
        if created and out.exists():shutil.rmtree(out)
        raise


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--check',action='store_true')
    parser.add_argument('--name',default='Cycle9_Fusion_v1')
    a=parser.parse_args()
    if a.check:preflight()
    else:build(a.name)

if __name__=='__main__':main()
