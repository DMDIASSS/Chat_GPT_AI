"""Actual RocketSim checks for freestyle reward causality and state validity."""
from pathlib import Path
import os
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_freestyle_physics_observations_and_reward_guards(tmp_path):
    source = Path(os.environ.get("SLATER_GIGA_SOURCE", ROOT / "data/isolated/native_attention/source"))
    libraries = Path(os.environ.get("SLATER_RLGYM_LIB_DIR", ROOT / "data/isolated/native_attention/build/rlgym"))
    include = source / "GigaLearnCPP/RLGymCPP/src"
    compiler = shutil.which("g++") or shutil.which("clang++")
    if not compiler or not all(path.is_file() for path in (
        include / "RLGymCPP/Gamestates/GameState.h", libraries / "libRLGymCPP.a",
        libraries / "RocketSim/libRocketSim.a",
    )):
        pytest.skip("Optional native RocketSim toolchain unavailable")
    from rlgym.rocket_league.sim import RocketSimEngine
    import inspect
    meshes = Path(inspect.getfile(RocketSimEngine)).parent / "collision_meshes"
    binary = tmp_path / "freestyle-checks"
    compile_result = subprocess.run([
        compiler, "-std=c++20", "-O1", f"-I{ROOT}", f"-I{include}",
        str(ROOT / "tests/freestyle_native_checks.cpp"), str(libraries / "libRLGymCPP.a"),
        str(libraries / "RocketSim/libRocketSim.a"), "-pthread", "-o", str(binary),
    ], capture_output=True, text=True)
    assert compile_result.returncode == 0, compile_result.stderr
    result = subprocess.run([str(binary), str(meshes)], capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "FREESTYLE_NATIVE_PASS real_wheel_reset=1 proximity_farming=0" in result.stdout
    assert "randomized_starts=240" in result.stdout
    assert "two_car_learner=blue offpolicy_defender_reward=0" in result.stdout
    assert "controls=94 masks_valid=1" in result.stdout
