"""Package the source update needed by the update271 format-target preset."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT = Path(__file__).resolve().parent
FILES = (
    'GigaLearn_Project/Native_Attention/AttentionMain.cpp',
    'slater_native_attention.py', 'slater_champion_campaign.py',
    'slater_model_selection.py', 'slater_training_studio.py',
    'export_rlbot_v4.py', 'ATTENTION_NATIVE.bat',
    'TRAINING_STUDIO.bat', 'TRAINING_STUDIO.vbs', 'U271_TARGETS_SETUP.bat',
    'STUDIO_CAMPAIGN_U271_FORMAT_TARGETS.json', 'TRAINING_U271_FORMAT_OPPONENTS.json',
    'docs/U271_FORMAT_TARGETS.md',
    'tests/test_champion_campaign.py', 'tests/test_model_selection.py',
    'tests/test_native_attention_training_mix.py', 'package_u271_format_targets.py',
)

def build():
    target = ROOT / 'Slater_U271_Format_Targets_Update.zip'
    with ZipFile(target, 'w', ZIP_DEFLATED) as archive:
        for name in FILES:
            if not (ROOT / name).is_file():
                raise FileNotFoundError(name)
            archive.write(ROOT / name, name)
    with ZipFile(target) as archive:
        if archive.testzip() or set(archive.namelist()) != set(FILES):
            raise RuntimeError('Source archive verification failed')
    print(target.name, target.stat().st_size, 'bytes; no models or compiled binaries')
    return target

if __name__ == '__main__':
    build()
