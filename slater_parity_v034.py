"""Slater v0.3.4: read-only checkpoint/export/action and inference parity audit.

Requires the existing v0.3.0.3/0.3.0.4 Slater evaluation modules, their
project dependencies, and a locally exported u60 TorchScript model.
No training, model mutation, benchmark promotion, or overwrites.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

import numpy as np
import torch

EXPECTED_SHAPES = ((1, 32), (41, 24), (41,))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1048576), b''):
            h.update(chunk)
    return h.hexdigest()


def check_output(raw: str, root: Path) -> Path:
    dst = (root / raw).resolve()
    allowed = (root / 'data' / 'isolated').resolve()
    if not dst.is_relative_to(allowed) or dst.suffix != '.json':
        raise ValueError('JSON output must be within data/isolated')
    if dst.exists():
        raise FileExistsError(f'Refusing to overwrite report: {dst}')
    return dst


def canonical_obs(parts):
    if not isinstance(parts, (tuple, list)) or len(parts) != 3:
        raise ValueError('Observation must contain q, kv, mask')
    output = []
    for idx, (raw, shape) in enumerate(zip(parts, EXPECTED_SHAPES)):
        arr = np.asarray(raw, dtype=np.float32)
        if arr.shape == (1, *shape):
            arr = arr[0]
        if arr.shape != shape:
            raise ValueError(f'Observation component {idx} has shape {arr.shape}, expected {shape} or (1,...)')
        if not np.isfinite(arr).all():
            raise ValueError('Non-finite observation')
        output.append(np.ascontiguousarray(arr))
    return tuple(output)


def model_state_diff(reference, exported):
    a, b = reference.state_dict(), exported.state_dict()
    missing = sorted(set(a) - set(b))
    extra = sorted(set(b) - set(a))
    mismatched = []
    for name in set(a) & set(b):
        if a[name].shape != b[name].shape or not torch.equal(a[name].cpu(), b[name].cpu()):
            mismatched.append(name)
    return {'identical': not (missing or extra or mismatched),
            'parameter_tensors': len(a), 'missing': missing,
            'extra': extra, 'different': sorted(mismatched)}


def load_action_table(agent_file: Path):
    name = '_slater_v034_rlbot_agent'
    spec = importlib.util.spec_from_file_location(name, str(agent_file))
    if spec is None or spec.loader is None:
        raise ImportError(f'Cannot import {agent_file}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return np.asarray(module.Agent.make_lookup_table(), dtype=np.float32)


def compare_actions(native_actions, rlbot_actions):
    a = np.asarray(native_actions, dtype=np.float32)
    b = np.asarray(rlbot_actions, dtype=np.float32)
    if a.shape != (90, 8) or b.shape != (90, 8):
        return {'identical': False, 'sim_shape': list(a.shape), 'rlbot_shape': list(b.shape), 'mismatched_ids': []}
    ids = np.flatnonzero(np.any(a != b, axis=1)).astype(int).tolist()
    return {'identical': not ids, 'sim_shape': list(a.shape), 'rlbot_shape': list(b.shape), 'mismatched_ids': ids}


def infer(model, obs):
    arrs = canonical_obs(obs)
    batch = tuple(torch.from_numpy(a.copy()).unsqueeze(0) for a in arrs)
    with torch.no_grad():
        out = model(batch)
    logits = out[0] if isinstance(out, (tuple, list)) else out
    vals = np.asarray(logits.detach().cpu().numpy(), dtype=np.float32).reshape(-1)
    if vals.shape != (90,) or not np.isfinite(vals).all():
        raise ValueError(f'Bad model logits {vals.shape}')
    return vals


def compare_inference(native, exported, obs):
    a, b = infer(native, obs), infer(exported, obs)
    return {'top_action_native': int(a.argmax()), 'top_action_rlbot': int(b.argmax()),
            'max_abs_logit_diff': float(np.max(np.abs(a - b))),
            'top_action_same': bool(a.argmax() == b.argmax()),
            'allclose_1e-5': bool(np.allclose(a, b, atol=1e-5, rtol=1e-5))}


def opponent_defaults(path: Path):
    if not path.is_file():
        return {'status': 'no bot.py at requested path'}
    import ast
    tree = ast.parse(path.read_text(encoding='utf-8-sig'))
    for n in ast.walk(tree):
        if isinstance(n, ast.FunctionDef) and n.name == '__init__':
            args = [x.arg for x in n.args.args]
            defaults = n.args.defaults
            values = {}
            for k, v in zip(args[len(args)-len(defaults):], defaults):
                if k in ('hardcoded_kickoffs', 'stochastic_kickoffs', 'beta'):
                    try:
                        values[k] = ast.literal_eval(v)
                    except (ValueError, TypeError):
                        values[k] = 'nonliteral'
            if values:
                return {'status': 'constructor defaults ONLY, not proof of runtime config', 'defaults': values}
    return {'status': 'kickoff defaults not found'}


def simulated_observations(root, native, nexto, actions, seeds):
    import slater_fullmatch_eval_v0302 as fm
    import slater_cycle9_native_ppo_v025 as base
    from afk_team_research import TeamObserver  # verifies simulator installed
    _ = TeamObserver  # loaded by the isolated environment on reset
    rows = []
    inputs = []
    for side in ('blue', 'orange'):
        env = fm.IsolatedKickoffEnv(side, actions, nexto, max_steps=6)
        try:
            for i in range(seeds):
                seed = 1700420699 + i * 997
                obs, signature = fm.seeded_reset(env, seed)
                inputs.append(('sim', f'{side}_{seed}_kickoff', obs))
                a = int(infer(native, obs).argmax())
                next_obs, _, done, _ = env.step(a)
                if not done:
                    inputs.append(('sim', f'{side}_{seed}_after_action', next_obs))
                rows.append({'side': side, 'seed': seed, 'first_kickoff_signature': signature,
                             'initial_selected_action': a, 'done_after_one_decision': bool(done)})
        finally:
            env.close()
    return inputs, rows


def capture_inputs(folder: Path, limit=64):
    if not folder.is_dir():
        raise FileNotFoundError(f'Capture folder not found: {folder}')
    files = sorted(folder.glob('capture_*.npz'))
    inputs, meta = [], []
    for fp in files[:limit]:
        with np.load(fp, allow_pickle=False) as data:
            obs = canonical_obs([data[k] for k in ('q','kv','mask')])
            a = np.asarray(data['selected_action'], dtype=np.float32)
            prev = np.asarray(data['previous_action'], dtype=np.float32)
            if a.shape != (8,) or prev.shape != (8,):
                raise ValueError(f'Invalid action shape in {fp.name}')
            meta.append({'file': fp.name, 'selected_action': a.tolist(),
                         'previous_action': prev.tolist(),
                         'team': int(data['team']), 'beta': float(data['beta']) if 'beta' in data else None, 'time': float(data['seconds_elapsed'])})
            inputs.append(('live', fp.name, obs))
    return inputs, meta, len(files)


def classify_report(model, actions, tested, live_count):
    if not model['identical']:
        return 'FAIL_MODEL_WEIGHTS'
    if not actions['identical']:
        return 'FAIL_ACTION_TABLE'
    if tested and any(not r['allclose_1e-5'] for r in tested):
        return 'FAIL_INFERENCE'
    if live_count > 0:
        return 'PASS_WEIGHTS_ACTIONS_AND_LIVE_INPUT_INFERENCE__OBS_SEMANTICS_UNVERIFIED'
    return 'PASS_WEIGHTS_ACTIONS_AND_SIM_INPUT_INFERENCE__LIVE_OBS_NOT_TESTED'


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--checkpoint', required=True, help='u60 PPO .pt')
    p.add_argument('--exported', required=True, help='manually exported TorchScript nexto-model.pt')
    p.add_argument('--rlbot-dir', required=True, help='RLBot bot folder containing agent.py and nexto-model.pt')
    p.add_argument('--capture-dir', default='', help='Optional captured real-game RLBot obs .npz directory')
    p.add_argument('--opponent-bot', default='', help='Optional actual opponent Nexto bot.py for default flag inspection')
    p.add_argument('--sim-seeds', type=int, default=3)
    p.add_argument('--out', required=True)
    a = p.parse_args(argv)
    if not 1 <= a.sim_seeds <= 32:
        p.error('--sim-seeds must be 1..32')
    root = Path.cwd().resolve()
    dst = check_output(a.out, root)
    folder = Path(a.rlbot_dir).resolve()
    agent_file = folder / 'agent.py'
    deployed = folder / 'nexto-model.pt'
    exported = Path(a.exported).resolve()
    checkpoint = Path(a.checkpoint).resolve()
    for f in (checkpoint, exported, agent_file, deployed):
        if not f.is_file():
            raise FileNotFoundError(str(f))
    import slater_fullmatch_eval_v0303 as fm3
    native, nexto, actions = fm3.load_actor_and_nexto(root, checkpoint)
    export_actor = torch.jit.load(str(exported), map_location='cpu').eval()
    export_deployed_sha_equal = sha256(exported) == sha256(deployed)
    weights = model_state_diff(native, export_actor)
    action_result = compare_actions(actions, load_action_table(agent_file))
    sim_obs, sim_rows = simulated_observations(root, native, nexto, actions, a.sim_seeds)
    live_obs, live_rows, live_total = (capture_inputs(Path(a.capture_dir).resolve()) if a.capture_dir else ([], [], 0))
    all_obs = sim_obs + live_obs
    results = []
    live_lookup = {x['file']: x for x in live_rows}
    for source, label, obs in all_obs:
        outcome = compare_inference(native, export_actor, obs)
        outcome.update({'source': source, 'label': label})
        if source == 'live':
            entry = live_lookup[label]
            beta = entry['beta']
            selected = np.asarray(entry['selected_action'], dtype=np.float32)
            expected = np.asarray(actions[outcome['top_action_rlbot']], dtype=np.float32)
            outcome['rlbot_nn_action_matches_greedy'] = (bool(np.array_equal(expected,selected)) if beta == 1.0 else None)
            outcome['rlbot_beta'] = beta
        results.append(outcome)
    max_diff = max((r['max_abs_logit_diff'] for r in results), default=None)
    status = classify_report(weights, action_result, results, len(live_obs))
    if not export_deployed_sha_equal:
        status = 'FAIL_DEPLOYED_MODEL_DIFFERS_FROM_EXPORTED'
    if any(x.get('rlbot_nn_action_matches_greedy') is False for x in results):
        status = 'FAIL_LIVE_GREEDY_ACTION_MISMATCH'
    report = {
        'version': 'v0.3.4', 'status': status, 'checkpoint_sha256': sha256(checkpoint),
        'exported_sha256': sha256(exported), 'deployed_sha256': sha256(deployed),
        'deployed_same_as_exported': export_deployed_sha_equal,
        'model_weights': weights, 'action_table': action_result,
        'sim_samples': sim_rows, 'inference_samples': results,
        'max_abs_logit_diff': max_diff, 'live_capture_files_total': live_total,
        'live_capture_files_tested': len(live_rows), 'live_sample_metadata': live_rows,
        'opponent_kickoff_constructor_defaults': opponent_defaults(Path(a.opponent_bot)) if a.opponent_bot else None,
        'caveats': ['Passing model/action/inference checks does NOT prove TeamObserver == NextoObsBuilder semantic equivalence.',
                    'A real-game RLBot capture is required for testing actual RLBot input vectors.',
                    'RLBot clock/control scheduling, scripted opponent kickoffs and physics differences remain separate tests.',
                    'Policy evaluations are read-only. No checkpoint or opponent is modified.'],
    }
    dst.parent.mkdir(parents=True, exist_ok=True)
    with dst.open('x', encoding='utf-8') as f:
        json.dump(report, f, indent=2, sort_keys=True)
    print('SLATER_PARITY_V034', status)
    print('MODEL_WEIGHTS', json.dumps(weights, sort_keys=True))
    print('ACTION_TABLE', json.dumps(action_result, sort_keys=True))
    print('DEPLOYED_MODEL_MATCH', export_deployed_sha_equal)
    print('INPUT_SAMPLES', len(results), 'LIVE', len(live_obs), 'MAX_ABS_LOGIT_DIFF', max_diff)
    print('OBS_SEMANTICS', 'UNVERIFIED (needs equivalent real-game and simulator states)')
    print('PARITY_REPORT', dst)
    if status.startswith('FAIL_'):
        sys.exit(2)


if __name__ == '__main__':
    main()
