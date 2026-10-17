"""Prevent accidental retraining, input drift and progress-loss confusion."""
from pathlib import Path
import json
import shutil
import tempfile
import uuid
import numpy as np
import pytest
import torch
import replay_il_workflow as workflow
from replay_il_prepare_snapshot import freeze_inputs
from slater_v041_core import atomic_json,sha256
from test_replay_imitation import raw_rows,fixture_dataset


def layout(tmp_path,monkeypatch,*,epoch=None,stale=0):
    monkeypatch.setattr(workflow,'ROOT',tmp_path)
    folder,dataset,marker=workflow.locations('mixed')
    dataset.mkdir(parents=True);atomic_json(dataset/'manifest.json',{'samples':100,'matches_by_format':{'3v3':6}})
    if epoch is not None:
        folder.mkdir(parents=True);progress={'epoch':epoch,'updates':epoch*10,'stale_epochs':stale}
        torch.save({'progress':progress},folder/'latest.pt');atomic_json(folder/'progress.json',progress)
    import audit_replay_mix
    monkeypatch.setattr(audit_replay_mix,'audit',lambda dataset,**kwargs:{'verified_3v3_coverage':True})
    return folder,dataset,marker


@pytest.mark.parametrize('epoch,stale,expected',[(10,0,'COMPLETE'),(3,4,'EARLY_STOPPED')])
def test_finished_or_early_stopped_run_does_not_add_more_training(tmp_path,monkeypatch,epoch,stale,expected):
    folder,dataset,marker=layout(tmp_path,monkeypatch,epoch=epoch,stale=stale)
    before={p:sha256(p) for p in folder.iterdir()}
    monkeypatch.setattr(workflow.subprocess,'run',lambda *a,**k:pytest.fail('Completed run launched a training process'))
    assert workflow.start('mixed',dataset,epochs=10)==0
    assert json.loads(marker.read_text())['stage']==expected
    assert before=={p:sha256(p) for p in before}


def test_resume_uses_checkpoint_not_stale_json_and_remaining_total_epochs(tmp_path,monkeypatch):
    folder,dataset,marker=layout(tmp_path,monkeypatch,epoch=4)
    atomic_json(folder/'progress.json',{'epoch':1,'updates':10}) # Interrupted JSON write after checkpoint save.
    commands=[]
    def run(command,**kwargs):
        commands.append(command);return type('Result',(),{'returncode':0})()
    monkeypatch.setattr(workflow.subprocess,'run',run)
    assert workflow.start('mixed',dataset,epochs=10)==0
    assert len(commands)==1 and commands[0][4]=='resume'
    assert commands[0][-2:]==['--epochs','6']
    assert workflow.summary('mixed',dataset)['epoch']==4


def test_fresh_run_does_not_create_training_folder_before_trainer(tmp_path,monkeypatch):
    folder,dataset,marker=layout(tmp_path,monkeypatch)
    def run(command,**kwargs):
        assert not folder.exists();assert command[4]=='train';return type('Result',(),{'returncode':0})()
    monkeypatch.setattr(workflow.subprocess,'run',run)
    assert workflow.start('mixed',dataset)==0
    assert not folder.exists()


def test_completed_dataset_survives_previous_3v3_gate_without_reparsing(tmp_path,monkeypatch):
    folder,dataset,marker=layout(tmp_path,monkeypatch)
    atomic_json(dataset/'format_audit.json',{'verified_3v3_coverage':False})
    before=sha256(dataset/'manifest.json');calls=[]
    import replay_il_prepare_snapshot
    monkeypatch.setattr(replay_il_prepare_snapshot,'freeze_inputs',lambda *a,**k:pytest.fail('Completed cache was reparsed'))
    import audit_replay_mix
    def audit(path,*,require_3v3):
        assert path==dataset and not require_3v3
    monkeypatch.setattr(audit_replay_mix,'audit',audit)
    def run(command,**kwargs):
        calls.append(command);assert command[4]=='train'
        return type('Result',(),{'returncode':0})()
    monkeypatch.setattr(workflow.subprocess,'run',run)
    assert workflow.summary('mixed',dataset)['stage']=='READY_TO_TRAIN'
    assert workflow.start('mixed',dataset)==0
    assert len(calls)==1 and sha256(dataset/'manifest.json')==before


def test_fresh_default_discovers_all_nested_modes_and_keeps_existing_snapshot_budget(tmp_path):
    inputs=tmp_path/'data/replays'
    for folder in ('ranked-duels','ranked-doubles','ranked-standard/group','another-folder'):
        path=inputs/folder;path.mkdir(parents=True);(path/'one.replay').write_bytes(folder.encode())
    dataset=tmp_path/'dataset'
    frozen=freeze_inputs(dataset,[inputs])
    assert len(frozen['files'])==4 and frozen['max_replays']==100000
    older=tmp_path/'older'
    previous=freeze_inputs(older,[inputs],max_replays=3000,max_samples=400000)
    assert freeze_inputs(older,[inputs])==previous


def test_format_policy_cli_defaults_and_legacy_flag(tmp_path,monkeypatch):
    monkeypatch.setattr(workflow,'ROOT',tmp_path);calls=[]
    monkeypatch.setattr(workflow,'start',lambda *a,**k:calls.append(k) or 0)
    for args in (['start'],['start','--allow-no-3v3'],['start','--require-3v3']):assert workflow.main(args)==0
    assert [c['require_3v3'] for c in calls]==[False,False,True]
    assert all(c['max_replays'] is None and c['max_samples'] is None for c in calls)


def test_explicit_sample_budget_cannot_silently_skip_tail_replays(tmp_path):
    inputs=tmp_path/'inputs';inputs.mkdir()
    for i in range(8):(inputs/f'{i}.replay').write_bytes(str(i).encode())
    with pytest.raises(ValueError,match='cannot cover every selected replay'):
        freeze_inputs(tmp_path/'dataset',[inputs],max_samples=100)
    assert not (tmp_path/'dataset/input_snapshot.json').exists()


def test_closed_log_cleanup_does_not_throw_or_change_saved_log():
    import io
    from replay_il_prepare_snapshot import ClosingSafeTee
    screen=io.StringIO();log=io.StringIO();tee=ClosingSafeTee(screen,log)
    tee.write('saved');assert log.getvalue()=='saved';log.close()
    tee.write('cleanup');tee.flush();assert screen.getvalue()=='savedcleanup'


def test_pause_preserves_checkpoints_and_parser_failure_never_starts_training(tmp_path,monkeypatch):
    monkeypatch.setattr(workflow,'ROOT',tmp_path)
    folder,dataset,marker=workflow.locations('mixed');inputs=tmp_path/'replays';inputs.mkdir()
    (inputs/'one.replay').write_bytes(b'private-test-fixture')
    calls=[]
    def run(command,**kwargs):
        calls.append(command);return type('Result',(),{'returncode':1})()
    monkeypatch.setattr(workflow.subprocess,'run',run)
    assert workflow.start('mixed',dataset,inputs=[str(inputs)])==1
    assert len(calls)==1 and 'replay_il_prepare_snapshot.py' in calls[0][2]
    assert not folder.exists()
    workflow.pause('mixed',dataset);assert (dataset/'pause.flag').exists()
    assert json.loads(marker.read_text())['stage']=='STOPPED_WITH_SAVED_PROGRESS'


def test_input_snapshot_excludes_new_downloads_and_rejects_changed_budget_or_content(tmp_path):
    inputs=tmp_path/'inputs';inputs.mkdir();first=inputs/'a.replay';first.write_bytes(b'first')
    dataset=tmp_path/'dataset';initial=freeze_inputs(dataset,[inputs],max_replays=3000,max_samples=500000)
    (inputs/'b.replay').write_bytes(b'second')
    resumed=freeze_inputs(dataset,[inputs],max_replays=3000,max_samples=500000)
    assert resumed==initial and len(resumed['files'])==1
    with pytest.raises(ValueError,match='budget is frozen'):freeze_inputs(dataset,[inputs],max_replays=1000,max_samples=500000)
    first.write_bytes(b'changed-size')
    with pytest.raises(ValueError,match='Frozen replay changed'):freeze_inputs(dataset,[inputs],max_replays=3000,max_samples=500000)


def test_results_uses_validation_without_running_or_reopening_heldout_test(tmp_path,monkeypatch):
    folder,dataset,_=layout(tmp_path,monkeypatch,epoch=10)
    (folder/'best.pt').write_bytes(b'private-model-fixture')
    atomic_json(folder/'selected.json',{'sha256':sha256(folder/'best.pt'),'validation':{
        'token_top1':.3,'value_mse':.2,'constant_zero_value_mse':.25}})
    atomic_json(folder/'epoch_0010.json',{'parameter_change_l2':2.})
    (folder/'heldout_test.json').write_text('This file must not be read by status/results.')
    report=workflow.summary('mixed',dataset)
    assert report['optimizer_change_verified'] and report['selected_hash_valid']
    assert report['value_mse_reduction_vs_zero_percent']==pytest.approx(20.)
    assert not report['competitive_strength_verified']


def test_progress_tail_tolerates_partial_writes_and_reads_latest_complete_event(tmp_path):
    path=tmp_path/'events.jsonl'
    path.write_text(json.dumps({'update':42,'kind':'supervised_batch','metrics':{'train/policy_ce':3.1}})+'\n{"update":43,')
    assert workflow.last_event(path)['update']==42
    assert workflow.last_event(tmp_path/'missing')=={}


def test_real_subprocess_workflow_trains_resumes_and_preserves_a_completed_run(raw_rows):
    # Synthetic physics fixtures are isolated engineering tests, never user's
    # replay data or candidates for the user's selected bot.
    base=workflow.ROOT/'data/isolated/replay_debug';base.mkdir(parents=True,exist_ok=True)
    run='workflow_test_'+uuid.uuid4().hex[:10]
    folder,_,marker=workflow.locations(run)
    try:
        with tempfile.TemporaryDirectory(prefix='workflow_fixture_',dir=base) as temporary:
            dataset=fixture_dataset(Path(temporary)/'dataset',raw_rows[:8])
            # No 3v3 in this completed dataset. The default must verify/reuse
            # its chunks and actually train, even after a legacy audit failed.
            atomic_json(dataset/'format_audit.json',{'verified_3v3_coverage':False})
            manifest_before=sha256(dataset/'manifest.json')
            shard_before={p:sha256(p) for p in dataset.rglob('*.npz')}
            assert workflow.start(run,dataset,epochs=1,device='cpu',wandb_mode='disabled')==0
            assert sha256(dataset/'manifest.json')==manifest_before
            assert all(sha256(p)==digest for p,digest in shard_before.items())
            first=workflow.summary(run,dataset,epochs=1)
            assert first['epoch']==1 and first['updates']>0 and first['optimizer_change_verified']
            before=sha256(folder/'latest.pt')
            assert workflow.start(run,dataset,epochs=1,device='cpu',wandb_mode='disabled',require_3v3=False)==0
            assert sha256(folder/'latest.pt')==before
            assert workflow.start(run,dataset,epochs=2,device='cpu',wandb_mode='disabled',require_3v3=False)==0
            final=workflow.summary(run,dataset,epochs=2)
            assert final['epoch']==2 and final['updates']>first['updates']
            from analyze_replay_policy import analyze
            before_model=sha256(folder/'best.pt');before_training=sha256(folder/'latest.pt')
            report=analyze(folder,dataset,device='cpu',limit=8)
            assert report['split']=='validation' and report['samples']==8
            assert report['training_baseline_complete'] and 0<=report['training_constant_baseline_top1']<=1
            assert sha256(folder/'best.pt')==before_model and sha256(folder/'latest.pt')==before_training
            assert not (folder/'heldout_test.json').exists()
    finally:
        shutil.rmtree(folder,ignore_errors=True);marker.unlink(missing_ok=True);marker.with_suffix('.lock').unlink(missing_ok=True)
