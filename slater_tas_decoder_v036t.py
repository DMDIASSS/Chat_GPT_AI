#!/usr/bin/env python3
"""Lossless field extraction for the six supplied Blaku-style RL TAS .data files.

This does NOT assert the undocumented controller channel semantics and does not
create an RLBot-compatible trained policy.
"""
from __future__ import annotations
import argparse
from collections import Counter
import csv
import hashlib
import json
import math
from pathlib import Path
import struct

HEADER = struct.Struct('<II')
INPUT = struct.Struct('<I7f')
TRAILER_BYTES = 128
FIELD_NAMES = ['frame', 'button_mask_u32', 'button_mask_hex'] + [f'analog_{i}' for i in range(7)]


def parse_tas(path: Path):
    raw = path.read_bytes()
    if len(raw) < HEADER.size + TRAILER_BYTES:
        raise ValueError('File is shorter than expected header and trailer')
    version, n = HEADER.unpack_from(raw, 0)
    if version != 1 or n < 1 or n > 10000000:
        raise ValueError(f'Unsupported header version={version} frames={n}')
    expected = HEADER.size + n * INPUT.size + TRAILER_BYTES
    if len(raw) != expected:
        raise ValueError(f'Unexpected file length {len(raw)}; expected {expected}')
    rows = []
    for i in range(n):
        flags, *vals = INPUT.unpack_from(raw, HEADER.size + i * INPUT.size)
        if not all(math.isfinite(x) and abs(x) <= 1.0001 for x in vals):
            raise ValueError(f'Invalid analog values at frame {i}')
        rows.append((flags, vals))
    trailer = raw[-TRAILER_BYTES:]
    counts = Counter(flag for flag, _ in rows)
    meta = {
        'source_name': path.name,
        'sha256': hashlib.sha256(raw).hexdigest(),
        'format': 'v1_binary_8B_header_32B_records_128B_trailer',
        'version': version,
        'frames': n,
        'frame_stride_bytes': INPUT.size,
        'raw_button_mask_counts': {str(k): v for k, v in sorted(counts.items())},
        'nonzero_button_mask_frames': sum(count for flag, count in counts.items() if flag),
        'analog_ranges': [[round(min(r[1][j] for r in rows), 6), round(max(r[1][j] for r in rows), 6)] for j in range(7)],
        'trailer_128_hex': trailer.hex(),
        'important': [
            'Only the binary storage structure is verified here, not the button-bit layout or analog semantics.',
            'A TAS recording is an open-loop input sequence, not a state->action demonstration.',
            '120Hz duration is an estimate until the producer/playback tick rate is confirmed.',
            'Some names imply multiple players, but these files each expose one stream of 32-byte records.'
        ]
    }
    return rows, meta


def export_one(path: Path, directory: Path):
    rows, meta = parse_tas(path)
    name = path.name + '.csv'
    dest = directory / name
    with dest.open('x', newline='', encoding='utf-8') as out:
        writer = csv.writer(out)
        writer.writerow(FIELD_NAMES)
        for i, (flags, floats) in enumerate(rows):
            writer.writerow([i, flags, f'0x{flags:08x}'] + [format(v, '.9g') for v in floats])
    meta['csv_file'] = name
    return meta


def main():
    p = argparse.ArgumentParser(description='Decode v1 TAS .data files without guessing undocumented controls')
    p.add_argument('--input-dir', type=Path, required=True)
    p.add_argument('--out-dir', type=Path, required=True)
    a = p.parse_args()
    sources = sorted(a.input_dir.glob('*.data'))
    if not sources:
        p.error('No .data files in input directory')
    # Parse *all* first so a malformed input cannot cause a partial export.
    for path in sources:
        parse_tas(path)
    if a.out_dir.exists():
        raise FileExistsError(f'Refusing to overwrite existing directory: {a.out_dir}')
    a.out_dir.mkdir(parents=True, exist_ok=False)
    files = [export_one(path, a.out_dir) for path in sources]
    manifest = {
        'schema': 'slater_tas_v036t_raw_v1',
        'files': files,
        'total_frames': sum(x['frames'] for x in files),
        'estimated_total_seconds_at_120hz': round(sum(x['frames'] for x in files) / 120, 3),
        'format_is_reverse_engineered': True,
        'not_training_ready': True,
    }
    with (a.out_dir / 'manifest.json').open('x', encoding='utf-8') as out:
        json.dump(manifest, out, indent=2, ensure_ascii=False)
    print('TAS_RAW_FRAMES', manifest['total_frames'], 'FILES', len(files))
    for f in files:
        print('TAS_FILE', f['source_name'], 'FRAMES', f['frames'], 'SHA256', f['sha256'])
    print('TAS_EXTRACTED_TO', a.out_dir.resolve())
    print('WARNING: Unknown flag mapping; not yet safe for policy behavior cloning')

if __name__ == '__main__':
    main()
