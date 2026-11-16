import importlib.util
from pathlib import Path
from types import SimpleNamespace as S
import json

def module(name,file):
    spec=importlib.util.spec_from_file_location(name,Path(__file__).resolve().parents[1]/'tools'/file)
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def test_blocks_repeat_but_pause_and_failed_gates_do_not(tmp_path):
    m=module('curriculum_entry','contact_curriculum.py');calls=[]
    states=iter(['step_budget_saved','step_budget_saved','trajectory_gate_failed_paused'])
    def start(**kw):calls.append(kw);return {'status':next(states)}
    result=m.continuous_start(S(start=start),5000000,tmp_path)
    assert len(calls)==3 and result['status']=='trajectory_gate_failed_paused'
    calls.clear();m.continuous_start(S(start=lambda **k:calls.append(k) or {'status':'step_budget_saved'}),64,tmp_path,once=True)
    assert len(calls)==1
    (tmp_path/'STOP').write_text('stop')
    calls.clear();m.continuous_start(S(start=lambda **k:calls.append(k) or {'status':'step_budget_saved'}),64,tmp_path)
    assert len(calls)==1

def test_resume_uses_server_step_and_switching_does_not_finish_old_run(tmp_path):
    m=module('newsidecar','wandb_sidecar.py');root=tmp_path
    (root/'curriculum.json').write_text(json.dumps({'stage_index':0}))
    for index,name in enumerate(m.STAGES[:2]):
        f=root/name;f.mkdir();(f/'latest.pt').write_bytes(b'unopened')
        (f/'config.json').write_text(json.dumps({'wandb':{'enabled':True,'project':'duelforge'}}))
        (f/'metrics.jsonl').write_text(''.join(json.dumps({'learning_transitions':s})+'\n' for s in (100,200,300)))
    logs=[];runs=[];queries=[]
    class Run:
        step=0;entity='test';url='test'
        def __init__(self):self.finished=False
        def log(self,row,step):
            logs.append(step);(root/'curriculum.json').write_text(json.dumps({'stage_index':1}))
        def finish(self):self.finished=True
    def init(**kw):
        assert kw['reinit']=='create_new'
        assert all(not r.finished for r in runs)
        r=Run();runs.append(r);return r
    def query(path):queries.append(path);return S(lastHistoryStep=200)
    fake=S(init=init,Settings=lambda **kw:kw,util=S(generate_id=lambda:'id'),Api=lambda **kw:S(run=query))
    m.run(root,fake,max_polls=3,interval=0)
    assert logs==[300,300] and len(queries)==2
    assert len(runs)==2 and all(r.finished for r in runs)

def test_acquisition_tracker_is_external_without_environment_flag(monkeypatch,tmp_path):
    from duelforge.train import tracker
    monkeypatch.delenv('DUELFORGE_WANDB_EXTERNAL',raising=False)
    assert tracker({'acquisition':{'stage':'contact'},'wandb':{'enabled':True}},tmp_path,None) is None
