"""Build a source-only Studio update for extraction over the existing project."""
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile
from package_native_attention import FILES as ATTENTION_FILES

ROOT = Path(__file__).resolve().parent
FILES = tuple(sorted(set(ATTENTION_FILES) | {
    'TRAINING_STUDIO.bat', 'TRAINING_STUDIO.vbs', 'slater_training_studio.py',
    'slater_champion_campaign.py', 'slater_model_selection.py', 'slater_v041_worker.py',
    'GigaLearn_Project/Native_Attention/AttentionCurriculum.h',
    'GigaLearn_Project/Native_Attention/AttentionEval.h',
    'GigaLearn_Project/Native_Attention/AttentionTasks.h',
    'docs/TRAINING_STUDIO.md', 'docs/AUTO_CHAMPION_CAMPAIGN.md', 'docs/MODEL_SELECTION.md',
    'docs/NATIVE_ATTENTION_SELECTION_EVAL.md', 'docs/NATIVE_PRACTICE_ROUTINES.md',
    'docs/WALL_RESET_CURRICULUM.md', 'docs/TRAINING_STUDIO_VALIDATION.md',
    'tests/test_training_studio.py', 'tests/test_champion_campaign.py',
    'tests/test_model_selection.py', 'tests/test_native_attention_portability.py',
    'tests/test_native_attention_curriculum.py', 'tests/native_attention_curriculum.cpp',
    'tests/test_native_attention_tasks.py', 'tests/native_attention_tasks.cpp',
    'tests/test_native_attention_selection_eval.py',
    'tests/native_attention_eval/CMakeLists.txt', 'tests/native_attention_eval/Smoke.cpp',
    'tests/test_native_attention_training_mix.py', 'package_training_studio.py',
}))


def build():
    output = ROOT / 'Slater_Training_Studio_Update.zip'
    for name in FILES:
        path = Path(name)
        if path.is_absolute() or '..' in path.parts or path.parts[0] in ('data', 'attachments', 'vendor'):
            raise ValueError('Private or unsafe archive member: ' + name)
        if path.suffix.lower() not in ('.py', '.cpp', '.h', '.md', '.bat', '.vbs', '.txt'):
            raise ValueError('Unsupported archive member: ' + name)
        if not (ROOT / path).is_file():
            raise FileNotFoundError(name)
    with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        for name in FILES:
            archive.write(ROOT / name, name)
    with ZipFile(output) as archive:
        if archive.testzip() or set(archive.namelist()) != set(FILES):
            raise RuntimeError('Studio archive verification failed')
    print(output.name, len(FILES), output.stat().st_size)
    return output


if __name__ == '__main__':
    build()
