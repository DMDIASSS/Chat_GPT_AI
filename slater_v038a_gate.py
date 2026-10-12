"""Slater v0.3.8a: read-only RocketSim physics and stock-Nexto approximation gate.

Commands:
  engine-gate  - do eight physics ticks in one engine call vs eight 1-tick calls
  stress-obs   - more identical-state RLGym/legacy NextoObsBuilder comparisons
  ablation     - greedy/scripted/stock-approx Nexto single-goal episodes

Never trains or saves models. Reports are create-only under data/isolated.
NOTE: This does NOT establish equivalence to live RLBot packets or kickoff pause.
"""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
import random
import hashlib
import numpy as np

VERSION = 'v0.3.8a'
EXPECTED_V037A = 'a647823c227602f9c658a58a3e32b0d18a8dfe0dd1b144eadd93aaf9a856fd44'


def digest(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(2**20),b''):
            h.update(b)
    return h.hexdigest()


def validate_report_path(root, value):
    root=Path(root).resolve()
    dest=(root/value).resolve()
    if not dest.is_relative_to((root/'data'/'isolated').resolve()) or dest.suffix != '.json':
        raise ValueError('Reports must be JSON files under data/isolated')
    if dest.exists() or Path(str(dest)+'.partial').exists():
        raise FileExistsError(f'Refusing to overwrite: {dest}; use a NEW filename')
    return dest


def report_create(root, value, payload):
    dest=validate_report_path(root,value)
    dest.parent.mkdir(parents=True,exist_ok=True)
    with dest.open('x',encoding='utf8') as f:json.dump(payload,f,indent=2,sort_keys=True)
    print('V038A_REPORT',dest)
    return dest


def flat_state(state):
    """Comparable continuous state fields; no assumptions about backend's contact metadata."""
    arrays=[]
    ball=state.ball
    for phys in (ball,):
        arrays.extend(np.asarray(getattr(phys,k),dtype=np.float64).ravel()
                      for k in ('position','linear_velocity','angular_velocity'))
    for cid in sorted(state.cars):
        c=state.cars[cid]
        arrays.extend(np.asarray(getattr(c.physics,k),dtype=np.float64).ravel()
                      for k in ('position','linear_velocity','angular_velocity','rotation_mtx'))
        arrays.append(np.asarray([float(c.boost_amount)],dtype=np.float64))
    arrays.append(np.asarray(state.boost_pad_timers,dtype=np.float64).ravel())
    ret=np.concatenate(arrays)
    if not np.isfinite(ret).all():raise RuntimeError('Engine reported nonfinite physics')
    return ret


def comparison(a,b,atol=1e-3):
    va,vb=flat_state(a),flat_state(b)
    if va.shape!=vb.shape:raise ValueError('State shapes differ')
    delta=np.abs(va-vb)
    return {'max_abs_error':float(delta.max()),'mean_abs_error':float(delta.mean()),
            'components_differing':int((delta>atol).sum()),'components':int(delta.size),
            'close':bool((delta<=atol).all()),
            'goal_scored_match':bool(a.goal_scored==b.goal_scored)}


def engine_gate(seed=20261011, blocks=12, atol=1e-3):
    """Compare 8-tick batch stepping to 1-tick stepping from SAME kickoff state.

    If this fails, a sub-tick interruption patch could change underlying physics
    and must not be used to rank policies before investigation.
    """
    from rlgym.rocket_league.sim import RocketSimEngine
    from rlgym.rocket_league.state_mutators import FixedTeamSizeMutator,KickoffMutator
    import slater_nexto_kickoff_v037a as previous
    if previous.control_hash()!=previous.EXPECTED_SCRIPT_SHA256:
        raise RuntimeError('Nexto scripted control hash invalid')
    if not 1<=blocks<=128 or not 0<=seed<2**31-1 or not 0<atol<=1e-2:
        raise ValueError('Invalid physics gate parameters')
    random.seed(seed)
    rng=np.random.default_rng(seed)
    grouped=RocketSimEngine(rlbot_delay=False)
    sequential=RocketSimEngine(rlbot_delay=False)
    rows=[]
    from nexto_teacher import nexto_actions
    table=nexto_actions()
    try:
        initial=grouped.create_base_state()
        FixedTeamSizeMutator(blue_size=1,orange_size=1).apply(initial,{})
        KickoffMutator().apply(initial,{})
        ga=grouped.set_state(copy.deepcopy(initial),{})
        sb=sequential.set_state(copy.deepcopy(initial),{})
        if not comparison(ga,sb,atol)['close']:raise RuntimeError('Engines begin in different states')
        ids=sorted(ga.cars)
        for b in range(blocks):
            commands={}
            for j,cid in enumerate(ids):
                if j==1 and b<21:
                    ctrl=previous.KICKOFF_CONTROLS[b*8:(b+1)*8].copy()
                    if ctrl.shape!=(8,8):
                        ctrl=np.tile(previous.KICKOFF_CONTROLS[-1][None],(8,1))
                else:
                    # Discrete Nexto lookup actions, held 8 ticks.
                    action=np.asarray(table[int(rng.integers(0,90))],dtype=np.float32).reshape(8)
                    ctrl=np.tile(action[None],(8,1))
                commands[cid]=np.asarray(ctrl,dtype=np.float32)
            ga=grouped.step(commands,{})
            for tick in range(8):
                sb=sequential.step({cid:ctrl[tick:tick+1] for cid,ctrl in commands.items()},{})
            item=comparison(ga,sb,atol)
            item.update(block=b,game_tick=(b+1)*8)
            rows.append(item)
            if not item['close'] or not item['goal_scored_match']:break
        passed=len(rows)==blocks and all(x['close'] and x['goal_scored_match'] for x in rows)
        return {'version':VERSION,'test':'eight_ticks_batch_vs_eight_single_ticks',
                'passed':passed,'seed':seed,'blocks_requested':blocks,'blocks_checked':len(rows),
                'atol':atol,'max_abs_error':max(x['max_abs_error'] for x in rows),
                'checks':rows,'nexto_script_sha':previous.control_hash(),
                'limitation':'Proves engine stepping equivalence only for this trajectory; not live Rocket League parity.'}
    finally:
        grouped.close(); sequential.close()


def _load_gate(root,name,test,require_pass_field):
    f=(root/name).resolve()
    if not f.is_relative_to((root/'data'/'isolated').resolve()) or not f.is_file():
        raise ValueError('Must supply previously saved report under data/isolated')
    doc=json.loads(f.read_text(encoding='utf-8'))
    if doc.get('version')!=VERSION and not (test=='same_state_reference_nexto_vs_teamobserver' and doc.get('version')=='v0.3.8'):
        raise ValueError('Unexpected gate report version')
    if doc.get('test')!=test or not doc.get(require_pass_field):
        raise ValueError('Gate did not pass: '+name)
    return {'path':str(f),'sha256':digest(f),'test':test}


def benchmark(root,checkpoint,seeds=4,horizon=600,seed=20261019,physics_gate=None,obs_gate=None):
    """Generate ablation without training or re-exporting any checkpoint.

    This tests the CURRENT v037a modes, not a new, proven stock RLBot port.
    The stochastic option often has no observable effect in 1v1 because the
    scripted kickoff overrides NN actions while kickoff pause is active.
    """
    if not 2<=seeds<=64 or not 90<=horizon<=4500 or not 0<seed<2**31-100000:
        raise ValueError('Invalid ablation parameters')
    import slater_nexto_kickoff_v037a as old
    src=root/'slater_nexto_kickoff_v037a.py'
    if digest(src)!=EXPECTED_V037A:raise ValueError('V037a source has changed; please audit before using this harness')
    import torch
    torch.set_num_threads(2);torch.manual_seed(seed);np.random.seed(seed);random.seed(seed)
    ck=(root/checkpoint).resolve()
    actor,orig,nexto,actions,doc,provenance=old.load_protected(root,ck)
    gates={}
    if physics_gate:
        gates['physics']=_load_gate(root,physics_gate,'eight_ticks_batch_vs_eight_single_ticks','passed')
    if obs_gate:
        gates['observation']=_load_gate(root,obs_gate,'same_state_reference_nexto_vs_teamobserver','allclose')
    modes=('nexto_greedy','nexto_script','nexto_stock_approx')
    rr=old.evaluate(actor,orig,nexto,actions,modes=modes,seeds=seeds,horizon=horizon,seed_base=seed)
    # Collapse the repeated seed/side rows into comparable pairs; report
    # timeouts separately, never treat as RLBot draw or policy victory.
    pair=[]
    for k in sorted({(x['seed'],x['side'],x['policy']) for x in rr['records']}):
        selected={x['mode']:x for x in rr['records'] if (x['seed'],x['side'],x['policy'])==k}
        if len(selected)==len(modes):
            pair.append({'seed':k[0],'side':k[1],'policy':k[2],
                         'greedy_outcome':selected['nexto_greedy']['outcome'],
                         'script_outcome':selected['nexto_script']['outcome'],
                         'stock_approx_outcome':selected['nexto_stock_approx']['outcome']})
    rr.update({'version':VERSION,'test':'v037a_greedy_script_stock_approx_ablation',
               'model_provenance':provenance,'source_sha':digest(src),'gates':gates,
               'paired_outcomes':pair,'can_establish_stock_rlbot_parity':False,
               'warnings':['Single-goal episodes, not five-minute games. Timeouts are censored, not draws.',
                           'nexto_stock_approx inherits v037a ball-center based kickoff pause, not packet.is_kickoff_pause.',
                           'Stochastic NN action may be entirely hidden by simultaneous scripted override in 1v1.',
                           'Engine gate passing does NOT mean dynamic mid-step interruption is implemented.']})
    return rr


def stress_obs(root,seeds=8,steps=32,model='data/rlbot_exports/V60/nexto-model.pt'):
    obs_path=root/'slater_v038_reference'/'nexto_obs.py'
    mp=(root/model).resolve()
    if not mp.is_relative_to(root) or not mp.is_file():raise FileNotFoundError('Missing local model')
    if not 2<=seeds<=128 or not 4<=steps<=128:raise ValueError('Invalid stress parameters')
    import slater_fidelity_v038 as v38
    report=v38.compare_same_state(root,obs_path,seeds=seeds,steps=steps,model_path=mp)
    report['version']=VERSION
    report['limitation_extended']='Still compares two builders on the same RocketSim states; NO RLBot live packet validation.'
    return report


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    for cmd in ('engine-gate','stress-obs','ablation'):
        sp=sub.add_parser(cmd);sp.add_argument('--out',required=True)
        if cmd=='engine-gate':
            sp.add_argument('--seed',type=int,default=20261011)
            sp.add_argument('--blocks',type=int,default=12)
        elif cmd=='stress-obs':
            sp.add_argument('--seeds',type=int,default=8)
            sp.add_argument('--steps',type=int,default=32)
            sp.add_argument('--model',default='data/rlbot_exports/V60/nexto-model.pt')
        else:
            sp.add_argument('--from-checkpoint',default='data/isolated/slater_v027_campaign01_u0060.pt')
            sp.add_argument('--seeds',type=int,default=4)
            sp.add_argument('--episode-steps',type=int,default=600)
            sp.add_argument('--seed',type=int,default=20261019)
            sp.add_argument('--physics-gate',default=None)
            sp.add_argument('--obs-gate',default=None)
    a=parser.parse_args(argv)
    root=Path.cwd().resolve()
    validate_report_path(root,a.out) # Fail fast before expensive simulation.
    if a.command=='engine-gate':
        result=engine_gate(a.seed,a.blocks)
        print('V038A_ENGINE_GATE',result['passed'],'MAX_ERROR',result['max_abs_error'],flush=True)
    elif a.command=='stress-obs':
        result=stress_obs(root,a.seeds,a.steps,a.model)
        print('V038A_OBSERVATION_STRESS',result['pass_count'],'/',len(result['samples']),
              'ACTION_DISAGREEMENTS',result['action_disagreement_count'],flush=True)
    else:
        result=benchmark(root,a.from_checkpoint,a.seeds,a.episode_steps,a.seed,a.physics_gate,a.obs_gate)
        print('V038A_ABLATION',json.dumps(result['summary'],sort_keys=True),flush=True)
    report_create(root,a.out,result)
    if a.command=='engine-gate' and not result['passed']:
        print('WARNING: PHYSICS_TICK_SPLITTING_NOT_EQUIVALENT; do not implement per-tick Nexto yet.')

if __name__=='__main__':main()
