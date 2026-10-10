# AFK Improved v2.1 — user-request audit (2026-10-09)

## Data-supported choice

- Main training lineage: **Cycle 9**, checkpoint name `20261008T224518_775472Z_cycle0009_steps000008192_candidate.pt`, SHA starts `50f34d4a3723`.
- Held-out tournament: 58.75% on 160 first-goal episodes for Cycle 9, 55% Wavedash, 47.19% original champion. Rankings vary with seeds, opponent, and duration.
- Finishing Lab smoke test was 96 decision ticks, 4 draws each; inconclusive. Subsequent training candidates were weaker than their reference in provided larger reports, so **no promotion**.
- User replay inventory: 200 `.replay` files, 184 unique by content hash, 16 duplicated hashes. NOT training-ready.
- CUDA crash: baked-in CPU action embedding vs CUDA linear weights in Nexto TorchScript, confirmed in the serialized program. Safe CPU fallback is implemented.

## Delivered and tested in this patch

| Requirement | Actual status |
|---|---|
| Single selected baseline and protected original | YES: Cycle 9, isolated data/afk_improved/league |
| Unlimited/time-limited 1v1 self-play + Nexto | YES via existing AutoLeague runner; improvement not guaranteed |
| Model inventory, safe archival copies, original backups | YES |
| Independent verified best gate | YES; first-goal eval caveats remain |
| GUI legible dark entry fields | YES code/style checks; Windows screenshot needed |
| Hide persistent CMD terminal | YES `.vbs` + pythonw; subprocesses hidden |
| Separate concurrent training/replay jobs | YES; bounded CPU/IO contention |
| Replay download parallel (1–3) + resume/skip + pause | YES simulated tests; actual Ballchasing authentication/network not tested here |
| Accurate API rank and date arguments | YES based on published Ballchasing API |
| Offline replay audit and dedup reports | YES (does NOT delete replay files) |
| Reports tab and process logs | YES |
| Windowed RocketSim camera, ball cam, car distance/height/FOV | YES optional pywebview, user must test on Windows; simplified cars |
| RLBot v4 export | Existing exporter retained, runtime RLBot match not validated |
| CUDA crash prevention | YES, auto CPU fallback (not CUDA acceleration) |

## Not completed — intentionally NOT represented as functional

| Requirement | Why not yet complete / acceptance criterion |
|---|---|
| Actual 1v2/1v3, 2v2/3v3, 2v3/3v2 team training | Current `native_nexto.Match` and state encoder hard-code one blue and one orange. Need variable-player state parity, role control, rewards and real tests. |
| Learn directly from human/Zen replays | Replay files lack verified native controller labels. Need decoded telemetry, control reconstruction confidence, split by players/seasons, offline holdout and game-eval gate. |
| Specialized bumps, aerial bumps, post-shot demos, flick/dribble/backboard learning | Requires reward + scenario curriculum and rollout telemetry; not a raw demo-count bonus. Finishing/tactical experiments stay isolated. |
| Training opponent strength automatically scaled up to two/three Nextos | Needs multi-car environment and tests, then gradual opponent curriculum. |
| GigaLearn 10x speed | Claimed experience collection speed is not validated on user's machine. Requires actor observation/action parity, checkpoint conversion and wall-clock comparison. |
| RLBot v5 support | Existing export targets v4; v5 API port and match test needed. |
| Rocket League native graphics / polished GigaLearn 3D graphics | Viewer is separate window with custom 3D canvas, not native RL graphics. |
| Guaranteed infinite/linear/exponential improvement | Impossible to promise. PPO can plateau/regress; verified-best gates and rollback are essential. |

## What not to delete

DO NOT DELETE `data/autoleague`, `data/afk_improved`, `data/native_nexto`, `data/finishing_lab`, `data/tactical_balance`, backups, `.pt` files, `.rar` archived weights, or any replay originals.

Potential cleanup after code audit: old `MECH_*` and `SF_*` launchers from abandoned labs (but keep their checkpoints until deduplicated/archived). `.part` temp files can only be cleaned when no jobs are running and after checking that no checkpoint/download recovery relies on them.

## Recommended next sequence

1. Extract patch, open GUI with `.vbs`, run preflight. Ensure `CPU` selected.
2. Resume the isolated 1v1 league. Run replay downloading **separately**; no replay-to-policy learning yet.
3. Evaluate new candidates using held-out general-play and multiple scenario seeds plus full-match tests; preserve original Cycle 9.
4. Build a true variable-player engine and test 1v2 before attempting RLHF-style replay distillation, bumps/demos and GigaLearn port.
