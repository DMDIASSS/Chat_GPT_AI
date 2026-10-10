"""Read-only teacher viewer installer. Does not replace existing viewer or trainer."""
from pathlib import Path
import shutil
HERE=Path(__file__).resolve().parent
GL=HERE.parents[1]
UPSTREAM=GL/'upstream'
CPP=UPSTREAM/'src/HubWatchTeacher.cpp'
SOURCE=HERE/'HubWatchTeacher.cpp'
CMAKE=UPSTREAM/'CMakeLists.txt'
MARK='# FROZEN_TEACHER_WATCH_V1'

def install():
    if not SOURCE.is_file() or not CMAKE.is_file() or not (UPSTREAM/'src/ExampleMain.cpp').is_file():
        raise RuntimeError('Missing Watch teacher source or installed GigaLearn upstream')
    content=CMAKE.read_text(encoding='utf-8-sig')
    needle='add_executable(GigaLearnBot ${FILES_SRC})'
    if CPP.is_file() and CPP.read_bytes()!=SOURCE.read_bytes():
        raise RuntimeError('HubWatchTeacher.cpp differs from package. Refusing overwrite.')
    if MARK not in content:
        if content.count(needle)!=1:raise RuntimeError('Cannot find unique trainer executable CMake definition')
        # Critical: GigaLearnBot's source glob would otherwise link a second main().
        patched=content.replace(needle,
          'list(FILTER FILES_SRC EXCLUDE REGEX "HubWatchTeacher\\\\.cpp$")\n'+needle,1)
        patched+='\n'+MARK+''' : C++ teacher viewer, does not alter existing models/viewer.
add_executable(GigaLearnWatchTeacher src/HubWatchTeacher.cpp)
set_target_properties(GigaLearnWatchTeacher PROPERTIES CXX_STANDARD 20)
target_link_libraries(GigaLearnWatchTeacher PRIVATE GigaLearnCPP RLBotCPP)
'''
        backup=CMAKE.with_name('CMakeLists.txt.before_frozen_teacher_watch_v1.bak')
        if not backup.exists():backup.write_text(content,encoding='utf-8')
        CMAKE.write_text(patched,encoding='utf-8')
    else:
        if 'add_executable(GigaLearnWatchTeacher src/HubWatchTeacher.cpp)' not in content:
            raise RuntimeError('CMake marker exists without viewer executable definition')
    if not CPP.exists():shutil.copyfile(SOURCE,CPP)
    print('PASS: Installed separate GigaLearnWatchTeacher target (read-only).')
    print('PASS: Original GigaLearnWatch, Learner.cpp and checkpoints were not touched.')
if __name__=='__main__':
    install()
