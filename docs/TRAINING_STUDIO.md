# Rocket League Training Studio

Double-click **`TRAINING_STUDIO.vbs`** in your project folder. If startup fails, use
**`TRAINING_STUDIO.bat`** to see the error. The app uses the existing project
`.venv`; no additional Python packages are needed for its interface. Windows
Python must include Tkinter. The native trainer still needs the installed
Visual Studio C++ tools, matching PyTorch/CUDA toolkit and collision meshes.

Keep the extracted files inside `E:\Downloads\Chat_GPT_AI`, alongside your current
models and data. The app does not download models, collect credentials, delete
checkpoints or replace the existing AFK Improved launcher.

## Start with model selection

1. Open **Find best models**. The default selector includes original mechanics
   `update_*.pt` and `accepted*.pt`, team checkpoints and native attention run
   `update180_attention02`. Use **All settings → Load selector defaults** to
   review the exact families, anchors and rivals. Add other attention run folders
   or exact rival checkpoints there if needed. Click **Apply JSON** after editing.
2. Keep **Stop after stage = screen** for the first pass. The default finite
   game budget is 512 per launch. **Inventory models** checks actors and identifies
   identical weights before comparing them. The baseline and anchors must exist;
   absent models are reported instead of silently replaced.
3. Click **Start comparison**. Completed games are cached. Use **Resume comparison**
   to extend the budget. Reusing a completed stage does not replay its cached games.
   If inventory already initialized the run, Start comparison automatically
   resumes that pinned inventory without changing its settings.
4. Progress through **refine**, **finalists**, then **confirm** using the same
   selection run name. Later stages use independent seeds and team modes. Do not
   edit an existing run's pinned protocol; create a new selection run for a new
   opponent pool or scoring protocol.
5. Review **Results** and the selector's `SHORTLIST.md`. The screen is exploratory;
   losses, training reward and teacher KL are not substitutes for match evidence.
   **Use this selection for training** selects the current completed stage's
   source for a new isolated experiment. It does not replace your playing bot.

The app's **Saved models** browser lists original mechanics models, accepted
models, team updates and complete attention checkpoints. It reads filenames and
completion markers; the backend verifies model compatibility before using them.
**Browse file** can select a compatible attention `.pt` anywhere on your PC.
Native checkpoint folders can be used through their `actor.pt`. Old native MLP
`.lt` actors have a different architecture and are not attention continuation
sources.

## Train or run the automatic campaign

On **Training**, choose your starting model or selection JSON, a new run name,
device and routine. The app exposes learning rates, teacher anchor, PPO KL,
parallel worlds, rollout length, team formats and self-play refresh. Additional
native settings are editable under `native_profile` in **All settings**.

**Balanced teams** selects 1v1, 2v2 and 3v3. **All nine formats** also includes
unequal team sizes such as 1v3, 2v3 and 3v1. Either preset updates new native
training formats and the new campaign's evaluation formats/weights together.
All nine formats increase evaluation cost; use a finite budget first. Existing
runs keep their saved formats.

Build the engine after extracting a code update, then run **Parity check** and
**Smoke test** on the selected model and device. These diagnostics receive fresh
names, so they do not occupy your intended training run. **Start new run** then
starts the chosen number of updates. **Resume** adds updates using the saved
profile and optimizer state; changing common fields does not rewrite that run.

For fewer manual steps, use **Auto campaign**:

1. Choose a source or completed selection JSON. Give the campaign a fresh name.
2. Click **Load full campaign defaults into editor** and inspect **All settings**.
   Set a finite number of cycles or an explicit time budget. Infinite continuation
   requires the explicit `unlimited_until_paused` setting.
3. Adjust routine order, per-routine profiles, branch budget, chunk size, plateau
   limits, evaluation frequency, confidence guards and team formats as needed.
   Click **Apply JSON**, then **Start auto campaign**.
4. The campaign preserves its starting model, creates isolated branches, screens
   saved candidates and confirms improvements on fresh evaluation seeds.
   Stalled or regressing branches retain their files and rotate to another
   configured routine. The parent remains eligible when selecting the branch's
   best checkpoint. Results record why a candidate was retained or rejected.
5. **Resume campaign** uses its pinned settings and saved state. Changes to a
   running campaign are made through a new campaign rather than rewriting history.

The Auto campaign page exposes cycle count, updates per branch, chunk size,
screen interval, plateau limit and time budget directly. For continuous operation
until a safe pause, explicitly set **Cycles = 0**, **Time limit = 0**, and
**Allow unlimited = True** before starting a new campaign. Finite defaults use
eight cycles. A stalled branch still rotates even in continuous operation.

Available native routines are normal matches, defense, wall-to-reset sequences,
air control, recovery, boost management, bumping and bump evasion. The exact
implemented drills, attribution rules and bounded rewards are described in the
native curriculum documentation. These are training opportunities, not a promise
of learned mastery. Team formats are explicit, and self-play uses frozen policy
snapshots; frozen cars do not contribute learner PPO rows. Opponents retain
scripted kickoff while the selected learner uses its policy.

The Studio's native common fields provide defaults for a **new campaign**'s
`native_profile`. Explicit fields in `campaign.native_profile` take precedence;
the campaign's `routine_profiles` can override those fields by routine.
Its top-level `formats` and `routines` choose the branch queue. Every backend
configuration field remains accessible in the JSON editor. Selection and campaign
configuration sections accept the corresponding backend defaults and overrides.

## Pause, status and background jobs

**Pause active job safely** requests a checkpoint boundary. Wait for the status
to finish before shutting down your laptop. Completed checkpoints and evaluation
games are preserved. A power loss can discard unfinished work; resume restores
the latest complete checkpoint and resets physical arenas to reproducible starts.

Only one Studio job runs at a time. Logs go directly to durable files instead of
through the GUI. Closing the window offers three choices: keep the job running,
request a safe pause and stay open, or cancel closing. Reopening the Studio
reconnects to its last live worker, displays its log and prevents an accidental
second launch. It does not monitor arbitrary training started from other CMD
windows, so stop those before starting a competing training workload.

Training and comparison logs update without blocking the window. **Results →
Refresh reports** reads progress and shortlists from disk. The displayed champion
is a campaign selection; a checkpoint's update number or KL is never presented
as proof of greater playing strength.

## Evaluation and export

For a native run, **Evaluate checkpoint** compares a chosen complete checkpoint
against that run's original source. Leave the checkpoint field empty for the
latest saved model, or choose an earlier checkpoint directory. Set evaluation
duration and independent seeds before launching. Reports save under the run's
`evaluations` folder. This native evaluation is separate from the broader
multi-mode selector and campaign promotion checks.

**Export attention .pt** creates a checked portable actor checkpoint under the
native run. **Export chosen model to RLBot** instead exports the model currently
shown in **Starting model**, including an actor selected in the model browser.
This button does not infer that the latest training update is strongest.
**Choose campaign champion** fills the starting model from the campaign's
saved `selected.json` and checks that its actor file still matches the recorded
hash. You can then export that model or use it as another training source.

Choose **both**, **learned**, or **scripted** kickoff. The app reuses the checked
RLBot v4 exporter and verifies the weights without changing the source. Exports
appear under `data\rlbot_exports` with `_Learned` and `_Scripted` names. Existing
export names are protected; use a new name to export again. Import each folder's
`bot.cfg` into a compatible RLBot v4 setup. The original Nexto-derived license
and runtime requirements remain included in those packages.

## Replay tools

**Prepare replay dataset** calls the existing bounded replay parser and prepares
its attention observations, aligned input targets and independent source splits.
Choose your replay folder and an output folder under `data/isolated`. Maximum
replays and parser workers are exposed in the tab; samples per replay and total
samples are editable in **All settings → replays**. Matching cached data can be
reused; changed settings require a new output folder. This prepares data for the
existing replay tooling and future work; **the native attention trainer currently
does not consume human replay gradients**.

**Audit legacy replay inputs** runs the existing input-provenance audit for the
earlier native MLP event bank and its `.lt` checkpoint. Select an event-corpus
folder containing `manifest.json`, its legacy native checkpoint folder and your
raw replay folder. This is separate from the dataset just prepared above. The
report distinguishes recorded throttle/steer evidence from reconstructed aerial
axes and events, and checks that legacy student's label agreement. It is not an
attention policy evaluation or proof of human input recovery.

Both replay utilities have finite budgets and preserve their caches; they have
no safe pause command. Let them finish or keep them running when closing the
window. Reports and provenance errors appear in the durable Studio log.

## Saved files

| Content | Project-relative location |
| --- | --- |
| Studio settings, worker records and logs | `data/isolated/training_studio/` |
| Selector inventory, cached games and family shortlists | `data/isolated/model_selection/runs/<run>/` |
| Native training checkpoints and evaluations | `data/isolated/native_attention/runs/<run>/` |
| Automatic campaign champions, branches and decisions | `data/isolated/champion_campaigns/<run>/` |
| RLBot packages | `data/rlbot_exports/` |

**Import settings** and **Export settings** move configuration JSON only. Secret
fields such as tokens, passwords and API keys are rejected. Model weights,
replays, logs and credentials are not embedded in exported settings.
