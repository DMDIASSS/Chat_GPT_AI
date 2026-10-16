"""Package the native attention update without checkpoints or private exports."""
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parent
FILES = (
    'ATTENTION_NATIVE.bat', 'slater_native_attention.py',
    'GigaLearn_Project/Native_Attention/CMakeLists.txt',
    'GigaLearn_Project/Native_Attention/AttentionMain.cpp',
    'GigaLearn_Project/Native_Attention/AttentionObs.h',
    'GigaLearn_Project/Native_Attention/AttentionWorld.h',
    'GigaLearn_Project/Native_Attention/AttentionPPO.h',
    'GigaLearn_Project/Native_Attention/ObsParity.cpp',
    'docs/NATIVE_ATTENTION_README.md', 'docs/NATIVE_ATTENTION_VALIDATION.md',
    'docs/ATTENTION_OBS_PARITY.md', 'docs/ATTENTION_TIMING_PARITY.md',
    'docs/ATTENTION_PPO_PARITY.md',
    'tests/native_attention_obs_fixtures.py',
    'tests/native_attention_world.cpp',
    'tests/test_native_attention_launcher.py',
    'tests/test_native_attention_obs.py', 'tests/test_native_attention_world.py',
    'tests/native_attention_ppo/CMakeLists.txt',
    'tests/native_attention_ppo/PPOParity.cpp',
    'tests/native_attention_ppo/generate_fixture.py',
    'package_native_attention.py',
)


def build():
    output = ROOT / 'Slater_Native_Attention_Update.zip'
    for name in FILES:
        path = Path(name)
        if path.is_absolute() or '..' in path.parts or path.parts[0] in ('data', 'attachments', 'vendor'):
            raise ValueError('Unsafe or private package path: ' + name)
        if path.suffix.lower() not in ('.py', '.cpp', '.h', '.md', '.bat', '.txt'):
            raise ValueError('Unsupported package member: ' + name)
        if not (ROOT / path).is_file():
            raise FileNotFoundError(name)
    with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        for name in FILES:
            archive.write(ROOT / name, name)
    with ZipFile(output) as archive:
        if archive.testzip() is not None or set(archive.namelist()) != set(FILES):
            raise ValueError('Package verification failed')
    print(output.name, len(FILES), output.stat().st_size)
    return output


if __name__ == '__main__':
    build()
