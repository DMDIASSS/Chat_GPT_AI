from pathlib import Path
import sys, struct, json
import numpy as np
import pytest
import torch
from torch import nn

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import slater_nexto_kickoff_v037a as k
import slater_tas_decoder_v036t2 as tas


def synth_tas(n, version=1):
    return struct.pack('<II', version, n) + b''.join(
        struct.pack('<I7f', 12, .5, -.5, 0, 0, 1, 0, 0)
        for _ in range(n)) + bytes(tas.TRAILER_BYTES)


def test_fresh_torchscript_anchor_correct_and_disjoint(tmp_path):
    torch.manual_seed(7)
    source = nn.Sequential(nn.Linear(4, 12), nn.Tanh(), nn.Linear(12, 5)).eval()
    scripted = torch.jit.trace(source, torch.randn(1, 4))
    file = tmp_path / 'source.pt'
    torch.jit.save(scripted, str(file))
    student = torch.jit.load(str(file))
    with torch.no_grad():
        for p in student.parameters():p.add_(.3)
    snapshot = {key: val.detach().clone() for key,val in student.state_dict().items()}
    anchor = k.new_u60_anchor(file, snapshot, student)
    for a,b in zip(student.parameters(), anchor.parameters()):
        assert torch.equal(a,b)
        assert a.untyped_storage().data_ptr() != b.untyped_storage().data_ptr()
    before = [p.detach().clone() for p in anchor.parameters()]
    with torch.no_grad():
        for p in student.parameters():p.add_(1.)
        _ = anchor(torch.zeros(1,4))
    assert all(torch.equal(p,old) for p,old in zip(anchor.parameters(),before))


def test_no_deepcopy_teacher_or_requires_grad_mutation():
    source = (Path(__file__).resolve().parents[1] / 'slater_nexto_kickoff_v037a.py').read_text()
    assert 'teacher = new_u60_anchor(' in source
    assert 'copy.deepcopy(actor)' not in source
    assert 'for p in teacher.parameters():p.requires_grad_(False)' not in source


def test_zero_frame_is_not_exported_but_good_is(tmp_path, monkeypatch, capsys):
    src=tmp_path/'tas';src.mkdir()
    (src/'good.data').write_bytes(synth_tas(2))
    (src/'zero.data').write_bytes(synth_tas(0))
    (src/'bad_version.data').write_bytes(synth_tas(2,version=99))
    dest=tmp_path/'out'
    monkeypatch.setattr(sys,'argv',['tas','--input-dir',str(src),'--out-dir',str(dest)])
    tas.main()
    report=json.loads((dest/'manifest.json').read_text())
    assert report['total_files_scanned']==3
    assert report['total_files_exported']==1
    assert report['total_frames']==2
    assert {d['source_name'] for d in report['skipped']}=={'zero.data','bad_version.data'}
    assert not (dest/'zero.data.csv').exists()
    assert 'TAS_SKIPPED zero.data' in capsys.readouterr().out
    with pytest.raises(FileExistsError):tas.main()


def test_all_bad_fails_without_creating_output(tmp_path,monkeypatch):
    src=tmp_path/'tas';src.mkdir()
    (src/'empty.data').write_bytes(synth_tas(0))
    dest=tmp_path/'out'
    monkeypatch.setattr(sys,'argv',['tas','--input-dir',str(src),'--out-dir',str(dest)])
    with pytest.raises(SystemExit): tas.main()
    assert not dest.exists()


def test_bad_analog_not_silently_accepted(tmp_path,monkeypatch):
    src=tmp_path/'tas';src.mkdir()
    (src/'valid.data').write_bytes(synth_tas(1))
    damaged=bytearray(synth_tas(1));struct.pack_into('<f',damaged,12,float('nan'))
    (src/'corrupt.data').write_bytes(damaged)
    dest=tmp_path/'out'
    monkeypatch.setattr(sys,'argv',['tas','--input-dir',str(src),'--out-dir',str(dest)])
    tas.main()
    report=json.loads((dest/'manifest.json').read_text())
    assert len(report['files'])==1
    assert 'Invalid analog' in report['skipped'][0]['reason']


def test_control_sequence_is_unchanged():
    assert k.control_hash()==k.EXPECTED_SCRIPT_SHA256
    assert k.SCRIPT_TICKS==168
    arr=k.grouped_control(40,enabled=True,active=True,nn_control=np.zeros(8))
    assert tuple(arr.shape)==(8,8)
