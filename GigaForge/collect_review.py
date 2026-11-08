"""Collect selected project source and diagnostics; never start or modify a run."""
from pathlib import Path
import argparse, hashlib, json, os, stat, sys, time, uuid, zipfile

CODE_EXT = {'.py', '.cpp', '.cc', '.c', '.h', '.hpp', '.cmake', '.bat', '.md', '.toml', '.cfg'}
PRUNE = {'.git', '__pycache__', '.pytest_cache', 'node_modules', 'vendor', 'external',
         'third_party', 'build', 'cache', 'assets', 'runs', 'exports', 'reports',
         'review_uploads', 'lib', 'libs', 'venv', 'env'}
RUN_JSON = {'config.json', 'lab.json', 'lab_state.json', 'lab_provenance.json',
            'provenance.json', 'state.json', 'status.json', 'tuning.json',
            'latest_h2h.json', 'export_latency.json', 'confirmation_audit.json',
            'hash_and_symmetry_reconciliation.json',
            'hash_and_symmetry_reconciliation_addendum.json',
            'h2h_2000x2_verified_report.json', 'experiment08_defense_summary.json',
            'experiment08_apex_summary.json', 'experiment07_summary.json',
            'experiment07b_summary.json'}
META_JSON = {'build.json', 'native_release.json', 'native.json', 'actor.lt.json',
             'pin_manifest.json', 'runtime_selection.json', 'active_research.json'}


def reparse(p):
    try:
        s = p.lstat()
        return stat.S_ISLNK(s.st_mode) or bool(getattr(s, 'st_file_attributes', 0) & 0x400)
    except OSError:
        return True


def walk(base, code=True):
    if not base.is_dir() or reparse(base):
        return
    for directory, dirs, names in os.walk(base, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d.lower() not in PRUNE
                         and not d.startswith('.') and not reparse(Path(directory) / d))
        for name in sorted(names):
            p = Path(directory) / name
            if name.startswith('.') or reparse(p):
                continue
            if code and (p.suffix.lower() in CODE_EXT or name == 'CMakeLists.txt'
                         or name.startswith('requirements') and p.suffix == '.txt'):
                yield p
            elif not code and p.suffix.lower() in {'.json', '.csv', '.jsonl'}:
                yield p


def collect(root, output=None):
    root = Path(root).resolve()
    if not (root / 'run.py').is_file():
        raise FileNotFoundError('Place both collector files inside gigaforge, beside run.py.')
    parent = root.parent
    selected = {}
    skipped = []

    def add(p):
        p = Path(p)
        if not p.is_file() or reparse(p):
            return
        try:
            relative = p.resolve().relative_to(parent)
        except ValueError:
            skipped.append({'file': str(p), 'reason': 'outside project parent'})
            return
        selected['chat_gpt_ai/' + relative.as_posix()] = p

    # Code is collected before diagnostics so large results cannot crowd it out.
    for p in walk(root):
        add(p)
    for name in META_JSON:
        add(root / name)
        add(root / 'native' / name)
    nova = next((p for p in (parent / 'novaforge', parent / 'NovaForge') if p.is_dir()), None)
    if nova:
        for folder in ('nova', 'configs', 'tests'):
            for p in walk(nova / folder):
                add(p)
        for p in sorted(nova.iterdir()):
            if p.is_file() and (p.suffix.lower() in CODE_EXT
                                or p.name.startswith('requirements') and p.suffix == '.txt'):
                add(p)
        fixture = nova / 'tests/fixtures/giga_reference.json'
        add(fixture)
    # The optimizer was modified in upstream vendor code as well as the patch script.
    for vendor in ('vendor/GigaLearnCPP', 'native/external/GigaLearnCPP', 'native/GigaLearnCPP'):
        base = root / vendor
        for name in ('PPOLearner.cpp', 'PPOLearner.h', 'LearnerConfig.h', 'PPOLearnerConfig.h'):
            if base.is_dir() and not reparse(base):
                for p in base.rglob(name):
                    if not any(reparse(q) for q in p.parents if q != root and root in q.parents):
                        add(p)
    for run_name in ('research03', 'research04'):
        run = root / 'runs' / run_name
        if reparse(run):
            continue
        for name in RUN_JSON:
            add(run / name)
        for folder in ('h2h', 'evaluations', 'watch_requests', 'watch_pins', 'champions', 'controller_configs'):
            for p in walk(run / folder, code=False):
                # These folders contain generated evaluation/provenance data, never weights.
                add(p)
        branches = run / 'branches'
        if branches.is_dir() and not reparse(branches):
            for directory, dirs, names in os.walk(branches, followlinks=False):
                dirs[:] = sorted(d for d in dirs if not reparse(Path(directory)/d)
                                 and d not in {'checkpoints', 'policy_versions', 'versions'})
                for name in ('recipe.json', 'metrics.jsonl'):
                    if name in names:
                        add(Path(directory)/name)
        # Exported Python runtime can differ from the working NovaForge package.
        for p in walk(root / 'exports' / run_name):
            add(p)
        for p in walk(root / 'exports' / run_name, code=False):
            if p.name in META_JSON:
                add(p)

    output = Path(output).resolve() if output else root / 'review_uploads'
    output.mkdir(parents=True, exist_ok=True)
    archive = output / ('GigaForge_source_and_results_' + time.strftime('%Y%m%d_%H%M%S', time.gmtime())
                        + '_UTC_' + uuid.uuid4().hex[:8] + '.zip')
    manifest = {'version': 1, 'purpose': 'Source review, not a model backup',
                'files': [], 'skipped': skipped, 'training_started': False,
                'model_weights_included': False, 'existing_files_modified': False}
    total = 0
    with archive.open('xb') as handle, zipfile.ZipFile(handle, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for name, p in selected.items():
            try:
                size = p.stat().st_size
                if size > 8*1024*1024 or total + size > 64*1024*1024:
                    skipped.append({'file': name, 'reason': 'size limit', 'bytes': size})
                    continue
                data = p.read_bytes()
                z.writestr(name, data)
                total += len(data)
                manifest['files'].append({'path': name, 'bytes': len(data),
                                          'sha256': hashlib.sha256(data).hexdigest()})
            except OSError as error:
                skipped.append({'file': name, 'reason': type(error).__name__})
        z.writestr('REVIEW_MANIFEST.json', json.dumps(manifest, indent=2))
        z.writestr('READ_ME.txt', 'Selected GigaForge/NovaForge code and research03/research04 diagnostics.\n'
                   'No .pt/.lt/.pth weights, CUDA libraries, venvs, login files or environment files are selected.\n'
                   'Existing files and training state are unchanged. Nothing is uploaded automatically.\n'
                   'REVIEW_MANIFEST.json lists included files, hashes and skipped files.\n'
                   'Paths and source may contain personal information; review before sharing.\n')
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:
            raise RuntimeError('ZIP integrity check failed')
    print('REVIEW_ZIP:', archive, flush=True)
    print('FILES:', len(manifest['files']), 'ZIP_MIB:', round(archive.stat().st_size / 1024**2, 2),
          'SKIPPED:', len(skipped), flush=True)
    print('Training and existing files were left unchanged. Upload this ZIP here after reviewing it.', flush=True)
    if archive.stat().st_size > 28*1024*1024:
        print('ZIP exceeds 28 MiB; share the source portion separately if the upload is rejected.', flush=True)
    return archive


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        collect(args.root, args.output)
    except Exception as error:
        print('COLLECTION_FAILED:', type(error).__name__, str(error), file=sys.stderr, flush=True)
        raise SystemExit(1)
