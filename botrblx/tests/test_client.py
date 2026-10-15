"""Execute the real Lua client under deterministic Roblox API mocks."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from client_cases import CASES

HERE = Path(__file__).resolve().parent
LUAU = os.environ.get("LUAU_BIN") or shutil.which("luau")


@unittest.skipUnless(LUAU, "Set LUAU_BIN to exercise the mocked Roblox client")
class ClientTests(unittest.TestCase):
    def run_case(self, name):
        _, behaviour, checks = next(case for case in CASES if case[0] == name)
        prefix = (HERE / "fixtures/roblox_mock.luau").read_text(encoding="utf-8")
        source = (HERE.parent / "client271.lua").read_text(encoding="utf-8")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / (name + ".luau")
            path.write_text(prefix + behaviour + source + checks, encoding="utf-8")
            result = subprocess.run([LUAU,str(path)],capture_output=True,text=True,timeout=10)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_live_frames_buttons_and_close(self): self.run_case("live_frames_and_close")
    def test_goal_respawn_resumes(self): self.run_case("goal_respawn_resumes")
    def test_teleport_invalidates_frame(self): self.run_case("teleport_invalidates_frame")
    def test_missing_boost_never_fabricates_state(self): self.run_case("missing_boost_no_fake_state")


if __name__ == "__main__": unittest.main(verbosity=2)
