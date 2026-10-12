# Slater Research Add-on v0.1.1 — Windows extraction hotfix

This hotfix replaces four Python modules and adds/updates two tests. No
checkpoint is overwritten. Extract to `E:\Downloads\Chat_GPT_AI`, preserving
`slater_research\` folder paths and replacing the files when prompted.

## Changes

- `checkpoint.py`: removed `copy.deepcopy()` of the TorchScript actor (some
  PyTorch versions return non-leaf parameters); loads an independent teacher
  through `torch.jit.load` and runs teacher inference under `torch.no_grad`.
- `replay_engine.py`: `goal_events` now reads goal frame boundaries from
  `analyzer.gameplay_periods` rather than requiring `is_goal` on hits. Selects
  the last scoring-team ball toucher as a **proxy** for the shooter, rejects
  apparent own goals, and prevents snippets crossing known kickoff periods.
  Reconstructed replay controls still require physics fidelity validation.
- `extract.py`: exports per-replay diagnostics to manifest.json; `--limit N`
  supports a small smoke test before converting hundreds of replays.
- `train_scenarios.py`: validates the dataset before loading Cycle 9.
- Regression tests: 14 locally passing tests in this package.

## Commands to run (Windows CMD, no shell comment lines)

    cd /d E:\Downloads\Chat_GPT_AI
    .venv\Scripts\python.exe -m pytest slater_research\tests -q
    .venv\Scripts\python.exe -m slater_research.extract --replays data\replays --out data\replay_scenarios_smoke --lead 12 --limit 10

Inspect the printed diagnostics and
`data\replay_scenarios_smoke\manifest.json`. A goal can be rejected because
there was less than 10 seconds of playable lead-up, because the scorer could
not be identified, or because of missing/invalid frames. Inspect the data
rather than lowering validation thresholds until clips appear.

If you have verified the smoke-test clips, extract the full dataset to a
separate clean output folder:

    .venv\Scripts\python.exe -m slater_research.extract --replays data\replays --out data\replay_scenarios --lead 12

Do NOT start PPO training yet. Check the number of extracted clips, the
replay physics fidelity, and the Cycle 9 SHA and original performance first.
Training and simulator integration have NOT been validated in your Windows
runtime from this environment; this hotfix was unit tested with synthetic data.
