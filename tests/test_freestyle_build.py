"""Exercise the actual CMake source replacement with Windows path spellings."""
from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('spellings', [
    [r'E:\Downloads\Chat_GPT_AI\source\GigaLearnCPP\src\public\GigaLearnCPP\Learner.cpp'],
    ['e:/downloads/chat_gpt_ai/source/gigalearncpp/src/public/gigalearncpp/learner.cpp'],
    ['src/public/GigaLearnCPP/Learner.cpp'],
])
def test_cmake_replaces_exactly_one_learner_across_windows_path_formats(tmp_path, spellings):
    result, sources = configure(tmp_path, spellings)
    assert result.returncode == 0, result.stdout + result.stderr
    assert sources == ['untouched.cpp', 'different/Learner.cpp', 'generated/FreestyleLearner.cpp']


@pytest.mark.parametrize('spellings', [[], [
    'src/public/GigaLearnCPP/Learner.cpp',
    r'E:\Downloads\Chat_GPT_AI\source\GigaLearnCPP\src\public\GigaLearnCPP\Learner.cpp',
]])
def test_cmake_refuses_missing_or_duplicate_upstream_learner(tmp_path, spellings):
    result, _ = configure(tmp_path, spellings)
    assert result.returncode != 0
    assert 'Expected exactly one upstream Learner.cpp' in result.stderr


def configure(folder, spellings):
    compiler = ROOT / '.venv/bin/cmake'
    cmake = str(compiler) if compiler.is_file() else shutil.which('cmake')
    if not cmake:
        pytest.skip('CMake unavailable')
    module = ROOT / 'GigaLearn_Project/Freestyle/FreestyleBuild.cmake'
    output = folder / 'sources.txt'
    arguments = ' '.join('[[%s]]' % source for source in [*spellings, 'untouched.cpp', 'different/Learner.cpp'])
    (folder / 'CMakeLists.txt').write_text(f'''
cmake_minimum_required(VERSION 3.20)
project(FreestyleSourceReplacement LANGUAGES NONE)
set(WIN32 TRUE)
include([[{module.as_posix()}]])
add_library(Fake INTERFACE)
set_property(TARGET Fake PROPERTY SOURCES {arguments})
freestyle_replace_learner(Fake
 [[E:/Downloads/Chat_GPT_AI/source/GigaLearnCPP/src/public/GigaLearnCPP/Learner.cpp]]
 [[generated/FreestyleLearner.cpp]] [[E:/Downloads/Chat_GPT_AI/source/GigaLearnCPP]])
get_target_property(retained Fake SOURCES)
file(WRITE [[{output.as_posix()}]] "${{retained}}")
# The test checks source identities, not whether Windows files exist in Linux.
set_property(TARGET Fake PROPERTY SOURCES "")
''', encoding='utf-8')
    result = subprocess.run([cmake, '-S', str(folder), '-B', str(folder / 'build')],
                            capture_output=True, text=True)
    return result, output.read_text().split(';') if output.exists() else []
