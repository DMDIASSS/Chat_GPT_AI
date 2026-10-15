"""Build the source-only Freestyle overlay for an existing Chat_GPT_AI checkout."""
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent


def package(output=None):
    destination = Path(output or ROOT / 'Slater_Freestyle_Update.zip')
    files = [ROOT / 'slater_freestyle.py', ROOT / 'slater_v041_core.py', ROOT / 'package_freestyle.py',
             ROOT / 'docs/FREESTYLE.md', ROOT / 'docs/FREESTYLE_RESEARCH.md',
             ROOT / 'export_freestyle_rlbot_v5.py', ROOT / 'docs/FREESTYLE_RLBOT_V5.md',
             ROOT / 'tests/test_freestyle_v5_export.py',
             ROOT / 'tests/freestyle_export_native/CMakeLists.txt',
             ROOT / 'tests/freestyle_export_native/reference.cpp',
             ROOT / 'tests/freestyle_native_checks.cpp',
             ROOT / 'tests/test_freestyle_native_checks.py', ROOT / 'tests/test_freestyle_runner.py',
             ROOT / 'tests/test_freestyle_build.py', ROOT / 'tests/test_freestyle_dll_bridge.py',
             ROOT / 'tests/test_freestyle_metrics.py', ROOT / 'tests/test_atomic_json_windows.py',
             ROOT / 'tests/test_freestyle_continuation.py', ROOT / 'tests/test_freestyle_native_continuation.py']
    files += sorted(ROOT.glob('FREESTYLE_*.bat')) + sorted(ROOT.glob('FREESTYLE_*.vbs'))
    files += [ROOT / 'FREESTYLE_SETTINGS.json', ROOT / 'FREESTYLE_MECHANICS.json']
    files += sorted((ROOT / 'freestyle_rlbot_v5').glob('*.py'))
    files += sorted(path for path in (ROOT / 'GigaLearn_Project/Freestyle').iterdir()
                    if path.is_file() and path.suffix in ('.cpp', '.h', '.txt', '.cmake'))
    with zipfile.ZipFile(destination, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, path.relative_to(ROOT).as_posix())
        archive.writestr('FREESTYLE_INSTALL.txt',
            'Extract directly into E:\\Downloads\\Chat_GPT_AI beside the existing .venv and data folders.\n'
            'This overlay contains source, settings, launchers and tests only.\n'
            'Run FREESTYLE_SETUP.bat, then Start new in the Freestyle app.\n'
            'See docs/FREESTYLE.md for training, W&B login, safe pause and resume.\n'
            'Requires the existing native-quality-campaign project helpers.\n')
    with zipfile.ZipFile(destination) as archive:
        if archive.testzip() is not None:
            raise RuntimeError('Freestyle package failed ZIP integrity verification')
        if any(name.startswith(('.venv/', 'data/')) or name.endswith(('.lt', '.pt', '.dll', '.exe'))
               for name in archive.namelist()):
            raise RuntimeError('Source package unexpectedly contains runtime/model files')
    print(destination, destination.stat().st_size, 'bytes;', len(files), 'source files')
    return destination


def package_v5_exporter(output=None):
    """Exporter-only overlay; no training settings or native sources are replaced."""
    destination = Path(output or ROOT / 'Slater_Freestyle_RLBot_V5_Exporter.zip')
    names = ['export_freestyle_rlbot_v5.py', 'FREESTYLE_EXPORT_V5.bat',
             'slater_freestyle.py', 'docs/FREESTYLE_RLBOT_V5.md']
    names += [p.relative_to(ROOT).as_posix()
              for p in sorted((ROOT / 'freestyle_rlbot_v5').glob('*.py'))]
    with zipfile.ZipFile(destination, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name in names:
            archive.write(ROOT / name, name)
        archive.writestr('FREESTYLE_V5_INSTALL.txt',
            '1. Extract into E:\\Downloads\\Chat_GPT_AI, replacing the included files.\n'
            '2. Run FREESTYLE_EXPORT_V5.bat. Select freestyle_rewards02 and latest\n'
            '   or a saved update number. Scripted kickoff is enabled by default.\n'
            '3. Run INSTALL.bat once inside the exported bot folder under\n'
            '   data\\rlbot_v5_exports, then import its bot.toml in RLBot v5.\n'
            'No native rebuild is needed. Training and saved models are preserved.\n'
            'This download contains exporter source only; your actual model is\n'
            'exported locally. Keep the project Python/Torch installation available.\n'
            'See docs/FREESTYLE_RLBOT_V5.md for commands and runtime limitations.\n')
    with zipfile.ZipFile(destination) as archive:
        if archive.testzip() is not None:
            raise RuntimeError('Exporter package failed ZIP integrity verification')
        if any(name.startswith(('data/', '.venv/', 'GigaLearn_Project/'))
               for name in archive.namelist()):
            raise RuntimeError('Exporter overlay unexpectedly includes training/runtime files')
    print(destination, destination.stat().st_size, 'bytes;', len(names), 'source files')
    return destination


def package_reward_revision(output=None):
    """Small overlay: leave the user's settings and stable obs/action files alone."""
    destination = Path(output or ROOT / 'Slater_Freestyle_Rewards_V2.zip')
    names = ['slater_freestyle.py', 'slater_v041_core.py', 'FREESTYLE_REWARDS_V2.bat',
             'docs/FREESTYLE.md']
    names += ['GigaLearn_Project/Freestyle/' + name for name in (
        'FreestyleBridge.cpp', 'FreestyleBridge.h', 'FreestyleConfig.h',
        'FreestyleCurriculum.h', 'FreestyleMain.cpp', 'FreestyleRewards.h')]
    with zipfile.ZipFile(destination, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for name in names:
            archive.write(ROOT / name, name)
        archive.writestr('FREESTYLE_REWARDS_V2_INSTALL.txt',
            '1. Safe pause Freestyle and close the app after its checkpoint saves.\n'
            '2. Extract into E:\\Downloads\\Chat_GPT_AI, replacing the included source files.\n'
            '3. Run FREESTYLE_REWARDS_V2.bat. It rebuilds if needed, copies the latest\n'
            '   completed freestyle01 actor into freestyle_rewards02, and trains 200 updates.\n'
            '4. Future launches resume freestyle_rewards02 for another 200 updates.\n'
            'The parent run, all checkpoints and your settings are preserved.\n'
            'First 10 child updates train the fresh critic while the actor stays fixed.\n'
            'W&B uses your existing local login and creates a new child run.\n'
            'For the GUI: Build, Run=freestyle01, Continue with revised rewards.\n'
            'See docs/FREESTYLE.md for other parent names and custom budgets.\n')
    with zipfile.ZipFile(destination) as archive:
        if archive.testzip() is not None:
            raise RuntimeError('Reward update failed ZIP integrity verification')
        assert not any(name.startswith(('data/', '.venv/')) for name in archive.namelist())
    print(destination, destination.stat().st_size, 'bytes;', len(names), 'source files')
    return destination


if __name__ == '__main__':
    package()
    package_v5_exporter()
