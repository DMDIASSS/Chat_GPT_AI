# Campaign from update271 with format-specific rivals

Extract `Slater_U271_Format_Targets_Update.zip` into the existing
`E:\Downloads\Chat_GPT_AI` folder. Request a safe pause and close Studio before
installing: updating the code/build changes the identities used by existing runs.
Start a new campaign; do not resume `c17_universal01` with this implementation.
All its saved models and reports remain available for testing/export.

Double-click `U271_TARGETS_SETUP.bat`. It checks the required model paths,
refuses to run while a recorded Studio job is active, builds the native engine,
backs up Studio settings and loads `STUDIO_CAMPAIGN_U271_FORMAT_TARGETS.json`.
Then click **Auto campaign → Start auto campaign**. Check that the name is
`u271_targets01`, Starting model ends in `update_000271.pt`, and Selection JSON
is empty. Use a fresh name if this campaign already exists.

| Format | Fixed training/evaluation targets |
| --- | --- |
| 1v1 | Original update271 |
| 2v2 | Original update271 |
| 3v3 | Checkpoint 14 from `update_271_training`, original Nexto |

Frozen parent policies and recent snapshots also provide self-play experience.
The mapping applies to every native training routine. Wall/aerial practice
scenarios that use a one-car drill select the 1v1 targets; ordinary team worlds
retain their configured roster and targets. Frozen teammates use parent/snapshot
policies. The native trainer records `selfplay.external`, `rivals_by_format`
and `assigned_opponents`; an empty external list with this preset is an error.

Scripted kickoff is ON for the learner and frozen players in training, campaign
evaluation and the selector preset. Only each team's designated kickoff taker
uses the kickoff sequence. When a script overrides any packet of a sampled
transition, that transition is excluded from PPO/critic updates. GAE uses the
complete timeline before filtering; scripted actions are not falsely attributed
to the neural policy. This trains play with scripted kickoffs, not a learned
copy of the kickoff sequence. Export with scripted kickoff to use the same setup.

The finite campaign has six branches: match, defense, boost, air control,
bump evasion, match. Each has at most 100 updates, in chunks of 20, screening
every 20 saved updates; stalled/regressing branches rotate early. Confirmation
uses eight fresh independent seeds, both colors and all three formats.
Preserved source files include the base, rivals and every candidate checkpoint.

Promotion still requires confirmed improvement over the branch parent, with
guards against format regression. `target_scores` in each screen/confirmation
reports the **absolute** goal difference/minute against each required target,
so relative improvement cannot be mistaken for beating that target. The preset
allows incremental improvements to become later branch parents. If desired,
set `campaign.require_target_advantage=true` before a NEW campaign to require a
positive lower confidence bound against every fixed target before any promotion;
this stricter gate can retain the starting model despite useful partial gains.

Standalone Training uses `TRAINING_U271_FORMAT_OPPONENTS.json` and the same
scripted kickoff option. **Evaluate checkpoint** on a run with a format mapping
uses the native batched evaluator in all configured formats. **Find best models**
has the same format-specific rivals, discovers checkpoints from this campaign
and the standalone run, and uses scripted kickoff. Its rankings remain exploratory
until confirmed with independent seeds. Old presets preserve their legacy defaults.

Reports: `data\isolated\champion_campaigns\u271_targets01`.
Full checkpoints: `data\isolated\native_attention\runs\u271_targets01_c0001\checkpoints`
(and later branch numbers). Use **Pause active job safely**; resume restores
the new campaign's saved profile and complete checkpoints.

Cloud validation: compiled the C++ engine; checked campaign/selector routing and
promotion rules; ran real CPU scripted training, filtered PPO rows, external
opponent loading, resume and evaluation across 1v1/2v2/3v3. The cloud fixtures use
the bundled Nexto actor because your actual 271/14 files are local to your PC.
Windows CUDA performance and real-match strength still require your local run.
