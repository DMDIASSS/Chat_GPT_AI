import importlib.util,json,sys
from pathlib import Path
from types import SimpleNamespace as S
import numpy as np
import pytest

spec=importlib.util.spec_from_file_location('sidecar',Path(__file__).resolve().parents[1]/'tools/wandb_sidecar.py')
sidecar=importlib.util.module_from_spec(spec);spec.loader.exec_module(sidecar)

def test_partial_lines_are_retained_for_retry(tmp_path):
    p=tmp_path/'metrics';p.write_bytes(b'{"a":1}\n{"a":')
    rows,pos=sidecar.rows(p,0);assert rows==[{'a':1}] and pos==8
    with p.open('ab') as f:f.write(b'2}\n')
    rows,end=sidecar.rows(p,pos);assert rows==[{'a':2}] and end==p.stat().st_size

def test_worker_resumes_existing_id_and_skips_acknowledged_metrics(tmp_path):
    root=tmp_path/'contact01';folder=root/'01_contact';folder.mkdir(parents=True)
    (root/'curriculum.json').write_text(json.dumps({'stage_index':0}))
    (folder/'config.json').write_text(json.dumps({'wandb':{'enabled':True,'project':'duelforge'}}))
    (folder/'latest.pt').write_bytes(b'not opened by uploader')
    (folder/'wandb_status.json').write_text(json.dumps({'id':'existing-id'}))
    (folder/'metrics.jsonl').write_text('\n'.join(json.dumps({'learning_transitions':s,'game/test':s,'state':'training'}) for s in (100,200,300))+'\n')
    received=[];arguments=[]
    class Run:
        step=201;url='https://example.invalid/run';entity='test'
        def log(self,row,step):received.append((row,step))
        def finish(self):pass
    def init(**kw):arguments.append(kw);return Run()
    fake=S(init=init,Settings=lambda **kw:kw,util=S(generate_id=lambda:'new-id'),Api=lambda **kw:S(run=lambda path:S(lastHistoryStep=200)))
    sidecar.run(root,fake,max_polls=1,interval=0)
    assert arguments[0]['id']=='existing-id'
    assert received==[({'learning_transitions':300,'game/test':300},300)]
    assert (folder/'latest.pt').read_bytes()==b'not opened by uploader'
    assert json.loads((root/'external_wandb_status.json').read_text())['last_queued_step']==300

def test_external_logging_bypasses_tracker(monkeypatch,tmp_path):
    from duelforge.train import tracker
    monkeypatch.setenv('DUELFORGE_WANDB_EXTERNAL','1')
    assert tracker({'wandb':{'enabled':True}},tmp_path,None) is None

def test_failed_trajectory_gate_does_not_resume_training(monkeypatch,tmp_path):
    from duelforge import acquisition_experiment as experiment
    from duelforge.runtime import sha
    from duelforge.acquisition import RECIPE
    import duelforge.train as training
    root=tmp_path/'contact01';root.mkdir();(root/'baseline.pt').write_bytes(b'preserved')
    state={'recipe':RECIPE,'baseline_sha256':sha(root/'baseline.pt'),'stage_index':2,
           'probes':['failed.json'],'status':'paused'}
    (root/'curriculum.json').write_text(json.dumps(state))
    (root/'failed.json').write_text(json.dumps({'stage':'trajectory','gate_passed':False}))
    def forbidden(*a,**k):raise AssertionError('Failed trajectory must not resume')
    monkeypatch.setattr(training,'train',forbidden);monkeypatch.setattr(experiment,'report',lambda root:None)
    result=experiment.start(root,tmp_path/'source',steps=500000)
    assert result['status']=='trajectory_gate_failed_paused'

@pytest.mark.parametrize('stage',['contact','possession','trajectory'])
@pytest.mark.parametrize('direction',[-1,1])
def test_goal_reward_signs_match_actual_home_net(stage,direction):
    from duelforge.runtime import config,batch
    from duelforge.acquisition import AcquisitionBatch,stage_config,drill_states
    c=stage_config(config(),stage);c['acquisition']['drill_fraction']=0
    e=AcquisitionBatch(batch(c,n=1),c,927)
    w=drill_states(np.random.default_rng(1),1)[0]
    w[0,:3]=[0,direction*4800,200];w[0,3:6]=[0,direction*1600,0]
    w[1,:3]=[-3000,0,17];w[2,:3]=[3000,0,17]
    w[1:,3:9]=0;e.env.inject(0,w);e.raw=e.env.observe()
    found=False
    for _ in range(15):
        r=e.step(np.array([[10,10]],np.int64))
        if r['terminated'][0]:
            assert r['info'][0,0]==direction
            np.testing.assert_array_equal(r['reward_parts'][0,:,0],[direction,-direction])
            found=True;break
    assert found
