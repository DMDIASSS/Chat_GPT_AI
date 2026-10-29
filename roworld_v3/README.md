# RoWorld 3.1 — experimental independent observation agent

**Play now:** paste the complete [`RoWorld_V3.lua`](RoWorld_V3.lua) into JJSploit,
execute in a multiplayer RoWorld match, then press **Start bot**. Confirm **3.1.0**
in the panel. Extract the ZIP anywhere. No Python, model download or training is
required for the built-in policy. Re-execution stops the previous v2/v3 instance.
The friends toggle, F6, match-report button and ordinary multiplayer connection
are retained. The optional local loader expects `RoWorld_V3.lua` directly in your
JJSploit workspace, usually
`C:\Users\almas\AppData\Roaming\jjsploit\workspace`.

This is a **separate rewrite of the decision core**, inspired by
[djmango/openfront-ai](https://github.com/djmango/openfront-ai/tree/474536340480659c53d9a9e497b08fa1fefb9589).
It does not run the old `Policy`, `Strategy` or `Planner`. The tested connection,
protocol, public-state mirror and pure rule helpers are retained in `shared/`.
Your existing v2.4 files remain available and are not overwritten by this ZIP.

There are two policy modes:

- **Built-in policy:** immediately playable, chooses among scored, legal RoWorld
  proposals. This is the default download, without neural weights.
- **Learned residual policy:** an optional 9,250-parameter actor–critic re-ranks
  those same proposals. PPO training, self-play workers, checkpoint resume,
  evaluation and a standalone Luau export are included. There is **no trained
  multiplayer champion bundled**. OpenFront checkpoints are incompatible.

## New in 3.1: tactical donations and opportunistic treaty breaks

- Ordinary treaty allies can receive a calculated troop grant for an observed
  attack or a nearby counter against an overcommitted attacker. The target must
  be hostile to both participants; formal alliances, permanent teams, protected
  friends and pending peace arrangements exclude the operation. We cannot force
  another player's actions or guarantee they spend a grant as intended.
- A grant must close the estimated funding gap, fit recipient capacity, and be
  at most 8% of our bank. It retains at least 75% of our bank, 42% of troop capacity
  and twice observed incoming armies. A modest invasion can permit tactical aid;
  one above 20% of our bank blocks it. Strong target coalitions, expiring treaties,
  marked traitors and a gift creating a dominant recipient are rejected.
- The 45-second support cooldown remains. A recipient/target pair cannot get
  another tactical gift without new target land losses or a larger observed
  attack; the bounded project ledger resets on a new match. Existing limited
  defensive friend/teammate support is retained.
- A weak wealthy bordering treaty ally may be considered for betrayal when the
  estimated capture value outweighs army, treaty and trade costs. Teammates and
  protected Roblox friends are excluded. New wars, invasions, fortified fronts,
  nearby coalition strength, retaliatory silos and nearby coalition warships can
  veto the plan. Every break causes RoWorld's **300-tick / 30-second half-defense
  penalty**, including breaks against marked traitors.
- It issues the break first, waits for a real alliance-state change, then
  rechecks the opportunity before proposing an attack. At least 80% of the home
  bank and 42% of capacity are reserved during the plan/penalty. A 35-second plan
  deadline and three-minute break cooldown prevent repeated speculative breaks.
- Relationship, funding and risk checks run again immediately before sending.
  Reports show the intended support target, project progress, betrayal assessment
  and outcome. Construction diagnostics now show availability, legal/safe site
  counts and rejected investment reasons, plus owned structure locations.

These are conservative public-state estimates, not proof of hidden intent or a
guaranteed profit. No training is required to use the new built-in decisions.
Previously exported learned scripts must be rebuilt with the updated code to gain
these functions. For ongoing training after updating, use a new run directory
with `--init` from the previous JSON, as described below.

## What was adapted

The upstream project reports that its 38.6M-parameter final policy cleared easy
tiers but struggled when multiple nations shared a map. It supplies useful
engineering ideas, not a model guaranteed to beat players. This implementation
borrows the separation of spatial context from exact facts, action masking,
action-result context, real-engine training and evaluation of actual outcomes.
No upstream code or weights are bundled. The pinned source has no top-level
license file; this is an independent implementation of those ideas.

| Topic | RoWorld v3 handling |
|---|---|
| Map | Actual `W`, `H`, `k_lin`, terrain bytes, impassable cells, coast and connected water bodies. Local 5×5 and coarse 4×4 current ownership/passability/fallout samples. Candidate destinations are precise tiles. |
| Exact facts | Public player banks/capacity/gold/income, player kind, team IDs, formal alliance graph, pending requests/expiry, attacks, unit health/routes, missile flights and reload stamps. These are read directly. |
| Learned input | 204 context values and 48 values per candidate: globals, map samples, eight recent command/result values, action identity, target relationships, allied army strength, costs, quantities and risk. Full raw public rows are also in reports. |
| Model | Small shared candidate scorer and value head, with the built-in score as a prior. No spatial autoencoder or LSTM; no learned reconstruction of diplomacy. It can only choose among the generated proposals. |
| Troops | Real global bank/capacity, approximate recruitment from RoWorld's formula, existing armies subtracted from reinforcement. Game minimum is 1% of home troops. |
| Counters | Reckless live attacker: its army against us exceeds 1.5× its home bank. Proportional funding retains at least `ceil(0.42 × capacity)`, strategic reserves and 1.5× incoming troops. Combat can still reduce the bank below that floor. |
| Countries/tribes/humans | Separate features and priorities; country treasury and useful assets affect targets. Private country grace/jitter/difficulty are not claimed as visible or as immunity. |
| Diplomacy | Actual expiry/renewal window, observed betrayals and uncertain display-name profiles, useful human/friend partnerships, permanent teams, pending-peace stand-down and limited allied troop aid. Strong treaty allies increase reserves without an automatic declaration of war. |
| Buildings | Current costs/placement/upgrade destination, interior setback, fallout/strike avoidance, concentration cost, productive investment and a rolling three-post cap. |
| Navy | Legal connected-water transports, useful water crossings, redundant neighboring landings excluded, open landing room and nearby human strength considered, one expedition at sea, 10% neutral survival expedition under overwhelming land attack, own warship construction/interception, damaged-ship repair respected. |
| Missiles | Atom/hydrogen/MIRV, real cost escalation/reloads, hostile SAM trajectories, friendly/friend blast protection, valuable clusters, duplicate-strike avoidance and flight alerts. MIRV warheads are not assumed SAM-immune. |
| Omitted OpenFront actions | No invented embargo, gold donation, unit deletion or boat-cancellation protocol. Other RoWorld arsenal types, paid unlocks and reinforce are not automated. |

Proposals first satisfy current game checks and explicit reserve/friendship/risk
filters. Those safety filters are distinct from legality; training is deliberately
restricted to this candidate space. A final adapter check rejects changed routes,
ownership, allies, bank, prices or weapon readiness before using a normal order.
An order being sent is not proof the server applied it.

Decisions use the same **10-tick / one-game-second cadence** in training and
live play. The connection/UI keep polling between decisions. This avoids feeding
a model trained on one-second outcomes ten-times-smaller live outcome deltas.
Phase changes and elimination are observed immediately; reports expose observation
tick/age. Timings count actual policy evaluations, not cheap waiting polls.

## Reports and diagnostics

**Save match report** writes `RoWorld_Match_Report.json` and an archived copy in
the executor workspace. The report includes the version/schema, built-in versus
loaded-model status, chosen orders, candidate scores/probabilities, filters, exact
public facts, missile alerts, observed opponent history and decision timing.
`getgenv().__RoWorldBot.report()` and `.diagnostics()` remain available. Reports
and profiles stay local; nothing is uploaded automatically.

Do not train on another player's inferred commands from these reports: public
state changes do not identify exact intent or account identity. The offline
training worker records our own chosen legal actions and actual simulator rewards.

## Optional training on your laptop

Inference needs no extra installation. Training needs Python 3.10+, the official
Luau CLI and the **original v111 RoWorld place you supplied**. It uses RoWorld's
own simulator, not a modified OpenFront environment. The game source is prepared
locally and is not included in this repository or download.

1. Run `SETUP_TRAINING.bat`. This creates a local Python environment with CPU
   PyTorch. For this small network, CPU training is a sensible starting point.
   To use the GTX 1650, install a compatible CUDA PyTorch build using
   [PyTorch's installer](https://pytorch.org/get-started/locally/).
2. Download `luau-windows.zip` from the
   [official Luau releases](https://github.com/luau-lang/luau/releases/latest).
   Put `luau.exe` and `luau-compile.exe` in `roworld_v3\tools`.
3. In Command Prompt, change to the extracted `roworld_v3` folder and run:

   ```bat
   PREPARE_TRAINING.bat "E:\path\to\place 137151641329864 RoWorld World PvP.rbxl"
   ```

   Preparation checks the supplied place hash. Existing extracted sources can
   alternatively be prepared with `training/prepare.py --sources PATH`.
4. Start a first country/tribe run:

   ```bat
   TRAIN_V3.bat --out runs\countries --stage 1 --updates 50 --episodes 6 --seconds 540 --workers 3 --threads 2 --device cpu
   ```

   Same command resumes `latest.pt` and performs 50 **additional** updates.
   Ctrl+C preserves the latest completed update. `progress.jsonl` records elapsed
   time, steps, land, deaths, terminal wins, truncations, losses and entropy.
   A timeout is not counted as a win. Estimate duration from your measured update
   time; development-host timings are not laptop timings.
5. Evaluate on seeds separate from training:

   ```bat
   .venv\Scripts\python.exe training\evaluate.py --engine private\engine.json --luau tools\luau.exe --weights runs\countries\latest.json --games 8 --seconds 540 --stage 1 --out runs\countries\evaluation.json
   ```

   Both built-in and learned policies use identical seeds. More land at a timeout
   is not a win; synthetic opponent wins do not establish human strength.
6. Export your trained checkpoint into a complete, standalone script:

   ```bat
   .venv\Scripts\python.exe build.py --weights runs\countries\latest.json --output RoWorld_V3_Trained.lua
   ```

   Paste that **complete file** into JJSploit. It embeds validated weights and
   needs no Python, GPU, JSON reader or external service while playing. To return
   to the built-in policy, execute the original `RoWorld_V3.lua` again.

The trainer does not call a checkpoint “best” based on training loss. Compare
saved `update_XXXXX.json` checkpoints using held-out evaluation before exporting.
The four manual curriculum stages are: `0` tribes, `1` easy countries/tribes,
`2` normal countries with water splits, `3` the same plus frozen-policy opponents.
For a new stage use a new output directory and initialize from the previous run:

```bat
TRAIN_V3.bat --out runs\water --stage 2 --init runs\countries\latest.json --updates 50 --seconds 540
TRAIN_V3.bat --out runs\selfplay --stage 3 --init runs\water\latest.json --updates 50 --seconds 540
```

Schema/engine/curriculum changes preserve the old run and require a new output
directory. An `--init` JSON can transfer compatible weights to the new run;
optimizer state is reset for that transfer. Same-run resume retains optimizer,
update/step counts and CPU random state. CUDA bitwise reproducibility is not
promised. Keep private engines, checkpoints and reports out of public uploads.

## Verification and limits

Run the transport/behavior/UI/compilation suite:

```bat
python tests\run.py --luau tools\luau.exe --compiler tools\luau-compile.exe
.venv\Scripts\python.exe tests\test_learning.py --luau tools\luau.exe
```

See [`VERIFICATION.json`](VERIFICATION.json) for the recorded engineering tests.
This release has an executable learning pipeline, not a demonstrated multiplayer
strength improvement over v2.4. Training maps are small synthetic layouts and the
current candidate generator is intentionally bounded. Harder water/self-play
worlds may stall. It cannot read hidden intentions, create money or guarantee wins.
