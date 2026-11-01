"""Optional actual C++/RocketSim drill checks, including a physical flip reset."""
from pathlib import Path
import subprocess

from test_native_attention_world import compile_fixture, native_toolchain  # noqa: F401


ROOT = Path(__file__).resolve().parents[1]


def test_native_wall_reset_events_and_real_physics(native_toolchain, tmp_path):
    binary = tmp_path / "curriculum-test"
    compile_fixture(native_toolchain, ROOT / "tests/native_attention_curriculum.cpp", binary)
    result = subprocess.run([str(binary), str(native_toolchain[3])],
                            check=True, capture_output=True, text=True)
    assert "NATIVE_ATTENTION_CURRICULUM_PASS" in result.stdout
    assert "real_wheel_reset=1" in result.stdout
    assert "proximity_farming=0" in result.stdout
