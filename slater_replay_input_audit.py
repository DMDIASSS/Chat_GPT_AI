"""Audit recorded replay controls and held-out native imitation without training."""
import argparse,json,re,struct,time
from pathlib import Path
import numpy as np
import torch
from slater_native_actor import NativeActor,observation,action_mask
from slater_native_inspect import current_checkpoint,snapshot
from slater_v041_core import read_json,sha256,atomic_json
ROOT=Path(__file__).resolve().parent
BASE=ROOT/'data/isolated/replay_input_audits'

def training_provenance():
    result=[];native_base=ROOT/'data/isolated/gigalearn_native/runs'
    for name in ('focused_teacher01','focused_curriculum01'):
        state=read_json(ROOT/f'data/isolated/event_curriculum/{name}/status.json',{})
        if not state:continue
        active=state.get('active_run')
        if not active and state.get('latest'):
            try:active=Path(state['latest']).resolve().relative_to(native_base.resolve()).parts[0]
            except ValueError:pass
        if not active:continue
        folder=native_base/active;profile=read_json(folder/'protocol.json',{}).get('profile',{});logs=list(folder.glob('training_*.log'))
        human=teacher=0
        for path in logs:
            text=path.read_text(encoding='utf8',errors='replace')
            human+=len(re.findall(r'^SLATER_REPLAY_BC epoch=',text,re.MULTILINE))
            teacher+=len(re.findall(r'^SLATER_TEACHER_BC_(?:PRE|POST) epoch=',text,re.MULTILINE))
        result.append(dict(campaign=name,native_run=active,focus=profile.get('focus'),human_bank=profile.get('bank'),teacher_bank=profile.get('teacher_bank'),
                           observed_human_imitation_epochs=human,observed_teacher_imitation_epochs=teacher,logs=[str(p) for p in logs],
                           note='Epoch counts are observed in this native run only; inherited training happened in earlier source runs. Bank presence/printed fit alone does not mean label gradients ran.'))
    return result

def field_stats(df,name,limits=None):
    if name not in df:return dict(present=False,rows=len(df),nonmissing=0)
    values=np.asarray(df[name],dtype=float);finite=values[np.isfinite(values)]
    result=dict(present=True,rows=len(values),nonmissing=len(finite),nonmissing_fraction=len(finite)/max(1,len(values)),unique_values=len(np.unique(finite)))
    if len(finite):result.update(minimum=float(finite.min()),maximum=float(finite.max()))
    if limits and len(finite):result['outside_range']=int(((finite<limits[0])|(finite>limits[1])).sum())
    return result

def raw_report(parsed):
    return {str(aid):dict(recorded_control_fields={k:field_stats(df,k,(0,255)) for k in ('throttle','steer')},
                          raw_state_flags={k:field_stats(df,k) for k in ('jump_is_active','double_jump_is_active','boost_is_active','handbrake')},
                          raw_aerial_fields={k:field_stats(df,k,(-1,1)) for k in ('pitch','yaw','roll')}) for aid,df in parsed.player_dfs.items()}

def bank_fit(checkpoints,bank,max_rows=3000):
    with open(bank,'rb') as f:
        if f.read(4)!=b'SGRB':raise ValueError('Invalid native replay bank')
        version,players,count,width=struct.unpack('<IIII',f.read(16));table=np.frombuffer(f.read(720*4),dtype='<f4').reshape(90,8)
    from nexto_teacher import nexto_actions
    if version!=1 or players!=2 or width!=231 or not np.array_equal(table,nexto_actions()):raise ValueError('Expected compatible native duel bank')
    if Path(bank).stat().st_size!=20+(720+102+count*width)*4:raise ValueError('Replay bank length mismatch')
    rows=np.memmap(bank,mode='r',dtype='<f4',offset=20+(720+102)*4,shape=(count,width))
    indices=np.flatnonzero(rows[:,-1]==1);rng=np.random.default_rng(181023)
    if len(indices)>max_rows:indices=np.sort(rng.choice(indices,max_rows,replace=False))
    x=[];ys=[];masks=[];weights=[];dropped=0
    for index in indices:
        r=rows[index]
        def body(b):return dict(pos=b[:3].tolist(),rot=b[3:12].tolist(),vel=b[12:15].tolist(),ang=b[15:18].tolist())
        p=dict(ball=body(r),timers=r[18:52].tolist(),cars=[])
        for i in range(2):
            b=r[52+43*i:95+43*i];p['cars'].append(dict(id=i+1,team=i,**body(b),boost=float(b[18]),ground=bool(b[19]),jumped=bool(b[20]),double_jumped=bool(b[21]),flipped=bool(b[22]),air_time=float(b[26]),demo=False,world_contact=False,contact_normal=[0,0,0],previous=b[27:35].tolist()))
        query=int(r[138]);mask=action_mask(p['cars'][query]);y=r[139:229]*mask
        if y.sum()<.5:dropped+=1;continue
        x.append(observation(p,query+1));ys.append(y/y.sum());masks.append(mask);weights.append(float(r[-2]))
    if not x:raise ValueError('No usable validation labels')
    x=torch.tensor(np.array(x));y=torch.tensor(np.array(ys));mask=torch.tensor(np.array(masks));w=np.array(weights);result={}
    for name,path in checkpoints.items():
        actor=NativeActor(path);ce=[];agreement=[];idle=[]
        with torch.inference_mode():
            for start in range(0,len(x),256):
                yy=y[start:start+256];prob=actor.probabilities(x[start:start+256],mask[start:start+256]);chosen=prob.argmax(-1)
                ce.extend((-(yy*prob.log()).sum(-1)).tolist());agreement.extend(yy.gather(1,chosen[:,None]).flatten().tolist());idle.extend((chosen==8).tolist())
        result[name]=dict(samples=len(x),masked_cross_entropy=float(np.mean(ce)),confidence_weighted_ce=float(np.average(ce,weights=w)),
                          label_mass_on_student_choice=float(np.mean(agreement)),idle_argmax_fraction=float(np.mean(idle)),checkpoint=actor.identity)
    return dict(partition='validation',test_used=False,rows_considered=len(indices),dropped_mask_mass=dropped,bank_sha=sha256(bank),models=result,
                note='Agreement is target probability mass assigned to the greedy student action; it is not proof of understanding or competitive skill. Same validation rows for both models.')

def audit(prepared,out,*,checkpoint,raw_count=0,inputs=None):
    out=Path(out).resolve();out.mkdir(parents=True,exist_ok=True);manifest=read_json(Path(prepared)/'manifest.json')
    if not manifest:raise FileNotFoundError('Prepared event corpus manifest is missing')
    bank=Path(manifest['bank'])
    if sha256(bank)!=manifest['bank_sha']:raise ValueError('Prepared bank changed')
    sources=manifest.get('sources',[]);good=[s for s in sources if 'coverage' in s]
    report=dict(source_count=len(sources),sources_with_recorded_throttle_and_steer=sum(len(s['coverage'])==2 and all(v.get('throttle',0)>0 and v.get('steer',0)>0 for v in s['coverage'].values()) for s in good),
                source_errors=[s for s in sources if s.get('error')],cached_coverage=good,raw_samples=[],training_provenance=training_provenance(),
                provenance=dict(throttle_steer='Recorded parser fields, then filled/interpolated/smoothed by replay_to_rlgym; coverage alone does not prove exact inputs at every frame.',
                                pitch_yaw_roll='Inferred from angular dynamics by rlgym-tools; converter overwrites these axes with inverse-control estimates.',
                                jump_boost='Reconstructed from replicated activity flags/events; flags are not a full original button stream.',
                                handbrake='Parser/converter dependent; inspect actual raw columns. Do not assume complete recorded eight-axis controls.'),
                note='This audit distinguishes recorded evidence from inferred labels. It does not claim original human controls are perfectly recoverable.')
    if raw_count:
        from rlgym_tools.rocket_league.replays.parsed_replay import ParsedReplay,process_replay
        paths=sorted(Path(inputs).rglob('*.replay')) if inputs else [Path(s['path']) for s in sources]
        if not paths:raise FileNotFoundError('No raw replays for input audit')
        take=min(raw_count,len(paths));chosen=np.random.default_rng(181024).choice(len(paths),take,replace=False)
        for i,index in enumerate(chosen):
            path=paths[int(index)];digest=sha256(path);cache=BASE/'parsed_cache'/digest[:24];cache.mkdir(parents=True,exist_ok=True)
            try:
                process_replay(str(path),str(cache));parsed=ParsedReplay.load(cache/path.stem)
                report['raw_samples'].append(dict(path=str(path),sha256=digest,players=raw_report(parsed)))
            except Exception as exc:report['raw_samples'].append(dict(path=str(path),error=str(exc)))
            atomic_json(out/'INPUTS.json',report);print('RAW_INPUT_AUDIT',i+1,'/',take,flush=True)
    current=snapshot(checkpoint,out/'student');models={'current':current}
    starting=ROOT/'data/isolated/gigalearn_native/runs/ranked_duels_train01/checkpoints/3711232'
    if starting.is_dir():models['original_native']=snapshot(starting,out/'original_native')
    torch.set_num_threads(1);report['human_imitation']=bank_fit(models,bank);atomic_json(out/'INPUTS.json',report)
    print('REPLAY_INPUT_REPORT',out/'INPUTS.json',flush=True);print('HUMAN_IMITATION',json.dumps(report['human_imitation']['models']),flush=True);return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepared',default=str(ROOT/'data/isolated/event_curriculum/windows01'));p.add_argument('--checkpoint');p.add_argument('--inputs');p.add_argument('--raw-count',type=int,default=12);p.add_argument('--run');a=p.parse_args()
    if not 0<=a.raw_count<=500:p.error('raw-count must be 0..500')
    audit(a.prepared,BASE/(a.run or 'audit_'+str(time.time_ns())),checkpoint=a.checkpoint or current_checkpoint(),raw_count=a.raw_count,inputs=a.inputs)
