"""Idempotent isolated C++ BC target installer; refuses to overwrite user modifications."""
from pathlib import Path
import hashlib,shutil

HERE=Path(__file__).resolve().parent
UPSTREAM=HERE.parents[1]/'upstream' # Curriculum_V2 -> Research_Hub -> GigaLearn_Project -> upstream
MARK='# GIGALEARN_CURRICULUM_REPLAY_BC_V1'
CMAKE_BLOCK='''
# GIGALEARN_CURRICULUM_REPLAY_BC_V1 - isolated native .lt behavior cloning executable
list(FILTER FILES_SRC EXCLUDE REGEX "HubReplayBC\\\\.cpp$")
add_executable(GigaLearnReplayBC src/HubReplayBC.cpp)
set_target_properties(GigaLearnReplayBC PROPERTIES CXX_STANDARD 20)
# Model/optimizer implementation is internal to GigaLearnCPP's DLL and is NOT
# exported on MSVC. Compile those two implementation files into this separate
# executable rather than relying on unexported DLL symbols.
target_sources(GigaLearnReplayBC PRIVATE
  GigaLearnCPP/src/private/GigaLearnCPP/Util/Models.cpp
  GigaLearnCPP/src/private/GigaLearnCPP/Util/MagSGD.cpp)
target_include_directories(GigaLearnReplayBC PRIVATE
  ${CMAKE_CURRENT_SOURCE_DIR}/GigaLearnCPP/src
  ${CMAKE_CURRENT_SOURCE_DIR}/GigaLearnCPP/src/private
  ${CMAKE_CURRENT_SOURCE_DIR}/GigaLearnCPP/src/public)
find_package(Torch REQUIRED)
target_link_libraries(GigaLearnReplayBC PRIVATE GigaLearnCPP RLBotCPP "${TORCH_LIBRARIES}")
'''

def install():
    cmake=UPSTREAM/'CMakeLists.txt';src=UPSTREAM/'src/HubReplayBC.cpp';dest=HERE/'cpp/HubReplayBC.cpp'
    if not cmake.is_file() or not (UPSTREAM/'src/ExampleMain.cpp').is_file():
        raise RuntimeError('GigaLearn upstream source missing. Need existing working GigaLearn_Project/upstream')
    if not dest.is_file():raise RuntimeError('Bundled C++ source is missing')
    existing=cmake.read_text(encoding='utf-8-sig')
    if MARK not in existing:
        if 'add_executable(GigaLearnBot ${FILES_SRC})' not in existing:
            raise RuntimeError('Unexpected upstream CMake structure; no changes made')
        # Add after existing target definitions. Glob commonly compiles new CPP into the main bot;
        # exclude it BEFORE add_executable(GigaLearnBot...).
        needle='add_executable(GigaLearnBot ${FILES_SRC})'
        patched=existing.replace(needle,'list(FILTER FILES_SRC EXCLUDE REGEX "HubReplayBC\\\\.cpp$")\n'+needle,1)+CMAKE_BLOCK
    else:patched=existing
    raw=dest.read_bytes()
    if src.exists() and src.read_bytes()!=raw:
        raise RuntimeError('Existing upstream HubReplayBC.cpp differs. Refusing overwrite.')
    if patched!=existing:
        backup=cmake.with_name('CMakeLists.txt.before_curriculum_bc.bak')
        if backup.exists() and backup.read_text(encoding='utf8')!=existing:raise RuntimeError('Different CMake backup already exists; manual review needed')
        if not backup.exists():backup.write_text(existing,encoding='utf8')
        cmake.write_text(patched,encoding='utf8')
    if not src.exists():shutil.copy2(dest,src)
    return {'cpp_target':'GigaLearnReplayBC','cpp_source':str(src),'cmake_changed':patched!=existing,
            'requires_build':True,'runtime_compiled':False}
if __name__=='__main__':print(install())
