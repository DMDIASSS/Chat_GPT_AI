# SLATER v0.4.0 — Multi-rival continuation of protected V60

**This is an experimental PPO TRAINING package, not a promise that a stronger bot was obtained.**
The original V60, OG Champion, Cycle9 and official Nexto models are never overwritten.

## Why this version

The previous v037a trainer has two training weaknesses:

1. Its PPO collector starts a fresh episode at every rollout/update boundary, discarding potentially valuable partial episodes.
2. It treats a time-limit truncation like a real goal terminal and loses the value bootstrap.

This version fixes both, preserves the user-reported pressure-heavy V60 playstyle via a **SHA-pinned V60 KL teacher**, and gives a new learner four non-trainable opponents:

- `nexto_script`: v037a's 168-tick scripted kickoff + Nexto greedy after kickoff (batched approximation)
- `nexto_greedy`: raw Nexto NN greedy
- `cycle9`: original frozen Cycle9
- `frozen_u60`: protected original V60 playing against the candidate (self-play **against a frozen reference**, not concurrent learning)

For faster rollout, the old scripted Nexto mode skips its redundant NN forward pass only when script controls completely override the forward-pass output. Otherwise it calls the unchanged v037a behavior.

It **does not** consume TAS/replay demonstrations (these are unverified as paired state/action labels). It **does not** use the slower v038b tick-aware opponent. The earlier v038c live Nexto controller-scheduling validation does not prove the batched script is exactly stock Nexto: this is a speed-versus-fidelity choice.

## Installation

Unzip into `E:\Downloads\Chat_GPT_AI` preserving folder structure. Prerequisites:

- Prior installed Slater v037a scripts and source modules.
- Original `vendor\nexto\nexto-model.pt`.
- Original `data\isolated\slater_v027_campaign01_u0060.pt` with SHA256 `5f9bf7cb6a0bcfb3bcf801ade021b11499181d80fb36b0cfad827e2648936c74`.
- Working Windows `.venv` with Torch, NumPy, RLGym/RocketSim, and your existing Nexto integrations.

Run offline tests:

```bat
cd /d E:\Downloads\Chat_GPT_AI
.venv\Scripts\python.exe -m pytest slater_v040_tests -q
```

Expected: **20 passed**. Tests include a synthetic end-to-end PPO update with checkpoint file serialization. Actual RocketSim/Nexto integration still requires testing on your PC.

## Step A: conservative integration smoke

First run a small training experiment that rotates between both of the most important rivals. The run prefix is new and cannot already exist.

```bat
.venv\Scripts\python.exe slater_v040_multirival.py --from-checkpoint data/isolated/slater_v027_campaign01_u0060.pt --run v040_multirival_smoke01 --modes nexto_script,frozen_u60 --eval-modes nexto_script,frozen_u60 --updates 2 --rollout-steps 512 --max-episode-steps 150 --checkpoint-every 2 --eval-seeds 1 --eval-steps 300 --epochs 2 --minibatch 128 --actor-lr 0.000002 --teacher-weight 0.35 --seed 20261011
```

Expected outputs (if the full Windows RocketSim training succeeds):

- `data\isolated\v040_multirival_smoke01_u0062.pt`
- `data\isolated\v040_multirival_smoke01_u0062.json`

The `V040_UPDATE` logs should show both opponent names in `rivals_finished` over the two updates. Any benchmark outcome on 1 seed is **not** evidence of an improvement.

## Step B: bounded multi-rival campaign (only after smoke passes)

```bat
.venv\Scripts\python.exe slater_v040_multirival.py --from-checkpoint data/isolated/slater_v027_campaign01_u0060.pt --run v040_multirival_campaign01 --updates 200 --rollout-steps 1024 --max-episode-steps 300 --checkpoint-every 10 --eval-seeds 2 --eval-steps 600 --epochs 2 --minibatch 128 --actor-lr 0.000002 --critic-lr 0.0001 --teacher-weight 0.35 --max-train-seconds 600 --seed 20261014
```

`--max-train-seconds 600` is a **training-loop check after each completed PPO update**, not a hard wall-clock deadline. Initial baseline evaluation, checkpoint evaluations, and the current update may push the total elapsed time beyond 600 seconds. Never interrupt while saving a checkpoint. To collect more decisions, use a NEW run name and point `--from-checkpoint` to the last candidate `.pt` produced; its V60 KL teacher remains the **same original SHA-pinned u60**.

The default `--modes` covers all four opponents. `--eval-modes` defaults to `nexto_script,frozen_u60` to keep periodic evaluations reasonably fast. Results are scored separately for candidate and original V60, on the same seed/side combos. **Timeouts are tracked separately, not treated as wins or draws.**

### Longer campaign

If there is a proven benefit and adequate measured throughput, a *separate* later run can increase budget (for example 300 updates × 4096 decisions ≈1.23 million simulated student decisions). Do not choose a budget based on speculative timing. A requested `v039_rollout_speed01.json` was not available in the ChatGPT session when this package was authored.

## Windows results to return

1. Tests: number passed (or full failure traceback).
2. `V040_BASELINE`, `V040_UPDATE`, `V040_EVAL`, `V040_SAVED` console output.
3. The new `data\isolated\v040_multirival_smoke01_u0062.json` or the relevant campaign report.
4. Actual `v039_rollout_speed01.json`, if it exists on your PC.
5. If a long real RLBot match is possible, scorelines from V60 vs unmodified stock Nexto, both sides, and from the new candidate once exported.

## Protection/integrity

- The independent fixed original-V60 anchor must match its known SHA256 and model architecture; it is not the same storage as the candidate.
- Cycle9, vendor Nexto, initial source checkpoint and original V60 are hashed and checked before writing a new result.
- A run prefix is create-only; repeated invocations must use a new run name.
- Saves contain `actor`, `critic`, optimizer states, version and provenance. The outer checkpoint stage remains `slater_v037` for compatibility with the already-existing protected v037a loader; `meta.origin_stage='slater_v040'` marks provenance.
- No existing model, export, bot configuration, or TAS file is modified.
- This trainer only trains in simulator 1v1, with 90 discrete Nexto actions, no continuous aerial/flip reset head, no verified live-physics parity.
- The new student must **beat protected original V60 under paired held-out evaluations and real RLBot matches** before promotion; no automatic promotion exists.

## Open source references

- https://github.com/VirxEC/rlgymppo_rs (multi-threaded PPO and self-play ideas)
- https://github.com/VirxEC/rlbot-rocketsim (live-vs-sim state mismatch work)
- https://github.com/VirxEC/replay-to-rocketsim (future replay demonstrations, reconstructed aerial controls are approximate)
- https://github.com/NicEastvillage/Rlgym-v2-to-rlbot-v5 (inference observation/action synchronization)
- https://github.com/NicEastvillage/AutoLeague3 (later full-match evaluation)
