# Backseat Rally Assist 1.0.0

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

Drag the title bar to move the window. **–** minimizes/restores it while driving
continues. **×** closes it, disconnects the controller and restores handling/input
settings owned by this GUI. Running the script again shuts down the previous copy.
After travelling to a different Roblox place, run the script there again.

## Controls

| Control | Range | Effect |
| --- | --- | --- |
| Speed / power boost | 1–3× | More acceleration and a taller gear range when the native chassis is accessible; otherwise grounded acceleration assistance. |
| Turn response boost | 1–2.5× | Faster steering and more available angle; grounded yaw assistance in fallback mode. |
| Grip boost | 1–3× | More lateral/longitudinal grip; grounded slip damping in fallback mode. |
| Autodrive speed cap | 50–260 km/h | Upper bound; corners, surface, obstacles and the reference can require lower speeds. |
| Reference pace | 0.60–1.25× | Adjusts the reference speed plan; it does not replay a clock or change race results. |

Set an individual multiplier to **1×** for its original value. The defaults are
1.40× speed, 1.20× turn, 1.20× grip, 180 km/h and 1.00× reference pace. Higher power
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
uses the independent numeric route and conservative estimates. Changing a car
build causes the handling adjustments to be reapplied from its new baseline.

Autodrive uses automatic gears temporarily. Manual controls and that preference
return on stop. Menus, chat, replay/knockout states and lost driver ownership
release control. Focus loss pauses assistance; **F6** restarts it. A large frame
stall suspends the controller instead of applying an old input.

## Driving lines and ghosts

- **Showcase** follows the recorded menu driving line for the selected stage,
  with current-position steering correction, corner-speed preview, braking,
  obstacle checks and road-width limits. It uses car physics, not car teleports.
  Numeric references for the seven saved stages are included.
- **Road** follows the stage geometry without the recorded run's speed targets.
- **Personal ghost** follows a full-stage ghost that the game has already loaded
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
reverse can clear a stationary obstruction; it does not teleport or reset the car.

## Diagnostics and validation

**Save diagnostics** writes `BackseatRally_Report.json` in the executor workspace
with settings, stage, recent poses/commands, input mode and the last error. It
does not contain account names or private model weights.

Offline tests cover the generated script, UI dragging/minimizing/closing,
keyboard verification, F8/focus/seat changes, reinjection, native input/handling
restoration, corner braking, ghost decoding and numeric route alignment against
the uploaded place's collision road. A separate planar driving model checks
steering/braking over complete routes. It does not reproduce Roblox collisions,
suspension, networking or every car tune. **This release has not been live-tested
in Roblox/JJSploit.** See `VERIFICATION.json` for the checks actually run.

Maintainers can rebuild with `python build.py`, run
`python -m unittest discover -s tests -v` with `LUAU_BIN` / `LUAU_COMPILE` set,
run `python tests/run_planar.py` for the synthetic stage checks,
and package with `python package.py`. The uploaded place and original game
scripts are excluded from this download.
