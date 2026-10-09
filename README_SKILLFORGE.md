# Chat GPT AI — SkillForge v1: Real Wavedash Discovery

**Status:** New, physics-based *experimental* mechanics research kit. Not a trained mechanic, not a patched Nexto, and not yet a plug-in for 1v1 gameplay.

## What it fixes

The old Mechanics Lab classified a low flip followed by a quick landing and extra speed as a wavedash. It could report 11/12 even though it did not require the flip to make contact with the ground during the dodge. **Those results do not prove genuine wavedashes.**

This kit instead inspects actual RocketSim flags every **physics tick (120 Hz)**. It will only accept a maneuver when ALL of the following happen:

1. The car starts in midair, having jumped but retaining its dodge/flip.
2. `has_flipped` changes **False → True** while airborne at low height. This confirms a dodge was initiated.
3. The car lands during the dodge's early phase (**within 22 physics ticks**) rather than completing a normal aerial flip.
4. Ground/wheel contact stabilizes for **5 consecutive ticks** with the car substantially upright.
5. Forward speed increases by at least **105 uu/s**, ending above **350 uu/s**, with **no boost**.
6. Integrated angular movement does not exceed **280°**. A full flip, bad landing, or missing boost-free impulse fails.

These thresholds are a conservative experimental verifier, **not** an official Rocket League wavedash detection API. Review footage once a verified candidate exists.

## Installation (Windows)

Extract ZIP **into your existing** `E:\Downloads\Chat_GPT_AI` project. You should see `skillforge_core.py` beside `native_nexto.py`. Nothing replaces your current files. All new checkpoints, reports and demonstrations stay under `data\skillforge\`.

**Your strong policies are never loaded or modified by v1:**

- `data\native_nexto\best_10k.pt` — protected 10K foundation.
- `data\mechanics\kickoff\last.pt` — 7W/0L/5D experimental checkpoint.
- `data\native_nexto\last.pt` — whatever policy you've selected for viewing.
- `vendor\nexto\nexto-model.pt` — original Nexto.

### Recommended run order

**1. `SF_0_REAL_PREFLIGHT.bat`** — **run this first**, and send its complete output. Uses real RocketSim, checks that correct car physics and flip flags persist after state reset, that idle does *not* count as a wavedash, and that at least one test dodge is detected. **Do not run search if it fails.**

**2. `SF_1_SEARCH_REAL_WAVEDASH.bat`** — only after preflight success. Uses a derivative-free **cross-entropy method (CEM)** to search hundreds of short, exact controller sequences; includes independent held-out scenario testing. It uses only **pitch and jump**, never throttle, steer, boost, or handbrake. Saves `data\skillforge\wavedash\discovery.json` and progress. *It does NOT claim a skill unless the real physical detector verifies it.*

**3. `SF_2_INDEPENDENT_EVAL.bat`** — tests the winning macro on new, never-seen seeds, against no-input control. Reports real verified successes. No competitive Nexto win-rate claims.

**4. `SF_4_MORE_SEARCH.bat`** — optional expanded discovery with more scenarios and harder spawns; saves to **separate** `data\skillforge\wavedash_large\`.

**5. `SF_5_IMITATE_LARGE.bat`**, then **`SF_6_EVAL_LARGE.bat`** — ONLY if larger discovery reaches >=50% holdout success and yields >=8 separate successful training demonstrations. Behavior cloning trains a small **specialist** on tick-level physics and controller sequences, then tests it on independent RocketSim states. It is NOT installed in live matches automatically.

The short discovery uses 4 training situations, so `SF_3_TRAIN_IMITATION.bat` intentionally refuses to imitate the short run if fewer than 8 different genuine demonstrations exist. Use the expanded run instead.

### Why use CEM before PPO?

For a timed maneuver, PPO with sparse success from scratch often sees 0 successes and has no useful learning signal. CEM can directly optimize the small number of key decisions: **dodge delay, jump press time, directional input, flip-cancel delay and duration**. After we have verified examples, imitation can train a robust conditional specialist. PPO can come later, after this works reliably.

### Allowed controls / user's restrictions

- **Forward wavedash:** pitch (`W/S` equivalent) plus jump; roll, steer, throttle and boost are locked to 0.
- **Sideways wavedash:** yaw/roll plus jump (experimental parameterization, currently not given a dedicated launcher).
- **Airroll-only `Q/E`:** orientation practice only; roll alone cannot initiate a directional dodge, so we deliberately do not treat airroll-only as a valid wavedash.

A complete 360° flip is penalized and never accepted as success.

### Important limitations

1. **Real RocketSim is not installed in the packaging environment.** Unit tests use controlled mock physics, not live RocketSim. Your Windows preflight is required.
2. The forward wavedash **has not been discovered or trained yet**. This is the mechanism to search, verify and then learn it. If no valid maneuvers are found, it reports failure, not fictitious 11/12 success.
3. The trial imitator is not wired into Nexto matchmaking or self-play, because it hasn't passed physical or competitive acceptance tests. Your strong gameplay policy is unchanged.
4. Uses an exact 120Hz physics observer, rather than Nexto's original 8-tick action repeat. The specialist will need an adapter/gate for real Rocket League once its action timing is proven.
5. `SF_1` and `SF_4` refuse to overwrite earlier discovery artifacts; give a fresh `--out` or seed when repeating a run.

### Next build stages once a real wavedash exists

- **Recovery:** partial air control and landing facing a live ball/target, minimize time-to-ground and time-to-useful-motion, preserve speed.
- **Speed flip:** separate flip-cancel validation plus quickest path-to-ball, then real 50/50 evaluation.
- **Kickoffs:** first touch, ball location after 1–3 seconds, direct goal/own-goal risk, recovery position.
- **Aerial shooting:** airborne hit into goal, eventually moving balls and defended shots; not just proximity.
- **Wall-to-air dribbles:** wall pop, controlled airborne contacts matching velocity, directed scoring.
- **Double taps:** verify own first touch, *actual backboard bounce*, own second touch, goal, boost cost.
- **Flip resets:** show flip spent -> four-wheel contact on ball -> flip recharged midair -> use flip in shot.
- **Pinches:** prove car/ball/surface collision near same tick, high outgoing *netward* velocity, eventually goals.
- **Hierarchical selector:** only activate a specialist when the spawn and game context match its tested operating envelope. Compare against saved 10K/kickoff baselines on randomized full matches before promoting.

If preflight fails, **send the full terminal output**. Don't waste time training with bad spawn physics.

Source references for underlying engine physics:
- https://github.com/RLGym/rlgym/blob/main/rlgym/rocket_league/sim/rocketsim_engine.py
- https://rlgym.org/Rocket%20League/Configuration%20Objects/state_mutators/
- https://github.com/RLGym/rlgym-tools/blob/main/rlgym_tools/rocket_league/replays/convert.py
