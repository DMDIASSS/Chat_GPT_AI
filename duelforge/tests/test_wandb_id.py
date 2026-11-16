import importlib.util,json,re
from pathlib import Path
from types import SimpleNamespace as S

def test_new_run_id_works_without_wandb_util_and_is_reused(tmp_path):
    p=Path(__file__).resolve().parents[1]/'tools/wandb_sidecar.py'
    spec=importlib.util.spec_from_file_location('id_sidecar',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    f=tmp_path/'03_trajectory';f.mkdir()
    (tmp_path/'curriculum.json').write_text(json.dumps({'stage_index':2}))
    (f/'config.json').write_text(json.dumps({'wandb':{'enabled':True,'project':'test','name':'air01_jump_recovery'}}))
    (f/'latest.pt').write_bytes(b'never read')
    (f/'metrics.jsonl').write_text(json.dumps({'learning_transitions':61246563,'value':1})+'\n')
    ids=[];logs=[]
    class Run:
        step=0;entity='test';url='test'
        def log(self,row,step):logs.append(step)
        def finish(self):pass
    def init(**kw):ids.append(kw['id']);assert kw['name']=='air01_jump_recovery';return Run()
    # Deliberately no util attribute: the exact interface that failed on the PC.
    fake=S(init=init,Settings=lambda **kw:kw,Api=lambda **kw:S(run=lambda path:S(lastHistoryStep=-1)))
    m.run(tmp_path,fake,max_polls=1,interval=0)
    assert re.fullmatch('[0-9a-f]{8}',ids[0])
    assert logs==[61246563]
    m.run(tmp_path,fake,max_polls=1,interval=0)
    assert ids[0]==ids[1]
    assert json.loads((tmp_path/'external_wandb_ids.json').read_text())['03_trajectory']==ids[0]
    assert (f/'latest.pt').read_bytes()==b'never read'
