"""Exercise the real optional C++ batched evaluator, not a mocked simulator."""
from pathlib import Path
import hashlib
import inspect
import json
import os
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def native_selection_binary():
    explicit = os.environ.get("SLATER_ATTENTION_EVAL_SMOKE_BINARY")
    if explicit:
        binary = Path(explicit)
        standalone = True
    else:
        binary = ROOT / "data/isolated/native_attention/build/SlaterAttentionNative"
        standalone = False
    if not binary.is_file():
        pytest.skip("Optional built native attention evaluation executable absent")
    return binary, standalone


@pytest.fixture
def selection_files(tmp_path):
    from rlgym.rocket_league.sim import RocketSimEngine
    meshes = Path(inspect.getfile(RocketSimEngine)).parent / "collision_meshes"
    actor = ROOT / "vendor/nexto/nexto-model.pt"
    if not actor.is_file():
        pytest.skip("Protected integration attention actor absent")
    sha = hashlib.sha256(actor.read_bytes()).hexdigest()
    actors = [{"id": name, "path": str(actor), "sha256": sha}
              for name in ("baseline", "candidate", "rival")]
    return tmp_path, meshes, actors


def make_manifest(folder, actors, *, scripted=False, seconds=1.25, formats=((1, 1), (2, 2), (3, 3), (1, 3))):
    jobs = []
    for candidate in ("baseline", "candidate"):
        for fmt in formats:
            for team in ("blue", "orange"):
                jobs.append({"id": f"{candidate}_{fmt[0]}v{fmt[1]}_{team}",
                             "candidate_id": candidate, "rival_id": "rival",
                             "reference_id": "baseline", "format": list(fmt),
                             "seed": 42, "learner_team": team, "seconds": seconds,
                             "learner_scripted_kickoff": scripted,
                             "frozen_scripted_kickoff": True})
    path = folder / "manifest.json"
    path.write_text(json.dumps({"schema": 1, "protocol_sha": "1" * 64,
                                "reference_id": "baseline", "actors": actors,
                                "jobs": jobs}))
    return path, jobs


def invoke(tool, manifest, meshes, output, pause, worlds=8, *, check=True):
    binary, standalone = tool
    if standalone:
        cmd = [str(binary), str(manifest), str(meshes), str(output), str(pause), str(worlds)]
    else:
        cmd = [str(binary), "--mode", "selector-eval", "--eval-manifest", str(manifest),
               "--meshes", str(meshes), "--out", str(output), "--pause", str(pause),
               "--eval-worlds", str(worlds), "--device", "cpu", "--threads", "1",
               "--sim-threads", "2"]
    proc = subprocess.run(cmd, check=check, text=True, capture_output=True, timeout=90)
    if check:
        assert "SLATER_SELECTOR_COMPLETE" in proc.stdout
    return proc


@pytest.mark.parametrize("scripted", [False, True])
def test_real_batched_rosters_full_clock_and_immutable_cached_resume(native_selection_binary, selection_files, scripted):
    folder, meshes, actors = selection_files
    actor = Path(actors[0]["path"])
    before = hashlib.sha256(actor.read_bytes()).hexdigest()
    manifest, jobs = make_manifest(folder, actors, scripted=scripted)
    output = folder / "run"
    invoke(native_selection_binary, manifest, meshes, output, folder / "PAUSE")
    result = json.loads((output / "evaluation.json").read_text())
    assert result["status"] == "FINITE_EVALUATION_COMPLETE"
    assert result["completed"] == len(jobs) == len(result["records"])
    assert result["max_loaded_actors"] == 1  # All IDs alias identical immutable weights.
    by_key = {(r["candidate_id"], tuple(r["format"]), r["learner_team"]): r for r in result["records"]}
    for row in result["records"]:
        assert row["finish"] == "COMPLETE" and row["game_complete"]
        assert row["physics_ticks"] == 150 and row["seconds"] == 1.25
        assert row["early_goal_window_seconds"] == 10
        assert 0 <= row["early_goal_concessions"] <= row["goals_against"]
        assert 0 <= row["early_goals_for"] <= row["goals_for"]
        assert row["frozen_script_ticks"] > 0
        assert (row["learner_script_ticks"] > 0) == scripted
        assert row["policy_sampling"] is False
        partner = by_key[("candidate" if row["candidate_id"] == "baseline" else "baseline",
                          tuple(row["format"]), row["learner_team"])]
        assert (row["goals_for"], row["goals_against"]) == (partner["goals_for"], partner["goals_against"])
    record_paths = list((output / "records").glob("*.json"))
    frozen = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in record_paths}
    invoke(native_selection_binary, manifest, meshes, output, folder / "PAUSE")
    resumed = json.loads((output / "evaluation.json").read_text())
    assert resumed["cached"] == len(jobs) and resumed["physics_ticks"] == 0
    for path, expected in frozen.items():
        assert (path.read_bytes(), path.stat().st_mtime_ns) == expected
    assert hashlib.sha256(actor.read_bytes()).hexdigest() == before


def test_pause_before_scheduling_and_resume(native_selection_binary, selection_files):
    folder, meshes, actors = selection_files
    manifest, jobs = make_manifest(folder, actors, formats=((1, 1),), seconds=.25)
    pause = folder / "PAUSE"
    pause.write_text("pause")
    output = folder / "paused"
    invoke(native_selection_binary, manifest, meshes, output, pause)
    result = json.loads((output / "evaluation.json").read_text())
    assert result["status"] == "PAUSED" and result["completed"] == 0
    assert result["physics_ticks"] == 0 and result["records"] == []
    pause.unlink()
    invoke(native_selection_binary, manifest, meshes, output, pause)
    result = json.loads((output / "evaluation.json").read_text())
    assert result["completed"] == len(jobs)


def test_corrupt_cache_and_changed_protocol_are_rejected(native_selection_binary, selection_files):
    folder, meshes, actors = selection_files
    manifest, _ = make_manifest(folder, actors, formats=((1, 1),), seconds=.25)
    output = folder / "run"
    invoke(native_selection_binary, manifest, meshes, output, folder / "PAUSE")
    record_path = next((output / "records").glob("*.json"))
    row = json.loads(record_path.read_text())
    row["descriptor"]["seed"] += 1
    record_path.write_text(json.dumps(row))
    proc = invoke(native_selection_binary, manifest, meshes, output, folder / "PAUSE", check=False)
    assert proc.returncode != 0 and "cache descriptor mismatch" in proc.stderr
    manifest_data = json.loads(manifest.read_text())
    manifest_data["jobs"][0]["seed"] += 1
    manifest.write_text(json.dumps(manifest_data))
    proc = invoke(native_selection_binary, manifest, meshes, output, folder / "PAUSE", check=False)
    assert proc.returncode != 0 and "different manifest/configuration" in proc.stderr


def test_flat_lt_and_invalid_rosters_are_rejected(native_selection_binary, selection_files):
    folder, meshes, actors = selection_files
    fake = folder / "policy.lt"
    fake.write_bytes(b"not original attention")
    invalid = [dict(actors[0], path=str(fake)), *actors[1:]]
    manifest, _ = make_manifest(folder, invalid, formats=((1, 1),), seconds=.25)
    proc = invoke(native_selection_binary, manifest, meshes, folder / "invalid_lt", folder / "PAUSE", check=False)
    assert proc.returncode != 0 and ".lt is not attention" in proc.stderr
    manifest, _ = make_manifest(folder, actors, formats=((4, 1),), seconds=.25)
    proc = invoke(native_selection_binary, manifest, meshes, folder / "invalid_roster", folder / "PAUSE", check=False)
    assert proc.returncode != 0 and "Invalid or duplicate selection job" in proc.stderr


def test_active_pause_finishes_bounded_games_then_resumes(native_selection_binary, selection_files):
    folder, meshes, actors = selection_files
    manifest, template = make_manifest(folder, actors, seconds=10, formats=((1, 1),))
    data = json.loads(manifest.read_text())
    data["jobs"] = []
    for seed_index in range(10):
        for row in template:
            job = dict(row, id=f"{row['id']}_{seed_index}", seed=42 + seed_index)
            data["jobs"].append(job)
    manifest.write_text(json.dumps(data))
    output = folder / "active_pause"
    pause = folder / "PAUSE"
    binary, standalone = native_selection_binary
    if standalone:
        command = [str(binary), str(manifest), str(meshes), str(output), str(pause), "4"]
    else:
        command = [str(binary), "--mode", "selector-eval", "--eval-manifest", str(manifest),
                   "--meshes", str(meshes), "--out", str(output), "--pause", str(pause),
                   "--eval-worlds", "4", "--device", "cpu", "--threads", "1", "--sim-threads", "2"]
    with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as process:
        for line in process.stdout:
            if line.startswith("SLATER_SELECTION_GAME "):
                pause.write_text("pause after a durable game")
                break
        _, error = process.communicate(timeout=90)
        assert process.returncode == 0, error
    paused = json.loads((output / "evaluation.json").read_text())
    assert paused["status"] == "PAUSED"
    assert 1 <= paused["completed"] < len(data["jobs"])
    assert all(row["seconds"] == 10 for row in paused["records"])
    frozen = {path: path.read_bytes() for path in (output / "records").glob("*.json")}
    pause.unlink()
    invoke(native_selection_binary, manifest, meshes, output, pause, worlds=4)
    resumed = json.loads((output / "evaluation.json").read_text())
    assert resumed["status"] == "FINITE_EVALUATION_COMPLETE"
    assert resumed["cached"] == paused["completed"]
    assert len(resumed["records"]) == len(data["jobs"])
    assert all(path.read_bytes() == content for path, content in frozen.items())
