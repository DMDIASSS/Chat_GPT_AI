# AFK Improved project state — share this in a new Temporary Chat

Date: 2026-10-09. Windows local project path: `E:\Downloads\Chat_GPT_AI`.

## Goals

A Rocket League bot which reliably exceeds original Nexto in 1v1. Maintain aggression but improve shooting decisions, flicks, backboard setup and follow-ups, defensive positioning and boost efficiency. User also wants windowed camera configuration and eventual RLBot export. Longer-term interest in GigaLearnCPP and training from high-level Ballchasing replays.

## Preferred training baseline

**Cycle 9 checkpoint**, SHA256 `50f34d4a3723bc2849c97200e8e42969e0cc1d82328473b017505994be1966d2`:

`data/autoleague/backups/20261008T224518_775472Z_cycle0009_steps000008192_candidate.pt`

The original AutoLeague champion SHA256 `c9596e2945ca6997f9ed496d90e89a772e519e4377db9989ef0645f827f6501a` is protected but is not the baseline for the new lineage.

Tournament: Cycle 9 scored 58.75% against Nexto in 160 first-goal episodes; champion 47.19%. Other independent tests had smaller or mixed differences. Cycle 9 was aggressive, generated shots but missed frequently. In a recent AFK test Cycle 9 tied champion against Nexto and won their direct comparison. Current champion may outperform Cycle 9 in some matchup settings. No absolute superiority is proven.

Finishing Lab candidate evaluations on 2026-10-09 did not clearly beat Cycle 9. It was NOT accepted as baseline. Smoke tests alone cannot claim better skill.

## Installed add-on (AFK Improved v1)

`AFK_IMPROVED.bat` launches Tkinter Windows app, with:
- Continuous or time-bounded protected 1v1 self-play/Nexto AutoLeague in `data/afk_improved/league`
- Safe pause at cycle boundary
- `best_verified.pt` distinct from experimental champion; independent verdict gate
- Checkpoint browser, backups, safe copies
- Local Ballchasing GC3/SSL ranked 1v1 replay download+offline hash audit; **NOT replay-to-native-policy training**
- Windowed Python/RocketSim camera via optional `pywebview`; adjust settings with `C`,`Tab`,`H`
- Separate existing RLBot v4 export (v5 not supported)
- GigaLearn migration checklist (`AFK_IMPROVED_GIGALEARN.md`); no C++ runtime integrated

Do NOT delete older `.pt` models or state files. Training modifications have been limited to this new isolated experiment. Ask for fresh benchmark results and training logs before suggesting promotion.

## What next

1. Validate real RocketSim preflight, then run overnight. Collect `data/afk_improved/reports`, `runner.log`, `status.json`.
2. Review real per-cycle promotion reliability, evaluate against Nexto and original champion across larger fresh held-out datasets and five-minute games.
3. Develop **true** replay-to-native learning only after reconstructing per-player state, Nexto observation/action labels, data quality filtering and evaluation. Prefer recent GC3/SSL 1v1 diverse players; Zen clips can be a supplementary qualitative source, not full dataset.
4. Port native Nexto attention policy into GigaLearn C++ and benchmark forward-output parity, steps/sec and improvement/wall-clock-hour on user's hardware. Do not swap live trainer before those are proven.
5. Extend 1v2 only when a three-car environment, reward scheme and evaluation are tested.

## Critical caveat

No AI improves linearly/exponentially forever. The runner is designed to avoid damaging original champions, not to guarantee every experimental checkpoint is better. A small first-goal gate can still promote false positives within its independent experiment directory.
