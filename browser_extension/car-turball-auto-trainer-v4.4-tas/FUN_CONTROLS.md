# Car Soccer fun controls — 4.5.1

This update fixes left/right steering and powersliding with continuous effects.
It also adds friend-hosted control with both players running this update.

Copy this update's files **inside your existing unpacked extension directory**,
keeping private model binaries, then click **Reload** on `chrome://extensions`
and reload Car Soccer. Keeping the directory preserves its extension ID and
stored models. No model, importer or Python process is needed for fun controls.

Open **Fun controls · Car Soccer** in the panel. You can use the buttons or the
following keys with the game focused; chat and text fields are ignored.

| Key | Effect |
| --- | --- |
| **G** | Toggle ball glue above the hood, following your car's position and rotation. |
| **B** | Toggle your car's infinite boost, including matches using limited boost. |
| **J** | Toggle extra air jumps/flips. Release and press the normal jump button again for each jump/flip. |
| **V** | Toggle the speed override. Default 6,000 units/s; choose 2,300–10,000 in the panel. |
| **H** | Bring the ball to the hood once. |
| **L** | Launch the ball toward the opponent net, using your current team. |
| **P** | Teleport the ball inside the opponent goal. Normal game scoring detects it on the next physics step. |
| **F8** | Turn off fun controls and AI/TAS takeover. |

The **−** button minimizes the menu while effects continue. Click the small
**Trainer** button or press **F7** to reopen it. Focus loss, a hidden tab, a
changed car/session or losing host authority turns continuous effects off.
Launch and goal teleport release ball glue automatically. Ball glue pauses
during match countdowns/goal pauses and resumes during active play.

## Playing with friends

Your friend can keep hosting for their better connection:

1. **Both players install 4.5.1**, reload the extension, and reload Car Soccer.
2. The host opens **Fun controls · Car Soccer** and switches **Allow friend
   controls** to **ON**. Hosting and driving continue normally.
3. You join a team, open your fun panel, and click **Connect to friend’s host**.
4. Use the same effect buttons or keys. The host applies effects to **your car**,
   and your client mirrors the acknowledged effects for prediction.

The shared ball actions use your team when choosing the opponent goal. One
friend can own the effects at a time; host controls take ownership back. Other
players keep their ordinary boost and car physics. Both teams are supported.

**The host needs this update and must enable the option.** Unmodified hosts
overwrite client-only physics changes. This mode uses the existing reliable
peer connection and native message validation; it does not remove that authority.
Extension frames are consumed before normal chat on updated peers. A connection
attempt to an unmodified host may appear as one encoded chat message.

Host **F8**, focus loss, starting AI/TAS, or leaving the room stops the effects
and turns friend access off. Re-enable it when resuming. Losing heartbeats stops
friend effects within four seconds. Your F8 asks the host to stop your effects.
Local/offline play and hosting without friend control still work as before.

The fun panel and hotkeys are **Car Soccer only**. Turball's existing AI/TAS
adapter is retained and gets no fun controls from this update.

## Behavior and limits

- Infinite boost refills **your car**, without enabling the global unlimited
  boost rule for other players.
- Extra jumps/flips re-arm native jump state on real jump-button edges. Holding
  jump is not an automatic jump spammer; directional input still chooses the
  flip, and neutral input can produce an air jump.
- The speed override bypasses the usual 2,300 units/s clamp through per-step
  velocity restoration. It changes actual integrated motion, not a HUD number.
  It has a configurable finite ceiling of 10,000 units/s; it is not literally
  unbounded. Boost/throttle provide extra acceleration while it is on. Collision
  responses can still slow or redirect the car. Normal limiting returns on the
  next physics step after switching it off.
- Ball launch aims a ballistic shot but does not guarantee a goal through cars
  or walls. Teleport places the ball inside the goal and lets the normal scoring
  path handle it; this does not directly edit a scoreboard or fabricate stats.
- Standard-arena native checkpoints are validated against observable body poses
  before editing. Custom maps, unknown native layouts and spectators are refused.
  Failed state writes roll back rather than leaving a half-applied checkpoint.
- Per-step edits retain native wheel steering and rotation for every car. The
  normal snapshot restore clears these values; repeatedly clearing them was the
  cause of the previous update's steering failure. Unchanged state is not restored.
- Effects act on the current world. Turning them off does not rewind scored
  goals or restore the car and ball to their earlier positions.
- Enabling fun controls returns AI/TAS control to the player. Starting AI or TAS
  disables fun controls so that recordings and the policy keep their normal
  physics. An AI worker finishing after F8 cannot re-enable a cancelled takeover.

## Validation

The uploaded `main-DVUMtcmY.js` passes full transformation and syntax checking.
Its actual native WASM physics engine passes own-car boost tests, moving ball
glue, goal detection after teleport for both teams, three consecutive air flips
from an already spent flip, and speed tests measuring both velocity and distance.
The overspeed test travelled about 2,498 units in 0.5 s versus 1,169 with the
ordinary clamp. The override also accelerated from rest to about 4,875 units/s.
The normal cap returned after disabling the override.
Left and right turns now pass for both cars with every continuous effect alone
and with all four combined. Powerslide turns also pass, and refreshes add no ticks.
Two-peer tests exercise the actual game text sanitizer/message parser and native
physics: friend-only boost, the joining player's prediction, team-aware goals,
host opt-in/revocation, normal chat, timeouts, F8 and leaving a room.

Those tests use a synthetic floor, not copied arena assets. They verify native
state/motion/scoring behavior, not every wall interaction or a live match. Runtime
tests cover host-only writes, guest rejection, hotkeys, chat-field exclusion,
F8/focus stops, wrapper restoration and cancelled asynchronous AI startup.
Chromium UI checks cover toggle buttons, speed selection, minimize/restore and
F8 while minimized, plus absence of this panel on Turball. No live match with
friends was played in this environment; peer presentation may still need tuning.

Developer checks:

```sh
node test_fun_controls.mjs
node test_fun_physics.mjs /private/path/main-DVUMtcmY.js
node test_fun_coop.mjs
node test_fun_coop.mjs /private/path/main-DVUMtcmY.js
node test_fun_runtime.mjs /private/path/main-DVUMtcmY.js
python test_fun_browser.py
```

The download excludes model weights, uploaded TAS recordings, HARs, original
game JavaScript, native engine binaries and original collision assets.
