"""Continue the original attention actor; never substitute a native student."""
import argparse
import json
from pathlib import Path
import torch
import slater_versatile_trainer as trainer
from slater_mechanics_eval import load_actor
from slater_v041_core import atomic_json, sha256, read_json

SOURCE = trainer.ROOT / 'data/isolated/mechanics_curriculum/selected7_mechanics01/update_000180.pt'
CONFIG = {**trainer.DEFAULT, 'actor_lr': 3e-6, 'teacher_anchor': .10,
          'target_kl': .005, 'updates_per_cycle': 20, 'max_cycles': 12,
          'tasks': {'match': .50, 'ground': .15, 'defense': .15,
                    'recovery': .05, 'low_boost': .05, 'aerial': .05, 'replay': .05}}

def verify_actor(source):
    digest = sha256(source)
    frozen = load_actor(trainer.ROOT, source)
    student = load_actor(trainer.ROOT, source, trainable=True)
    if not all(torch.equal(v, student.state_dict()[k]) for k, v in frozen.state_dict().items()):
        raise RuntimeError('Starting actor does not match the protected source')
    if sha256(source) != digest:
        raise RuntimeError('Source changed during verification')
    return {'source': str(source), 'sha256': digest, 'actor_weights_identical': True,
            'critic': 'new versatile critic', 'framework': 'RocketSim + original attention actor'}

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('command', choices=('run', 'pause', 'status', 'verify'))
    p.add_argument('--run', default='update180_continue01')
    p.add_argument('--source', type=Path, default=SOURCE)
    p.add_argument('--dataset', type=Path)
    p.add_argument('--cycles', type=int, default=3)
    a = p.parse_args()
    if not 1 <= a.cycles <= 12: p.error('cycles must be 1..12')
    run = trainer.run_path(a.run)
    if a.command == 'status':
        print(json.dumps({'progress': read_json(run/'progress.json', {}),
                          'selected': read_json(run/'selected.json', {})}, indent=2)); return
    if a.command == 'pause':
        if not (run/'progress.json').is_file(): raise ValueError('No started run to pause')
        (run/'pause.flag').touch(); print('Pause requested; wait for VERSATILE_PAUSED.'); return
    if a.command == 'run' and (run/'protocol.json').is_file():
        try: trainer.train(a.run, resume=True, cycles=a.cycles)
        except trainer.Paused: print('VERSATILE_PAUSED: checkpoints saved.')
        return
    source = a.source.resolve()
    if not source.is_file(): raise FileNotFoundError('Required attention checkpoint is missing: '+str(source))
    torch.set_num_threads(2)
    report = verify_actor(source)
    if a.dataset:
        trainer.DemoDataset(a.dataset.resolve())
    report['human_replay_gradients'] = bool(a.dataset)
    print('DIRECT_CONTINUATION_VERIFIED', json.dumps(report), flush=True)
    if a.command == 'verify': return
    atomic_json(trainer.ROOT/'data/isolated/continuation_checks'/f'{a.run}.json', report)
    try:
        trainer.train(a.run, source, a.dataset.resolve() if a.dataset else None,
                      cycles=a.cycles, config=CONFIG)
    except trainer.Paused: print('VERSATILE_PAUSED: checkpoints saved.')

if __name__ == '__main__': main()
