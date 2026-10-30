# How To Drift Assist 1.0.0

A separate client driving panel for the supplied **How To Drift — NEW CARS** place, ID `91374382281493`.
No training or extra model is needed. The complete script is **HowToDrift_Assist.lua**.

## Start

1. Extract the ZIP anywhere, such as your Desktop. Open `HowToDrift_Assist/HowToDrift_Assist.lua` in a text editor.
2. Join How To Drift, spawn your car and sit in its driver seat. Use the game's **Auto** gearbox; switch to it before starting road automation.
3. In JJSploit, paste the **entire** Lua file and execute it. No loader or additional script files are required.
4. Start with **30 degrees**, **65 km/h**, **1.25x power**, **1.00x speed**, **0.85 angle strength**.
5. Select **Manual + angle hold** or **Road auto**, then click **Start** or press **F6**.

The dashboard should say **DRIFT ASSIST 1.0.0**. Executing the script again stops and removes its previous instance.

## Controls

| Control | Effect |
| --- | --- |
| Drift angle | Target slide angle, 15–50 degrees, measured between the car's forward direction and its movement direction. |
| Manual + angle hold | You drive with W/S/A/D or arrows. Hold W and tap A or D to select a drift direction; the selected side stays active while you hold throttle. |
| Side: Auto / left / right | Auto uses A/D in manual mode and the road's turns in Road auto. Fixed left/right holds that side. |
| Road auto | Follows the nearest replicated road in your facing direction, or the active race's 3D course. Accelerates, steers, slows for corners and stops for detected obstacles or the end of an open route. |
| Speed target / manual cap | Cruise target in Road auto; an approximate upper speed cap while throttling in manual mode. |
| Power assistance | Extra acceleration assistance, 0.5–4x. This is a client physics assist, not a modification to your saved engine upgrades or literal engine horsepower. |
| Speed multiplier | Multiplies the speed target/cap, 0.5–2.5x. Road corner limits still apply. |
| Hold Shift | Temporary extra power and a 1.35x speed target. The overall target is capped at 360 km/h. |
| Angle lock strength | 0–1; zero turns off yaw assistance. |
| Nearest road | Re-selects a nearby road. Position the car on the road first. |
| Reverse route | Stops assistance and reverses the current route direction. Align your car, then Start again. |
| F6 | Start / Stop. Stop immediately releases automatic input and physics updates. |
| F7 | Switch driving mode. |
| F8 | Cycle drift side. |
| S or Space | Temporarily override road automation with your normal brake/handbrake. |
| Save diagnostics | Export a report with current settings, telemetry, route and recent behavior. |

Keyboard controls above use the game's default bindings; do not remap them while using the assist. Gamepad triggers / thumbstick are also read. Touch-only manual driving is not supported.

At low speeds the target angle eases toward zero. During very sharp turns and recovery the actual angle can differ from the selection. The assist controls yaw and applies bounded horizontal impulses; it does not teleport the car or keep the car glued to a route.

## Road behavior and limits

Minimap lines are smoothed before steering so their quantized points do not cause artificial zigzags. The nearest route stays selected; it does not repeatedly switch onto adjacent hairpins. An active race uses the replicated 3D course to distinguish elevations.

If the car is far from the selected road, the route ends, an obstacle is detected, or the road ahead is not loaded, Road auto brakes and waits. It does not plan a detour around traffic or choose a destination across the map. Open minimap segments stop at their ends instead of turning around automatically.

Assistance pauses when you leave your own seat, lose the car's `NetOwner`, open chat/a text box or the Roblox menu, enter the garage/replay/spectating, lose window focus, or the car is airborne/overturned. Physics assistance requires at least three ground rays. Race countdowns are respected. Stop or close the panel to return to normal driving.

Only your `OwnerUserId` car is touched. Another script's `DebugInput` override is left intact; stop that other controller before starting this one.

## Admin panel

The supplied game's existing admin panel uses **F2** and checks the player's `Admin` attribute. The uploaded place contains client code, not the server's permission implementation. This script provides its own driving controls and does not grant admin access or call admin remotes. Saved money, cars, upgrades and server settings are unchanged.

## If it does not work in the live game

Click **Save diagnostics** immediately after the problem. Send back **HowToDrift_Diagnostics.json**.

If JJSploit provides `writefile`, the file is saved in its executor workspace. On your previous setup that was commonly:

```text
C:\Users\almas\AppData\Roaming\jjsploit\workspace\HowToDrift_Diagnostics.json
```

Other installations can use a different workspace. If file writing is unavailable, the script copies diagnostics to the clipboard when supported, otherwise prints them in the F9 console. The dashboard shows which method succeeded.

The report includes your own car's attributes, current angle/speed/ground contact, route, controller timings and the latest two minutes of sampled behavior. It does not collect other players' accounts or send reports anywhere automatically.

The script uses the live game's original `DebugInput` format for automatic throttle/steering and Roblox physics properties for angle/power assistance. A game update or server correction can change whether those controls work. JJSploit / Windows / live Roblox execution has **not** been tested here.

## Offline verification

The generated file compiles with the official Luau CLI. Verification covers settings, angle sign, invalid inputs, braking, reverse, boost, ownership, focus/chat/menu/garage/countdown pauses, ground contact, input cleanup, diagnostics and reinjection.

Closed-loop tests cover 36 road/angle/direction/frame-rate combinations and a finite-road stop. A separate private check loaded the uploaded game's **actual CarPhysics and GarageConfig code** into a flat planar rig: 24 manual cases and 18 circular road cases passed. The original client parsed our automatic input correctly; all 11 minimap lines and 64 race-course point records were readable. See `VERIFICATION.json` for measured results and scope.

The planar rig does not reproduce Roblox's 3D collision/suspension solver, other cars, streaming, network corrections or the executor. Small errors in that fixture do not guarantee identical live drift angles or road performance.

An exploratory 80 km/h run on the real Circuit minimap line still had about 14.5 degrees mean target-angle error through its sharp / low-speed transitions, while tracking stayed within 5.2 studs of the centerline. Road auto needs live validation and tuning on complex tracks; start with the lower default speed.

## Development files

The ZIP includes our editable modules and tests. It excludes the uploaded place, its extracted game scripts, and real player data. Running the controller requires only the single generated Lua file.

```bash
python build.py
python tests/run.py --luau /path/to/luau --compiler /path/to/luau-compile
```

Optional, with a private extraction of your own supplied place:

```bash
python tests/check_place.py --scripts-dir /path/to/private/extraction --luau /path/to/luau
```
