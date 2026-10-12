# Slater v0.3.8a — RocketSim fidelity gate (read-only)

## Why this release exists

Your v0.3.8 Windows reports showed:
- 7 offline tests passed.
- `v038_reference_audit01.json`: deployed V60 `nexto_obs.py` SHA exactly matches archived RLBotPack reference.
- `v038_same_state_obs01.json`: 20/20 same-RocketSim-state observations identical; max q/KV/logit delta 0, zero action disagreements.
- `v038_kickoff_audit01.json`: five source-level differences remain between real Nexto's kickoff logic and v037a's approximate RocketSim implementation.

**Crucial qualification:** v038 observation agreement is based on two kickoffs, both sides, five snapshots each. The legacy packet encoding was reconstructed from the *same simulated state*. Nothing has yet proven live RLBot state conversion equivalence.

**Do not promote u62.** No new training in v038a.

## Installation

Extract this ZIP into `E:\Downloads\Chat_GPT_AI` preserving paths. The scripts require the existing:
- `slater_nexto_kickoff_v037a.py` (v037a source must have the original SHA256 `a647823c227602f9c658a58a3e32b0d18a8dfe0dd1b144eadd93aaf9a856fd44`)
- `slater_fidelity_v038.py` and `slater_v038_reference/nexto_obs.py`
- All the previous Slater project modules and dependencies including RLGym v2, RocketSim, TorchScript and frozen checkpoints.

Run tests first:

```bat
cd /d E:\Downloads\Chat_GPT_AI
.venv\Scripts\python.exe -m pytest slater_v038a_tests -q
```

Expected local test count: **9 passed**. Tests check report provenance/guards and state comparisons but do not replace a real RocketSim run.

## 1. The most important new test: engine tick splitting

```bat
.venv\Scripts\python.exe slater_v038a_gate.py engine-gate --seed 20261011 --blocks 12 --out data/isolated/v038a_engine_gate01.json
```

Creates two independent RocketSim engines with the *same copied kickoff state* and feeds them identical physics-tick inputs. First engine processes eight ticks at once; second processes the same eight inputs via eight separate single-tick calls. Includes real scripted Nexto stage transitions during the first 96 physics ticks and lookup-table controls on the opposing car. Tests ball and car position/velocity, rotation, boost and boost-pad timer, goal events.

- `V038A_ENGINE_GATE True` is **only an enabling prerequisite** to investigate sub-tick scripted controller interruption safely.
- `V038A_ENGINE_GATE False` means **do not use single-tick RocketSim stepping** to alter training before understanding differences.
- If `RocketSimEngine.step` raises an exception on a single tick, report the exception (and do not train). No partial checkpoint can be produced.

This test **does not implement** sub-tick Nexto script interruption and **does not prove** RLBot live physics parity.

## 2. Stress observation parity beyond four transitions

```bat
.venv\Scripts\python.exe slater_v038a_gate.py stress-obs --seeds 8 --steps 32 --model data/rlbot_exports/V60/nexto-model.pt --out data/isolated/v038a_obs_stress01.json
```

Expected number of same-RocketSim-state comparisons: `8 * (32+1) * 2 = 528`. Compares reference Nexto `NextoObsBuilder` against our `TeamObserver` and evaluates V60 action choices. This is still an **on-simulator comparison only**, not a real RLBot packet test; canonical kickoff initializations and deterministic control schedules limit diversity.

## 3. Optional exploratory 3-way Nexto ablation

**Only do this after the two reports above.** This is deliberately still the *existing* v037a environment, and uses its **stock approximation**, not a verified clone of the RLBot stock Nexto controller. This avoids presenting a newer, unvalidated simulator rewrite as the real opponent.

```bat
.venv\Scripts\python.exe slater_v038a_gate.py ablation --from-checkpoint data/isolated/slater_v027_campaign01_u0060.pt --seeds 4 --episode-steps 600 --seed 20261019 --physics-gate data/isolated/v038a_engine_gate01.json --obs-gate data/isolated/v038a_obs_stress01.json --out data/isolated/v038a_stock_ablation01.json
```

The command will **refuse to run** if either supplied gate failed or its report type is unrecognized. It evaluates frozen Cycle9 and frozen u60 against the greedy, deterministic scripted and `nexto_stock_approx` modes. Reports 48 episodes (4 seeds * 2 team sides * 2 student policies * 3 opponent modes), with individual records.

Do **not** interpret a lack of difference between scripted and stock approximation as proof of stock parity: the v037a script typically overrides the sampled NN action in 1v1. Do not treat single-goal timeouts as match draws or wins. The purpose is checking whether there is any measurable effect in the current implementation.

## Send back

1. `data\isolated\v038a_engine_gate01.json`
2. `data\isolated\v038a_obs_stress01.json`
3. Optional `data\isolated\v038a_stock_ablation01.json`

If the first two are healthy, the **next implementation** should be an isolated, physics-tick-aware Nexto controller state machine that separately models kickoff pause, kickoff-taker selection, script clock, stochastic sampling, action carry-over, and mid-step interruption. Benchmark it head-to-head with the old controller using paired states, then evaluate long matches and real RLBot. *Only then* resume training.

## Safety

- No training, no checkpoint/model writes, no bot exports or installations.
- New JSON reports can only be created under `data/isolated`; overwrite prevented.
- Hash pinned v037a source; frozen Nexto and Cycle9 hashes are validated by existing `load_protected`.
- No download or internet access from this package.
- Locally unit-tested without RLGym/RocketSim; its actual engine gate and benchmarks must be executed on your Windows installation.
