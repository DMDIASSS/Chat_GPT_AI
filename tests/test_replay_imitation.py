"""Physics fixtures validate implementation; they are NOT professional replay data."""
import copy,json,uuid
from pathlib import Path
from types import SimpleNamespace as S
import numpy as np
import pytest
import torch
from replay_il.model import ChunkPolicy
from replay_il.tokens import fit,tokenize
from replay_il.data import make_rows,fit_transition,split
from replay_il.fetch import eligible,download
from replay_il.monitor import Monitor
from slater_v041_core import atomic_json,sha256

def trace(seconds=1.6,seed=1,players=2):
    from rlgym.rocket_league.sim import RocketSimEngine
    from rlgym.rocket_league.state_mutators import FixedTeamSizeMutator,KickoffMutator
    engine=RocketSimEngine(rlbot_delay=False);out=[]
    try:
        state=engine.create_base_state();FixedTeamSizeMutator(players//2,players//2).apply(state,{});KickoffMutator().apply(state,{})
        state=engine.set_state(state,{})
        for tick in range(0,int(seconds*120)+1,4):
            controls={aid:np.array([1,((tick//24+seed+i)%5-2)/2,0,0,0,float(90<=tick<98),float(tick<80),0],np.float32) for i,aid in enumerate(state.cars)}
            out.append(S(state=copy.deepcopy(state),actions=controls,update_age={k:0. for k in controls},
                scoreboard=S(go_to_kickoff=False,is_over=False,kickoff_timer_seconds=0),next_scoring_team=seed%2,episode_seconds_remaining=3.))
            state=engine.step({aid:np.tile(raw,(4,1)) for aid,raw in controls.items()},{})
    finally:engine.close()
    return out

@pytest.fixture(scope='module')
def raw_rows():
    rows,book,stats=make_rows(trace(),cap=32)
    assert len(rows)>8 and stats['accepted_fit']>30
    return rows

def test_fresh_model_all_weights_train_and_no_pretrained_load(monkeypatch):
    def forbidden(*a,**k):raise AssertionError('Pretrained weights were loaded')
    monkeypatch.setattr(torch,'load',forbidden);monkeypatch.setattr(torch.jit,'load',forbidden)
    torch.set_num_threads(2);torch.manual_seed(9);model=ChunkPolicy()
    assert 3_200_000<model.describe()['parameters']<3_400_000
    assert model.describe()['parameters']==model.describe()['trainable_parameters']
    x=(torch.randn(2,8,1,32),torch.randn(2,8,41,24),torch.zeros(2,8,41))
    policy,values=model(x);(policy.sum()+values.sum()).backward()
    assert model.encoder.query_preprocess[0].weight.grad.abs().sum()>0
    assert policy.shape==(2,256) and values.shape==(2,3)

def test_reconstruction_has_no_future_outcomes_in_inputs(raw_rows):
    frames=trace();altered=copy.deepcopy(frames)
    for f in altered:f.next_scoring_team=1-f.next_scoring_team;f.episode_seconds_remaining=15.
    a,_,_=make_rows(frames,cap=32);b,_,_=make_rows(altered,cap=32)
    assert len(a)==len(b)
    for first,second in zip(a,b):
        for x,y in zip(first['history'],second['history']):np.testing.assert_array_equal(x,y)
        np.testing.assert_array_equal(first['controls'],second['controls'])
    assert any(abs(x['value']-y['value'])>.1 for x,y in zip(a,b))
    assert a[0]['history'][0].shape==(8,1,32) and a[0]['controls'].shape==(32,8)

def test_bad_observed_transition_is_rejected():
    from rlgym.rocket_league.sim import RocketSimEngine
    frames=trace(.2);a,b=frames[:2];b=copy.deepcopy(b);b.state.ball.position[0]+=1000
    engine=RocketSimEngine(rlbot_delay=False)
    try:_,valid,_,_=fit_transition(engine,a.state,b.state,a.actions,4,{'position':40,'velocity':180,'rotation':.3})
    finally:engine.close()
    assert not valid

def test_token_book_preserves_actual_buttons_and_reconstructs(raw_rows):
    chunks=np.stack([r['controls'] for r in raw_rows]).astype(np.float32)
    book,stats=fit(chunks,16);tokens,error=tokenize(chunks,book)
    assert 1<=len(book)<=16 and np.isin(book[:,:,5:],[0,1]).all()
    assert all(any(np.array_equal(row,source) for source in chunks) for row in book)
    assert np.isfinite(error).all() and stats['fit_split']=='train_only'

def fixture_dataset(path,rows):
    path.mkdir(parents=True);records=[]
    for index,partition in enumerate(['train','train','validation','validation','test','test']):
        shard=path/f'{index}.npz'
        np.savez_compressed(shard,**{k:np.stack([r['history'][j] for r in rows]) for j,k in enumerate(('q','kv','mask'))},
            controls=np.stack([r['controls'] for r in rows]),value=np.array([r['value'] for r in rows],np.float32),players=np.full(len(rows),2,np.uint8))
        records.append({'group':f'physics-fixture-{index}','split':partition,'samples':len(rows),'shard':str(shard),'sha256':sha256(shard)})
    atomic_json(path/'manifest.json',{'schema':'replay-il-v2-raw','sources':records,'provenance':'SYNTHETIC_PHYSICS_TEST_ONLY'})
    return path

def test_real_supervised_optimizer_save_resume_and_split_guards(tmp_path,raw_rows,monkeypatch):
    import replay_il.train as training
    from rlgym.rocket_league.sim import RocketSimEngine
    def no_games(*a,**k):raise AssertionError('Training attempted to generate a game')
    monkeypatch.setattr(RocketSimEngine,'__init__',no_games)
    monkeypatch.setattr(training,'ROOT',tmp_path)
    # code_identity refers to the actual source files, independent of output root.
    monkeypatch.setattr(training,'code_identity',lambda:{'test':'fixed'})
    dataset=fixture_dataset(tmp_path/'dataset',raw_rows[:16]);folder=tmp_path/'data/isolated/test_run'
    training.train(dataset,folder,epochs=1,batch_size=8,device='cpu',wandb={'mode':'disabled','project':'test','entity':''})
    first=torch.load(folder/'latest.pt',weights_only=True)
    assert first['progress']['updates']>0 and len(first['optimizer']['state'])>0
    assert json.loads((folder/'model.json').read_text())['pretrained_weights_loaded'] is False
    assert json.loads((folder/'epoch_0001.json').read_text())['parameter_change_l2']>0
    initial_validation=(folder/'validation_initial.json').read_bytes()
    training.train(dataset,folder,epochs=1,batch_size=8,device='cpu',resume=True,wandb={'mode':'disabled','project':'test','entity':''})
    second=torch.load(folder/'latest.pt',weights_only=True)
    assert (folder/'validation_initial.json').read_bytes()==initial_validation
    assert second['progress']['updates']>first['progress']['updates']
    assert any(not torch.equal(v,second['model'][k]) for k,v in first['model'].items())
    selected=json.loads((folder/'selected.json').read_text());assert not selected['competitive_improvement_verified']
    manifest=json.loads((dataset/'manifest.json').read_text());manifest['sources'][1]['group']=manifest['sources'][0]['group'];atomic_json(dataset/'manifest.json',manifest)
    with pytest.raises(ValueError,match='leakage'):training.Dataset(dataset)

def test_exact_duos_filter_and_bounded_authenticated_download(tmp_path,monkeypatch):
    monkeypatch.setenv('BALLCHASING_TOKEN','PRIVATE_TEST_TOKEN')
    rid=str(uuid.uuid4());meta={'id':rid,'playlist_id':'ranked-doubles',**{t:{'players':[{'rank':{'tier':21}},{'rank':{'tier':22}}]} for t in ('blue','orange')}}
    assert eligible(meta);bad=copy.deepcopy(meta);bad['blue']['players'][0]['rank']['tier']=20;assert not eligible(bad)
    calls=[]
    def fetch(url,binary=False):
        calls.append(url);return b'BINARY_REPLAY_TEST' if binary else {'list':[meta,bad],'next':None}
    result=download(tmp_path,count=1,prompt=False,fetch=fetch)
    assert result['downloaded']==1 and result['metadata_rejected']==1 and len(calls)==2
    assert not any('PRIVATE_TEST_TOKEN' in p.read_text(errors='ignore') for p in tmp_path.iterdir())

def test_local_metrics_keep_real_update_steps_and_filter_nonfinite(tmp_path):
    monitor=Monitor(tmp_path,{'mode':'disabled'},{});monitor.emit(7,'validation',{'loss':2.,'missing':None,'bad':float('nan')});monitor.close()
    row=json.loads((tmp_path/'events.jsonl').read_text());assert row['update']==7 and row['metrics']=={'loss':2.}

def test_planner_uses_private_world_and_measures_latency(raw_rows):
    from replay_il.planner import Planner
    state=trace(.1)[0].state;before=state.ball.position.copy();model=ChunkPolicy(vocabulary=4)
    book=np.stack([r['controls'] for r in raw_rows[:4]]).astype(np.float32)
    planner=Planner(model,book,candidates=2,horizon_ticks=32)
    try:action,report=planner.choose(state,{k:np.zeros(8,np.float32) for k in state.cars},next(iter(state.cars)))
    finally:planner.close()
    np.testing.assert_array_equal(before,state.ball.position)
    assert action.shape==(32,8) and report['candidates']==2 and report['latency_ms']>0

def test_tas_audit_retains_starting_pose_and_never_fabricates_training_labels(tmp_path):
    import struct
    from replay_il.tas import decode,audit
    raw=bytearray(8+2*32+128);struct.pack_into('<II',raw,0,1,2)
    struct.pack_into('<I7f',raw,8,13,1,-1,.5,0,0,.7,-.3)
    struct.pack_into('<I7f',raw,40,2,0,0,0,0,0,0,0)
    start=8+64
    struct.pack_into('<3f',raw,start+12,100,200,17)
    struct.pack_into('<3f',raw,start+64,800,900,93)
    path=tmp_path/'clip.data';path.write_bytes(raw)
    empty=tmp_path/'empty.data';empty.write_bytes(struct.pack('<II',1,0)+bytes(128))
    controls,meta=decode(path)
    np.testing.assert_array_equal(controls[:,5:],[[0,1,1],[1,0,0]])
    assert meta['car']['position']==[100,200,17] and meta['ball']['position']==[800,900,93]
    assert meta['dodge_axes_nonzero_frames']==1 and not meta['ball_starts_near_center']
    report=audit(tmp_path,tmp_path/'report.json')
    assert report['decoded']==1 and len(report['rejected'])==1
    assert report['automatically_added_training_examples']==0
