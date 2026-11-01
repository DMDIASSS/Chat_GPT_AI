"""Compile and exercise event-gated practice rewards with real RocketSim libraries."""
from pathlib import Path
import os
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_native_practice_starts_event_edges_farming_and_real_pickup(tmp_path):
    source = Path(os.environ.get("SLATER_GIGA_SOURCE", "/workspace/native-giga-test/upstream-source"))
    libraries = Path(os.environ.get("SLATER_RLGYM_LIB_DIR", "/workspace/native-giga-test/build2/giga/RLGymCPP"))
    include = source / "GigaLearnCPP/RLGymCPP/src"
    compiler = shutil.which("g++") or shutil.which("clang++")
    required = [include / "RLGymCPP/Gamestates/GameState.h", libraries / "libRLGymCPP.a",
                libraries / "RocketSim/libRocketSim.a"]
    if not compiler or not all(path.is_file() for path in required):
        pytest.skip("Optional C++ RocketSim toolchain unavailable")
    from rlgym.rocket_league.sim import RocketSimEngine
    import inspect
    meshes = Path(inspect.getfile(RocketSimEngine)).parent / "collision_meshes"
    binary = tmp_path / "tasks-test"
    build = subprocess.run([compiler, "-std=c++20", "-O1", f"-I{ROOT}", f"-I{include}",
                            str(ROOT / "tests/native_attention_tasks.cpp"),
                            str(libraries / "libRLGymCPP.a"), str(libraries / "RocketSim/libRocketSim.a"),
                            "-pthread", "-o", str(binary)], capture_output=True, text=True)
    assert build.returncode == 0, build.stdout + build.stderr
    result = subprocess.run([str(binary), str(meshes)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "NATIVE_ATTENTION_TASKS_PASS" in result.stdout
