import json,struct
import numpy as np
import pytest
from audit_native_replay_bank import audit
from slater_native_teacher_repair import bank_rows

def test_teacher_bank_splits_and_training_audit_do_not_use_holdout(tmp_path):
    teacher=tmp_path/'teacher.pt';teacher.write_bytes(b'identity fixture')
    rows=np.zeros((120,231),dtype=np.float32);rows[:,229]=1;rows[:,139+16]=1
    rows[80:100,-1]=1;rows[100:,-1]=2
    rows[100:,139+16]=0;rows[100:,139+8]=1
    rows[:,52+19]=1
    bank=tmp_path/'bank.bin';meta=bank_rows(rows,bank,teacher,{0:[1,2],1:[3],2:[4]})
    assert meta['partitions']=={'0':80,'1':20,'2':20}
    assert meta['train_idle_target_mass']==0
    report=audit(bank);assert report['rows']==80 and report['idle_target_mass']==0 and report['ground_idle_target_mass']==0
    with pytest.raises(FileExistsError):bank_rows(rows,bank,teacher,{})


def test_teacher_bank_refuses_bad_targets_or_missing_splits(tmp_path):
    teacher=tmp_path/'teacher.pt';teacher.write_bytes(b'fixture')
    rows=np.zeros((120,231),dtype=np.float32);rows[:,229]=1
    with pytest.raises(ValueError):bank_rows(rows,tmp_path/'bad.bin',teacher,{})
    rows[:,139+16]=1
    with pytest.raises(ValueError):bank_rows(rows,tmp_path/'bad.bin',teacher,{})


def test_actor_kl_metrics_keep_scientific_notation_and_do_not_invent_values():
    import importlib.util
    from pathlib import Path
    path=Path('GigaLearn_Project/Native_Backend/native_setup.py');spec=importlib.util.spec_from_file_location('metric_helper',path);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    report=mod.training_metrics('Policy Loss: -2.3e-04\nMean KL Divergence: 0\nPost-update PPO KL: 3.813448e-04\nLearner Idle Fraction: 0.0470\n')
    assert report['Policy Loss']==pytest.approx(-.00023)
    assert report['Post-update PPO KL']==pytest.approx(.0003813448)
    assert 'Teacher KL' not in report
