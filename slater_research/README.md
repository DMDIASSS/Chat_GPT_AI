# Cycle 9 → advanced Rocket League training research add-on

**Scope:** Add-on code for `DMDIASSS/Chat_GPT_AI`, not a new replacement for its AutoLeague system. **No existing model is modified.** Implementations were syntax-checked and unit-tested for NumPy/PyTorch, but the RocketSim integration requires a Windows machine with compatible versions of the project's dependencies and real `.replay` files. No actual Cycle 9 model, replay, physics run or 100k TPS result was available in this execution environment.

## Key findings in your actual repository

- `auto_league.py:113` loads the **native Nexto TorchScript attention actor** from `vendor/nexto/nexto-model.pt`, then loads `checkpoint['actor']` into it. **Do not use** `chatgpt_ai/policy.py`'s `DiscreteFF` for Cycle 9.
- `nexto_teacher.py:88` is hardcoded to **two** players (`37 × 24` tokens). However, `afk_team_research.py:43-75` already implements a six-car `TeamObserver` with a **41 × 24** padded token layout, so don't throw that away. The underlying TorchScript actor must be smoke-tested at both widths.
- `afk_team_research.py:150` assumes token `kv[:,6]` is always the ball. This is true with 6 cars but not with 2 cars; the ball token is indexed by the number of players. `train_scenarios.MaskedValue` finds it by the `IS_BALL` feature instead.
- `replay_defense.py` currently handles 1v1/2v2 shot-like drills, not two-phase 1v1/2v2/3v3 **goal** scenarios. It already has important read-only fidelity gates. Keep those, extend alongside them.
- The source Cycle 9 checkpoint must have SHA `50f34d4a3723bc2849c97200e8e42969e0cc1d82328473b017505994be1966d2`. This hash was supplied by the project, **not recomputed here**. `checkpoint.py` recomputes it before loading.
- At 120Hz an 8-tick action repeat is 66.67ms. A 65ms flip-cancel cannot be represented reliably without finer control. Use a two-tick (=16.67ms) early-kickoff action scheduler or a 120Hz recording/expert macro; the current 90 discrete actions have limited analog precision.

## Definitions and reward mathematics

`geometry.py` implements approximate, explicit geometrical screens. `rewards_v2.py` exposes a RLGym v2 `RewardFunction` that must receive physics-rate calls (or be reweighted if decisions span multiple ticks). Parameters are experimental hypotheses; validate with ablations and benchmark matches.

### 1. Kickoff speedflip

On a genuine kickoff during first 2.1 seconds, with centre-of-car altitude `z` (uu), speed `s`, flip-init time `t_f` and opposite pitch control `p_t`:

```
r_kick = -0.010 [max(z-130,0)/100]^2
         + 0.003 I(on_ground and speed>=2200)
         + 0.40 I(first opposite-pitch cancellation at t-t_f<=0.065 s)
         + 1.00 I(ball touch)
```

**Do not hard-clamp the car's height:** doing so changes physics and may make the agent optimize an impossible trajectory. Track separate metrics: first-touch win rate, time-to-ball, maximum car-centre z, flip-cancel latency and boost consumed. If 130uu is not physically compatible with your best genuine kickoff, tune the threshold by rollout evidence rather than rewarding a broken speedflip.

The kickoff detector in `rewards_v2.py` reads controller vectors from `shared_info['controls']`. A default RLGym PPO eight-tick action parser alone doesn't supply these at 120Hz; instrument your transition loop. `action_precision.py` supplies a two-tick scheduler and a zero-initialized analog residual head. Train this head on verified 120Hz controls; it is not a magic speedflip script.

### 2. Demo approach, avoidance and hunting

Let opponent-relative position `r=p_opponent-p_self`, relative velocity `v=v_opponent-v_self`, and collision radius approximation `R=170`. Estimate impending collision as the smallest nonnegative root of:

```
(v·v)t² + 2(r·v)t + (r·r-R²) = 0
```

For opponent `||v_opponent||>2200` and first collision `0<=t<=0.55`, define danger `D=clip((0.55-t)/0.55,0,1)`. Penalize `0.015 D` per reward call while the trajectory remains dangerous, give `+0.12` when previously in danger but now safe and grounded, and reward a nearby newly demoed opponent `+2.0` *once*. Avoid rewarding mere supersonic aggression without actual demo outcomes. This is swept-sphere collision prediction, **not an engine raycast or exact hitbox contact**; upgrade to oriented bounding box sweeps and arena obstacle checks in production.

### 3. Flip resets, shadow defense and delayed aerial fakes

Candidate reset event: `not prev.has_flip AND curr.has_flip AND not curr.on_ground AND curr.ball_touches>0 AND distance(car,ball)<200`. Reward `+2.0`. Final verification must check contact points/wheel orientation because the public `Car` observation does not expose precise wheel-on-ball contact.

Ballistic goal-line screen for defending side `y_g ∈ {-5120,+5120}`:

```
t = (y_g-y_b)/v_y
x(t) = x_b + v_x*t
z(t) = z_b + v_z*t - 325*t²
```

Danger when `0<t<=2.5s` and horizontal/vertical goal aperture (892uu half-width, 642uu crossbar, ~92.75uu ball radius) is intersected. If a nearby airborne opponent still has a flip, expand the threat margin by 450uu. Let `q` be the closest point on the ball-to-goal line and `d=||car_xy-q_xy||`. Reward `+0.003 exp(-d²/(2*1300²)) clip(1.5/t,0,1)`, with a small `-0.002` exposure penalty if an aerial delay is possible and coverage <0.2. **This is a useful weak screen, not a predictive world model:** wall bounces, car-ball impact dynamics, flip timing and fake outcomes require a learned multi-hypothesis predictor trained on rollout data.

### 4. Multicar coordination

In your existing Nexto token scheme each query is `(1,32)`, each entity row is `(24)`, and attention mask is `(N)`. For 1v1, 2v2, 3v3 use respectively `N=37,39,41` after pad-to-6 token handling (actual entity count `34 boost pads +1 ball +number_of_players`; the `TeamObserver` always pads/reserves 41).

Use attention masks for absent players; encode each car's IS_SELF/IS_MATE/IS_OPP identity **from that player's perspective**. Pairwise collision with a teammate emits `-3.5` once at new `bump_victim_id` transition. Double-commit when two teammates are both inside 450uu and both closing on ball faster than 400uu/s emits `-4.0` once per entry into the double-commit region. Both are penalties **per participating learner**, not per global episode; pair-state deduplication prevents repeated charges while a situation persists.

You need to add at least a short temporal observation history / recurrence for decision-level tactical anticipation. Current single-frame attention cannot infer a delayed flip fake's actual planned time with certainty.

### 5. Possession, boost routing and recovery

The add-on currently uses light shaping: `+0.004(1-d/350)(1-v_rel/650)` if ball within 350uu, relative speed <650uu/s, and height within 100..350uu. Near-ball control rewards must be **gated by context** (not on-target shots). A newly collected small boost pad is rewarded `+0.08` if the collector is within 190uu of the pad, and late corner exposure while the own goal is threatened costs `-0.004` per call. A speed/recovery reward of up to `+0.002` per tick and forward-alignment reward of up to `+0.0015` are present. Improve these into **potential-based rewards** to reduce reward farming:

```
r_shaped = gamma*Phi(next_state) - Phi(current_state)
```

Recommended potentials: defensive expected-goals conceded, time-to-intercept, distance-to-safe-pad-route, number of opponents eliminated by a backboard clear, and expected possession value (EPV). Do not pay a standing bonus for simply driving supersonic when doing so exposes the net.

## Extraction / two-phase architecture

### Clip exporter

The `extract.py` tool iterates real GC3/SSL `.replay` files; `rlgym-tools` provides replay parse and RLGym-state conversion. It accepts only goal-labelled hits, 2/4/6-car rosters, stable car IDs, sufficient ≥10s unbroken pre-goal time, finite action vectors, and no source overwrite. Each clip stores state snapshots and inferred controls in compressed `.npz`, split by replay SHA across 80% train, 10% validation, 10% test.

**Critical replay limitations:** controller pitch/yaw/roll are estimated, the sim itself has small physics mismatches, and full deterministic reproduction from replay data alone is impossible. For high-fidelity training add paired 120Hz controller traces from custom games/TAS with verified action semantics, synchronized to observed states. Never label inferred controls as ground truth.

### Phase 1 — shooter

Load snapshot at `goal_time - 0.5,2,4,8,12 seconds` (curriculum). Learner controls scoring car; nonlearners are pose-aligned replay ghosts. After each 8-tick RocketSim step compare learner car position `p`, velocity `v`, rotation `R` against replay target:

```
score = 0.045*exp[-(||p-p*||/2300)^2/0.16
                  -(||v-v*||/2300)^2/0.64
                  -(||R-R*||F/3)^2/0.25]
        + 0.4*I(ball_touch) + 10*I(goal)
```

Strong advice: add exact 120Hz control capture, train supervised behavioural cloning first (cross-entropy on native 90 actions + continuous residual control loss), **then** run PPO. Pose cloning alone can reward matching trajectories while never learning the causal controller skill. Track finish-distance and intermediate touch-timing error on held-out replays.

### Phase 2 — defender

Same start physics; the shooter follows the original replay ghost path; the defending team is controlled by the learner policy (1v1 one defender, 2v2 both defenders, 3v3 all three or select primary challenger + last man). Reward `+1` for a reversal clear after ball contact, `-10` conceding, `+10` scoring, plus a negligible time cost. **No large reward for reaching horizon without a goal**, because replay counterfactual can be non-threatening. The reference defender trainer calls `counterfactual_goal_check()` and skips clips failing the gate; before any high-throughput training, verify reproduces a scorer-side goal from replay-inferred defender controls and keeps the ball near reference position. Manually inspect visual fidelity too.

Kinematic replay ghosts **teleport to reference physics poses each decision**. This lets defenders counter a repeatable threat, but creates potentially unphysical contacts when the defender changes the trajectory. Production progression:

1. Reference ghosts for simple imitation diagnostics;
2. All cars using inferred or recorded controller scripts, physically simulated and filtered by replay-fidelity gates;
3. A frozen learned shooter policy (trajectory imitation / diffusion / BC) that interacts physically;
4. Adaptive challenger policies from the league, finally human GC2 custom-game evaluation.

## Running on Windows in your existing project

Copy the `slater_research/` directory to the **repository root**, next to `auto_league.py`, `replay_defense.py`, and `nexto_teacher.py`. Activate the project's existing Windows venv. Back up checkpoints and stop other PPO/AutoLeague runs before training candidates.

```powershell
cd E:\Downloads\Chat_GPT_AI
.\.venv\Scripts\python.exe -m pip install "rlgym[rl-sim]" "rlgym-tools>=2.6.0" pyarrow pandas pytest
.\.venv\Scripts\python.exe -m pytest slater_research\tests -q

# Physics-only benchmark before neural inference, ONE arena first.
.\.venv\Scripts\python.exe -m slater_research.bench --arenas 1 --seconds 10 --players 2 --ticks 8

# Extract 10–15s goal clips from local replay collection.
.\.venv\Scripts\python.exe -m slater_research.extract --replays data\replays --out data\replay_scenarios --lead 12

# These are research smoke experiments, not auto-promotions:
.\.venv\Scripts\python.exe -m slater_research.train_scenarios --clips data\replay_scenarios --phase shooter --episodes 12 --epochs 2 --out data\isolated\cycle9_shooter_trial.pt
.\.venv\Scripts\python.exe -m slater_research.train_scenarios --clips data\replay_scenarios --phase defender --episodes 12 --epochs 2 --out data\isolated\cycle9_defender_trial.pt
```

Both trainer commands currently initialize **independent** candidates from Cycle 9; the defender command does not automatically continue from the shooter file. To implement sequential transfer, add a verified candidate loader, retain the original teacher, and gate each transfer. If no clips pass the parser or fidelity tests, **stop** and fix source data; do not loosen thresholds to fabricate progress.

For replay classification/evaluation prefer the existing repository entrypoints `REPLAY_1_EXTRACT.bat`, `REPLAY_2_FIDELITY.bat`, `README_REPLAY_DEFENSE.txt`, `AUTO_0_PREFLIGHT.bat`, `INDEPENDENT_BENCHMARK.bat`, `afk_team_research.py` and `auto_league.py` rather than replacing their battle-proven logic. The reference trainer is single-process and slow by design; it does NOT implement the final concurrent native C++ worker queue.

## Throughput: 32–64 RocketSim arenas, PyTorch, RLViser

1. Pin versions of RocketSim C++, RocketSim Python bindings, RLGym 2.x, and Torch in a lockfile; record Git commit hashes and run integration tests. Do not use old `rlgym-compat` (`AechPro/rlgym-compat` URL was 404 at review).
2. Build **Release x64 /O2** with a supported MSVC toolchain; initialize collision meshes **once** before creating arenas. Give each worker its own arena and random seed; do not share one mutable Bullet world across threads. `rocketsim_bench.cpp` is a physics-only 32/64-thread benchmark (must link to RocketSim in your existing CMake project).
3. Start with 8/16/32 arenas and scale to 64 only while throughput still increases. Measure `physics_ticks_per_sec = sum(arena_ticks)/wall_time` separately from `policy_decisions_per_sec = physics_ticks/(action_repeat)`.
4. In production native trainer, share **struct-of-arrays** observation/action/reward buffers between physics workers and a batched inference server (TorchScript/ONNX or LibTorch). GPU should receive inference batches ≥256 where latency permits. Avoid per-worker Python/Torch models and CPU→GPU copies per car per frame.
5. Train PPO asynchronously *between rollout boundaries*: 32 arenas × 8192 decisions means 262,144 actor samples, but only use a batch that fits RAM/GPU. Actor updates must be versioned; use policy-lag correction or discard overly stale samples. On-policy PPO should not silently mix data from multiple generations.
6. **RLViser** supports a protocol through `RLViserRenderer`/`rlviser-py`; it is **not JSON sent over UDP**. Launch the visualizer and forward **one evaluation arena** sampled at 10–15Hz to the default UDP port 45243 through `viewer.VisualizerTap`. Do not stream every arena; that destroys benchmarking validity.
7. The upstream RocketSim README describes >100k *physics ticks/s* on a particular CPU/version for an isolated single-thread benchmark. This is **not proof** that a complete 32–64 arena PPO stack will reach 100k policy decisions/s. Profile physics, encoders, inference queue wait, training, and IPC separately before assigning performance targets.

## Candidate preservation and promotion

The provided `checkpoint.cycle9_pair(root)` performs byte-for-byte SHA-256 verification, loads the native Nexto TorchScript reference weights twice, freezes the original, and returns independent learner/teacher modules.

Use a restrained start: actor LR `3e-6`, critic LR `2e-4`, PPO clip `0.15`, entropy weight `0.005`, teacher KL temperature `1.5`, teacher loss coefficient `0.08` (sweep 0.05, 0.1, 0.2); gradient clipping norm `0.5`. These are starting points, not tuned optimums. Interleave training from the existing AutoLeague and recovery state distribution, not just replay clips. Proposed curriculum mix after specialist warmup: **35% diverse 1v1 self-play, 20% replay scenarios, 15% kickoff/recovery, 15% 2v2, 10% 3v3, 5% goal-line/demo adversity**. Sample curriculum by per-skill failure, not a fixed ratio forever.

Suggested promotion gates, all on held-out seeded matches, side-swapped and using untouched source:

| Gate | Proposed acceptance criterion |
|---|---|
| Model stability | finite losses, no SHA mismatch, no corrupted or overwritten references |
| Retained mechanics | Cycle 9 win/tie-adjusted head-to-head ≥50% and no substantial flick/aerial-50 regression |
| Ground kickoff | beats GC2 benchmark or trusted kickoff specialist ≥50% first touches on each spawn; valid early cancel, no excessive altitude |
| Defensive scenarios | ≥20% relative conceded-goal reduction vs Cycle 9 on held-out, **counterfactually threatening** clips |
| Demo evasion | improves survived high-speed attack rate without raising conceded-goal rate |
| Team behavior | teammate collision and double-commit event rate ↓≥30% vs Cycle 9, no degraded 2v2/3v3 win rate |
| Generalization | exceeds Cycle 9 and Nexto on ≥3 opponent classes in full matches, not just first-goal episodes |

These are **research acceptance targets**, not current measured achievements. Never promote based on imitation loss alone. Compare Slater directly in local offline matches only if you have a legal reproducible Slater opponent; defeating 3–5 copies of Nexto is an especially distribution-dependent exhibition and does not automatically imply GC/SSL human equivalence.

## Sources (version-check before production)

- Your repo: https://github.com/DMDIASSS/Chat_GPT_AI
- Nexto/Necto: https://github.com/Rolv-Arild/Necto
- RocketSim C++: https://github.com/ZealanL/RocketSim
- RLGym v2: https://github.com/RLGym/rlgym
- RLGym tools replay conversion: https://github.com/RLGym/rlgym-tools
- RLViser: https://github.com/VirxEC/rlviser
- RLBot v4: https://github.com/RLBot/RLBot

**Licensing/usage:** Nexto-derived original code/weights carry restrictions; consult the upstream Necto/Nexto licenses and follow attribution/noncommercial obligations. RocketSim should be used for offline simulation and permitted RLBot/custom-game testing, not cheating in ranked online matches.
