# Automatic champion branches

The campaign trains a protected attention model in several routines, evaluates
saved candidates automatically, and starts the next routine from the strongest
confirmed experiment champion. It never overwrites the starting model, deletes
checkpoints, or silently exports a replacement for the bot you play with.

Launch `TRAINING_STUDIO.bat` and use the automatic campaign page. Choose either
an original attention checkpoint, a complete native checkpoint folder, or a
completed model-selector `selection.json`. Selecting a model from an
exploratory screen means choosing an experiment source, not declaring it the
best bot. Finish the build, parity and smoke checks before a long campaign.

## What runs automatically

Each branch starts from the current experiment champion with unchanged actor
weights. It receives its own teacher, optimizers, full checkpoints, training
seed, routine and pinned native profile. The queue supports the implemented
native routines: match, defense, wall/reset, air control, recovery, boost,
bumping and bump evasion. The same actor can practise 1v1, 2v2 and 3v3, and
the native format setting also accepts asymmetric teams.

The default budget is eight branches, at most 100 updates each, with a screen
every 20 updates. Each screen includes the branch parent, every fifth saved
checkpoint, and the current checkpoint. All intervening checkpoints still
remain available for a later exhaustive selector run. Set `screen_every` to
1 to screen every update; this increases evaluation cost substantially.

Screening uses the same starts, rivals, durations, team assignments and both
colors for each candidate and the parent. Cached parent matches are reused
within a branch. Team screens use the candidate policy for its squad. The
selected car plays without a scripted kickoff; its frozen-policy teammates
and opponents retain scripted kickoff. Frozen experience is excluded from
learner updates.

The manager keeps a four-model exploratory shortlist per branch. Its score
weights paired goal difference per minute by the configured modes, rather
than mixing training reward with match strength. Defaults weight 1v1 at .4,
2v2 at .3 and 3v3 at .3. Training KL and mechanic reward are useful diagnostics,
but neither directly decides a promotion.

A branch ends after its update budget, three screens without a meaningful
new screen leader, or two screens where its latest checkpoint is below
the configured regression threshold. An earlier good checkpoint remains in
the shortlist and can receive confirmation even when the later branch
collapses. The screening seeds are reused during
that branch, so these stopping rules conserve resources; they are not
independent proof of regression. If the parent wins, the manager keeps it
and moves to another routine.

A promising child receives a separate confirmation against its parent, using
new seeds that were not used for training or screening. Confirmation requires
at least eight independent seed clusters, a positive lower confidence bound
beyond `min_improvement`, and a mode-specific lower bound above the allowed
regression margin in every configured mode. Repeated confirmations spend a
decreasing alpha budget, with a share for the overall and mode comparisons.
These are deterministic seed-cluster bootstrap intervals with approximate
coverage. They do not guarantee the strongest model, a Rocket League rank,
or behavior in untested real matches.

An inconclusive confirmation retains the parent. A confirmed child becomes
the private experiment champion for later branches. Its original branch
checkpoint, all other children and the parent remain saved. The playing
model still requires deliberate export and testing.

When enabled, recent complete checkpoints become frozen self-play opponents
inside the native branch. Campaign defaults refresh every ten updates and
include the configured fixed rivals, the current champion, and up to four
earlier confirmed champions in each branch's private opponent pool. Opponent
copies remain frozen during collection; no simultaneous learner updates are
applied to them.

## Commands

Start from the locally verified update278:

```cmd
cd /d E:\Downloads\Chat_GPT_AI
.venv\Scripts\python.exe -u slater_champion_campaign.py run --run champion01 --source data\isolated\mechanics_curriculum\selected7_mechanics01\update_000278.pt
```

Or start from the completed cross-family selector report:

```cmd
.venv\Scripts\python.exe -u slater_champion_campaign.py run --run champion01 --selection data\isolated\model_selection\runs\best_models01\selection.json
```

Request a safe pause from another CMD window, then wait for the manager to
report `PAUSED`:

```cmd
.venv\Scripts\python.exe slater_champion_campaign.py pause --run champion01
.venv\Scripts\python.exe slater_champion_campaign.py status --run champion01
```

Resume the remaining saved campaign budget:

```cmd
.venv\Scripts\python.exe -u slater_champion_campaign.py resume --run champion01
```

Resume restores the most recent complete native actor, teacher, critic,
optimizers and RNG state. As in the native trainer, physical arenas start
fresh on a resumed chunk; a partially played game is not restored. An abrupt
power loss may lose the current unsaved update or game, but completed updates
and cached evaluation games are preserved. Interrupted checkpoint directories
are renamed and retained. The persisted chunk target prevents a resume from
accidentally granting a whole new chunk after partially finishing it.

Do not run a standalone native trainer against a campaign's active branch.
The manager owns its budget and pause file, and rejects a branch advanced
beyond its expected checkpoint.

## Adjustable budgets and settings

Generate a full configuration from the currently installed trainer:

```cmd
.venv\Scripts\python.exe slater_champion_campaign.py config > champion_config.json
```

Edit that file before starting and pass `--config champion_config.json`.
The Studio also exposes the native profile and the full campaign configuration.
Settings are pinned for an existing run. To change a saved experiment's
parameters, start a new campaign from its chosen champion and keep the old
campaign intact.

| Setting | Purpose |
| --- | --- |
| `cycles`, `branch_updates`, `chunk_updates` | Total branch budget, per-branch budget, evaluation cadence |
| `screen_every` | Saved update sampling interval for automatic screens |
| `plateau_chunks`, `regression_chunks` | Consecutive screens before ending an unproductive branch |
| `routines`, `routine_profiles` | Queue and native parameter overrides for individual routines |
| `native_profile` | Device, learning rates, PPO target KL, teacher anchor, rollout size, native self-play and practice settings |
| `rivals` | Explicit named checkpoint paths; the private frozen pool is validated and copied |
| `formats`, `mode_weights` | Evaluation/training roster formats and their importance |
| `screen_seeds`, `screen_seconds` | Cheap, reusable branch-screen workload |
| `confirm_seeds`, `confirm_seconds` | Fresh confirmation workload; fewer than eight seeds cannot promote |
| `min_improvement` | Required lower bound on paired improvement in goals per minute |
| `mode_regression_margin` | Largest allowed mode-specific regression in goals per minute |
| `screen_regression_margin` | Exploratory screen threshold for ending a clearly weak branch |
| `promotion_alpha` | Campaign confirmation error budget; bootstrap coverage is approximate |
| `worlds`, `job_group` | Batched evaluation size and pause/checkpoint responsiveness |
| `history_opponents` | Number of earlier confirmed champions retained in frozen branch pools |
| `max_minutes`, `min_disk_gb` | Time and disk budgets, checked at completed phase boundaries |
| `seed_base` | Disjoint screening and confirmation namespaces |

`cycles=0` is accepted only with a positive time budget or an explicit
`unlimited_until_paused=true`. Time budgets may overrun by the current bounded
training chunk or evaluation group; reduce their sizes when pause latency is
important. The C++ trainer also retains its own disk floor. Nothing in this
manager installs missing replay parsers or enables human replay gradients.

## Reports and preserved models

Campaign files save in `data\isolated\champion_campaigns\champion01`:

- `progress.json`: current routine, phase, training/evaluation progress and budgets.
- `selected.json`: private experiment champion, hashes and protected playing-model path.
- `shortlist.json` and `SHORTLIST.md`: retained branches and exploratory candidates.
- `branches\cycle_000001\screen.json`: paired mode scores for that branch.
- `branches\cycle_000001\confirmation.json`: fresh-seed evidence, when a child qualified.
- `branches\cycle_000001\decision.json`: the branch result and retained champion.
- `cache\records`: durable content-derived evaluation game records.
- `actors`: private, weight-verified portable actors used for evaluation.

Full native training checkpoints stay under
`data\isolated\native_attention\runs\champion01_c0001\checkpoints`.
You can deliberately evaluate or export a chosen complete checkpoint through
the Studio/native trainer. A private champion `actor.pt` is also a valid source
for a new isolated experiment.

The protocol records source hashes, configuration, private actor weights,
code, compiled backend, runtime and selection evidence. Resume rejects changed
inputs or implementation. This prevents an old cached result from being
treated as evidence for newly edited weights or a different simulator build.
The chosen selector report is copied once into `source_selection.json`; a
later independent selector report can advance without changing this campaign's
frozen input evidence.
