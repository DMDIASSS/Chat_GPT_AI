"""Slater v0.3.8: read-only same-RocketSim-state Nexto observation parity audit.

The RLBot v4 NextoObsBuilder is extracted from a local user-supplied file via
AST with a strict source SHA-256 allowlist. No RLBot app, checkpoint or model
is mutated and no neural-network training is run.

Reference comparison uses an explicit RLGym v2 -> legacy Nexto encoding adapter;
it is an *audit*, not a validated production state converter. Incorrect fields
are reported, never silently accepted as proof of equivalence.
"""
from __future__ import annotations
import argparse
import ast
import hashlib
import json
from pathlib import Path
import types

import numpy as np

VERSION = 'v0.3.8'
KNOWN_OBS_SHA256 = '7247046d836059ab4428fb8f08968af1a977cf3228f1462a0235cd7a825362b0'
SCRIPT_SHA256 = '6f3b9fadf306e5f1275a149ecb672028258086586cbdd1190fe533c25248fc88'
FEATURES = ['is_self','is_mate','is_opp','is_ball','is_boost',
            'pos_x','pos_y','pos_z','vel_x','vel_y','vel_z',
            'forward_x','forward_y','forward_z','up_x','up_y','up_z',
            'ang_x','ang_y','ang_z','boost','demo','ground','flip']


def sha256(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):
            h.update(b)
    return h.hexdigest()


def guarded_path(root, out):
    root=Path(root).resolve()
    dst=Path(out)
    if not dst.is_absolute():dst=root/dst
    dst=dst.resolve()
    isolated=(root/'data'/'isolated').resolve()
    if not dst.is_relative_to(isolated) or dst.suffix!='.json':
        raise ValueError('Output must be a .json inside data/isolated')
    if dst.exists() or Path(str(dst)+'.partial').exists():
        raise FileExistsError('Report exists; choose another --out: '+str(dst))
    return dst


def write_report(root,out,data):
    dst=guarded_path(root,out)
    dst.parent.mkdir(parents=True,exist_ok=True)
    with dst.open('x',encoding='utf-8') as f:json.dump(data,f,indent=2,sort_keys=True)
    print('V038_REPORT',dst)


def reference_obs_builder(path):
    """Use only vetted declarations from the exact archived NextoObsBuilder.

    Not `importlib` of an untrusted bot: extracts class and numeric constants;
    rejects variants instead of interpreting arbitrary third-party code.
    """
    path=Path(path)
    digest=sha256(path)
    if digest != KNOWN_OBS_SHA256:
        raise ValueError('Different nexto_obs.py SHA256 '+digest+'; refusing unverified reference. Use original RLBotPack Nexto version.')
    tree=ast.parse(path.read_text(encoding='utf-8-sig'))
    global_names={'BOOST_LOCATIONS','IS_SELF','POS','LIN_VEL','FW','UP',
                  'ANG_VEL','BOOST','DEMO','ON_GROUND','HAS_FLIP','ACTIONS',
                  'BALL_STATE_LENGTH','PLAYER_CAR_STATE_LENGTH',
                  'PLAYER_TERTIARY_INFO_LENGTH','PLAYER_INFO_LENGTH'}
    nodes=[]
    for n in tree.body:
        if isinstance(n,ast.Assign) and any(isinstance(x,ast.Name) and x.id in global_names for t in n.targets for x in ast.walk(t)):
            nodes.append(n)
        elif isinstance(n,ast.FunctionDef) and n.name=='rotation_to_quaternion':
            nodes.append(n)
        elif isinstance(n,ast.ClassDef) and n.name in ('BatchedObsBuilder','NextoObsBuilder'):
            nodes.append(n)
    sandbox={'__builtins__':__builtins__,'np':np,'Any':object,'GameState':object,'PlayerData':object}
    exec(compile(ast.fix_missing_locations(ast.Module(body=nodes,type_ignores=[])),str(path),'exec'),sandbox)
    for name in ('NextoObsBuilder','rotation_to_quaternion'):
        if name not in sandbox:raise ValueError('Missing reference definition '+name)
    return types.SimpleNamespace(**{k:v for k,v in sandbox.items() if k!='__builtins__'})


def vector(v, n=3):
    a=np.asarray(v,dtype=np.float64).reshape(-1)
    if a.size!=n or not np.isfinite(a).all():raise ValueError('Invalid physics vector '+repr(a))
    return a.tolist()


def legacy_boost_amount(car):
    # RLGym v2 uses boost units 0..100; legacy rlgym_compat uses normalized 0..1.
    b=float(car.boost_amount)
    if b < 0 or b > 100.001:raise ValueError('Invalid boost amount')
    return b/100.0


def player_block(car, team, car_id, quat_fn):
    p=car.physics
    ip=car.inverted_physics
    def physical_block(x):
        m=np.asarray(x.rotation_mtx,dtype=np.float64)
        if m.shape!=(3,3):raise ValueError('Invalid rotation matrix')
        return vector(x.position)+vector(quat_fn(m),4)+vector(x.linear_velocity)+vector(x.angular_velocity)
    # Legacy Nexto encoded player car length = 38:
    # id, team, normal 13, inverted 13, five spare, demo, ground, touch, flip, boost.
    attrs=[0.,0.,0.,0.,0.,float(bool(car.is_demoed)),float(bool(car.on_ground)),
           float(bool(car.ball_touches)),float(bool(car.has_flip)),legacy_boost_amount(car)]
    block=[float(car_id),float(team)]+physical_block(p)+physical_block(ip)+attrs
    if len(block)!=38:raise AssertionError('Bad legacy player length')
    return block


def encode_sim_state(state, ref):
    """RocketSim RLGym 2 state -> archived Nexto's encoded flat array.

    Uses explicit semantics for timers/boost; report marks this conversion
    as unverified until the RLBot packet reference itself is compared.
    """
    timers=np.asarray(state.boost_pad_timers,dtype=np.float64).reshape(-1)
    if len(timers)!=34:raise ValueError('Expected 34 Soccar boost pad timers')
    pads=(timers<=0.00001).astype(np.float64).tolist()
    v=[0.,0.,0.]+pads
    for ball in (state.ball,state.inverted_ball):
        v+=vector(ball.position)+vector(ball.linear_velocity)+vector(ball.angular_velocity)
    ids={str(k):k for k in state.cars}
    if len(ids)!=len(state.cars):raise ValueError('Stringified car IDs collided')
    sorted_ids=sorted(ids,key=lambda k:(int(state.cars[ids[k]].team_num),k))
    if len(sorted_ids)>6:raise ValueError('Too many players for this audit')
    for idx,key in enumerate(sorted_ids):
        car=state.cars[ids[key]]
        v+=player_block(car,int(car.team_num),idx,ref.rotation_to_quaternion)
    return np.asarray(v,dtype=np.float64),sorted_ids,ids


def normalize_obs(obs):
    result=[]
    for v,shape in zip(obs,((1,32),(41,24),(41,))):
        a=np.asarray(v,dtype=np.float32)
        if a.shape==(1,)+shape:a=a[0]
        if a.shape!=shape:raise ValueError('Expected shape '+str(shape)+', got '+str(a.shape))
        if not np.isfinite(a).all():raise ValueError('Nonfinite observation')
        result.append(a)
    if len(result)!=3:raise ValueError('Invalid observation tuple')
    return result


def compare_obs(sim, reference, atol=3e-4):
    sim=normalize_obs(sim);reference=normalize_obs(reference)
    q0,k0,m0=sim;q1,k1,m1=reference
    mask_diffs=np.flatnonzero(np.abs(m0-m1)>atol).tolist()
    mismatched=[]
    for j,name in enumerate(FEATURES):
        delta=np.abs(k0[:,j]-k1[:,j]); imax=int(delta.argmax())
        mx=float(delta[imax]);cnt=int(np.count_nonzero(delta>atol))
        if cnt:mismatched.append({'feature':name,'max_abs_delta':round(mx,7),'token_at_max':imax,'mismatching_tokens':cnt,
                                  'sim_value':float(k0[imax,j]),'ref_value':float(k1[imax,j])})
    q_delta=np.abs(q0-q1)
    q_changed=np.argwhere(q_delta>atol)
    return {'allclose':bool(np.allclose(q0,q1,atol=atol,rtol=0) and
                             np.allclose(k0,k1,atol=atol,rtol=0) and
                             np.allclose(m0,m1,atol=atol,rtol=0)),
            'max_q_abs_delta':float(q_delta.max()),
            'max_kv_abs_delta':float(np.max(np.abs(k0-k1))),
            'mask_mismatch_tokens':mask_diffs,
            'q_mismatching_columns':sorted(set(int(p[1]) for p in q_changed)),
            'kv_feature_mismatches':mismatched}


def reference_obs(state, previous, ref):
    encoded,ids,original_ids=encode_sim_state(state,ref)
    builder=ref.NextoObsBuilder(field_info=None,n_players=6)
    # Batched builder bypasses legacy GameState construction yet calls the exact reference algorithm.
    inputs=builder.batched_build_obs(encoded[None,:])
    output={}
    for i,key in enumerate(ids):
        pid=original_ids[key]
        control=np.asarray(previous.get(pid,np.zeros(8)),dtype=np.float32).reshape(8)
        builder.add_actions(inputs,control,i)
        output[pid]=normalize_obs(inputs[i])
    return output


def greedy_action(model, obs):
    import torch
    q,kv,mask=normalize_obs(obs)
    xs=tuple(torch.from_numpy(np.asarray(v)[None].copy()) for v in (q,kv,mask))
    with torch.no_grad():
        output=model(xs)
        logits=output[0] if isinstance(output,(tuple,list)) else output
        arr=np.asarray(logits.detach().cpu(),dtype=np.float32).reshape(-1)
    if len(arr)!=90 or not np.isfinite(arr).all():
        raise ValueError('Reference model did not produce 90 finite action logits')
    return arr


def compare_same_state(root,obs_path,*,seeds=2,steps=4,atol=3e-4,model_path=None):
    """Reseed RocketSim from canonical kickoffs; compare both builders on SAME state."""
    from afk_team_research import TeamObserver
    from rlgym.rocket_league.sim import RocketSimEngine
    from rlgym.rocket_league.state_mutators import FixedTeamSizeMutator,KickoffMutator
    import random
    ref=reference_obs_builder(obs_path)
    policy=None
    if model_path is not None:
        import torch
        policy=torch.jit.load(str(model_path),map_location='cpu').eval()
    rows=[]
    for seed in range(seeds):
        engine=RocketSimEngine(rlbot_delay=False)
        try:
            random.seed(20261011+seed*997)
            init=engine.create_base_state()
            FixedTeamSizeMutator(blue_size=1,orange_size=1).apply(init,{})
            KickoffMutator().apply(init,{})
            state=engine.set_state(init,{})
            prior={}
            for t in range(steps+1):
                sim=TeamObserver().observe(state,prior)
                reference=reference_obs(state,prior,ref)
                for pid in sorted(state.cars):
                    result=compare_obs(sim[pid],reference[pid],atol=atol)
                    if policy is not None:
                        al=greedy_action(policy,sim[pid]); bl=greedy_action(policy,reference[pid])
                        result.update(sim_action=int(al.argmax()),reference_action=int(bl.argmax()),
                                      same_selected_action=bool(al.argmax()==bl.argmax()),
                                      max_logit_abs_delta=float(np.max(np.abs(al-bl))))
                    result.update(seed=seed,step=t,side=pid)
                    rows.append(result)
                if t<steps:
                    # deterministic controls exercise previous-action handling + normal physics
                    cmds={pid:np.tile(np.array([1.,0.,0.,0.,0.,0.,int((t+i)%2),0.],dtype=np.float32),(8,1))
                          for i,pid in enumerate(sorted(state.cars))}
                    state=engine.step(cmds,{})
                    prior={pid:cmds[pid][-1] for pid in cmds}
        finally:engine.close()
    return {'test':'same_state_reference_nexto_vs_teamobserver','seed_count':seeds,'physics_steps_per_seed':steps,
            'reference_nexto_obs_sha256':sha256(obs_path),'samples':rows,
            'pass_count':sum(r['allclose'] for r in rows),'fail_count':sum(not r['allclose'] for r in rows),
            'allclose':all(r['allclose'] for r in rows),
            'model_path':str(model_path) if model_path is not None else None,
            'action_disagreement_count':sum(not r.get('same_selected_action',True) for r in rows),
            'important':'RLGym->legacy Nexto encoding is a test adapter, not a verified live RLBot packet conversion. Inspect per-feature discrepancies.'}


def compare_capture_only(folder):
    """Check live capture health; unlike same-state comparison, cannot infer semantic parity."""
    paths=sorted(Path(folder).glob('capture_*.npz'))
    out=[]
    for path in paths[:128]:
        with np.load(path,allow_pickle=False) as d:
            try:
                o=normalize_obs([d['q'],d['kv'],d['mask']]);
                v={'file':path.name,'ok':True,'team':int(d['team']),'kickoff_pause':bool(d['is_kickoff_pause']),
                   'mask_sum':float(o[2].sum()),'ball_tag_count':int((o[1][:,3]>.5).sum())}
            except (KeyError,ValueError,IndexError) as e:
                v={'file':path.name,'ok':False,'reason':str(e)}
            out.append(v)
    return {'total_files':len(paths),'checked':len(out),'valid_count':sum(v['ok'] for v in out),
            'samples':out,'observation_semantic_parity':'UNVERIFIED__LIVE_CAPTURE_IS_NOT_SAME_STATE'}


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=('audit','compare-obs','inspect-capture'))
    p.add_argument('--reference-obs',default='slater_v038_reference/nexto_obs.py')
    p.add_argument('--deployed-obs',default='data/rlbot_exports/V60/nexto_obs.py',
                   help='For provenance comparison only; does not execute unknown bot code')
    p.add_argument('--model',default='',help='Optional exported V60 TorchScript nexto-model.pt; compare selected actions')
    p.add_argument('--seeds',type=int,default=2)
    p.add_argument('--steps',type=int,default=4)
    p.add_argument('--atol',type=float,default=3e-4)
    p.add_argument('--capture-dir',default='data/isolated/slater_v034_livecapture_u60_01/capture_v034')
    p.add_argument('--out',required=True)
    a=p.parse_args(argv)
    root=Path.cwd().resolve()
    guarded_path(root,a.out)
    ref=(root/a.reference_obs).resolve()
    deployed=(root/a.deployed_obs).resolve()
    deployed_info={'path':str(deployed),'exists':deployed.is_file(),
                   'sha256':sha256(deployed) if deployed.is_file() else None,
                   'same_as_reference':sha256(deployed)==sha256(ref) if deployed.is_file() else None}
    if a.command=='audit':
        result={'version':VERSION,'kind':'reference_source_audit','reference_obs':str(ref),
                'known_reference_sha256':KNOWN_OBS_SHA256,'reference_sha256':sha256(ref),
                'approved':sha256(ref)==KNOWN_OBS_SHA256,
                'deployed_obs':deployed_info,
                'model_checkpoint_writes':False,
                'limitations':['Real Nexto may use a different nexto_obs.py version.',
                               'Checkpoint and PPO unaffected; same-state comparison is the next gate.']}
    elif a.command=='compare-obs':
        if not 1<=a.seeds<=32 or not 0<=a.steps<=128 or not 0<a.atol<=.01:
            p.error('Invalid seeds/steps/atol')
        model_path=(root/a.model).resolve() if a.model else None
        if model_path is not None and not model_path.is_file():raise FileNotFoundError(str(model_path))
        result=compare_same_state(root,ref,seeds=a.seeds,steps=a.steps,atol=a.atol,model_path=model_path)
        result['deployed_obs']=deployed_info
        result['version']=VERSION
    else:
        result=compare_capture_only(root/a.capture_dir)
        result['version']=VERSION
    write_report(root,a.out,result)
    print('V038_STATUS', 'PASS' if result.get('allclose',result.get('approved',result.get('valid_count',0)>0)) else 'INVESTIGATE')
    if 'fail_count' in result:
        print('V038_SAME_STATE_SAMPLES',len(result['samples']),'MISMATCHES',result['fail_count'],
              'ACTION_DISAGREEMENTS',result.get('action_disagreement_count'))
        for r in (x for x in result['samples'] if not x['allclose']):
            print('V038_MISMATCH',r['seed'],r['step'],r['side'],
                  [z['feature'] for z in r['kv_feature_mismatches'][:12]],
                  'Q_COLS',r['q_mismatching_columns'][:16],'MASK',r['mask_mismatch_tokens'][:12])
            if sum(not x['allclose'] for x in result['samples'])>8 and r is result['samples'][7]:break

if __name__=='__main__':main()
