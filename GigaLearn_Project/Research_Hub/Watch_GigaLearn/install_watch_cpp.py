"""Guarded installer: adds only a separate inference viewer build target."""
from pathlib import Path
import shutil

HERE=Path(__file__).resolve().parent
GL=HERE.parents[1]
UPSTREAM=GL/'upstream'
CPP=UPSTREAM/'src/HubWatch.cpp'
SOURCE=HERE/'cpp/HubWatch.cpp'
CMAKE=UPSTREAM/'CMakeLists.txt'
MARK='# AFK_GIGALEARN_WATCH_V1'
SNIPPET=r'''
# AFK_GIGALEARN_WATCH_V1: read-only .lt model viewer source.
add_executable(GigaLearnWatch src/HubWatch.cpp)
set_target_properties(GigaLearnWatch PROPERTIES CXX_STANDARD 20)
target_link_libraries(GigaLearnWatch PRIVATE GigaLearnCPP RLBotCPP)
'''

def install():
    if not SOURCE.is_file() or not CMAKE.is_file() or not (UPSTREAM/'src/ExampleMain.cpp').is_file():
        raise RuntimeError('Expected Research Hub and GigaLearn upstream source missing')
    content=CMAKE.read_text(encoding='utf-8-sig')
    original=content
    if CPP.exists() and CPP.read_bytes()!=SOURCE.read_bytes():
        raise RuntimeError('HubWatch.cpp already exists and differs. Refusing overwrite.')
    if MARK not in content:
        needle='add_executable(GigaLearnBot ${FILES_SRC})'
        if content.count(needle)!=1:raise RuntimeError('Cannot locate unique GigaLearnBot CMake target')
        # CMake GLOB sees new src/*.cpp; exclude before creating training executable.
        content=content.replace(needle,'list(FILTER FILES_SRC EXCLUDE REGEX "HubWatch\\\\.cpp$")\n'+needle,1)
        content+='\n'+SNIPPET
    if content!=original:
        backup=CMAKE.with_name('CMakeLists.txt.before_gigalearn_watch_v1.bak')
        if backup.exists() and backup.read_text(encoding='utf-8')!=original:
            raise RuntimeError('Existing CMake backup disagrees; refusing changes')
        if not backup.exists():backup.write_text(original,encoding='utf-8')
        CMAKE.write_text(content,encoding='utf-8')
    if not CPP.exists():shutil.copy2(SOURCE,CPP)
    return {'target':'GigaLearnWatch','cpp':str(CPP),'cmake_changed':content!=original,
            'checkpoints_modified':False}

if __name__=='__main__':print(install())
