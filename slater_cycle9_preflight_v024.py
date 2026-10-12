"""Slater v0.2.4: read-only Cycle-9-native-policy integration preflight.

Run at the Windows project root:
  .venv\\Scripts\\python.exe slater_cycle9_preflight_v024.py \\
    --out data/isolated/cycle9_preflight_v024_01.json

This checks the REAL immutable SHA-pinned Cycle 9 checkpoint and exact
existing Nexto observation/action pipeline with a fresh RocketSim kickoff.
It does not train, optimize, save a policy or inspect/modify replay data.
"""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import traceback

import numpy as np
import torch


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as fp:
        for block in iter(lambda: fp.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def allowed_report(out: Path, root: Path) -> Path:
    dest = out.resolve()
    allowed = (root / 'data' / 'isolated').resolve()
    if not dest.is_relative_to(allowed) or dest.suffix != '.json':
        raise ValueError(f'Only new JSON reports in {allowed} are allowed; got {dest}')
    if dest.exists():
        raise FileExistsError(f'Refusing to replace preexisting report {dest}')
    return dest


def _network_logits(net, inputs):
    out = net(inputs)
    return out[0] if isinstance(out, tuple) else out


def perform_checks(root: Path) -> dict:
    from slater_research.checkpoint import CYCLE9, CYCLE9_SHA, cycle9_pair
    from afk_team_research import TeamObserver
    from nexto_teacher import nexto_actions
    from rlgym.rocket_league.sim import RocketSimEngine
    from rlgym.rocket_league.state_mutators import FixedTeamSizeMutator, KickoffMutator

    source = (root / 'vendor' / 'nexto' / 'nexto-model.pt').resolve()
    checkpoint = (root / CYCLE9).resolve()
    for path in (source, checkpoint):
        if not path.is_file():
            raise FileNotFoundError(f'Required existing model missing: {path}')
    before_ckpt_sha = sha256(checkpoint)
    if before_ckpt_sha != CYCLE9_SHA:
        raise RuntimeError(f'Cycle 9 SHA mismatch: expected {CYCLE9_SHA} got {before_ckpt_sha}')
    source_sha = sha256(source)
    print('CYCLE9_SHA256_VERIFIED', before_ckpt_sha, flush=True)
    print('NEXTO_SCRIPT_SHA256', source_sha, flush=True)

    torch.set_num_threads(2)
    student, teacher = cycle9_pair(root)
    student.eval()
    teacher.eval()
    student_ptrs = {int(p.data_ptr()) for p in student.parameters()}
    teacher_ptrs = {int(p.data_ptr()) for p in teacher.parameters()}
    independent = bool(student_ptrs and teacher_ptrs and not student_ptrs.intersection(teacher_ptrs))
    if not independent:
        raise RuntimeError('Student and frozen teacher share parameter storage or contain no parameters')
    print('INDEPENDENT_STUDENT_TEACHER', independent, flush=True)

    action_lookup = nexto_actions()
    controls = np.stack([np.asarray(action_lookup[i], dtype=np.float32).reshape(-1)
                         for i in range(90)])
    if controls.shape != (90, 8) or not np.isfinite(controls).all():
        raise RuntimeError(f'Unexpected native action lookup shape/values {controls.shape}')
    print('NATIVE_NEXTO_ACTIONS', controls.shape, flush=True)

    engine = RocketSimEngine(rlbot_delay=False)
    try:
        s = engine.create_base_state()
        FixedTeamSizeMutator(blue_size=1, orange_size=1).apply(s, {})
        KickoffMutator().apply(s, {})
        state = engine.set_state(s, {})
        aid = 'blue-0'
        views = TeamObserver().observe(state, {})
        if aid not in views:
            raise RuntimeError(f'TeamObserver did not return {aid}; returned {list(views)}')
        q, kv, mask = [np.asarray(x, dtype=np.float32) for x in views[aid]]
        if not all(np.isfinite(x).all() for x in (q, kv, mask)):
            raise RuntimeError('Nonfinite actor input from kickoff observation')
        tensors = tuple(torch.as_tensor(x[None], dtype=torch.float32) for x in (q, kv, mask))
        with torch.no_grad():
            a = _network_logits(student, tensors)
            b = _network_logits(teacher, tensors)
        if tuple(a.shape) != (1, 90) or tuple(b.shape) != (1, 90):
            raise RuntimeError(f'Unexpected Cycle9 output shapes {tuple(a.shape)} {tuple(b.shape)}')
        if not (torch.isfinite(a).all() and torch.isfinite(b).all()):
            raise RuntimeError('Nonfinite Cycle9 policy outputs')
        max_abs_diff = float((a - b).abs().max().item())
        if max_abs_diff > 1e-5:
            raise RuntimeError(f'Student/teacher outputs differ on identical kickoff: max_abs={max_abs_diff}')
        chosen_action = int(a.argmax(-1).item())
        chosen_control = controls[chosen_action]
        no_op = np.zeros((8, 8), dtype=np.float32)
        actions = {aid: np.repeat(chosen_control[None, :], 8, axis=0), 'orange-0': no_op}
        after = engine.step(actions, {})
        if not np.isfinite(after.ball.position).all():
            raise RuntimeError('Nonfinite ball state after physics step')
        if not np.isfinite(after.cars[aid].physics.position).all():
            raise RuntimeError('Nonfinite car state after physics step')
        print('ROCKETSIM_1V1_STEP', 'OK', 'native_action', chosen_action, flush=True)
        print('OBSERVER_SHAPES', json.dumps({'q': list(q.shape), 'kv': list(kv.shape), 'mask': list(mask.shape)}), flush=True)
        print('NATIVE_POLICY_OUTPUT', list(a.shape), 'max_student_teacher_diff', max_abs_diff, flush=True)

        # Exercise a gradient path for the independent student ONLY, with no optimizer step.
        # This verifies that the checkpoint can be a PPO initialization, not just a frozen bot.
        student.zero_grad(set_to_none=True)
        test_logits = _network_logits(student, tensors)
        torch.log_softmax(test_logits, dim=-1)[0, chosen_action].backward()
        grad_norm = float(sum(float(p.grad.detach().square().sum().item())
                              for p in student.parameters() if p.grad is not None) ** 0.5)
        if not np.isfinite(grad_norm) or grad_norm <= 0:
            raise RuntimeError(f'Cycle9 student gradient missing or invalid: norm={grad_norm}')
        print('STUDENT_GRADIENT_PROBE', 'OK', 'norm', round(grad_norm, 6), flush=True)
    finally:
        engine.close()

    after_ckpt_sha = sha256(checkpoint)
    after_source_sha = sha256(source)
    if (after_ckpt_sha, after_source_sha) != (before_ckpt_sha, source_sha):
        raise RuntimeError('Model file changed during read-only preflight')
    return {
        'schema_version': 1,
        'purpose': 'read-only Cycle 9 native observation/action/gradient preflight',
        'cycle9_checkpoint_path': str(checkpoint),
        'cycle9_sha256': before_ckpt_sha,
        'source_nexto_model_sha256': source_sha,
        'student_teacher_independent': independent,
        'student_teacher_max_logit_diff': max_abs_diff,
        'observation_shapes': {'q': list(q.shape), 'kv': list(kv.shape), 'mask': list(mask.shape)},
        'action_count': len(controls),
        'action_width': controls.shape[1],
        'greedy_action_index': chosen_action,
        'student_grad_norm': grad_norm,
        'one_step_rocketsim_1v1': True,
        'writes_to_checkpoint': False,
        'starts_ppo': False,
        'replay_data_used': False,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out', required=True)
    args = ap.parse_args()
    root = Path.cwd().resolve()
    report = allowed_report(Path(args.out), root)
    start = time.perf_counter()
    print('READ_ONLY_CYCLE9_PREFLIGHT', 'root', str(root), flush=True)
    result = perform_checks(root)
    result['duration_seconds'] = round(time.perf_counter() - start, 3)
    report.parent.mkdir(parents=True, exist_ok=True)
    with report.open('x', encoding='utf-8') as f:
        json.dump(result, f, indent=2)
    print('SAVED_READ_ONLY_REPORT', str(report), flush=True)
    print('SUMMARY', json.dumps(result, sort_keys=True), flush=True)
    print('CYCLE9_AND_NEXTO_FILES_VERIFIED_UNCHANGED', flush=True)


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f'PREFLIGHT_FAILED {type(e).__name__}: {e}', file=sys.stderr, flush=True)
        raise
