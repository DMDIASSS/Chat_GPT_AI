"""Prove an existing attention actor can infer and receive gradients in C++.

Only private copies are used. This is a compatibility probe, not a GigaLearn
attention trainer, a model-strength assessment, or a throughput benchmark.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import random
import re
import subprocess
import sys

import numpy as np
import torch

from afk_team_research import TeamMatch, TeamObserver
from nexto_teacher import NextoTeacher, nexto_actions
from slater_mechanics_eval import load_actor
from slater_v041_core import atomic_json, sha256
from slater_versatile_data import native_observation

ROOT = Path(__file__).resolve().parent
BACKEND = ROOT / 'GigaLearn_Project/Native_Backend/attention_probe'
BASE = ROOT / 'data/isolated/attention_native_probe'
DEFAULT_SOURCE = ROOT / 'data/isolated/mechanics_curriculum/selected7_mechanics01/update_000180.pt'


class ProbeInputs(torch.nn.Module):
    def __init__(self, q, kv, mask, expected):
        super().__init__()
        self.register_buffer('q', q)
        self.register_buffer('kv', kv)
        self.register_buffer('mask', mask)
        self.register_buffer('expected', expected)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return x + self.expected


def fixture(actor, observations, destination):
    q, kv, mask = (torch.tensor(np.stack([view[i] for view in observations])) for i in range(3))
    with torch.no_grad():
        expected = actor((q, kv, mask))[0]
    if expected.shape != (len(observations), 90) or not torch.isfinite(expected).all():
        raise ValueError('Actor did not produce finite 90-action logits')
    torch.jit.script(ProbeInputs(q, kv, mask, expected)).save(str(destination))
    return q, kv, mask, expected


def generate_inputs(actor, out, seed=10201):
    from rlgym.rocket_league.sim import RocketSimEngine
    engine = RocketSimEngine(rlbot_delay=True)
    observer = TeamObserver()
    observations = []
    formats = []
    try:
        for blue in range(1, 4):
            for orange in range(1, 4):
                random.seed(seed + 31 * blue + orange)
                match = TeamMatch(engine, observer, blue, orange, seed=seed + 31 * blue + orange)
                previous = {aid: nexto_actions()[(index * 17 + 4) % 90]
                            for index, aid in enumerate(match.state.cars)}
                views = observer.observe(match.state, previous)
                for view in views.values():
                    q, kv, mask = view
                    if (q.shape != (1, 32) or kv.shape != (41, 24)
                            or mask.shape != (41,) or np.sum(mask) != 6 - blue - orange
                            or not np.isfinite(q).all() or not np.isfinite(kv).all()):
                        raise ValueError('Invalid team observation')
                    observations.append(native_observation(view))
                formats.append({'blue': blue, 'orange': orange, 'car_views': len(views),
                                'masked_player_slots_per_view': 6 - len(views)})
        q, kv, mask, expected = fixture(actor, observations, out / 'team_inputs.pt')
        permutation = torch.randperm(41, generator=torch.Generator().manual_seed(seed + 812))
        with torch.no_grad():
            permuted = actor((q, kv[:, permutation], mask[:, permutation]))[0]
        permutation_error = float((permuted - expected).abs().max())

        # Compare the same state and previous controls through both wrappers.
        random.seed(seed + 32)
        match = TeamMatch(engine, observer, 1, 1, seed=seed + 32)
        previous = {aid: nexto_actions()[(index * 17 + 4) % 90]
                    for index, aid in enumerate(match.state.cars)}
        padded = observer.observe(match.state, previous)
        legacy_views = NextoTeacher().observe(match.state, previous)
        duel = [tuple(view[1:]) for view in legacy_views]
        _, _, _, duel_expected = fixture(actor, duel, out / 'duel_inputs.pt')
        raw = [padded[view[0]] for view in legacy_views]
        qr, kr, mr = (torch.tensor(np.stack([view[i] for view in raw])) for i in range(3))
        fixed = [native_observation(view) for view in raw]
        qp, kp, mp = (torch.tensor(np.stack([view[i] for view in fixed])) for i in range(3))
        with torch.no_grad():
            raw_padding_error = float((actor((qr, kr, mr))[0] - duel_expected).abs().max())
            padding_error = float((actor((qp, kp, mp))[0] - duel_expected).abs().max())
        if permutation_error > 1e-4 or padding_error > 1e-4:
            raise ValueError('Attention permutation or padding compatibility failed')
        return {'formats': formats, 'team_car_views': len(observations), 'duel_car_views': len(duel),
                'entity_permutation_max_abs_logit_error': permutation_error,
                'duel_37_to_41_padding_max_abs_logit_error': padding_error,
                'raw_boolean_padding_mask_max_abs_logit_error': raw_padding_error}
    finally:
        engine.close()


def build_probe(folder):
    from GigaLearn_Project.Native_Backend.native_setup import tool, cuda_configuration
    import shutil
    if os.name == 'nt' and not shutil.which('cl'):
        raise ValueError('Open the x64 Native Tools Command Prompt for VS 2022 before running this probe')
    folder = Path(folder).resolve()
    cuda_args, build_env = cuda_configuration(torch)
    configure = [tool('cmake'), '-S', str(BACKEND), '-B', str(folder), '-G', 'Ninja',
                 '-DCMAKE_BUILD_TYPE=Release', f'-DCMAKE_MAKE_PROGRAM={tool("ninja")}',
                 f'-DCMAKE_PREFIX_PATH={torch.utils.cmake_prefix_path}', *cuda_args]
    for command in (configure, [tool('cmake'), '--build', str(folder), '-j', '1']):
        print('RUN', subprocess.list2cmdline(command), flush=True)
        subprocess.run(command, env=build_env, check=True)
    binary = folder / ('attention_native_probe.exe' if os.name == 'nt' else 'attention_native_probe')
    if not binary.is_file():
        raise FileNotFoundError('Standalone attention probe executable was not produced')
    return binary


def run(source, name, build_dir=None):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', name):
        raise ValueError('Use a short run name containing letters, numbers, underscore or hyphen')
    source = Path(source).resolve()
    if not source.is_file():
        raise FileNotFoundError(f'Attention source not found: {source}')
    source_sha = sha256(source)
    torch.set_num_threads(1)
    actor = load_actor(ROOT, source, trainable=True)
    parameter_count = sum(p.numel() for p in actor.parameters())
    if len(list(actor.parameters())) != 44 or parameter_count != 444032:
        raise ValueError('This probe expects the original Nexto attention architecture')
    out = BASE / name
    out.mkdir(parents=True, exist_ok=False)
    exported = out / 'actor.pt'
    torch.jit.save(actor, str(exported))
    portable = torch.jit.load(str(exported), map_location='cpu').eval()
    if not all(torch.equal(value, portable.state_dict()[key]) for key, value in actor.state_dict().items()):
        raise ValueError('Private attention export did not preserve source weights')
    observations = generate_inputs(portable, out)
    binary = build_probe(build_dir or BASE / 'build')
    env = os.environ.copy()
    if os.name == 'nt':
        env['PATH'] = str(binary.parent) + os.pathsep + str(Path(torch.__file__).parent / 'lib') + os.pathsep + env.get('PATH', '')
    proc = subprocess.run([str(binary), str(exported), str(out / 'team_inputs.pt'), str(out / 'duel_inputs.pt')],
                          env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    (out / 'cpp_probe.log').write_text(proc.stdout, encoding='utf-8')
    print(proc.stdout, end='', flush=True)
    if proc.returncode:
        raise RuntimeError(f'C++ attention probe failed: {out / "cpp_probe.log"}')
    cpp = json.loads(proc.stdout.strip().splitlines()[-1])
    if sha256(source) != source_sha:
        raise RuntimeError('Original attention source changed during the probe')
    report = {'status': 'ATTENTION_CPP_FORWARD_AND_GRADIENT_VERIFIED',
              'source': str(source), 'source_sha256': source_sha,
              'source_unchanged': True, 'export_weights_identical': True,
              'exported_actor_sha256': sha256(exported), 'torch': torch.__version__,
              'binary_sha256': sha256(binary), 'probe_code_sha256': sha256(BACKEND / 'AttentionProbe.cpp'),
              'observations': observations, 'cpp': cpp,
              'limitations': ['CPU compatibility only; actual native attention PPO training is not implemented.',
                              'No stronger-model or faster-training conclusion follows from this probe.',
                              'Optimizer test uses synthetic targets and modifies only in-memory private actor weights.']}
    atomic_json(out / 'report.json', report)
    print('ATTENTION_NATIVE_REPORT', out / 'report.json', flush=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=DEFAULT_SOURCE)
    parser.add_argument('--run', default='attention_probe_' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S'))
    parser.add_argument('--build-dir', type=Path)
    args = parser.parse_args()
    run(args.source, args.run, args.build_dir)


if __name__ == '__main__':
    main()
