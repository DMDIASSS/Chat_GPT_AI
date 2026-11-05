from argparse import Namespace
import json
from pathlib import Path
import pytest
from filelock import FileLock,Timeout
from nova import imitation
from nova.core import write_model_meta,check_model
from nova.training import resolve_model


def make_run(tmp_path):
    run=tmp_path/'runs/copy02';(run/'checkpoints').mkdir(parents=True)
    records={}
    for name,step in [('published',250000),('best',1050000),('resume',1050000)]:
        path=run/'checkpoints'/f'{name}.zip';path.write_bytes(name.encode())
        write_model_meta(path,timesteps=step)
        records[name]=dict(path=str(path.relative_to(run)),sha256=check_model(path)['sha256'],timesteps=step)
    (run/'copy_state.json').write_text(json.dumps(records))
    (run/'latest.json').write_text(json.dumps(records['published']))
    (run/'config.json').write_text('{}')
    return run,records


def test_named_selection_finds_new_candidate_without_changing_published_pointer(tmp_path):
    run,records=make_run(tmp_path);before=(run/'latest.json').read_bytes()
    for choice,key in [('published','published'),('validation','best'),('resume','resume')]:
        path=resolve_model(run,choice)
        assert path==run/records[key]['path']
        assert check_model(path)['sha256']==records[key]['sha256']
    assert (run/'latest.json').read_bytes()==before
    state=json.loads((run/'copy_state.json').read_text());state['best']['sha256']='0'*64
    (run/'copy_state.json').write_text(json.dumps(state))
    with pytest.raises(ValueError,match='run record'):resolve_model(run,'validation')


def test_named_selection_rejects_escape_and_requires_a_run_folder(tmp_path):
    run,records=make_run(tmp_path)
    with pytest.raises(ValueError,match='run folder'):resolve_model(run/records['best']['path'],'validation')
    state=json.loads((run/'copy_state.json').read_text());state['best']['path']='../outside.zip'
    (run/'copy_state.json').write_text(json.dumps(state))
    with pytest.raises(ValueError,match='escapes'):resolve_model(run,'validation')


def test_candidate_comparison_uses_published_baseline_and_preserves_training_state(tmp_path,monkeypatch):
    from nova import evaluation
    run,records=make_run(tmp_path);monkeypatch.setattr(imitation,'ROOT',tmp_path)
    calls=[];reports=[]
    monkeypatch.setattr(evaluation,'evaluate',lambda args:calls.append(args))
    monkeypatch.setattr(imitation,'report_copy',lambda args:reports.append(args.run))
    before={p.name:p.read_bytes() for p in run.glob('*.json')}
    imitation.compare_copy(Namespace(run='copy02',candidate='validation',pairs=5,seconds=20))
    assert len(calls)==2 and reports==['copy02']
    for call in calls:
        assert Path(call.model)==run/records['best']['path']
        assert Path(call.baseline)==run/records['published']['path']
        assert call.pairs==5 and call.seconds==20
    assert calls[0].seed==950001 and calls[1].seed==960001
    assert calls[0].out!=calls[1].out
    assert {p.name:p.read_bytes() for p in run.glob('*.json')}==before
    with FileLock(str(run/'train.lock'),timeout=0):
        with pytest.raises(Timeout):
            imitation.compare_copy(Namespace(run='copy02',candidate='validation',pairs=5,seconds=20))
    assert len(calls)==2


def test_report_labels_candidate_and_published_metrics_separately(tmp_path,monkeypatch):
    import zipfile
    run,records=make_run(tmp_path);monkeypatch.setattr(imitation,'ROOT',tmp_path)
    state=json.loads((run/'copy_state.json').read_text())
    validation=dict(samples=1000,balanced_loss=3.7,accuracy=.17,by_scenario={'kickoff':{'samples':1000}})
    state.update(teachers=['nexto'],teacher_lock_sha256='f'*64,history=[],shards=[],phase='fit',
                 best_validation=validation,published_validation=dict(balanced_loss=9.6,accuracy=.10))
    (run/'copy_state.json').write_text(json.dumps(state))
    (run/'config.json').write_text(json.dumps(dict(copy={},curriculum={'weights':{'kickoff':1.}})))
    imitation.report_copy(Namespace(run='copy02'))
    out=next((tmp_path/'reports').glob('*.zip'))
    with zipfile.ZipFile(out) as z:
        report=json.loads(z.read('report.json'));html=z.read('progress.html').decode()
    assert report['checkpoint_roles']['published']['timesteps']==250000
    assert report['checkpoint_roles']['validation']['timesteps']==1050000
    assert report['best_validation']['balanced_loss']==3.7 and report['selected_validation']['balanced_loss']==9.6
    assert any('launcher 33' in n and '250000' in n and '1050000' in n for n in report['review_notes'])
    assert 'Published policy teacher-copy metrics' in html and 'Best held-out candidate teacher-copy metrics' in html
    assert str(run) not in json.dumps(report)
