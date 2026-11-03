# TurboBall Roblox bot — Local v6.8

**Chronos V2.1 preset:** the new `downloads/TurboBall_Chronos.lua` embeds the
public Chronos actor and its matching 225-value inputs, reflection and action
masks. It runs locally with this adapter. It won 30 of 32 bounded RocketSim 1v1
first-goal episodes against original Nexto; this is not an all-bot ranking or a
live Roblox result. See [Chronos setup, loader and verification](CHRONOS_README.md).

Your measured goal positions, opening widths and crossbar heights are built into
v6.8 and used automatically from startup. Run the new script and press **F6**;
loading a calibration file or pressing Apply is unnecessary. The panel confirms
**Measured goal defaults active**. The optional wizard can override these defaults
with a future manual fit; Reset returns to the baked measurements.

## Ready-to-run original Nexto

The ZIP now includes **TurboBall_Nexto.lua**, built from the original public
Nexto actor. No Python, checkpoint export or running bridge is needed for this
preset. Its source SHA256 was checked against the upstream public file; it is
not a renamed Update271 checkpoint. Attribution and the CC BY-NC-SA 4.0 license
are in `NEXTO_NOTICE.md` and `NEXTO_LICENSE.txt`.

1. Close the old standalone bot panel.
2. Copy `TurboBall_Nexto.lua` from this folder into the JJSploit workspace.
3. Execute:

   ```lua
   loadstring(readfile("TurboBall_Nexto.lua"))()
   ```

4. Wait for **Nexto LOCAL v6.8 ready**, then press **F6**. **F8** stops.

Nexto starts with **Physics assist: OFF** and **Yield to teammate: OFF**. The actor
chooses its actions, with the existing kickoff, bounded stuck recovery, and the
separate **Goal safety: ON** guard. These switches control our overrides; they do not retrain Nexto or
remove teammates from its observation. Pause with F8 to change either switch.
If enabled, teammate yielding now requires a nearby, grounded teammate moving
toward the ball and facing it; a stationary or misaligned teammate is insufficient.

To rebuild from the original asset already in your project, run
**EXPORT_NEXTO_BOT.bat**. It installs `botrblx_standalone.lua` in the executor
workspace, using the existing project Python. `EXPORT_LOCAL_BOT.bat` continues to
export your private Update271 checkpoint separately. Both builds identify the
model by name and SHA256 in diagnostics.

## Movable window, goal calibration and physics recording (local v6.8)

**F4** minimizes/restores the window during play. Pause with **F8** to drag its
title bar. Open **Calibration / physics test** while paused; the bot stays paused
while you position or drive the car.

The **Goal landmarks** wizard records nine points: field centre, then both inner
posts, the crossbar underside and the rear net wall at orange and blue. Touch the
specified face with the front collision body. At ground landmarks, hold still
and press **F10**. At each crossbar, press **F10** to arm, then fly nose-up into
the underside; the tool records the impact without requiring a hover. Capture
works while minimized. The tool accounts for the car's source box
and offset, checks stillness, and validates the fitted dimensions. **Apply goal
measurements** activates the fit; **Save test file** writes
`TurboBall_Calibration.json`. Loading also requires review and Apply. Partial
files can be saved and resumed. See the [placement guide](CALIBRATION_GUIDE.md)
for contact directions and the alternative centre-marker reference.

Local v6.8 accepts post pitch/roll on the concave mouth and supported nose-up
rear-wall poses. It uses full rotated body support; the centre capture's heading
does not rotate the fit. Existing saved landmarks can be loaded and applied
without recapturing. The current built-in measurements already apply at startup. Rear-wall body depth is explicitly approximate. Landmarks
do not establish a persistent shooting bias; use an F9-marked physics report to
record the wide/high shot itself.

The built-in measured goals, or an optional applied manual fit, inform Goal safety and, when
enabled, Physics assist's ground aiming. The rear-wall samples validate and
export the layout; they do not replace the analytic curved collision profile.
The frozen actor's observations and weights remain unchanged.

**Motion / physics test** records up to twenty seconds while you drive straight,
brake, and launch the ball into clear flight. It reports a verified radius when
available, consistent airborne gravity, and sampled acceleration/braking. Only
consistent gravity can be applied here. Static landmarks and this short recording
cannot identify masses or all handling/contact parameters. The saved masses stay
unchanged. Save and upload the calibration file for further analysis.

**Goal safety** brakes a close, straight ground push toward the own-goal opening
and suppresses a likely retouch of an uncontested low ball forecast to score
cleanly. A forecast post/wall bounce or another car within reach prevents the
clear-shot override. It preserves jumps and aerials, and can be disabled while
paused. These bounded guards do not guarantee goals or prevent every own goal.

Press **F9 immediately after a bad decision**, then pause and **Save physics
report**. The report retains up to two marked windows containing the preceding
eight seconds even after the normal trace advances. It also reports goal-guard
actions, calibration and the guard's timing separately from model inference.

The latest supplied v6.4 report records 15.07 decisions/s and a 20.04 ms mean model
phase across 120 decisions (114 model calls). The retained trace does not identify
the reported own goal or last-second redirect precisely enough to establish a
cause. This update has offline scenario/runtime coverage; it has not been
live-tested in Roblox and has no measured win-rate improvement.

## Jump direction and input sequencing (local v6.4)

The previous mapper selected throttle while the wheel-contact estimate said
"grounded", even for a jump action requesting forward/back pitch. Twelve jump
actions consequently lost or reversed their requested pitch under that estimate;
a diagonal flip could become a sideways flip. Jump actions now prioritize the
actor's pitch/yaw and avoid the Shift/free-air-roll modifier. Ordinary ground
driving keeps its existing throttle/steering mapping. WASD still cannot express
fully independent throttle and pitch; jump direction takes priority during jumps.

A new jump edge is sent only after Roblox observes the requested W/A/S/D/Q/E/Shift
state, including release of the previous steering/roll keys. Immediate delivery
adds no wait. Queued direction events defer the jump to a later frame. The controller waits
for acknowledgment before its next model decision, without a blocking sleep loop. F8/focus loss cancels a pending jump. Missing direction
acknowledgment stops with a named error after 150 ms instead of jumping with the
wrong keys. The normal input-call timeout also applies to a deferred jump press.

Reports include up to 24 `jump_events`: requested model action, mapped action,
ground estimate, observed keys and wait time. These distinguish an intended
diagonal flip from incorrect delivery. `control_requirements` records the assumed
default bindings, pitch inversion OFF and aerial safety OFF; these are requirements,
not a claim that the bot verified your in-game settings.

Thirty-six jump mappings were compared with numeric references from the exported
control mapper. Offline tests cover delayed direction release/press, F8 cancellation
and a direction backend that stops responding. Nexto's weights, field dimensions
and default assist switches are unchanged. This fixes a reproducible input issue;
it does not establish that every near-post/crossbar miss has that cause. The game
predicts the whole match and smooths reconciliation, so this update adds no fixed
200 ms ball offset based on a ping estimate.

## Cadence and performance (local v6.3)

The previous loop rounded pose sampling and model decisions to whole frames. A
50 FPS game could consequently run decisions at 12.5 Hz despite a 15 Hz target.
Deadline scheduling now retains the target cadence and skips missed slots rather
than replaying old decisions in a burst. A slow startup reference case no longer
permanently lowers the target. Actual throughput still depends on your PC and
executor; the panel reports completed decisions rather than a promised rate.

The exact dense kernel shares input loads across four output rows. On cloud
Luau, twelve calls per case averaged:

| Entities | Previous kernel | New kernel |
| --- | --- | --- |
| 2 | 7.81 ms | 5.59 ms |
| 7 | 14.16 ms | 9.98 ms |
| 13 | 22.97 ms | 15.78 ms |

All twelve reference cases produced identical logits between the two kernels.
These are cloud interpreter timings, not measurements on Windows/JJSploit.
When ground assist is enabled, far ground approaches and recovery no longer run
an actor inference whose result would be discarded. The ground reach calculation
also reuses one travel curve across candidate ball positions. Close approaches
still consult the actor's jump choice.

The uploaded v6.2 report contained paused samples with a stale last decision, so
it could not establish the active-run bottleneck. Reports now retain the driving
trace while paused and store a separate `latest_pose`. A bounded `performance`
summary records model, planning, pose, physics-observation, input and scheduling
timings. It includes the age of the last active measurement; paused time is
excluded from the live decision-rate calculation. The earlier stop/error logs
and key-release protections remain in place.

The runtime passes offline policy-parity, cadence, teammate and input-lifecycle
checks. Live play quality and Windows performance still require an actual run.
Maintainers can regenerate the public preset with `python build_nexto.py`, run
`python -m unittest discover -s tests -v` with `LUAU_BIN` set, and package from a
full Git checkout with `python package.py`.

## Optional private Update271 export

**Use this mode for JJSploit/WRD.** The supplied diagnostic measured 1.2–1.3
seconds per file exchange. Local mode runs the actual two-block attention policy
inside Lua and sends inputs with the executor's keyboard/mouse functions. There
is no file exchange, HTTP request, or Python process during driving.

1. Close the old Roblox bot panel and stop `START_FILE_BOT.bat` with Ctrl+C.
2. Extract the [folder-only ZIP](https://github.com/DMDIASSS/Chat_GPT_AI/raw/refs/heads/codex/native-quality-campaign/downloads/botrblx.zip)
   into `E:\Downloads\Chat_GPT_AI`, replacing `botrblx` application files.
3. Double-click **`EXPORT_LOCAL_BOT.bat`** once. It reads the existing update271
   with the project's existing Python, exports all policy weights at float32
   precision, and installs **`botrblx_standalone.lua`** in the saved JJSploit
   workspace. Wait for **`READY STANDALONE`**. You can then close CMD.
4. In standard soccer or freeplay, execute:

   ```lua
   loadstring(readfile("botrblx_standalone.lua"))()
   ```

5. Wait for **`LOCAL v6.8 ready | model self-test passed`**, then press **F6**.
   **Team: AUTO** identifies `Deadline_coolgun` from the match scoreboard and
   cross-checks the rendered nameplate relationship. It follows team changes.
   If the team cannot be identified, open the in-game scoreboard once. The
   paused panel cycles **AUTO → manual BLUE → manual ORANGE → AUTO** as a fallback.
   The first start briefly tests W/A/S/D/Q/E/Shift and chooses a keyboard method
   only when Roblox observes both keydown and keyup for every key. Then it drives.
   **F6** pauses and **F8** stops and releases the inputs. Keep default controls:
   WASD, Q/E air roll, LMB boost, RMB jump, Shift powerslide. Disable mouse
   steering, pitch inversion, and aerial safety.

The private exported file is the complete standalone bot, including your model. It is
also saved as `botrblx\botrblx_standalone.lua`. **Keep it private:** it contains
your model weights. It is ignored by Git and excluded from the public download.
The download also includes the verified public Nexto preset; it excludes your private checkpoint.
Re-export only when changing the model or updating this runtime.

The panel reports inference time, executor input-call time, actual decisions per
second, the keyboard method, requested keys, and keyboard keys Roblox actually
sees. Requested keys alone are not proof that an executor delivered them.
It targets 15 decisions/second and samples
poses at up to 30 Hz. Startup runs twelve saved PyTorch reference cases (including
live-pad and other-car entity inputs) and refuses
to drive if local logits/actions differ or inference exceeds 200 ms. F8, focus
loss, chat, invalid poses, missing boost HUD, and errors release owned inputs.
Goal/reset waits resume after valid car/ball poses return.

This removes the measured file-transfer delay; inference and frame/input timing
still take time. The cloud Luau interpreter averaged about 10 ms/inference with
the supplied actor, matching all four reference actions within 0.000016 maximum
absolute logit error. This is **not** a Windows/JJSploit speed measurement. The
current generic kernel supports verified boost entities too: in cloud Luau, two
entities took about 11 ms and eight took about 21 ms. More entities cost more CPU
time. Runtime checks and the panel report the result on your PC. No executor
input was sent during cloud validation.

This version also fixes the float attention mask: unavailable boost pads now
receive **-10000**, rather than **+1**, in the Python bridge. Local mode omits
those masked rows, which is checked against the complete PyTorch observation.
Neither change retrains the model. Local v4 also supplies observed opponents and
teammates through the actor's existing car entity features, as described below.

Local mode requires `mouse1press`, `mouse1release`, `mouse2press`, `mouse2release`,
and Roblox's buffer API. Keyboard v2 first tests normal Roblox enum key events;
if those are disallowed or ineffective it tests executor `keypress`/`keyrelease`
with virtual-key and scan-code mappings. Shift uses generic VK_SHIFT (0x10)
in the virtual-key mapping. No thread identity or game-module access is changed.
If no method changes observable key state, it stays paused with the failure
reason. A later silent keyboard failure stops the bot and requires a retest.
Keep Roblox focused, chat closed, and release physical movement keys during the
brief test. F8 cancels and releases test inputs. A passed test verifies Roblox's
input state; it does not prove that custom game controls use those inputs.

Missing functions are named in the panel. Loading the script does not press keys;
the keyboard test starts only with F6/the Start button. It reads rendered poses and HUD
values; it does not require game modules or change execution identity/remotes.

Optional exporter overrides:

```bat
EXPORT_LOCAL_BOT.bat --workspace "C:\Users\almas\AppData\Roaming\jjsploit\workspace"
EXPORT_LOCAL_BOT.bat --model "D:\Models\update.pt"
```

## Updated-place review and team tactics (local v6.2 history)

The new Beta 10 export confirms all 54 numeric constants and curve entries used
by this adapter's arena/physics profile. The existing calibration remains in use.
Twelve ball/world scenarios were also compared with the updated exported solver,
including its enabled fast geometry path. Ordinary surfaces remain close to the
reference; curved goal-frame contacts retain the documented approximation limits.
See `UPDATE_REVIEW.json` for the measured errors and source hashes.

The export includes the normal bot's decision code and the SuperBot tier settings.
The stronger tiers select `willo` and `wisp`; their model implementations were not
found in the client export. This package keeps your existing model and adds
independent ground tactics using the car poses the adapter already observes:

- **Support teammate** leaves a goal-side teammate with a clearly earlier
  estimated arrival to challenge, while covering behind the ball. Incoming
  own-goal threats take priority. Opponents, unknown teams and airborne teammates
  cannot trigger this support choice.
- Ground-shot aiming compares several goal-mouth lanes with the observed
  defenders' short constant-velocity projections. It retains the chosen lane
  through small score changes to reduce switching. This is a tactical estimate;
  opponents can change direction or jump after it is chosen.

Close touches, jumps, aerials and wall play continue through the trained policy.
No new model is trained or supplied. These changes have offline scenario and
runtime coverage, but have not been live-tested in Roblox/JJSploit and are not a
measured win-rate improvement.

After replacing this folder, rerun **EXPORT_LOCAL_BOT.bat** and execute the newly
generated private Lua file. The ready badge must show **LOCAL v6.8** for a private export. Exporting the
place itself does not update a standalone script you already generated.

## Match pad detection and stop diagnostics (local v6.1)

Rerun **EXPORT_LOCAL_BOT.bat** after updating this folder. Existing generated Lua
scripts contain the previous runtime; the current ready badge is **v6.8**.

The first live v6 report showed a measured standard ball radius and gravity close
to the saved profile, but zero discovered boost pads throughout the run. The
saved match renderer nests `BoostPads` inside `MatchView`. The old reader only
searched the scene's direct children. Discovery now follows the local car's
render view and finds nested pads, excluding unrelated views. Verified pad state
reaches both the actor and a new small detour option in ground assistance. With
low boost, it can collect a nearby active pad along its approach. It avoids
unknown/inactive pads, long detours and incoming own-goal threats.

Boundary recovery now also detects a stationary neutral policy action near a
wall or goal post. The old timer reset whenever throttle was zero, so that state
could never recover. Close-ball control, kickoff countdowns and intentional
midfield waits keep their existing behavior.

The uploaded report did **not** include the error that stopped that run; it does
not establish that error's cause. Runtime exceptions now retain the exact error,
stage, frame timing, pause reason and lifecycle events. When `writefile` is
available, the stopped run automatically saves **TurboBall_Last_Error.json** in
the executor workspace. Repeated failures while paused do not overwrite it.
The manual report keeps that original error too. Both files remain local.

Reports now include full car orientation, anonymous other-car poses, observed
pads, held/observed inputs and each decision's age. A paused trace can no longer
present an old action without marking it stale. Hitbox marker counts and nearest
preset measurements explain an unverified `standard?` fallback instead of silently
calling it measured. Last valid flight-error measurements survive pose resets.
The attached private standalone model and original diagnostics are excluded from
the public download. These fixes are covered by offline tests; a new live run is
still needed to confirm behavior and identify the earlier stop error.

## Physics-aware ground approach (local v6)

This update targets **standard soccer in place 101880234193261**. Extract it over
the existing `botrblx` folder and rerun **EXPORT_LOCAL_BOT.bat**. Keep your existing
checkpoint; no training is required to use the new controller.

**Physics assist: ON** is the default. A new independent ball/world predictor
steps at the saved game's 120 Hz, forecasting 2.5 seconds ahead with gravity,
exponential drag, friction, restitution, contact spin, speed limits and sleep.
It uses the analytic collision field and scales both collision radii from the
observed ball marker. Future car touches are unknown and are not simulated.

On the flat ground, the approach controller selects a low future ball position
using a bounded travel estimate with the saved throttle torque curve, speed cap
and finite boost. It sets up behind the ball toward the opposing goal, takes a
side approach from the wrong side, checks for an incoming own-goal trajectory,
brakes for turns and only boosts when aligned. Steering accounts for current
yaw rate. Rounded corners constrain approach targets. The frozen actor still
handles close contact, jumps, aerials and wall play; scripted kickoffs and stuck
recovery retain priority. The actor's observation format and weights are unchanged.
The flip timer now uses the saved **1.25 seconds**, and pose/nearby-car coordinates
honor the selected profile scale throughout.

The panel shows gravity in use and the median short-flight position error when
measurable. Gravity can adapt after at least six consistent isolated airborne
position windows. Near-car motion, boundary contacts, pose gaps and resets are
excluded. This does not infer arbitrary arena dimensions, friction or steering
from a few frames. A gross geometry/flight mismatch returns approach decisions
to the actor and displays **MISMATCH / model**. Unknown or alternate arenas still
need their own profile.

Pause with **F8** to switch **Physics assist: ON/OFF** for comparison. **Save physics
report** writes `TurboBall_Physics_Report.json` to the executor workspace on click.
It contains the selected numeric profile, radius/contact measurements, bounded
recent pose/control trace, calibration result and decision timing. Nothing is
uploaded. It excludes model tensors and account names. The last 150 samples at
up to 5 Hz are retained (about 30 seconds).

Offline checks compare twelve ball scenarios with numeric results from the saved
solver, including scaled balls, ramps, spin, goals and sleep. Flat-world cases
agree within 0.004 simulation units; curved goal-frame responses are approximate
and use separate tolerances. These tolerances describe these reference cases,
not an error guarantee for every trajectory. Controller scenarios cover leading
lateral motion, team mirroring, approach direction, defensive interception and
handoff to the actor. This release has **not been live-tested in Roblox/JJSploit**.
It adds a physics controller around the existing model; full adaptation of its
learned aerial/touch mechanics still requires target-physics training.

## Measured arena, hitboxes and boost pads (local v3)

`arena_profile.json` records numeric specifications recovered from the saved
place, including six car collision presets, ball/world radii, field/goal geometry,
faceted ramp angles, boost coordinates and basic physics constants. The original
place, game scripts, visual mesh assets and model weights are not in this folder.

The standard field is already 8192 × 10240 × 2048 simulation units, with a
1792 × 640 rounded goal mouth, back extent ±6000, 91.25 ball/car collision radius
and 93.15 ball/world radius. One Roblox stud is ten simulation units. Most of
these values match Rocket League; copying different-looking visual art does not
establish a different collision size.

The local runtime now:

- Queries the faceted collision volume, rounded corners, goal lips, sloped goal
  roof/floor and rear cavity instead of flat-wall height thresholds. Four wheel
  rays estimate contact using the selected car preset and measured ball radius.
- Reads the car's hidden collision box via its `SelectionBox` and matches size
  **and offset** against all six presets. Hats, rendered body bounds and the tiny
  root marker never substitute for a hitbox. If measurement fails, `standard?`
  explicitly marks the fallback estimate.
- Reads the ball's source-verified trail attachment scale marker. A `?` after its
  radius means the default was used, not that a rendered mesh was measured.
- Discovers actual boost positions from `PadHalo` objects, identifies large/small
  pads by 16/10 ring segments, and observes active/cooldown cues. Unknown colors,
  missing segments and unavailable state stay excluded. No active pads are invented.
  All discovered pads are tracked; six verified pads are supplied per policy
  decision, reserving up to two slots for nearby large pads. This keeps the local
  inference cost bounded. `Pads known/total -> used` shows the exact counts.
- Briefly overrides the policy after sustained lack of movement near a boundary,
  or when stationary upside down, with a bounded reverse/turn or upright action.
  It avoids overriding close-ball control, has a cooldown, and labels the mode in
  the panel. This is controller recovery, not a learned new skill.

`arena_collision_preview.obj` is a closed, 42,026-triangle **inspection preview**
generated from the same collision volume at a 128-unit sampling grid. The runtime
uses the finer analytic surface, not this approximate preview or decorative
Roblox mesh bounds. Its metadata records profile identity and resolution.
Maintainers can regenerate it with `build_collision_preview.py --luau <luau-cli>`;
the normal Windows exporter does not need a Luau CLI.

**Model 271 has no hitbox-size, mesh, goal-shape or physics-parameter input.** Its
existing 24-feature entity format does accept the measured boost positions and
availability, which are now used. Hitbox and arena data inform contact estimation,
recovery and the v6 ground interception controller around the policy. Loading an OBJ cannot make frozen weights learn
different bounce, friction, jump or steering dynamics. Matching those dynamics
fully requires simulator validation and fine-tuning on the target physics.
No training is launched by this update. Alternate `ArenaFree` modes are paused instead of using the standard
stadium collision shape for them.

After updating this folder, **rerun `EXPORT_LOCAL_BOT.bat`** to embed the geometry
and physics/pad adapters in your private standalone script. An optional
`--arena-profile "D:\path\profile.json"` selects a numeric profile; it does not
change model weights or create a policy mesh input.

## Automatic team selection (local v5)

Rerun **EXPORT_LOCAL_BOT.bat after installing this update**: the previous generated
standalone script contains the previous adapter. No model weights are downloaded
or retrained. The current package shows a **v6.8** badge after re-export.

The game uses its own match teams. The new reader matches your name to the
scoreboard row's team edge; it does not assume Roblox's `Player.Team` is the match
team. As a fallback, the game's teammate nameplate has a shorter plate and a
boost bar, while an opponent's does not. Agreement with its standard team color
identifies your team even in 1v1 without a teammate. Unknown or conflicting match
UI pauses input instead of choosing blue. Freeplay without an active match HUD
uses blue. Manual override remains available while paused.

Other cars use scoreboard identity where available, then the verified nameplate
relationship, then recognized standard team color. Your own team changing clears
held controls, the previous action and kickoff/recovery state before fresh poses
are used. The panel displays the selected AUTO/MANUAL side and observed counts;
opponents' hidden boost and flip state remain estimates.

This is tested with executable Luau Roblox fixtures, including an orange 2v2
player with one teammate and two opponents, a side change, and F8 release.
A live JJSploit session cannot be run from this cloud environment.

## Multiplayer and scripted kickoff

The previous local adapter supplied only your car, the ball and known boost pads.
It omitted every other car, even in matches with friends. Local v4 discovers
other rendered car roots through their `Nametag` billboards, reads team identity
from the team-colored `Plate`, and samples position, orientation, linear velocity
and angular velocity. Chassis paint, props and effects do not identify players.
Up to five nearby cars reach the policy as separate car entities, with the same
team rotation and coordinate normalization as your car. The panel reports
**Opponents / teammates / unknown**; the first two counts are the cars actually
included in that decision. Allow about half a second for discovery and a second
pose sample. Removed, hidden, teleported and newly respawned cars are excluded
until a fresh, valid pair of poses is available. Unknown team colors are excluded.
Names hidden by the game and nonstandard game modes can limit discovery.

Teammate boost comes from the rendered nameplate's boost fill when present.
Opponent boost has no corresponding HUD bar, so the actor receives an explicitly
estimated 50%, not a claimed measurement. Other cars' wheel contact and flip
availability remain estimates; spent flips cannot be recovered reliably from
rendered poses alone. More cars increase inference cost; use the panel's timing
on your PC to assess this. This supplies missing observations without retraining
271 or promising that it will make good decisions against every opponent.

Kickoff detection requires a stationary ball at its measured center/rest height,
a grounded car at one of the five standard kickoff spawns, and a car facing the
ball. It holds neutral while confirming that state. The dedicated match HUD
countdown keeps inputs neutral until the countdown ends. When that HUD is absent,
the script starts driving/boosting but starts its jump timing only when the car
actually moves. It steers toward the ball and can use one bounded front flip
when aligned and fast enough, with explicit jump release between presses.
It yields to an observed closer teammate or the standard left-goes tie priority.

The policy takes over when the ball moves, the car approaches it, or the bounded
kickoff timer expires. This is a generic scripted kickoff, not a trained speedflip
or a guarantee of winning the first touch. The panel labels the active kickoff
phase. **F8**, pause, focus loss and invalid poses release inputs and reset the
routine. The model receives the actual scripted keys as its previous action on
handoff. Normal play around a centered ball away from a kickoff spawn does not
activate the routine.

After replacing this folder, **rerun `EXPORT_LOCAL_BOT.bat`**, close the old panel,
and execute the newly exported `botrblx_standalone.lua`. Merely replacing this
folder does not update a script already running in Roblox.

## External bridge modes (fallback)

Local freeplay inference: rendered Roblox state → update271 in Python → normal
Windows keyboard and mouse events. The model stays in your existing training
project; model weights, logs and recordings are not included in this folder.

## Download only this folder

[Download botrblx.zip](https://github.com/DMDIASSS/Chat_GPT_AI/raw/refs/heads/codex/native-quality-campaign/downloads/botrblx.zip)
contains only the `botrblx` folder, including the Python bridge, Lua clients,
launchers and templates. Extract it into `E:\Downloads\Chat_GPT_AI`, replacing
the existing folder's application files after stopping the bridge. Your existing
training environment and model stay in the project. This ZIP is stored separately
from full-repository archives and can be downloaded for bridge updates.

## One-shot connection diagnostic

For file errors, run this before changing the transport again:

1. Close the bot panel and stop the bridge CMD with Ctrl+C.
2. Double-click **`DIAGNOSE.bat`** in the updated `botrblx` folder. It uses the
   saved workspace or `%APPDATA%\jjsploit\workspace`. Wait for **`READY DIAGNOSTIC`**.
3. Execute this in JJSploit:

   ```lua
   loadstring(readfile("botrblx_diagnose.lua"))()
   ```

4. Wait for **`DIAGNOSTIC COMPLETE`** in CMD. Send the single file
   **`botrblx\DIAGNOSTIC_REPORT.txt`**. The Lua tests normally take about 10–30
   seconds; CMD allows five minutes for launching the script and transferring it.

If loading the installed script fails, open
`C:\Users\almas\AppData\Roaming\jjsploit\workspace\botrblx_diagnose.lua` in
Notepad and execute its complete contents. That is the configured script;
`JJSploit_Diagnose.lua` in this folder is its source template.

The tool tests flat and nested paths, `/` and `\`, short and long filenames,
file/directory metadata, Python-created versus Lua-created files, overwrite
visibility, immutable replies, two fresh generations and timing. It records API
errors individually and compares them with Python's actual filesystem view.
It does not import Torch, run the model, load game modules or send game inputs.
Only dedicated diagnostic files are written and cleaned up; the report remains
on your PC. It contains source fingerprints and test outcomes, with credentials
redacted and live mailbox contents excluded.

If report export fails, the Roblox panel keeps a copyable report: click its text,
Ctrl+A, Ctrl+C. CMD also saves a partial report on timeout or Ctrl+C. Optional
workspace override: `DIAGNOSE.bat --workspace "C:\path\to\workspace"`.

## JJSploit / WRD: file mode

### Normal start (WRD compatibility profile)

1. Stop old bridge/diagnostic CMD windows and close old bot panels. Extract the
   folder-only ZIP into `E:\Downloads\Chat_GPT_AI`, replacing the application files.
2. Double-click **`START_FILE_BOT.bat`**. It reuses the saved workspace or finds
   `%APPDATA%\jjsploit\workspace` automatically. Wait for **`READY FILE MODE v3.2 WRD`**.
3. In freeplay, execute `loadstring(readfile("botrblx_client.lua"))()` in JJSploit.
4. Press **F6** to start/pause; **F8** stops Windows inputs immediately.

The supplied diagnostic measured working paths with **1.2–1.3 second file round
trips**. Client v3.2 waits four seconds for a response, and file-mode input expiry
is three seconds. Focus loss, F8 and Ctrl+C still release inputs immediately;
duplicate requests do not refresh expiry. Pose sampling runs independently on
Heartbeat, so a slow reply does not invalidate every car/ball velocity sample.
The panel displays link latency separately from model inference time.

This profile fixes the measured timeouts; it cannot remove WRD's underlying
transfer delay. Reaction speed is limited by that delay. HTTP mode keeps its
0.4-second telemetry expiry and still requires a working localhost API.

The reported WRD HTTP request returned **403, Wrd Server Error: Connection
Failed**, without reaching Python. Loading Lua locally alone does not fix that:
telemetry also needs a working transport. File mode replaces HTTP entirely.
It requires working executor `readfile` and `writefile` functions.

1. Replace the complete `botrblx` folder in `E:\Downloads\Chat_GPT_AI` with this
   version. Stop the old bridge with Ctrl+C and close its Roblox panels.
2. Run **`START_FILE_BOT.bat`**. The first launch opens a folder picker.
   Select **JJSploit's workspace root**: the folder its `readfile` and `writefile`
   functions use. This is not automatically your training project folder.
3. Wait for **`READY FILE MODE v3.2 WRD`**. Python installs `botrblx_client.lua` in that
   workspace and creates its own `botrblx_exchange` subfolder. Keep Python open.
4. In freeplay, execute the complete **`JJSploit_File_Launch.lua`** file.
   It loads the installed Lua client from that workspace without a download.
5. The panel should show **Connected / PAUSED**, and Python should log
   **`CLIENT_HELLO`**. Then press **F6** to drive; **F8** stops inputs.

The folder choice is saved in local, ignored `file_connection.json`. To choose
again, run `START_FILE_BOT.bat --reset-workspace`. If the picker is unavailable,
use `START_FILE_BOT.bat --workspace "C:\path\to\executor\workspace"`.

If you do not know the workspace location, execute this file-function test:

```lua
writefile("botrblx_workspace_probe.txt", "botrblx workspace test")
```

Locate that file in your JJSploit installation/workspace and select its containing
folder. The script creates only that text file; it does not send controls.
`function function` from `print(type(readfile), type(writefile))` confirms the
functions exist, but the handshake above verifies the actual shared folder.

**File not found** in the launcher means the selected workspace differs from
the executor's workspace. A **No matching file reply** message includes the last
read/decode failure, a mismatched request ID, or another client's reply.
`CLIENT_HELLO` in Python confirms a request arrived; `FILE_REPLY: hello ... written`
confirms Python wrote the response. `FILE_REPLY_BLOCKED` reports an OS write error.
Look for `request.json` under `botrblx_exchange` and request-specific JSON replies
inside its `replies` subfolder. Do not paste full replies into a report because
they contain a local session token.

Version 3 publishes a separate reply file for each session/request ID. Once
published, its contents are not updated; a reader caching bytes by filename can
still obtain each new response from its new filename. Lua polls `readfile`
directly and retries missing/incomplete replies; existence metadata never gates
the read. Python retains the newest 16
replies and removes older ones; files held open by Windows are retried for cleanup.
Reply waits are four seconds; file-mode telemetry expires after three seconds.

**Upgrade both Python and Lua together for v3.** Stop the old bridge and close
its Roblox panel, replace the complete `botrblx` folder, restart the BAT, then
execute `JJSploit_File_Launch.lua` again. Older clients use one shared reply file
and cannot communicate with v3. Session and request-ID checks remain required;
an older reply never substitutes for the current response.

Client revision **v3.2** includes the measured-delay profile and independent sampling;
it also removes the `isfile` gate that could stop every read.
Update Python and Lua together for the WRD compatibility profile. Restarting
`START_FILE_BOT.bat` installs the matching client in the executor workspace;
the file launcher loads that installed copy.

File mode exchanges bounded JSON requests and replies, with per-client sessions,
fresh tokens, sequence checks and a stale-frame limit. It does not execute code
received from a request file. Python still performs inference and Windows input.
The Lua model is not embedded in the loader. No HTTP server is opened in this mode.

## HTTP mode (requires working localhost requests)

1. Update/download the complete `botrblx` folder into
   `E:\Downloads\Chat_GPT_AI\botrblx`.
2. Double-click `START_BOT.bat` and wait for `READY`. Keep its console open.
   It uses the project's existing `.venv`; no native rebuild is required.
3. Enter freeplay as `Deadline_coolgun` in place `101880234193261`.
4. Execute the contents of `JJSploit_Launch.lua` in JJSploit.
5. Close menus/chat and press **F6** to start or pause. **F8** stops inputs.

Copy the Lua file as plain text using GitHub **Raw**, your editor, or a code
block's Copy button. Do not include Markdown such as `**f**`, backtick fences,
or `[http://...](http://...)` in the executor; those are not Lua source.

`JJSploit_Launch.lua` first displays a **botrblx launcher** panel, then fetches
the client. Download, compilation and client-start errors stay visible in its
copyable text box. On successful startup, this panel closes and the main
**Update271** control panel remains. Execute the launcher file, not the Python
file or a browser's rendered text.

If the launcher reports **no response body**, the HTTP function did not return
usable source code. The adapter tries distinct `request` and `http_request`
functions and remembers the working one. It accepts raw body strings, common
response fields and APIs returning `(success, response)`. Failure messages show
the response type, field names/types, status and error message; header values
and session tokens are not printed. The same adapter handles live telemetry.

You can skip the code download completely: close the launcher panel, then open
`client271.lua` from this folder and execute its full contents directly in
JJSploit. That file is the standalone client and creates the main control panel.
It still needs an HTTP connection to Python for game state and model decisions;
an empty `/hello` or `/frame` reply is reported in that panel with the API details.

If the executor supports `readfile`, the launcher also tries the local workspace
paths `botrblx/client271.lua` and `client271.lua` after an HTTP download failure.
These paths refer to the executor's workspace, not the Python project directory.
Place the client there explicitly to use this optional local loading fallback.
`templates/http_compat.lua` is an internal source template, not an entry point.

Use the default bindings: WASD, Q/E air roll, Shift powerslide/free roll,
left mouse boost, right mouse jump. Disable mouse steering, pitch inversion
and aerial safety. Buttons hide during driving so injected boost clicks cannot
activate them; F6/F8 brings the controls back.

Focus loss and stalled telemetry release inputs and require Start again.
Goal/reset waits release inputs and resume when valid poses return.
Ctrl+C in the Python console exits and releases inputs.

## Files and startup errors

- `launcher.log` is created immediately, before Python is invoked. A missing
  interpreter or missing bridge/client file is reported here and in the console.
- `bridge.log` is created by Python before importing Torch/NumPy or loading the
  model. Dependency, checkpoint, or port errors are reported here.
- Neither log requires executing the JJSploit client first.

The Python console logs `CLIENT_DOWNLOAD` when the launcher requests `/client`
and `CLIENT_HELLO` when the Lua client connects. The read-only `/` and `/health`
routes return model/client status without starting, pausing, or reconfiguring
the bot. `model_loaded: true` with `client_connected: false` means Python is
ready but the Lua client has not begun streaming. Older versions returned
`Unknown route` at `/`; that response did not indicate a model-loading failure.

The launcher tries the checkout containing `botrblx`, then the existing
`E:\Downloads\Chat_GPT_AI` project. It also works when the whole folder is copied
elsewhere while that training project remains at its known path. An interpreter
path error in the old launcher meant Python never started, so there was no
`bridge.log` to inspect.

Optional overrides in Command Prompt:

```bat
set "BOTRBLX_PROJECT_ROOT=D:\MyFolder\Chat_GPT_AI"
set "BOTRBLX_PYTHON=D:\MyFolder\Chat_GPT_AI\.venv\Scripts\python.exe"
START_BOT.bat
```

The default checkpoint is
`data/isolated/mechanics_curriculum/selected7_mechanics01/update_000271.pt`
under the selected project root. The native checkpoint loader uses the existing
`vendor/nexto/nexto-model.pt` wrapper. Both native actor dictionaries and
TorchScript exports are supported. Checkpoints are read without modification.

To verify setup without sending inputs or opening the server:

```bat
START_BOT.bat --self-check
```

## Scope and validation

Local v5 targets standard soccer matches and freeplay, with scripted standard
kickoffs, team-verified other-car observations and verified live boost entities.
Rendered-pose velocities and wheel/flip state remain estimates. External bridge
clients still target freeplay and omit other cars; they mask pads unless observed
pad data is sent.
WASD couples controller axes. These limits
can affect policy performance compared with Rocket League or the browser
extension; this is not a claim of equivalent match strength.

The client reads rendered poses and HUD values. HTTP mode posts JSON only to
`127.0.0.1:28771`; file mode uses the chosen local workspace instead.
Neither mode requires game modules or changes game remotes,
execution identity, or server code. The HTTP server binds only to loopback and
rejects browser origins; there is no external model service or API key.

Development checks use Python's standard unittest runner:

```sh
.venv/bin/python -m unittest discover -s botrblx/tests -v
```

Model/HTTP tests use temporary synthetic checkpoints. An additional integration
case exercises the bundled Nexto actor when that local asset exists. Set
`LUAU_BIN` to a Luau interpreter to run the mocked Roblox client cases; those
cases are explicitly skipped if Luau is unavailable. Windows/JJSploit execution
still requires validation on the user's PC.

`JJSploit_File_Client.lua` is a generated standalone copy of `client271.lua` with
`templates/file_transport.lua` substituted for the HTTP block. The installer
generates the same source when copying it to the executor workspace. The tests
check that both copies share the same telemetry and control code.
