CAR SOCCER COMPATIBILITY UPDATE — 4.5.3

The uploaded Car Soccer HAR includes the full main-B95SF9Gf.js gameplay
bundle (SHA256 605448d5ef0bbff6a014fe723702875f925145220223392a0c5501f4306ca96b).
This release adds its verified variable bindings for AI, TAS, state fields,
rendered ball, all six offline physics hooks and multiplayer bot helpers.
The original multiplayer tick expression and native physics factory remain
unchanged. The previously supported main-DVUMtcmY.js still passes its checks.

INSTALL: copy these files INSIDE your existing unpacked extension folder,
keeping that same folder/extension ID and existing private model binaries.
Reload it at chrome://extensions, then reload https://car-soccer.com/.
Use Enable + reload if necessary. Confirm version 4.5.3 in the popup.
Use F7 to select an existing model or TAS; F8 returns control.
No model re-import or retraining is required by this compatibility change.

VERIFIED: actual new bundle transformation/syntax, injected runtime and visual
bindings, AI controls/neutral restoration, TAS tick order, fun-control hotkeys,
async cancellation, model storage and UI fixtures. The actual new embedded
WASM physics passes synthetic-floor TAS restore/ticks, boost, jumps, both-team
goals, steering, powerslide, combined effects and speed tests. These checks
are not a live multiplayer or full-arena recording-success measurement.
Full-page offline replay cannot reproduce the original service-worker startup
from these saved files; no live match was played.

TURBALL STATUS: your earlier Turball HAR still lacks chunk-KALAXRXF.js,
referenced by lobby chunk-DLWGG6LS.js in release 98f9b3003e60-41220884867-1.
New Turball gameplay compatibility is NOT verified. Its old strict patch is
retained and unsupported builds are passed through unchanged.
Enable + reload on Turball, enter Free Play, reopen the popup and click
Save gameplay JS. Upload that saved .js to complete the Turball adaptation.
Save diagnostics is optional. Captures stay in session storage until a new
scan or tab close, survive worker sleep, and are never auto-uploaded.
Only the extension popup can export gameplay source. The smaller connection
report omits gameplay source, HAR data, cookies and account information.

No game HTML/JS/WASM assets, HARs, account data or model weights are bundled.
The separate SingleFile HTML snapshot has no executable gameplay scripts;
its archive-only security policy is not changed by this extension.

CAR SOCCER + TURBALL AI TRAINER 4.5.3
===================================

NEW: Car Soccer fun controls. Read FUN_CONTROLS.md for keys and host/local scope.
4.5.3 fixes steering with effects enabled and adds friend-hosted controls.
Both players update; the host enables "Allow friend controls", then the joining
player clicks "Connect to friend's host". The friend keeps hosting normally.
TAS playback and minimize/restore are retained; see TAS_README.md.
For an existing installation, replace files INSIDE your existing extension
directory and click Reload in chrome://extensions. Keep private .bin files.
Loading a different folder as a new extension changes its storage identity.

TAS: standard Free Play > F7 > TAS > Upload TAS files > Play TAS from start.
Play restores the recorded car/ball position, rotation and velocities.
Select the recording's boost setting. F8 stops. The minus button minimizes
the panel without stopping playback; the Trainer button or F7 brings it back.

Latest Turball build: the uploaded HAR references chunk-TVJT3ATP.js but does
not include its body. Live compatibility with this build is not yet verified.
See NEW_TURBALL_BUILD_README.txt. Unsupported builds are left unchanged.

ONE CHROME EXTENSION FOR TWO WEBSITES
  https://car-soccer.com/
  https://turball.io/

The extension automatically detects the hostname when the game is opened
or reloaded, arms the matching patcher, and injects the game-specific
trainer runtime when that site's gameplay JavaScript loads.

Car Soccer uses patcher.js (the existing Car Soccer 4.2.7 code patch).
Turball uses turball-patcher.js (the Turball 4.2.7 experimental port).
The patchers must NOT be interchanged: each targets different minified code.

INSTALLATION
1. Extract the ZIP. Do not load the ZIP itself.
2. In Chrome, open chrome://extensions and enable Developer mode.
3. Choose "Load unpacked" and select Car_Turball_Auto_Trainer_v4.5.3,
   the directory containing manifest.json.
4. Disable/remove the previous separate AI trainer extensions before
   using this one; multiple extensions trying to patch the same page can
   conflict with Chrome's debugger attachment.
5. Open or reload https://car-soccer.com/ or https://turball.io/.
   The extension automatically recognizes the website and patches it.
6. In the extension popup, look for "patched" in the Game connection
   status. If it is still "armed", start a game: the Turball gameplay
   module is loaded on demand. If a game loaded before interception,
   click "Enable + reload" once to retry.

HOW TO USE
- On either supported website, the trainer overlay shows its model picker.
- F7: show model picker / free the pointer lock.
- Give Control: activate the currently selected AI.
- F8: immediately give control back to the player.
- Extension popup: import, rename, select and remove compatible
  Nexto models in .pt, .zip or .bin form.
- "Disable": restore the unmodified game and pause automatic patching
  for that browser tab until "Enable + reload" is pressed.
- Imported models are in this extension's own Chrome local storage and
  are shared between the two game websites.

KNOWN LIMITATIONS / HONEST TEST STATUS
- This package was verified against the exact Car Soccer JavaScript and
  Turball chunk present in the user's supplied network captures.
- Car Soccer: main-DVUMtcmY.js (patch and existing tests passed).
- Turball: chunk-IORKFJL5.js, build 6ecc13b81511-38608307515-1.
  Turball was verified by applying the patch and syntax checking the output.
- The Turball port is EXPERIMENTAL and was not live-playtested in Chrome.
  Its online/multiplayer input path is also unverified in real matches.
- The two source packages contain NO G9 or Nexto model weight binaries.
  You must supply compatible weights for those worker-based options.
  Turball's native Nexto option can be used without an imported model,
  subject to the game's own runtime availability. It is not identical to
  the original Car Soccer Grand Champion option.
- After a site update, a hashed gameplay module may change, invalidating
  an anchor or filename. If the popup says "armed" forever (even after
  starting a game) or "error", obtain a fresh HAR and gameplay chunk for
  that site so the patcher can be updated safely. We intentionally avoid
  rewriting unrecognized third-party JavaScript.
- The Chrome `debugger` permission is required to intercept the original
  gameplay module; Chrome may show a temporary debugging notification.
  The extension detaches after a successful one-time patch.
- Old models stored by separately installed extensions do not transfer
  automatically to this newly installed extension; reimport them here.

CARRIED-OVER FILES
- patcher.js, turball-patcher.js: separate site-specific runtime patches.
- content.js, background.js, popup.*: shared website-aware integration.
- model-*.js, nexto-*.js, kickoff.mjs: original Nexto inference/import.
- The original helper BAT/Python tools are retained for users who want
  to use them. Direct browser model importing does not require them.

Static verification completed on 2026-10-15.

V4.3.1 TURBALL UPDATE DETECTION (HISTORICAL)
- A newer Turball build 332c59c495f7-38732477493-1 was observed.
- Its loader imports chunk-TVJT3ATP.js, instead of the previous chunk-IORKFJL5.js.
- Turball now detects the gameplay chunk by its `export { ... as startGame }`
  signature, including future filename/hash changes, and ignores other chunks.
- IMPORTANT: The supplied new HAR did NOT include chunk-TVJT3ATP.js itself,
  so its compatibility with the existing Turball patch cannot be confirmed.
- If popup shows `unsupported`, the game is left unmodified. Please capture
  chunk-TVJT3ATP.js from DevTools > Network > JS while entering Free Play,
  then save the Response as a JS file and send it to update the patch anchors.
- Chrome debugger permission is still needed; it stays active while waiting
  for a gameplay chunk and detaches after a patch or compatibility failure.

EXPERIMENTAL BALL VISIBILITY WORKAROUND (4.3.2)
F9 toggles the anti-clip guard on/off. It is ON by default.
When the ball is close to arena side/end walls, its meshes temporarily render after the arena without wall depth/clipping so an invisible-wall depth artifact cannot cut them in half.
This is a rendering-only workaround: it does not move the ball, change physics, or alter bot position observations.
Trade-off: near walls the ball may appear through the nearest wall or a car. Press F9 to turn the workaround OFF if you prefer the original renderer.
It has been syntax-checked and regression-tested against available captured bundles, but the screenshot issue has not been reproduced live.
