"""Read-only diagnostic for the failed update180 -> stock GigaLearn attempt.

This tool never converts tensors, trains, executes a checkpoint's arbitrary Python
pickle, or writes into a supplied model/checkpoint directory.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parent
DEFAULT_SOURCE = ROOT / 'data/isolated/mechanics_curriculum/selected7_mechanics01/update_000180.pt'
STOCK = {'POLICY.lt', 'SHARED_HEAD.lt', 'CRITIC.lt', 'POLICY_OPTIM.lt',
         'SHARED_HEAD_OPTIM.lt', 'CRITIC_OPTIM.lt', 'RUNNING_STATS.json'}
ATTENTION = {'actor.pt', 'teacher.pt', 'critic.pt', 'actor_optimizer.pt',
             'critic_optimizer.pt', 'rng.pt', 'protocol.json', 'state.json'}


def digest(path: Path):
    h = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def describe_folder(folder: Path):
    folder = folder.resolve()
    if not folder.is_dir():
        return {'exists': False, 'path': str(folder), 'status': 'MISSING'}
    names = {p.name for p in folder.iterdir() if p.is_file()}
    if STOCK.issubset(names):
        kind = 'STOCK_GIGALEARN_SPLIT_ARCHIVE'
        compatible = False
        message = ('A stock-style POLICY/SHARED_HEAD/CRITIC checkpoint is not '
                   'proof of an imported Nexto attention actor. Never use this '
                   'as an update180 continuation without architecture and logits parity.')
    elif ATTENTION.issubset(names) and ('COMPLETE.json' in names or 'COMPLETE' in names):
        kind = 'NATIVE_ATTENTION_COMPLETE_LAYOUT'
        compatible = None
        message = 'Expected native attention layout; verify actor parameters and parity separately.'
    else:
        kind = 'UNKNOWN_OR_PARTIAL_LAYOUT'
        compatible = False
        message = 'Unrecognized/incomplete checkpoint; not a verified update180 continuation.'
    files = {name: {'bytes': (folder / name).stat().st_size, 'sha256': digest(folder / name)}
             for name in sorted(names & (STOCK | ATTENTION))}
    return {'exists': True, 'path': str(folder), 'type': kind,
            'attention_transfer_verified': compatible, 'files': files, 'message': message}


def describe_source(path: Path, load_weights=False):
    path = path.resolve()
    if not path.is_file():
        return {'exists': False, 'path': str(path), 'status': 'PRIVATE_SOURCE_MISSING'}
    report = {'exists': True, 'path': str(path), 'bytes': path.stat().st_size,
              'sha256': digest(path), 'attention_transfer_verified': False}
    if not load_weights:
        return report
    try:
        import torch
        # Use the project's actual actor loader, not arbitrary torch.load pickle.
        from slater_mechanics_eval import load_actor
        actor = load_actor(ROOT, path)
        params = list(actor.parameters())
        count = sum(p.numel() for p in params)
        report.update(parameters=count, parameter_tensors=len(params),
                      is_expected_attention=(count == 444032 and len(params) == 44))
        # Reading the source does not demonstrate import into a second architecture.
    except Exception as exc:
        report.update(source_load_error=type(exc).__name__ + ': ' + str(exc)[:180])
    return report


def archive_metadata(path: Path):
    """Read only ZIP entry names from LibTorch serializations; never unpickle."""
    if not path.is_file():
        return {'exists': False}
    item = {'exists': True, 'bytes': path.stat().st_size, 'sha256': digest(path)}
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path, 'r') as archive:
            item['archive_members'] = [n[:180] for n in archive.namelist()[:40]]
    else:
        item['archive_members'] = None
    return item


def make_report(source: Path, target: Path | None, inspect_model=False):
    result = {'source': describe_source(source, load_weights=inspect_model),
              'target': describe_folder(target) if target else None,
              'transfer_verified': False,
              'why_not_verified': 'File extensions, archive members, and tensor counts cannot prove identical observations, logits, or action semantics.',
              'required_next_step': ('Use ATTENTION_NATIVE.bat parity --source "path\\to\\update_000180.pt" '
                                     'in an isolated run, then match the frozen actor against its source before PPO.')}
    if target and target.is_dir():
        for filename in ('POLICY.lt', 'SHARED_HEAD.lt', 'actor.pt'):
            path = target / filename
            if path.is_file():
                result.setdefault('archive_inspection', {})[filename] = archive_metadata(path)
    return result


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, default=DEFAULT_SOURCE)
    p.add_argument('--target', type=Path, help='Existing stock .lt or native attention checkpoint directory')
    p.add_argument('--inspect-model', action='store_true', help='Check source parameters (imports torch; no training)')
    p.add_argument('--out', type=Path, help='Optional report JSON path outside source/target')
    a = p.parse_args(argv)
    report = make_report(a.source, a.target, a.inspect_model)
    if a.out:
        dest = a.out.resolve()
        protected = [a.source.resolve()]
        if a.target:
            protected += [a.target.resolve(), *a.target.resolve().parents]
        if dest in protected or (a.target and a.target.resolve() in dest.parents):
            p.error('Refusing to write into protected model/checkpoint directory')
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))
    return 0 if report['source']['exists'] else 2


if __name__ == '__main__':
    sys.exit(main())
