# Versatile hybrid training

This is a new, isolated training path for your chosen native Nexto checkpoint.
It combines replay imitation with PPO match/mechanics practice. It does not
change your current mechanics run, its configuration, source models or exports.
Neither this trainer nor upstream replay parsing guarantees continuous skill
growth, SSL rank or professional-level play.

## What to do after the current mechanics run

Keep promising raw checkpoints, including update 180. Teacher KL is a policy
difference metric, not strength. Compare promising checkpoints on fresh matches
and both teams; check exported play in Rocket League. Choose the actor to
continue explicitly. The commands below use your update 180 as a candidate,
not a certified winner. Replace that source path if another checkpoint wins.

Close the old trainer or wait for it to finish before starting a new trainer.
Keep source replays under `data/replays` or choose your own replay folder.
Use complete high-quality matches with varied offense, defense, low-boost and
recovery situations rather than only highlights. The importer does not infer
player rank or download replay files using account credentials.

## Install and prepare a small first dataset

Extract the update directly into `E:\Downloads\Chat_GPT_AI`, replacing included
code files. Your existing `.venv`, model/replay files and configurations stay.

```bat
cd /d E:\Downloads\Chat_GPT_AI
.venv\Scripts\python.exe -m pip install -r requirements-slater-versatile.txt
.venv\Scripts\python.exe -u slater_versatile_trainer.py prepare --inputs data/replays --out data/isolated/versatile_data01 --max-replays 100 --workers 2
```

Preparation uses the installed, pinned RLGym Tools parser and its carball
executable, inverse aerial control fitting and physically feasible action
selection. Parsing can be the expensive first step. Each complete replay shard
is cached; rerunning with unchanged settings reuses it. `parse_progress.json`
records failed files and progress. Adding files/settings requires a new dataset
folder, preventing an active run's dataset from changing silently.

Reservoir sampling spans entire games, with separate categories for general
play, close control, defense, aerial, attack and low boost. There are at most
1,024 rows per source by default (category caps can yield fewer), and 100,000
rows overall. Memory-mapped observation/target arrays avoid loading the whole
dataset into RAM on each training step. Balanced sampling chooses a category,
source group and row; long games cannot dominate just because they have more
frames. Parser/runtime versions participate in cache identity. Reconstructed controls carry a confidence weight. Equivalent feasible
actions use soft labels rather than arbitrary contradictory hard targets.

Sources split into 70% training, 15% validation and 15% untouched test by stable
group hash. Replay game IDs group matching recordings when available; otherwise
raw SHA is used. Aligned captures can supply `source_group` to group clips from
the same original recording. Exact duplicate files are removed. At least two
independent training groups and one validation and test group are required;
a very small sample may need more replay files to populate all partitions.
Only training shards provide PPO reset states. Validation is reported rather
than automatically treated as competitive strength. The test partition stays
out of training and cycle selection; use it for a separate final imitation audit.

Parsed hidden jump/flip state and human controls remain approximate. This is
not a separately trained and calibrated RL-RPT inverse-dynamics neural model.
Frames with old/nonfinite update ages, demos, nonstandard settings, bad physics,
incompatible rosters and uncertain action mappings are filtered. 1v1, 2v2 and
3v3 demonstrations are supported in the native padded 41-entity observation.

## Preflight, smoke, then train

```bat
.venv\Scripts\python.exe -u slater_versatile_trainer.py preflight --source data/isolated/mechanics_curriculum/selected7_mechanics01/update_000180.pt --dataset data/isolated/versatile_data01
.venv\Scripts\python.exe -u slater_versatile_trainer.py smoke --source data/isolated/mechanics_curriculum/selected7_mechanics01/update_000180.pt --dataset data/isolated/versatile_data01 --run versatile_smoke01
.venv\Scripts\python.exe -u slater_versatile_trainer.py start --source data/isolated/mechanics_curriculum/selected7_mechanics01/update_000180.pt --dataset data/isolated/versatile_data01 --run versatile01 --cycles 3
```

Use a new smoke run name when repeating. Smoke performs one real PPO update,
two small replay BC updates, saves a candidate and runs a tiny comparison; it
has insufficient evaluation budget to establish improvement. Inspect
`update_000001.json` for accepted PPO epochs, replay BC results and scripted
rival ticks. A zero accepted count needs investigation before a long run.

A dataset is optional: omit `--dataset` for mixed PPO practice alone. That skips
replay imitation and replay resets. Do not label that run as human replay learning.
A native full checkpoint or compatible Nexto TorchScript actor is accepted;
actor weights transfer to new critics/Adam states because the objectives differ.
Other architectures, FF92 and arbitrary ONNX models are not accepted.

## Desktop controls

Open `AFK_IMPROVED_DESKTOP.vbs` and select the new **Versatile Trainer** tab.
Browse the source checkpoint, enter your replay and prepared dataset folders,
and use Install dependencies, Prepare, Preflight, Smoke, then Start new run.
Use distinct smoke/train run names. Uncheck prepared demonstrations for PPO-only
training. Resume saved run loads the original run's saved source/data/settings.
Open run/reports shows all candidates and decisions; Export saved champion uses
the standard exporter with scripted kickoff enabled. Before the first promotion,
the saved champion is only the starting baseline. Individual raw candidates can
also be chosen in Viewer & RLBot's export browser.

## Curriculum and update boundaries

Every cycle has 20 updates by default. Eight simulator worlds batch learner
inference, while nonlearner cars share a batched frozen-policy inference within
each world. Physics worlds run serially in this implementation; it is not a C++
collector or a GPU pipeline. Original Nexto TorchScript remains on CPU. Placeholder players use a negative
additive attention mask; a parity test matches the unpadded RLBot observation
logits. This fixes a simulator/export mismatch in the older padded-observation
path without modifying the earlier trainer or your existing run.

Two worlds always practice match/ground play. Others rotate among defense,
recovery, low boost, aerial interception, walls, air dribbles, aerial finishes,
reset use, replay starts and 2v2. In 2v2 only the selected car is trained; other
cars, including its teammate, use frozen policies. This exposes team contexts
without claiming a validated tactical teamwork system or a trained 3v3 team.
Confirmed earlier champions can enter the practice opponent pool.

Goals/concessions dominate reward. Bounded potential differences, capped useful
contacts and the existing physical carry/reset events provide intermediate
feedback. Every fourth update adds two confidence-weighted replay BC batches.
PPO bounds each update's rollout policy KL; replay BC has its own batch KL check
and restores actor/Adam state after failed retries. No fixed teacher-KL value is
used to choose the best model. These bounds apply to sampled states, not all play.

The student learns its action policy during PPO. All frozen cars have scripted
kickoffs. Read-only match evaluation supplies the same scripted kickoff to both
candidate and reference, matching the intended exported wrapper. Kickoff timing
in RocketSim is a stationary-center-ball proxy, not authoritative RLBot parity.

## Selection and stopping

Each cycle screens the candidate against original Nexto and the frozen starting
actor, on matched blue/orange seeds. Only a positive screen runs the larger fresh
confirmation: 12 seed clusters, 60 seconds per game by default. Confirmation
requires positive paired goal difference, a one-sided sign test with a fixed
Bonferroni budget across at most 12 cycles, and per-rival regression guards.
Defense, recovery, aerial and 2v2 holdouts then check for obvious lost abilities.
These are finite simulator tests, not guarantees in unseen situations.

Evaluations save each completed candidate/reference pair and print total work,
completed pairs and measured ETA. Interrupted evaluations reuse complete pairs
with identical model/code/protocol hashes. No repeated first-goal marathon over
hundreds of old models is launched automatically.

All raw `update_*.pt` candidates remain available, even when rejected. After a
rejection, training restores the selected champion's actor, critic and optimizer
states. It commits that restored state before resume can restart. The champion
only changes after fresh match confirmation and skill guards. Resume restarts
simulator episodes from deterministic seeds; it does not reproduce a mid-episode
trajectory or preserve an unfinished update.

Three cycles per session means normally 60 updates plus evaluation. The run also
stops after three unconfirmed cycles (plateau), or after 12 total cycles. Repeating
resume on a plateau-stopped run does not bypass that stop. Inspect candidates,
data quality and reports; then start a new, revised experiment. Longer budgets
are configurable for new runs using `SLATER_VERSATILE_CONFIG.example.json` with
`--config`. The maximum-cycle budget also controls the confirmation threshold.

```bat
.venv\Scripts\python.exe -u slater_versatile_trainer.py resume --run versatile01 --cycles 3
.venv\Scripts\python.exe slater_versatile_trainer.py status --run versatile01
.venv\Scripts\python.exe slater_versatile_trainer.py pause --run versatile01
```

Pause finishes the current update or evaluation pair. After restarting, saved
checkpoints and complete evaluation pairs remain. Source/data/code changes refuse
resume; use a new run after upgrading trainer code. The patch does not change
files that participate in your earlier mechanics run's protocol hashes.

Outputs live in `data/isolated/versatile/RUN/`: `progress.json`, `selected.json`,
`update_*.pt/.json`, `cycle_*_resume.pt`, `evaluations/` and `session_summary.json`.
`selected.json` names the retained champion; the last update is not automatically
best. Existing source files and export folders are never overwritten.

## TAS captures

Legacy `.data` files provide controls without verified game-state alignment. They
are not accepted as imitation data. A verified capture `.npz` must contain:

- `states`: N+1 serialized RLGym Tools GameStates, with stable IDs/roster.
- `controls`: N x players x 8 actual controls, ordered by sorted serialized IDs.
- `tick_skip`: integer 8, and state tick counters spaced exactly eight ticks.
- Optional `source_group`: shared string for clips from the same recording.

Every interval is replayed in RocketSim with RLBot delay disabled and compared
against its recorded successor. Samples must match all-car/ball position within
3 UU, velocity within 20 UU/s, and rotation-matrix error within 0.06. This checks
short local consistency; it does not establish long-horizon real-game parity.
Use this format only when actual state/control recordings exist. The importer
does not guess unknown .data fields or fabricate starting positions. Add a folder
of verified captures to `prepare --inputs data/replays data/aligned_tas`.

## Upstream basis and validation

- [RLGym Tools](https://github.com/RLGym/rlgym-tools): pinned 2.6.5 parser,
  reconstruction, action feasibility and serialization APIs. Reviewed source
  `0c63b2a8878233f34869b9ea1e32e19548a0cd16`.
- [Replay-pretraining](https://github.com/Rolv-Arild/replay-pretraining): reviewed
  `8c15e847dc9ecf37ef8ad38d6c615b080772c959`; motivates confidence-filtered human
  imitation followed by RL. Its incompatible network/weights are not imported.
- [Replicar](https://github.com/Rolv-Arild/replicar): reviewed as a future alternative
  reconstruction backend; the native-backend update adds compatible Parquet
  import through its official reader. See `GigaLearn_Project/Native_Backend/README.md`.

Cloud validation includes a public parser fixture from
[Boxcars](https://github.com/nickbabcock/boxcars), `assets/replays/good/b2a19.replay`:
3v3, 8,540 parser frames, 96 native examples across six categories. This public
fixture is not asserted to be an SSL match. No raw replays, private weights or
synthetic training fixtures are included in the download. See
`docs/VERSATILE_VALIDATION.md` for checks and limitations. Test results prove
pipeline integration, not competitive improvement.
