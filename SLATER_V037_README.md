# Slater v0.3.7 — Scripted Nexto in RocketSim + conditional TAS preparation

**Status:** runnable Windows experiment. Python unit tests passed offline; **real RocketSim/PPO integration has NOT been run on the user's Windows project**, because `rlgym`, `afk_team_research`, and protected checkpoints are not available in this container. No model has been trained or deployed by this package. Do not claim RocketSim scripted Nexto is exactly RLBot stock Nexto.

## Files

- `slater_nexto_kickoff_v037.py`: opponent control adapter, 1v1 mini-benchmark, protected u60 PPO continuation.
- `slater_tas_phases_v037.py`: raw TAS phase segmentation, no axis/button guesswork.
- `data/isolated/v037_tas_phase_catalog.json`: precomputed *unverified* phase metadata for 6 uploaded examples, **324 heuristic segments / 6,580 frames**.
- `slater_v037_tests`: 10 offline tests, including an instrumented fake physics-engine check.

## Exact scripted controller stages

Source: `RLBotPack-master/RLBotPack/Necto/Nexto/bot.py` provided by the user.
Control order: `[throttle, steer, pitch, yaw, roll, jump, boost, handbrake]`.

| Frame range (0-based) | Ticks | Controls |
|---|---:|---|
| [0,44) | 44 | throttle=1, boost=1 |
| [44,60) | 16 | steer=-1, throttle=1, boost=1 |
| [60,68) | 8 | jump=1, throttle=1, boost=1 |
| [68,72) | 4 | throttle=1, boost=1 |
| [72,76) | 4 | jump=1, pitch=-.7, yaw=.8, throttle=1, boost=1 |
| [76,128) | 52 | pitch=1, throttle=1, boost=1 |
| [128,168) | 40 | pitch=.5, roll=1, throttle=1, boost=0 |

Scripted controls are supplied to RocketSim **per physics tick inside each 8-tick student action**. Critical transitions at tick 44/60 etc are not rounded to the RL policy's 8-tick grid. The script is gated on ball position y~=0 (as in the RLBot source), capped at tick 168 for each kickoff episode; neural actions resume after the predicate fails. This approximates the `is_kickoff_pause` test and applies the kickoff script even to blue/orange without adding coordinate mirroring (same as the public controller). The NN still runs at 8-tick intervals and `previous_action` records the last applied script input for the next observation. It is NOT an exact replication of RLBot packet timing, `is_kickoff_pause` state, or observation normalization; no mid-8-tick ball-touch cutover.

`nexto_stock_approx` is an internal optional mode: the public Nexto switches to beta=0.5 stochastic sampling while kickoff pause holds; we approximate that condition with ball_y==0. The trained modes default to **nexto_script** and **nexto_greedy** without sampling. This separates scripted mechanics from random action selection.

## Run on Windows (CMD)

Extract ZIP into `E:\Downloads\Chat_GPT_AI` **without overwriting any existing scripts or checkpoints**.

```
cd /d E:\Downloads\Chat_GPT_AI
.venv\Scripts\python.exe -m pytest slater_v037_tests -q
.venv\Scripts\python.exe slater_nexto_kickoff_v037.py audit --out data/isolated/v037_script_audit01.json
```

### Gate A: first test scripted-vs-greedy Nexto before training

```
.venv\Scripts\python.exe slater_nexto_kickoff_v037.py benchmark --from-checkpoint data/isolated/slater_v027_campaign01_u0060.pt --seeds 2 --episode-steps 180 --seed 20261012 --out data/isolated/v037_script_kickoff_smoke01.json
```

This performs `2 seeds × 2 sides × 2 Nexto modes × 2 student policies` = **16 kickoff episodes**, 12-second limit apiece, NOT full matches. Compare `V037_BENCHMARK` summaries. The tool refuses the benchmark if **zero scripted actions** were applied, a sign the gate is broken. New seed values do not guarantee new kickoff layouts.

### Gate B: optional expanded comparison

```
.venv\Scripts\python.exe slater_nexto_kickoff_v037.py benchmark --from-checkpoint data/isolated/slater_v027_campaign01_u0060.pt --seeds 8 --episode-steps 450 --seed 20601012 --out data/isolated/v037_script_kickoff_heldout01.json
```

Do not interpret any simulated 12- or 30-second win rate as a full-match RLBot metric. If the two modes show no difference, or rollout crashes, do not train yet; send the report/error.

### Gate C: **explicit** small training continuation from u60 (not Cycle9)

Only after Gate A works:

```
.venv\Scripts\python.exe slater_nexto_kickoff_v037.py train --from-checkpoint data/isolated/slater_v027_campaign01_u0060.pt --updates 2 --rollout-steps 512 --max-episode-steps 300 --checkpoint-every 2 --eval-seeds 2 --eval-steps 180 --seed 20261012 --run v037_script_nexto_smoke01
```

A new experimental policy is written to e.g. `data\isolated\v037_script_nexto_smoke01_u0062.pt` with an accompanying `.json`. No originals changed. 2 PPO updates are a smoke test, NOT enough to establish learning. The training mix alternates scripted and pure-NN Nexto from the same vendor SHA-pinned weights. Optionally add `--mix-cycle9` for original Cycle9 episodes. Source V60 actor, critic, and Adam optimizers are loaded; frozen **source u60** is the KL teacher rather than original Cycle9. The unchanged Nexto and original Cycle9 are integrity-checked before every checkpoint. No final promotion or export is done.

If Gate A and C both succeed, then consider a unique follow-up run with more updates and more held-out seeds. Do NOT overwrite existing run names. Preserve the existing V60 RLBot model as benchmark champion until a *new* checkpoint wins external tests.

## TAS — from fixed sequences to adaptive skills

The provided `.data` files have a verified binary frame layout but UNVERIFIED axis/button meanings and 128-byte initial-state semantics. v037 produces *candidate phase boundaries* from button-bit changes, analog discontinuities and max-duration caps. A filename label, e.g. `flip_reset_demo`, is only a guess about the **whole recording**. Individual segments have no reliable names yet. The provided `v037_tas_phase_catalog.json` is analysis only.

To create new TAS phase metadata, put the source `.data` files together in a folder such as `E:\TAS_Examples` and run:

```
.venv\Scripts\python.exe slater_tas_phases_v037.py --input-dir "E:\TAS_Examples" --out data/isolated/v037_tas_phases_new01.json
```

### Next (not yet implemented)

1. Obtain or verify the **TAS plugin's source/schema** for button masks and 7 floating analog values, including gamepad trigger axes, and decode the saved starting-state trailer. No assumption that it was KBM or controller can be proven from raw analogs alone.
2. Reconstruct identical starting car/ball physics. Re-run source TAS in RocketSim/RLBot; compare car pose/velocity, touches and landing. Reject a recording whose physics fails.
3. Label *verified* phases as approach, takeoff, dodge, contact and recovery, including reusable subskills. Train a condition predictor for the *entry state* of each skill (location, velocity, rotation, ball path).
4. Learn a state-conditioned **continuous** skill controller: action = demonstrated prior + clipped feedback residual based on target pose, velocity and opponent threat. Train with perturbed initial poses, mirrored spawns, boost variation and latency. 90 discrete Nexto actions are insufficient to reproduce all analog TAS values.
5. Use a high-level RL selector to plan an approach, choose/mix skills, check readiness, interrupt a failed skill, and recover. Reward ball touches and final match outcomes, not just imitation accuracy. Check mechanical accuracy against holdout setups and RLBot before deployment.

TAS alone does not supply tactics, opponent response data, full synchronized observations or proof of human competitive skill. **No v037 TAS policy is trained or deployed.**

## Report back

Send the `v037_script_kickoff_smoke01.json` and any errors first; they determine whether scripted Nexto is functioning in *your* RocketSim version. If you run PPO, send the candidate `.json` only at first; don't replace V60 before external evaluation.
