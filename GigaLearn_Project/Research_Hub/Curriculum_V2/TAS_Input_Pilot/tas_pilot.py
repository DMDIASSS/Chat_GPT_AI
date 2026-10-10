"""Input-only TAS memorization pilot. Never produces a gameplay-valid GigaLearn checkpoint.

Blaku TAS .data format: version/count, repeated uint32 flags + seven float32 inputs,
then a 128-byte trailer containing plausible initial-state fields. The actual
controller-bit/float semantics and per-frame gameplay states remain unverified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import struct
import sys
import time
import uuid

FRAME = struct.Struct('<I7f')
HEADER = struct.Struct('<II')
TRAILER_BYTES = 128
MAX_FRAMES = 400_000

class TASFormatError(ValueError):
    pass


def load_tas(file: Path):
    file = Path(file)
    data = file.read_bytes()
    if len(data) < HEADER.size + FRAME.size + TRAILER_BYTES:
        raise TASFormatError('too small')
    ver, count = HEADER.unpack_from(data)
    if ver != 1 or not (1 <= count <= MAX_FRAMES):
        raise TASFormatError('version/frame count unsupported')
    if len(data) != HEADER.size + count * FRAME.size + TRAILER_BYTES:
        raise TASFormatError('frame length/trailer mismatch')
    rows = [FRAME.unpack_from(data, HEADER.size + i * FRAME.size) for i in range(count)]
    if any(v > 127 or not all(math.isfinite(float(x)) and abs(float(x)) <= 1.0001 for x in f)
           for v, *f in rows):
        raise TASFormatError('invalid flag or analog controls')
    tail = data[-TRAILER_BYTES:]
    candidate_car = tuple(float(v) for v in struct.unpack_from('<3f', tail, 12))
    candidate_ball = tuple(float(v) for v in struct.unpack_from('<3f', tail, 64))
    plausible = (all(math.isfinite(x) and abs(x) <= 8000 for x in candidate_car + candidate_ball)
                 and (-500 <= candidate_car[2] <= 5000) and (-500 <= candidate_ball[2] <= 5000))
    return {
        'source': str(file.resolve()), 'sha256': hashlib.sha256(data).hexdigest(),
        'frames': count, 'rows': rows,
        'candidate_initial_car_xyz': [round(x, 3) for x in candidate_car] if plausible else None,
        'candidate_initial_ball_xyz': [round(x, 3) for x in candidate_ball] if plausible else None,
        'candidate_state_verified': False,
    }


def scan(root: Path):
    root = Path(root)
    if not root.is_dir():
        raise FileNotFoundError('TAS input folder does not exist: ' + str(root))
    found = sorted(root.rglob('*.data'), key=lambda p: str(p).casefold())
    if len(found) > 2000:
        raise TASFormatError('too many files')
    accepted, errors = [], []
    seen = set()
    for file in found:
        try:
            clip = load_tas(file)
            if clip['sha256'] in seen:
                continue
            seen.add(clip['sha256'])
            accepted.append(clip)
        except (OSError, TASFormatError) as ex:
            errors.append({'name': file.name, 'error': str(ex)})
    return accepted, errors


def public_summary(clips, errors):
    return {
        'mode': 'input-sequence-only; NOT gameplay behavior cloning',
        'valid_unique_files': len(clips), 'frames': sum(c['frames'] for c in clips),
        'errors': errors,
        'candidates': [{k: c[k] for k in ('source','frames','candidate_initial_car_xyz','candidate_initial_ball_xyz','candidate_state_verified')}
                       for c in clips[:25]],
        'blocking_issues': [
            'Starting-position offsets are plausible, not a confirmed complete RocketSim state',
            'No verified exact analog field mapping or flag bit meanings',
            'No reference per-frame car/ball trajectory: cannot compute a positional tracking loss',
            'This pilot must NOT be passed to GigaLearn PPO or advertised as a mechanics-capable bot',
        ],
    }


def _torch():
    try:
        import torch
        from torch import nn
        return torch, nn
    except ImportError as ex:
        raise RuntimeError('PyTorch is required. Run with Python 3.11 and the project .venv site-packages.') from ex


def fit(folder: Path, output_root: Path, epochs: int = 5, max_frames: int = 120_000):
    if not 1 <= epochs <= 20:
        raise ValueError('epochs must be 1..20')
    clips, errors = scan(folder)
    if len(clips) < 2:
        raise TASFormatError('need at least two structurally valid TAS files')
    torch, nn = _torch()
    torch.set_num_threads(max(1, min(4, torch.get_num_threads())))
    torch.manual_seed(4219)
    random.seed(4219)
    # No assumptions about 120 Hz controller semantics are made here.
    # This is time-conditioned memory, not state-conditioned gameplay policy.
    feature_rows, analog, flags, clip_ids, val_indicator = [], [], [], [], []
    indices = list(range(len(clips)))
    rng = random.Random(4219)
    rng.shuffle(indices)
    budget = max(8, max_frames // len(clips))
    for ci, clip in enumerate(clips):
        rows = clip['rows']
        stride = max(1, math.ceil(len(rows) / budget))
        sampled = list(range(0, len(rows), stride))
        for ri in sampled:
            bitfield, *raw = rows[ri]
            t = ri / max(1, len(rows) - 1)
            feats = [t, len(rows) / 2000.0]
            for freq in (1, 2, 4, 8):
                feats.extend((math.sin(2 * math.pi * freq * t), math.cos(2 * math.pi * freq * t)))
            # No unverified car/ball positions are input features.
            feature_rows.append(feats)
            analog.append(raw)
            flags.append([(int(bitfield) >> bit) & 1 for bit in range(7)])
            clip_ids.append(ci)
            # Hold out the latter 15% of each clip to test temporal prediction.
            # This is NOT an unseen-sequence or gameplay generalization test.
            val_indicator.append(t >= 0.85)
    x = torch.tensor(feature_rows, dtype=torch.float32)
    a = torch.tensor(analog, dtype=torch.float32)
    b = torch.tensor(flags, dtype=torch.float32)
    ids = torch.tensor(clip_ids, dtype=torch.int64)
    val = torch.tensor(val_indicator, dtype=torch.bool)
    train = ~val
    if int(train.sum()) < 500 or int(val.sum()) < 30:
        raise TASFormatError('too few frames for a split')

    class SequenceModel(nn.Module):
        def __init__(self, n_clips):
            super().__init__()
            self.embed = nn.Embedding(n_clips, 24)
            self.layers = nn.Sequential(nn.Linear(x.shape[1] + 24, 128), nn.GELU(),
                                        nn.Linear(128, 128), nn.GELU(), nn.Linear(128, 14))
        def forward(self, f, c):
            return self.layers(torch.cat((f, self.embed(c)), dim=1))

    model = SequenceModel(len(clips))
    optim = torch.optim.Adam(model.parameters(), lr=0.001)
    base = (a[val] - a[train].mean(dim=0, keepdim=True)).abs().mean().item()
    baseline_flags = ((b[train].mean(dim=0, keepdim=True) >= 0.5) == b[val]).all(dim=1).float().mean().item()
    train_idx = torch.where(train)[0]
    loss_log = []
    best_mae = float('inf')
    best_state = None
    best_epoch = 0
    for epoch in range(1, epochs + 1):
        model.train()
        perm = train_idx[torch.randperm(len(train_idx))]
        total_loss = 0.0
        for batch in perm.split(1024):
            pred = model(x[batch], ids[batch])
            pred_analog = torch.tanh(pred[:, :7])
            loss = nn.functional.smooth_l1_loss(pred_analog, a[batch]) + 0.25 * nn.functional.binary_cross_entropy_with_logits(pred[:, 7:], b[batch])
            optim.zero_grad(set_to_none=True)
            loss.backward()
            optim.step()
            total_loss += float(loss.item()) * len(batch)
        model.eval()
        with torch.no_grad():
            out = model(x[val], ids[val])
            val_mae = float((torch.tanh(out[:, :7]) - a[val]).abs().mean().item())
            flag_exact = float(((out[:, 7:] >= 0) == b[val]).all(dim=1).float().mean().item())
        record = {'epoch': epoch, 'training_objective': total_loss / len(train_idx),
                  'heldout_last_15_percent_analog_mae': val_mae,
                  'heldout_last_15_percent_exact_flag_match': flag_exact}
        loss_log.append(record)
        print(json.dumps(record), flush=True)
        if val_mae < best_mae:
            best_mae, best_epoch = val_mae, epoch
            best_state = {k: v.detach().cpu().clone() for k,v in model.state_dict().items()}
    if not (best_mae < base):
        status = 'not_better_than_constant_baseline'
    else:
        status = 'input_memory_passed_analog_baseline_only'
    stamp = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()) + '_' + uuid.uuid4().hex[:6]
    dest = Path(output_root) / ('tas_input_' + stamp)
    dest.mkdir(parents=True, exist_ok=False)
    weights = dest / 'tas_input_memory.pt'
    torch.save({'state_dict': best_state, 'feature_columns': 10,
                'clip_sha256': [c['sha256'] for c in clips], 'epochs': best_epoch,
                'type': 'tas_input_sequence_memory_not_gigalearn_policy'}, weights)
    result = {**public_summary(clips, errors), 'status': status,
              'saved_model': str(weights), 'checkpoint_kind': 'tas_input_sequence_memory_not_gigalearn',
              'train_samples': int(train.sum()), 'val_samples': int(val.sum()),
              'baseline_analog_mae': base, 'baseline_exact_flag_match': baseline_flags,
              'best_epoch': best_epoch, 'best_analog_mae': best_mae,
              'history': loss_log, 'positional_error': None,
              'trajectory_validated': False, 'can_seed_gigalearn': False,
              'next_stage': 'Get verified TAS initial pose, controller mapping, physics timing and per-frame states before native GigaLearn distillation.'}
    (dest / 'report.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps({'status': status, 'report': str(dest / 'report.json'), 'saved_model': str(weights),
                      'best_analog_mae': best_mae, 'baseline_analog_mae': base,
                      'positional_error': None, 'can_seed_gigalearn': False}, indent=2))
    return result


def opponent_plan(output: Path, cycles: int = 3, games_per_opponent: int = 4):
    if not (1 <= cycles <= 50 and 1 <= games_per_opponent <= 1000):
        raise ValueError('out-of-range plan')
    schedule = [{'round': i+1, 'teacher': opp, 'games': games_per_opponent,
                 'side_swap': True, 'weights_read_only': True}
                for i, opp in enumerate(('Nexto', 'Cycle 9', 'Wavedash') * cycles)]
    report = {'kind': 'plan_only_no_opponent_execution',
              'must_build_native_pt_opponent_bridge': True,
              'training_target': 'isolated future GigaLearn student; never overwrite teacher',
              'schedule': schedule}
    output = Path(output)
    if output.exists():
        raise FileExistsError('Refuse overwrite existing plan')
    output.parent.mkdir(exist_ok=True, parents=True)
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description='Safe TAS input-memory pilot (NOT a GigaLearn mechanics trainer)')
    sub = ap.add_subparsers(dest='cmd', required=True)
    i = sub.add_parser('inspect'); i.add_argument('--folder', required=True); i.add_argument('--out')
    t = sub.add_parser('train-inputs'); t.add_argument('--folder', required=True); t.add_argument('--output', required=True); t.add_argument('--epochs', type=int, default=5)
    p = sub.add_parser('plan-opponents'); p.add_argument('--output', required=True); p.add_argument('--cycles',type=int,default=3);p.add_argument('--games-per-opponent',type=int,default=4)
    args = ap.parse_args(argv)
    if args.cmd == 'inspect':
        clips, errors = scan(Path(args.folder))
        res = public_summary(clips, errors)
        if args.out:
            path = Path(args.out)
            if path.exists(): raise FileExistsError('Refuse overwrite existing report')
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(res, indent=2), encoding='utf-8')
        print(json.dumps(res, indent=2))
    elif args.cmd == 'train-inputs': fit(Path(args.folder),Path(args.output),args.epochs)
    else:
        r = opponent_plan(Path(args.output),args.cycles,args.games_per_opponent)
        print(json.dumps({'status':r['kind'],'rounds':len(r['schedule']),'output':args.output},indent=2))

if __name__ == '__main__':
    try: main()
    except Exception as ex:
        print('TAS PILOT ERROR:', ex, file=sys.stderr)
        sys.exit(1)
