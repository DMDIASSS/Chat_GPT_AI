import hashlib
from pathlib import Path
import struct
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from slater_tas_decoder_v036t import parse_tas, export_one, TRAILER_BYTES


def fake_tas(filename, frames=2, version=1):
    return struct.pack('<II', version, frames) + b''.join(struct.pack('<I7f', 12+i, 0.5, -0.5, 0, 0, 1, 0, 0) for i in range(frames)) + b'X'*TRAILER_BYTES


def test_read_frames(tmp_path):
    p = tmp_path / 'test.data'
    raw = fake_tas('test')
    p.write_bytes(raw)
    rows, info = parse_tas(p)
    assert len(rows) == 2 and rows[1][0] == 13 and rows[0][1][0] == 0.5
    assert info['sha256'] == hashlib.sha256(raw).hexdigest()
    assert info['trailer_128_hex'] == (b'X'*128).hex()


def test_version_rejected(tmp_path):
    p = tmp_path / 'test.data'; p.write_bytes(fake_tas('test', version=2))
    with pytest.raises(ValueError, match='Unsupported'):
        parse_tas(p)


def test_truncated_rejected(tmp_path):
    p = tmp_path / 'test.data'; p.write_bytes(fake_tas('test')[:-3])
    with pytest.raises(ValueError, match='length'):
        parse_tas(p)


def test_nan_rejected(tmp_path):
    p = tmp_path / 'test.data'; raw = bytearray(fake_tas('test'))
    struct.pack_into('<f', raw, 12, float('nan'))
    p.write_bytes(raw)
    with pytest.raises(ValueError, match='Invalid analog'):
        parse_tas(p)


def test_csv_preserves_numbers_and_refuses_overwrite(tmp_path):
    inp = tmp_path / 'file.data'; inp.write_bytes(fake_tas('test'))
    dst = tmp_path / 'output'; dst.mkdir()
    info = export_one(inp, dst)
    csv = (dst / info['csv_file']).read_text()
    assert 'button_mask_u32' in csv and '0x0000000c' in csv
    with pytest.raises(FileExistsError):
        export_one(inp, dst)
