"""Preserve a match-confirmed training reference; never silently promote weights.

The existing DuelForge panel is a simulator validation protocol, not a regulation
tournament or the older GigaForge direct-h2h-v1 protocol.
"""
import json
from pathlib import Path
import numpy as np
from .runtime import sha,pin,atomic_json
from .evaluate import summary,evaluate

CHECK_EVERY=5_000_000

def qualify(result,candidate_hash,parent_hash):
    if result.get('candidate_sha256')!=candidate_hash or result.get('opponent_sha256')!=parent_hash:return None
    rows=result.get('games',[])
    if len(rows)<2000 or len(rows)%2 or result.get('contexts',{}).keys()!={'match'}:return None
    blocks={};seeds=set()
    for r in rows:
        if r.get('context')!='match' or r.get('color') not in (0,1) or r.get('seconds',0)<100:return None
        if r.get('outcome')!=int(np.sign(r['goals_for']-r['goals_against'])):return None
        blocks.setdefault(r['pair'],[]).append(r)
    for block in blocks.values():
        if len(block)!=2 or {r['color'] for r in block}!={0,1}:return None
        if block[0]['native_seed']!=block[1]['native_seed']:return None
        seed=block[0]['native_seed']
        if seed in seeds or not 0xC0000000<=seed<0xD0000000:return None
        seeds.add(seed)
    s=summary(rows)
    return s if s['score_interval_95'][0]>.5 else None

def reference(root,folder):
    """Only an exact, independently evaluated checkpoint can establish a reference."""
    root=Path(root);folder=Path(folder);file=root/'match_reference.json'
    if not file.is_file() and (not (folder/'latest.pt').is_file() or not (folder/'initial.pt').is_file()):return None
    parent_hash=sha(folder/'initial.pt')
    if file.is_file():
        info=json.loads(file.read_text());actor=folder/info['actor_path']
        proof=folder/info['evaluation_file']
        if sha(actor)!=info['actor_sha256'] or parent_hash!=info['parent_sha256'] or sha(proof)!=info['evaluation_sha256']:
            raise ValueError('Match reference or its proof changed; training remains paused')
        return info
    candidate=sha(folder/'latest.pt')
    for proof in sorted(folder.glob('eval_*.json'),reverse=True):
        result=json.loads(proof.read_text());stats=qualify(result,candidate,parent_hash)
        if stats is None:continue
        actor,identity=pin(folder,folder/'latest.pt','match_confirmed_reference')
        info={'actor_path':str(actor.relative_to(folder)),'actor_sha256':identity,
              'parent_sha256':parent_hash,'evaluation_file':proof.name,'evaluation_sha256':sha(proof),
              'learning_transitions':result['candidate_learning_transitions'],'result':stats,
              'check_every_additional_steps':CHECK_EVERY,
              'scope':'Match-confirmed reference for further training under DuelForge panel conditions. No tournament promotion or general bot-strength claim.'}
        atomic_json(file,info)
        print('MATCH_REFERENCE_PINNED:',info['learning_transitions'],'score',round(stats['score_rate']*100,2),'%; original confirmed weights preserved.',flush=True)
        return info
    return None

def check(root,folder,state,reached,ref):
    last=state.get('last_reference_check_steps',ref['learning_transitions'])
    if reached-last<CHECK_EVERY:return False
    print('MATCH_REGRESSION_CHECK: 200 fresh-seed games versus pinned confirmed reference.',flush=True)
    result=evaluate(folder,games_per_context=200,seconds=100,
                    opponent=Path(folder)/ref['actor_path'],contexts=['match'])
    state['last_reference_check_steps']=reached
    state['reference_comparison']={'candidate_steps':reached,'candidate_sha256':result['candidate_sha256'],
                                    'reference_sha256':ref['actor_sha256'],'result':result['overall']}
    failed=result['overall']['score_interval_95'][1]<.5
    if failed:state['status']='match_regression_paused'
    print('MATCH_REGRESSION_RESULT:',result['overall'],'pause',failed,flush=True)
    atomic_json(Path(root)/'curriculum.json',state)
    return failed
