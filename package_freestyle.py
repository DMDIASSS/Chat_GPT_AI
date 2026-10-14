"""Build the source-only Freestyle overlay for an existing Chat_GPT_AI checkout."""
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent


def package(output=None):
    destination = Path(output or ROOT / 'Slater_Freestyle_Update.zip')
    files = [ROOT / 'slater_freestyle.py', ROOT / 'package_freestyle.py',
             ROOT / 'docs/FREESTYLE.md', ROOT / 'docs/FREESTYLE_RESEARCH.md',
             ROOT / 'tests/freestyle_native_checks.cpp',
             ROOT / 'tests/test_freestyle_native_checks.py', ROOT / 'tests/test_freestyle_runner.py',
             ROOT / 'tests/test_freestyle_build.py', ROOT / 'tests/test_freestyle_dll_bridge.py']
    files += sorted(ROOT.glob('FREESTYLE_*.bat')) + sorted(ROOT.glob('FREESTYLE_*.vbs'))
    files += [ROOT / 'FREESTYLE_SETTINGS.json', ROOT / 'FREESTYLE_MECHANICS.json']
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


if __name__ == '__main__':
    package()
