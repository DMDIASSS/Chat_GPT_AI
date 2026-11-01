# Backseat Rally Assist 1.1.0

A standalone Roblox client GUI for **Backseat Rally**, starting with Pine Forest
in place **94278659624110**. It contains independent control code, numeric road
profiles and the game's recorded menu driving lines. No Python, training, model
download or background bridge is needed to run the generated Lua file.

## Start

1. Extract `Backseat_Rally_Assist.zip`.
2. Execute **Backseat_Rally_Assist.lua** in your Roblox executor. For a file placed
   in its workspace, use:

   ```lua
   loadstring(readfile("Backseat_Rally_Assist.lua"))()
   ```

3. Sit in the **Driver** seat. The GUI starts with assistance disabled.
4. **F6** enables/disables manual driving assistance. **F7** enables/disables
   autodrive and enables assistance if needed. **F8** stops and releases controls.
5. **F9** toggles **Road assist** independently of the power/turn/grip boosts.
   Road assist is on by default once assistance is enabled.

Drag the title bar to move the window. **–** minimizes/restores it while driving
continues. **×** closes it, disconnects the controller and restores handling/input
settings owned by this GUI. Running the script again shuts down the previous copy.
After travelling to a different Roblox place, run the script there again.

## Controls

| Control | Range | Effect |
| --- | --- | --- |
| Speed / power boost | 1–3× | More acceleration and a taller gear range when the native chassis is accessible; otherwise grounded acceleration assistance. |
| Turn response boost | 1–2.5× | Faster steering and more available angle; damped yaw assistance in fallback mode. |
| Grip boost | 1–3× | More native tyre grip; grounded slip damping in fallback mode. The planner does not mistake fallback damping for additional tyre grip. |
| Brake force multiplier | 1–4× | Multiplies native brake force, or supplies additional grounded braking in fallback mode. Stopping predictions account for the setting and available native tyre grip. |
| Autodrive speed cap | 50–260 km/h | Upper bound; corners, stability, surface and obstacles can require lower speeds. |
| Extra road-edge clearance | 0.5–3.5 studs | Additional space outside the car's rotated footprint, including its width and length. Narrow bridges also reduce the available corridor. |
| Reference preference | 0.60–1.25× | Strength of the optional showcase/ghost lateral preference. It does not set speed or replay a clock. |

Set an individual multiplier to **1×** for its original value. The defaults are
1.40× speed, 1.20× turn, 1.20× grip, 1.50× brakes, 1.2 studs of extra clearance,
180 km/h and 1.00× reference preference. Higher power
does not make every corner faster. The saved stage configuration lists 190 studs/s
(about 192 km/h) as its plausible-speed threshold; higher settings can encounter
the game's own correction or validation.

The native input adapter uses an ordinary `require` of the already-loaded client
modules when permitted. It verifies that the game's reader actually calls the
adapter. It does not change thread identity. If that route is unavailable, it
tests keyboard backends and accepts one only when Roblox observes keydown and
keyup. Release physical movement keys during that short check. Missing/ineffective
input APIs leave autodrive disabled with an explanation in the status area.

When native client access is available, the controller also uses the current
vehicle's surface/wetness and the game's own corner/braking preview. The fallback
uses the independent numeric route and conservative estimates. Digital steering
accounts for the game's different turn/return rates; partial pedal commands are
preserved rather than being treated as full throttle/brake. Changing a car
build causes the handling adjustments to be reapplied from its new baseline.

Autodrive uses automatic gears temporarily. Manual controls and that preference
return on stop. Menus, chat, replay/knockout states and lost driver ownership
release control. Focus loss pauses assistance; **F6** restarts it. A large frame
stall suspends the controller instead of applying an old input.

## Road assist and autodrive

Road assist predicts lateral movement near the road boundary and applies inward
correction, yaw damping and risk-based braking. It allows movement inside the
usable corridor instead of fixing the car to the exact center. Roll/pitch damping
follows the measured ground normal; conservative cornering limits also account
for rollover risk when grip is high. These are physics forces, not position
teleports. Turning Road assist off leaves the selected handling boosts available.

Autodrive searches 36 combinations of lateral path and power/braking choices over
approximately 1.6 seconds, replanning at up to 10 Hz. It models steering response,
slip and braking, checks the full car footprint against road boundaries and
ray-detected obstacles, and rewards progress and throttle where a feasible path
exists. A longer curvature/braking preview reduces speed before tight corners.
When all predicted paths leave the corridor, it prioritizes braking.

Road assist and autodrive reduce risk; road profiles, sparse obstacle rays and
an approximate vehicle model cannot guarantee that every collision or rollover
will be prevented. Extreme boosts can make the car harder to control.

## Driving lines and ghosts

- **Road** is the default. It plans within the stage's usable road corridor.
- **Showcase** uses the recorded menu driving line as a weak lateral preference
  while the predictive planner chooses steering and speed. Numeric references
  for the seven saved stages are included.
- **Personal ghost** prefers a full-stage ghost that the game has already loaded
  for your car. If none is available, it explicitly falls back to Showcase.

The menu recordings are **not labelled as leaderboard/world-record runs**. This
GUI does not claim that they are the best runs, fetch other accounts' private
ghosts, or submit/alter scores. A different car, setup, surface or collision can
produce a different result even when using the same line.

To learn a visible personal ghost, enable **Learn loaded ghost**, start a fresh
run with the game's ghost available and let it finish. It watches the displayed
ghost, derives speed from its movement and rejects resets or a capture begun
mid-run. When an entire ghost payload arrives normally, it can use that more
precise data directly. **Save ghost lines** writes `BackseatRally_Ghosts.json` to
the executor workspace; **Load ghost lines** restores that local file next time.
Captures are separated by stage/car. Nothing is uploaded.

Start on the stage road or near its start. The controller can approach the start
slowly from the nearby service area, but it is not a navigation planner for every
parking lot or off-road location. If far from the road, it brakes and asks for
alignment. It waits for the countdown and brakes after the finish. A bounded
obstacle search can steer around detected obstructions when there is space;
otherwise it brakes. At a standstill it uses the handbrake so the brake key does
not select reverse. It does not teleport or reset the car.

## Diagnostics and validation

**Save diagnostics** writes `BackseatRally_Report.json` in the executor workspace
with settings, stage, recent poses/commands, input mode and the last error. It
does not contain account names or private model weights.

Offline tests cover the generated script, UI dragging/minimizing/closing,
keyboard verification, F8/focus/seat changes, reinjection, native input/handling
restoration, full-footprint corridor prediction, obstacle avoidance choices,
brake scaling, fallback steering, high-grip rollover steering limits, upright
torque, ghost decoding and numeric route alignment against
the uploaded place's collision road. A separate planar driving model checks
steering/braking over Pine Forest at 30/60/120 Hz and Riverbend Canyon at 60 Hz,
using a wide car and fallback grip estimates. It does not reproduce Roblox
collisions, suspension, roll dynamics, keyboard pulse timing, networking or every
car tune. **This release has not been live-tested
in Roblox/JJSploit.** See `VERIFICATION.json` for the checks actually run.

Maintainers can rebuild with `python build.py`, run
`python -m unittest discover -s tests -v` with `LUAU_BIN` / `LUAU_COMPILE` set,
run `python tests/run_planar.py` for the synthetic stage checks,
and package with `python package.py`. The uploaded place and original game
scripts are excluded from this download.
