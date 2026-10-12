# Slater Research v0.1.9 — defender action reachability (read-only)

**Requires:** Slater Research through v0.1.8, `shot_catalog_v016.json`, and v0.1.2 goal clips. Do not install this patch on earlier versions. This is a small incremental patch with two Python modules plus this guide.

v0.1.8 passed 12/12 baseline consistency tests on Windows. v0.1.7's static four-action counterfactuals changed zero outcomes in 48 trials. That result does **not** show that the shots are unsavable: the probes did not steer toward the ball.

This patch runs 12 alternative defender-control policies for each training-split clip:

- neutral, brake, forward boost
- turning left/right with throttle, turning left/right with boost
- powerslide left/right, jump+boost
- two feedback pursuit controllers using only **current simulated car and ball state**, not future replay frames

The original replay control is checked first. Each rollout uses its **own fresh RocketSim arena**. The attacker keeps the original replay controls, the defender is freely simulated, and the previously verified 0.5- or 1-second window plus goal tail is used.

The report records whether the attacker goal is observed by the deadline, whether the defender touched the ball, and how much the final ball position changed. Crucially, `no_goal_by_deadline` **is not a save**. Defender touches are not proof of a useful intervention. All comparisons are *exploratory*; the goalkeeping environment and reward model still need validation before training or model promotion.

## Install

Unzip this patch to the project root: `E:\Downloads\Chat_GPT_AI`. Merge the `slater_research` directory. Keep your original v0.1.8 files; this patch does not overwrite those.

Run from **Windows CMD** (no `#` comment lines):

```bat
cd /d E:\Downloads\Chat_GPT_AI
.venv\Scripts\python.exe -m pytest slater_research\tests -q
.venv\Scripts\python.exe -m slater_research.defender_reachability --clips data\replay_scenarios_smoke_v012 --catalog data\replay_scenarios_smoke_v012\shot_catalog_v016.json --limit 12 --out data\replay_scenarios_smoke_v012\defender_reachability_v019_12.json
```

Offline synthetic suite should show **59 passed** if v0.1.8 is installed and no additional tests were added. The physics results are **not** known until run on the user's actual Windows RocketSim installation.

If the destination report (or `.partial` file) already exists, choose a **new** filename. The script does not overwrite any existing report and never starts training or loads/modifies the saved Cycle 9 checkpoint.

Send `SUMMARY` and `defender_reachability_v019_12.json` before any PPO stage.
