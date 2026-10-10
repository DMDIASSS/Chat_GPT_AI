"""One-time guarded C++ evaluator install. Does not rewrite trainer source."""
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / 'upstream'
CPP_TARGET = SRC / 'src' / 'HubEvaluate.cpp'
CMAKE = SRC / 'CMakeLists.txt'
TAG = 'AFK_HUB_EVALUATOR_V1'

CMAKE_SNIPPET = r'''
# AFK_HUB_EVALUATOR_V1: separate read-only competitive evaluator executable.
add_executable(GigaLearnEval src/HubEvaluate.cpp)
set_target_properties(GigaLearnEval PROPERTIES CXX_STANDARD 20)
target_link_libraries(GigaLearnEval PRIVATE GigaLearnCPP RLBotCPP)
'''

def patch_source():
    source = HERE / 'src' / 'HubEvaluate.cpp'
    if not source.is_file():
        raise RuntimeError('Missing bundled C++ evaluator source')
    if not CMAKE.is_file() or not (SRC/'src'/'ExampleMain.cpp').is_file():
        raise RuntimeError('Missing upstream source. GigaLearn must be cloned and Research Hub must already be installed.')
    cmake=CMAKE.read_text(encoding='utf-8-sig')
    orig=cmake
    if TAG not in cmake:
        marker='add_executable(GigaLearnBot ${FILES_SRC})'
        if cmake.count(marker)!=1:
            raise RuntimeError('Unsupported upstream CMakeLists.txt; refusing to patch')
        # Do not compile the second main() into GigaLearnBot.
        cmake=cmake.replace(marker, 'list(FILTER FILES_SRC EXCLUDE REGEX "HubEvaluate\\\\.cpp$")\n'+marker,1)
        cmake+='\n'+CMAKE_SNIPPET
    current=CPP_TARGET.read_bytes() if CPP_TARGET.is_file() else None
    expected=source.read_bytes()
    if current is not None and current!=expected:
        raise RuntimeError('An existing HubEvaluate.cpp differs; refusing to overwrite it')
    if cmake!=orig:
        bak=CMAKE.with_name('CMakeLists.txt.before_hub_eval_v1.bak')
        if bak.exists() and bak.read_text(encoding='utf8') != orig:
            raise RuntimeError('CMake backup conflicts; inspect before applying evaluator')
        if not bak.exists():bak.write_text(orig,encoding='utf8')
        CMAKE.write_text(cmake,encoding='utf8')
    if current is None:
        shutil.copy2(source,CPP_TARGET)
    return {'installed':str(CPP_TARGET),'cmake_patched':cmake!=orig,'build_target':'GigaLearnEval'}

if __name__=='__main__':
    print(patch_source())
