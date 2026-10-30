# How To Drift Autodrive 1.2.0

The controller now has **Farm** and **Cool** modes, a speed setting up to **500 km/h**, near-floor tunnel probing, and a pose fitted to all four wheel supports.

## Install

1. Extract the ZIP anywhere. Open `HowToDrift_Assist.lua`.
2. Paste the **entire file** into JJSploit and execute once, then sit in your own car.
3. Check that the dashboard says **1.2.0**. It starts armed automatically.
4. Choose Farm or Cool. No training or manual restart is needed when changing settings.

Executing this version stops and replaces the previous instance.

## Farm mode

Farm holds the chosen speed without the old corner or route-end speed cap. It uses a fixed **60-degree** native drift angle: the supplied client's angle bonus reaches its maximum at 60 degrees, so 75 does not add more angle bonus. Select at least **25 km/h** to meet the visible client's drift-speed condition.

The **Farm: Loop / Area reverse** button chooses:

- **Loop:** drive connected road segments, then return to the recorded spawn/start when there is no supported continuation. Closed roads loop naturally. Official map/spawn changes and replaced road data trigger a fresh route selection automatically. There is no intentional speed reduction during a Farm route transition or spawn loop.
- **Area reverse:** drive back and forth over a local stretch, with the area length set by the third slider. Direction changes reverse the native drift side while preserving the car's facing direction. This is deliberately abrupt rather than a realistic braking manoeuvre.

The game's client has a **SAME SPOT** payout reduction. Area farming may therefore pay less than full loops. The 60-degree setting optimizes the visible angle factor; it is not a promise of maximum or guaranteed server rewards.

## Cool mode

Cool follows a flowing side-to-side lane line rather than staying on the centerline. Its offset is bounded by the road width **and the full angled car footprint**, with an extra edge margin. It reduces the weave at high speeds. Grass, leafy grass, mud and unsupported wheel contacts cause the controller to try a more central line.

The angle slider is the **maximum** angle (15–75 degrees), not a fixed sideways pose. The actual angle changes with road bends and speed and eases toward zero on straights and at stops. Cool slows for bends and brakes at a dead end before looping back. It is still assisted kinematic driving; it is not an unmodified tyre simulation.

## Ground and tunnel behavior

The old fixed 1.8-stud chassis height and always-upright car pose have been removed. The controller reads the car's wheel attachment positions, ride heights and tyre sizes. It probes below all four wheels, fits road pitch/bank and chooses a chassis height inside all four suspension contact ranges.

Ground checks now start close to the expected floor. **There is no sky/high-mountain ray fallback.** Validated road-height continuity and replicated 3D race-course elevations help distinguish tunnels and stacked roads. If a wheel has no support or ground is not loaded, the controller retries a centerline/known start or waits. It cannot force four real contacts over an arbitrary cliff or fix incorrect/missing game path data.

## Controls

| Control | Action |
| --- | --- |
| Farm mode / Cool mode | Switch behavior without stopping. |
| Farm: Loop / Area reverse | Choose full route farming or local forward/reverse farming. |
| Angle | Cool maximum, 15–75 degrees. Farm shows `60 auto`. |
| Speed | Requested 20–500 km/h. Cool can slow for bends; Farm holds the requested speed while active on supported ground. |
| Area length | Local farming stretch, 20–300 studs. |
| Reverse | Reverse motion and mirror the drift side. |
| Rejoin / F7 | Re-select a nearby road without disabling the controller. |
| F6 | Stop / Start. |
| S / Space | Temporary brake. |
| Save diagnostics | Export `HowToDrift_Diagnostics.json` in the executor workspace. |

Chat, menus, window focus loss, garage/replay, race countdowns, losing ownership and leaving your seat pause control. It resumes automatically when possible. Stop/close releases its input override. An existing external `DebugInput` controller is left intact.

## Diagnostics and verification

Diagnostics include actual native speed/angle and contact counts, fitted wheel distances and normal, route joins/loops, lane offset, reverse state, last surface error, elevation segment count and the game's visible payout factor/reason. File writing falls back to the clipboard or F9 output; reports are not uploaded automatically.

Offline checks passed for route joining/spawn loops, 500 km/h Farm speed, reverse-side handling, local area bounds, Cool lane bounds, four-wheel fitting and tunnel floor selection. A full script fixture exercised a banked tunnel below a roof and mountain layer. The uploaded game's actual tyre code detected all four contacts in **144 mocked road-plane cases**, including forward/reverse and 85/500 km/h poses.

**This release has not been run in live Roblox/JJSploit here.** Server corrections, collisions, terrain not representable by a four-wheel pose, or unloaded roads can interrupt the requested motion. The ZIP includes `VERIFICATION.json` with the exact test scope. Historical results are labeled separately.

No admin calls, reward submissions, saved currency/upgrade edits or external runtime downloads are used. The uploaded place, its extracted sources, and private diagnostics are excluded from the ZIP.

## Development

```bash
python build.py
python tests/run.py --luau /path/to/luau --compiler /path/to/luau-compile
python package.py
```

Optional original-game contact check, using a private extraction of the supplied place:

```bash
python tests/check_contact.py --scripts-dir /path/to/private/extraction --luau /path/to/luau
```
