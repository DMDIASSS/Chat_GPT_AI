"""Real CPU training/resume checks for the optional native attention build.

These integration fixtures use the protected original Nexto actor, not the
user's unavailable update180 checkpoint. Passing verifies execution and saved
state; it does not establish that an experiment produces a stronger policy.
"""
from pathlib import Path
import math
import os

import pytest
import torch

import slater_native_attention as launcher
from slater_v041_core import read_json, sha256

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def native_mix_runtime(tmp_path, monkeypatch):
    build = Path(os.environ.get("SLATER_ATTENTION_BUILD_DIR", str(ROOT / "data/isolated/native_attention/build")))
    binary = launcher.binary_path(build)
    if not binary.is_file():
        pytest.skip("Optional native attention build unavailable")
    # Refuse a stale executable rather than silently testing an older backend.
    launcher.binary_identity(build)
    source = launcher.DEFAULT_RIVAL
    if not source.is_file():
        pytest.skip("Protected original attention integration actor unavailable")
    monkeypatch.setattr(launcher, "run_path", lambda name: tmp_path / name)
    before = sha256(source)
    yield build, source, tmp_path
    assert sha256(source) == before


def finite_tree(value):
    if isinstance(value, float):
        assert math.isfinite(value)
    elif isinstance(value, dict):
        for item in value.values():
            finite_tree(item)
    elif isinstance(value, list):
        for item in value:
            finite_tree(item)


def actor_state(path):
    return {name: tensor.detach().clone() for name, tensor in
            torch.jit.load(str(path), map_location="cpu").state_dict().items()}


def state_changed(before, after):
    assert before.keys() == after.keys()
    return any(not torch.equal(before[name], after[name]) for name in before)


def assert_completed_snapshots(state):
    selfplay = state["selfplay"]
    assert selfplay["refresh_updates"] == 1
    assert selfplay["learner_experience_only"] is True
    assert selfplay["teacher_remains_initial_source"] is True
    snapshots = {}
    for key in selfplay["recent"]:
        path = Path(selfplay["snapshot_paths"][key])
        assert path.name == "actor.pt" and path.is_file()
        launcher.complete_checkpoint(path.parent)
        snapshots[key] = (path, sha256(path))
    return snapshots


def assert_task_metrics(row, expected_total, match_task, practice_task):
    """Count actual collected learner rows, independently of head-weight checks."""
    counts = row["learner_rows_per_task"]
    if isinstance(counts, list):
        assert sum(counts) == expected_total
        assert counts[match_task] > 0 and counts[practice_task] > 0
    else:
        assert sum(counts.values()) == expected_total
        assert counts[str(match_task)] > 0 and counts[str(practice_task)] > 0


def test_real_boost_team_mix_selfplay_and_saved_resume(native_mix_runtime):
    build, source, folder = native_mix_runtime
    profile = {**launcher.PROFILE, "device": "cpu", "games": 8, "steps": 64,
               "seconds": 3., "routine": "boost", "formats": "1v1,2v2,3v3",
               "selfplay_refresh": 1, "seed": 20261013}
    result = launcher.train("boost_mix", source, profile=profile, build_dir=build, updates=2)
    finite_tree(result)
    run = folder / "boost_mix"
    initial = run / "checkpoints/checkpoint_000000"
    saved = launcher.latest_checkpoint(run)
    assert result["updates"] == 2 and result["decisions"] == 1024
    assert result["frozen_teacher_unchanged"] is True and result["source_unchanged"] is True
    assert result["curriculum"]["normal_worlds"] == 4
    assert result["curriculum"]["practice_worlds"] == 4
    assert result["curriculum"]["routine"] == "boost"
    assert result["curriculum"]["formats"] == "1v1,2v2,3v3"
    original_actor = actor_state(initial / "actor.pt")
    trained_actor = actor_state(saved / "actor.pt")
    assert len(original_actor) == 44 and state_changed(original_actor, trained_actor)
    assert not state_changed(actor_state(initial / "teacher.pt"), actor_state(saved / "teacher.pt"))
    initial_critic = actor_state(initial / "critic.pt")
    trained_critic = actor_state(saved / "critic.pt")
    assert initial_critic["heads.weight"].shape == (12, 192)
    assert not torch.equal(initial_critic["heads.weight"][0], trained_critic["heads.weight"][0])
    assert not torch.equal(initial_critic["heads.weight"][9], trained_critic["heads.weight"][9])
    assert torch.equal(initial_critic["heads.weight"][1], trained_critic["heads.weight"][1])
    episode_outcomes = []
    for update in (1, 2):
        row = read_json(run / f"update_{update}.json")
        finite_tree(row)
        assert row["learner_scripted_kickoff"] is False
        assert row["frozen_scripted_kickoff"] is True
        assert_task_metrics(row, 512, 0, 9)
        episode_outcomes.extend(row["episode_outcomes"])
    assert any(row["practice"] for row in episode_outcomes)
    assert any(not row["practice"] for row in episode_outcomes)
    assert {row["side"] for row in episode_outcomes} == {"blue", "orange"}
    assert all(0 <= row["learner_slot"] < row["our_size"] for row in episode_outcomes)
    assert all(row["curriculum"]["routine"] == "boost" for row in episode_outcomes if row["practice"])
    state_before = read_json(saved / "state.json")
    snapshots_before = assert_completed_snapshots(state_before)
    assert set(snapshots_before) == {"snapshot_1", "snapshot_2"}
    checkpoint_before = sha256(saved / "actor.pt")
    result = launcher.train("boost_mix", build_dir=build, updates=1, resume=True)
    finite_tree(result)
    latest = launcher.latest_checkpoint(run)
    assert latest.name == "checkpoint_000003"
    assert result["updates"] == 3 and result["decisions"] == 1536
    assert result["frozen_teacher_unchanged"] is True
    assert sha256(saved / "actor.pt") == checkpoint_before
    snapshots_after = assert_completed_snapshots(read_json(latest / "state.json"))
    assert set(snapshots_after) == {"snapshot_1", "snapshot_2", "snapshot_3"}
    for key, (path, digest) in snapshots_before.items():
        assert snapshots_after[key] == (path, digest)
    assert not state_changed(actor_state(initial / "teacher.pt"), actor_state(latest / "teacher.pt"))
    launcher.verify_protected(read_json(run / "protocol.json"))


def test_real_wall_reset_mixed_allocation_and_nonzero_task_head(native_mix_runtime):
    build, source, folder = native_mix_runtime
    profile = {**launcher.PROFILE, "device": "cpu", "games": 2, "steps": 64,
               "seconds": 3., "routine": "wall-reset", "start_stage": 0,
               "practice_fraction": .5, "seed": 20261013}
    result = launcher.train("wall_mix", source, profile=profile, build_dir=build, updates=1)
    finite_tree(result)
    run = folder / "wall_mix"
    assert result["updates"] == 1 and result["decisions"] == 128
    assert result["curriculum"]["enabled"] is True
    assert result["curriculum"]["normal_worlds"] == result["curriculum"]["practice_worlds"] == 1
    assert result["frozen_teacher_unchanged"] is True
    row = read_json(run / "update_1.json")
    finite_tree(row)
    assert_task_metrics(row, 128, 0, 1)
    outcomes = row["episode_outcomes"]
    assert any(not item["practice"] for item in outcomes)
    practice = [item for item in outcomes if item["practice"]]
    assert practice
    for item in practice:
        assert item["curriculum"]["target_stage"] == 0
        assert item["curriculum"]["wall_side"] in (-1, 1)
    # With at least two completed practice episodes, the alternating learner
    # team must exercise both colors instead of repeatedly resetting one side.
    if len(practice) >= 2:
        assert {item["side"] for item in practice} == {"blue", "orange"}
    initial = run / "checkpoints/checkpoint_000000"
    latest = launcher.latest_checkpoint(run)
    first_critic = actor_state(initial / "critic.pt")
    last_critic = actor_state(latest / "critic.pt")
    assert not torch.equal(first_critic["heads.weight"][0], last_critic["heads.weight"][0])
    assert not torch.equal(first_critic["heads.weight"][1], last_critic["heads.weight"][1])
    assert state_changed(actor_state(initial / "actor.pt"), actor_state(latest / "actor.pt"))
    assert not state_changed(actor_state(initial / "teacher.pt"), actor_state(latest / "teacher.pt"))
    launcher.verify_protected(read_json(run / "protocol.json"))
