# Next steps toward a stronger Slater

The goal is competitive SSL+ play. No result in this update establishes that rank, professional-level skill, or superiority over the user's strongest existing V70/V60 models. Training infrastructure is a means to generate and verify candidates.

## What the upstream links change

Reviewed on 2026-10-12. Upstream claims below are attributed to their authors, not measurements from this project.

| Project | Useful evidence or capability | Decision for this actor |
| --- | --- | --- |
| [replay-pretraining](https://github.com/Rolv-Arild/replay-pretraining) | Its README describes inverse dynamics, SSL replay imitation, then extensive RL leading to Ripple. This contradicts the old blanket claim that replay learning never worked. | A promising next phase. Its BCNet/advanced-observation format differs from native Nexto `(q,kv,mask)`; port labels and validate alignment, not weights. Source at `8c15e847dc9ecf37ef8ad38d6c615b080772c959`. |
| [replicar](https://github.com/Rolv-Arild/replicar) | V2 reconstructs 120 Hz states with controls, provenance, hidden jump/flip state, diagnostics and an RLGym bridge. Air controls are fitted using later packets; author validation includes LAN ground truth and indirect online checks. | Compare against held-out real traces before using inferred controls as targets. Its Parquet format is not an rlgym-tools ReplayFrame bank. Source at `a775fb1c4e5ee5c3079de3d0e6a16edb9335b71d`. |
| [rlgym-tools](https://github.com/RLGym/rlgym-tools) | Replay parsing, ReplayMutator, numeric state serialization, augmentation and physics rewards. | Integrated optional prepared ReplayFrame reset banks, with `rlgym-tools==2.6.5`; no human control imitation yet. |
| [rl-high-level-dataset](https://github.com/Rolv-Arild/rl-high-level-dataset) | Author describes a curated 140k-match dataset with skill, bot, activity and anomaly filtering. The collection pipeline requires Python 3.13+. | Prefer diverse curated 1v1 data to isolated highlights. Use a separate data-preparation environment; the current trainer is Python 3.12. Start with a small representative sample, not the whole dataset. |
| [rocket-learn](https://github.com/Rolv-Arild/rocket-learn) | Distributed Redis workers, past-agent opponents, skill tracking. README describes the older live-game RLGym/Bakkesmod workflow. | Useful league design, but not a drop-in replacement for the current v2 RocketSim collector. Profile a native parallel collector first. |
| [python-ballchasing](https://github.com/Rolv-Arild/python-ballchasing) | API wrapper for replay discovery/download; requires a Ballchasing key. | Optional collection helper. Existing local data and prepared banks do not need this key. |
| [rlgym](https://github.com/Rolv-Arild/rlgym) | Environment API and RocketSim installation extras. | Existing simulator path; preserve version, timing, action and observation parity when changing backends. |
| [GigaLearnCPP-Leak](https://github.com/ZealanL/GigaLearnCPP-Leak) | Fast native PPO, action delay, skill tracker and configurable architecture. Author's throughput claims concern their hardware. | Benchmark after an actual Nexto architecture/observation/action conversion. No automatic checkpoint compatibility. |
| [NezBot](https://github.com/ZeroII99II/NezBot) | GigaLearn wrapper layout. Inspected `tools/checkpoint_converter.py` writes a placeholder text file. | This converter cannot transfer the current trained actor. |
| [RankedSSLRLBOT](https://github.com/ZeroII99II/RankedSSLRLBOT) | A proposed curriculum pipeline. Inspected `test_real_env_smoke.py` replaces RLGym with stub modules. | Naming and stub tests do not establish SSL skill, working real physics, or compatibility with this actor. |

Organization/profile pages are discovery lists, not specific dependencies. The repository's existing links to VirxEC replay reconstruction and NicEastvillage live evaluation/export tools remain useful follow-up candidates. No upstream project above was installed wholesale into or vendored into this repository.

## Implemented training changes

- Include ordinary, unperturbed PPO continuation alongside parameter-noise branches.
- Measure exact policy KL on rollout states after each PPO epoch and restore weights plus Adam moments when an epoch exceeds the budget. Keep the V60 teacher regularizer.
- Mix synthetic kickoff/ground/defense starts, with one-tick RLBot delay enabled in the new configuration.
- Optionally sample prepared 1v1 replay starts while preserving serialized hidden car state and remapping IDs to the league's `blue-0`/`orange-0`. Reject pauses, wrong rosters, nonstandard mutators, invalid physics, demo states and terminal goals. Future labels and reconstructed control arrays do not enter model inputs or PPO targets. Dataset hashes are locked across subprocesses/resume.
- Require larger balanced holdouts and consistent advantages across independent seed clusters; account for two finalists and repeated generations. Cache identity includes opponents, seed ranges, horizon and action delay.

Default `replay_starts` is null. Nothing here downloads replay data or imitates professional controls automatically.

## Optional prepared replay reset banks

The supported format is the serialized `ReplayFrame` matrix produced by rlgym-tools 2.6.5: `.npy`, or `.npz` with key `replay_frames`. Raw `.replay`, Replicar Parquet, old RLGym v1 state arrays and RL-RPT BC shards are different formats.

On Windows, install the optional dependency in the existing project environment:

```bat
cd /d E:\Downloads\Chat_GPT_AI
.venv\Scripts\python.exe -m pip install -r requirements-slater-replays.txt
```

Prepare a small, separate **training** set using the upstream `ReplayMutator.make_file` API or its `scripts/make_replay_mutator_states.py`; retain source replay IDs, conversion version/settings and a disjoint replay-level holdout. Do not blend train/test frames from the same match. Parsing/fitting does not certify fidelity: inspect sampled resets and continuation behavior before scaling. Keep the bank and raw data under ignored `data/`.

In a new league config, use:

```json
{
  "replay_starts": "data/replay_starts/train_1v1.npy",
  "replay_start_probability": 0.2
}
```

The other 80% of resets use `training_reset` (default mixed ground). A prepared bank is optional; adding it does not remove normal kickoff evaluation. Preflight decodes a sample and records the dataset SHA. Run the independent validation first, then the full six-rival smoke:

```bat
.venv\Scripts\python.exe slater_v041_validate.py --steps 512 --replay-starts data/replay_starts/train_1v1.npy --out data/isolated/replay_reset_integration01.json
.venv\Scripts\python.exe slater_v041_overnight.py preflight
.venv\Scripts\python.exe slater_v041_overnight.py smoke
```

The standalone validation uses original Nexto and samples replay starts at 50% to exercise the path; check `replay_episodes_finished` in the report. It discards its temporary actor. It is not a benchmark or V70 continuation. Use new report filenames on repetition.

## Gates before scaling toward SSL+

1. Supply full V70 PPO source, protected original V60/Cycle9 and six frozen opponents outside Git. Run full preflight and smoke. A TorchScript RLBot export does not contain critic/Adam resume state.
2. Compare a bounded continuation, mutation branches and the mixed/replay reset distributions on common held-out seeds. Measure goals and concessions, not touch counts alone. Use full-length matches and separately scored defense/recovery/shot drills in addition to the current first-goal protocol.
3. Measure complete collection + optimization + evaluation throughput before scaling to millions of decisions. Preserve action timing and native attention observations in any C++/vectorized backend. Validate against the frozen reference after conversion.
4. For human imitation, build an inverse-dynamics calibration set with **known** simulator actions, validate on held-out trajectories and real traces, then fit confidence-filtered SSL replay labels. Convert observations to this actor's native format. Keep future frames out of causal actor inputs; split by source replay/player as appropriate.
5. Fine-tune in an isolated lineage with behavior regularization and replay/self-play interleaving. Expand aerial, recovery and team curricula after their physics and success metrics work. Use stronger available opponents and skilled human offline/LAN evaluations to substantiate competitive claims.

Cloud tests exercise original Nexto, real RocketSim, mixed starts and a **synthetic** serialized replay-frame fixture. No real high-rank replay bank or private V70/V60 artifacts were available. Therefore human-replay training, full protected-league execution and improved competitive skill remain unvalidated.

The broad regression command was:

```sh
PYTHONPATH="$PWD/tests" OMP_NUM_THREADS=2 .venv/bin/python -m pytest --import-mode=importlib tests slater_v0*_tests slater_research/tests -q
```

Result: **448 passed, 2 failed, 1 skipped**. Both failures are existing v036 export tests requiring absent ignored `data/rlbot_exports/slater_v036_nexto_modes/.../bot.py` and `bot.cfg` files; the viewer skip expects an external model location. The updated v041 suite passed all **55** checks. Synthetic replay-reset integration completed 512 decisions, four training episodes (two replay starts), three timeout bootstraps, two accepted epochs and four paired evaluation cases; policy KL was `0.000744`, actor weights changed and original Nexto remained unchanged. No synthetic fixture is distributed as a human replay dataset.
