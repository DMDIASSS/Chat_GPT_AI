# TAS playback — 4.4.0

Update the files inside your **existing unpacked extension directory**, then
click **Reload** on `chrome://extensions` and reload the game tab. Keeping the
same extension directory preserves its ID and imported model storage. This
download contains source only; retain any existing private model binaries.
TAS itself does not require a model, Python or an inference worker.

1. Open **standard Free Play** and wait for the trainer panel to connect.
2. Press **F7**, choose **TAS — recorded inputs**, then **Upload TAS files**.
   You can choose several `.data` files and switch with the Recording selector.
3. Match the recording's car, ball size and boost setting. Starting boost can be
   100%, 33%, 0% or unlimited; it is not reliably identified in the legacy files.
4. **Restore starting car + ball** previews the saved setup. **Play TAS from
   start** always restores both bodies again, including rotations and velocities,
   before running the input sequence. No manual drive to a kickoff is required.
5. **F8** or **Stop TAS** returns control. **Play** restarts from the beginning.

The **−** button minimizes the entire menu to a small **Trainer** button while
playback continues. Click that button to restore the panel, or press **F7** to
restore it and open the picker. F8 works while minimized. Changing the selected
model stops the current takeover. Losing window focus, hiding the tab, entering
an online room, a physics reset or skipped simulation ticks also stops TAS.

## File and playback behavior

The supplied legacy files have a version-1/count header, 32-byte input records
and a 128-byte state trailer. The trailer contains integer UE3 rotations and
padding bytes, so interpreting every word as a float is incorrect. The reader
extracts car/ball position, rotation, velocity and angular velocity. Files are
treated as data and are never executed. Invalid lengths, versions, vectors,
analog values and unsupported flag ranges are rejected before state is written.

Controls follow the legacy BakkesMod ControllerInput order: throttle, steer,
pitch, yaw, roll, DodgeForward, DodgeStrafe. Button masks use handbrake=1,
jump=2 and boost=4|8; Jumped=16 is not an additional held jump. The two dodge
channels are redundant with pitch/yaw in the supplied inputs and are retained
in the original binary but are not independent controls in these games.
Upper flags 32/64 have no mapped car action. The recording producer's complete
metadata schema is not independently verified; this is a legacy-format adapter,
not a universal `.data` reader.

Playback applies **one input record per 120 Hz simulation step**. Browser
`setInterval`, display refresh rate and model inference do not drive the frame
counter. Duplicate hooks at one physics tick reuse the same record, preserving
jump press/release edges. Turball physics batches are split into individual
steps while TAS is active. Scripted AI kickoffs are bypassed during TAS.

The state restore uses the native physics checkpoint API and checks its layout
against observable body poses before writing. It checks the native state again
afterward, rolls back rejected changes, resets camera smoothing, and neutralizes
other cars' inputs. It does not write to the rendered state array or send a
teleport request to a server. Automatic positioning is supported in local Free
Play, where that state is authoritative, rather than online rooms.

**These files do not all start with the ball at center.** Four of the five
uploaded examples have the ball away from center; several start with nonzero
velocity. The saved setup is used rather than a guessed kickoff. Even the file
named `2 player tas.data` exposes one 32-byte input stream per frame, not a
separate recording for each car. Only one recorded car is played; other cars'
inputs are neutralized. Pads reset with the local kickoff baseline because
these legacy files do not provide a verified pad-state snapshot.

The original game physics, arena limits, car hitbox and ball size still apply.
Rocket League TAS inputs can diverge in Car Soccer/Turball despite correct
starting poses and exact tick ordering. Some uploaded coordinates are outside
the usual standard-field play area. This version restores them as recorded;
it does not change collision geometry or promise the recorded trick succeeds.

## Compatibility and validation

- **Car Soccer:** the full supplied `main-DVUMtcmY.js` passes transformation and
  syntax checks. Its actual native WASM engine accepts the saved position,
  rotation, linear/angular velocity and selected boost for all five uploads.
  Every supplied input frame also passes consecutive simulation-step playback to completion. The native test uses a synthetic flat
  floor, so it validates state/tick behavior, not full-arena trick outcomes.
- **Turball:** UI and patched adapter behavior pass tests, including physics
  batches, jump edges, F8, focus loss and mode changes. The patch retains the
  supplied extension's verified control-flow signatures. The newest uploaded HAR
  includes only the loader's reference to `chunk-TVJT3ATP.js`, not that gameplay
  file's contents. **Live compatibility with that newer Turball build remains
  unverified.** See `NEW_TURBALL_BUILD_README.txt` to capture the missing file.
- Chromium tests exercise binary upload, multiple-file selection, restore/play
  commands, minimize/restore, F7 toggling and F8 while minimized on both hostnames.
- Existing model-library, Nexto restore, model-picker and runtime checks pass.
- No live browser match was played during these checks. No uploaded recordings,
  HARs, original game code, native engine or model weights are included here.

Developer checks (Node.js; Chromium/Playwright for the UI tests):

```sh
node test_tas.mjs
node test_tas_adapters.mjs /private/path/main-DVUMtcmY.js
node test_tas_physics.mjs /private/path/main-DVUMtcmY.js /private/path/example.data
node test_game_bundle.mjs /private/path/main-DVUMtcmY.js
node test_runtime.mjs
node test_model_library.mjs
node test_nexto_restore.mjs
python test_tas_browser.py
python test_picker_browser.py
```
