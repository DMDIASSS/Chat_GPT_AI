# How To Drift Autodrive 1.3.0

New controls: **Flip Angle**, **0–90 degrees**, **30–10,000 km/h speed targets**, and **Reverse Hz**. Cool mode now uses the original physics-based driving controller during normal movement, with the newer road/tunnel recovery fixes.

## Install

1. Extract the ZIP anywhere and open `HowToDrift_Assist.lua`.
2. Paste the **entire file** into JJSploit and execute once, then sit in your own car.
3. Check that the dashboard says **1.3.0**. It starts armed automatically and replaces the previous instance.

You can edit the number boxes directly for precise angle, speed and Hz values.

## Controls

| Control | Action |
| --- | --- |
| Farm / Cool | Direct controlled farming, or the original driving controller's physics feel. |
| Farm: Loop / Area reverse | Connected-road/spawn loops, or local forward/reverse farming. |
| Flip Angle / F8 | Mirror the drift angle without reversing travel. The inverted setting persists through turns and travel reversals. |
| Angle | 0–90 degrees in both modes. Farm holds the selected angle; Cool steers toward it with low-speed easing. Default: 60 degrees. |
| Speed | Requested 30–10,000 km/h. Farm commands this speed on supported ground; Cool retains normal acceleration and corner limits. |
| Reverse travel | Reverse motion, also mirroring the drift side. |
| Area length | Local stretch, 20–300 studs, used when Reverse Hz is zero. |
| Reverse Hz | 0–60 direction changes per second, used in Farm Area. 0 selects distance-based reversing. |
| Rejoin / F7 | Select a nearby road while staying enabled. |
| F6 | Stop / Start. |
| S / Space | Temporary brake. |
| Save diagnostics | Export `HowToDrift_Diagnostics.json` in the executor workspace. |

## Farm mode

Farm holds your chosen angle and commands the chosen speed without corner or route-end slowdown. The visible client's angle bonus reaches its maximum at **60 degrees**; higher angles do not add more angle bonus. Zero degrees is allowed for driving, but does not qualify as a drift.

**Loop** connects supported road segments and returns to the recorded spawn/start when a continuation is unavailable. Closed roads loop naturally. Map/spawn changes and updated road data trigger route re-selection.

**Area reverse** moves back and forth locally. Reversals mirror the native drift side and preserve the car's facing direction, including at a selected angle of zero. The game has a SAME SPOT payout penalty, so full loops may earn more.

When **Reverse Hz = 0**, the Area length slider controls the stretch. With a positive Hz value, each leg is timed: for example, 2 Hz means two direction changes per second, or one complete back-and-forth cycle per second. Its span is calculated from speed divided by frequency and capped by the available road length. In timed mode the distance slider is not used. Very short roads can therefore make position travel differ from the commanded velocity. Visible reversals are limited by update/frame rate.

## Cool mode

Cool uses the original controller's tyre motion, throttle, steering, bounded acceleration and yaw assistance during normal driving. It follows a flowing side-to-side line, bounded by road width and the full car footprint. It slows for bends and stops; the selected speed is a target, not an instantaneous forced velocity. Flip Angle mirrors the desired drift side, while angle changes ease through the controller.

Pose resets are reserved for recovery: losing wheel support, overturning, major displacement, getting stuck, or returning to the start of an open route. It tries a more central line before recovering from unsupported/off-road terrain. This mode still includes assistance; it is not an unmodified tyre simulation.

## Ground and tunnels

Recovery and Farm poses use wheel attachments, ride heights and tyre sizes to fit road pitch, bank and chassis height inside all four suspension contact ranges. Ground probes start near the expected floor. **There is no sky/high-mountain ray fallback.** Validated height continuity and replicated 3D race-course elevations help distinguish tunnels and stacked roads.

Four supports cannot be forced over an arbitrary cliff or missing road. The controller uses a supported start fallback or waits when needed. Normal Cool wheel contact is governed by the game's suspension and checked for recovery.

Chat, menus, focus loss, garage/replay, race countdowns, ownership loss and leaving your seat pause control. Stop/close releases its input override. It leaves another script's input override intact.

## Verification and limits

Offline checks passed for Flip Angle, zero/90-degree reversing, extreme-speed area bounds, the reverse timer, route loops, tunnel floor selection, wheel fitting and lifecycle cleanup. The uploaded game's original tyre code detected all four supports in **324 mocked plane cases**, including 0/90-degree and reverse orientations with velocity targets up to 10,000 km/h. The original driving-controller physics benchmark also passed. These fixtures do not reproduce live Roblox collisions, server corrections or executor behavior.

**Live Roblox/JJSploit is untested here.** In particular, a selectable 10,000 km/h target is not a guarantee that the game will sustain that speed. See `VERIFICATION.json` for exact scope; older results are labeled separately.

If something goes wrong, click Save diagnostics. Reports include actual speed/angle/contact counts, surface fitting, mode, angle polarity, reverse Hz and area span. File writing falls back to the clipboard or F9 output. Reports are not uploaded automatically.

No admin calls, reward submissions, saved currency/upgrade edits or runtime downloads. The uploaded place, its extracted sources and private diagnostics are excluded from the ZIP.

## Development

```bash
python build.py
python tests/run.py --luau /path/to/luau --compiler /path/to/luau-compile
python package.py
```

Optional private source checks:

```bash
python tests/check_contact.py --scripts-dir /path/to/private/extraction --luau /path/to/luau
python tests/check_place.py --scripts-dir /path/to/private/extraction --luau /path/to/luau
```
