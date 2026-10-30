# How To Drift Autodrive 1.1.0

Autodrive-only replacement for Drift Assist 1.0.0.

1. Extract the ZIP anywhere. Open `HowToDrift_Assist.lua` and paste the **entire file** into JJSploit.
2. Execute once and sit in your own car. The **1.1.0** dashboard starts armed automatically.
3. Select **15–75 degrees** and a driving speed. It selects the nearest available road and starts driving.

No training, restart, manual alignment or separate loader is required. Re-executing replaces the previous instance.

| Control | Action |
| --- | --- |
| Angle | Desired drift angle, 15–75 degrees; drift direction follows road bends. |
| Speed | Requested speed, 20–180 km/h; tight corners reduce it automatically. |
| F6 / Start–Stop | Pause or resume the autopilot. |
| Rejoin nearest road / F7 | Select a road near your current position and recover onto it while staying enabled. |
| Reverse | Reverse the route while staying enabled. |
| S / Space | Temporarily brake; release to continue. |
| Save diagnostics | Save `HowToDrift_Diagnostics.json` in the executor workspace. |

This version directly sets your car's pose and velocity along the road. It continuously corrects its position and teleports back onto the route after displacement, overturning or becoming airborne. Open roads turn around automatically; closed roads loop. Turnarounds can be abrupt. It follows the centerline rather than stopping for obstacles. Angle transitions are smoothed.

It reads replicated minimap roads, local map MinimapLines / MinimapPath records, and the active race's 3D course when available. It cannot discover an arbitrary road with no path data. Ground must be loaded at the target position; otherwise it waits and retries automatically. Overlapping roads can select the wrong elevation when only a 2D path is available.

Chat, Roblox menus, garage, race countdowns and focus loss pause the autopilot; it resumes automatically afterwards. It only controls your own seated, network-owned car. Stop releases its input override. Closing or re-executing cleans up its connections.

If it does not move, click Save diagnostics and send HowToDrift_Diagnostics.json from your executor workspace. If writing is unavailable, diagnostics are copied to the clipboard or printed in F9 instead. Reports are not uploaded automatically.

Offline Luau compilation, 75-degree target, teleport recovery, active reverse/rejoin, pause/resume, end turnaround, cleanup and diagnostics tests passed. **This version has not been tested in live Roblox or JJSploit.** Server corrections may interfere; actual drift scores or rewards are not guaranteed. Previous physics benchmark results apply to version 1.0 only and are preserved separately.

No admin calls, reward submissions, saved upgrade/currency changes or runtime downloads. The uploaded place and extracted game sources are excluded from the ZIP.

Development:

```bash
python build.py
python tests/run.py --luau /path/to/luau --compiler /path/to/luau-compile
python package.py
```
