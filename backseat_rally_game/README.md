# DM / Rally Expedition 1.4.0

A playable rally expansion with 15 car profiles, first-person driving, configurable
handling, tyre and mechanical damage, human co-driving, friend races and saved replays.
The ready Sakura and Backseat downloads keep their supplied scenes, cars, bots and
hierarchies. The new rally runs on its own generated stages and backend.

## Download and play

Open **DM_Sakura_Pass_v1.4.0.rbxl** in Studio and press **Play**, then **Take the Road**.
This is the latest Sakura upload with the expansion and targeted startup repairs.
**DM_Backseat_Rally_v1.4.0.rbxl** extends the earlier upload.
**DM_Rally_Standalone_v1.4.0.rbxl** contains only the new game and portable geometry;
it is useful for isolating original-scene or asset issues. Binary `.rbxl` files open
directly; no installer command is needed. Zips contain the place, standalone files,
installer, sources, tests, hashes and preservation report. The `.lock` file is unnecessary.

Driving works without publishing or DataStore/mesh permission. Replays/settings are
session-only when cloud storage is unavailable. Original exterior skins and selected
scenery are reused after Roblox confirms their assets loaded. A complete native car
stays visible if a skin is unavailable. External imported audio is disabled by default.
Roblox private assets still require permission from their owner; this update cannot
unlock them. The errors supplied so far mostly concern sounds, video and animations,
so they do not establish why the original scene geometry disappears.

## Drive, co-drive and race

Driving remains inside the cockpit. **Settings / F4** adjusts FOV, seat position,
mouse look sensitivity, motion, assists, damage, crash effects and cold tyre pressure.
All keyboard bindings can be changed. Hold RMB to look around; release to recenter.
**C** centers the live view. Cockpit instruments show speed, gear, RPM, tyre pressure
and damage warnings. **H** switches headlights.

Defaults: W accelerate, S brake/reverse, A/D steer, Space handbrake, Down reverse,
R recover (+5 seconds), T service, B mark a replay moment, F4 settings. Touch controls
and gamepad left stick/R2/L2 remain available. Settings stop your driving inputs
while open; a live multiplayer race continues. Keyboard assists smooth throttle and
steering, with ABS/TCS and stability help; disable them for a less forgiving setup.

- **Rally Sprint:** 1.72 km with a finish gate.
- **Expedition:** 4.59 km across four biomes.
- **Daily Roadbook:** the same 2.29 km course for everyone on that UTC day.
- **Endless Journey:** bank the run when ready.

Friends in the same Roblox server can join an open co-driver seat. The passenger sees
a roadbook with upcoming turns and distances, sends turn/caution calls, shares the
recording and can leave without retiring the driver.

**Race Friends** opens a room browser. Host a rally, choose cars, mark every driver
ready and let the host start. All drivers receive the same seed and handling rules;
the countdown waits until every participant's road is ready. Live standings track
progress, finish times and retirements. These are simultaneous rally time trials on
separate collision lanes, without car-to-car collisions. The host's damage, assists
and pressure settings apply to everyone. Friends must join the same server first.

## Tyres, service and crashes

Each wheel tracks pressure, temperature, wear, load and slip. Impacts can puncture a
tyre; leaking pressure affects grip, drag, steering pull, wheel shape and body pose.
Wetness, biome temperature and wind affect driving. Split bump/rebound response,
body pitch/roll and load transfer use the car's weight balance and suspension data.

Engine, brakes, steering and suspension take mechanical damage. Large impacts can
stop the engine; checkpoint recovery does not silently repair it. Stop in the starting
apron or within 85 studs of the last checkpoint, then **T / Service** for repairs and
replacement tyres (+15 seconds). Cold tyre pressure applies at start/service.
Changes to damage/assist rules apply to the next run, keeping an active race consistent.

Damage and screen effects are independent settings. Choose off, red flash or an
optional brief blackout for severe impacts. Effects fade and never show graphic injury.
There is no soft-body mesh destruction or deformable tyre carcass solver.

## Replays and ghosts

Every run records its road, controls, suspension pose, tyre conditions, gear/RPM,
mechanical condition and impact events. Finished stages can update their personal-best
ghost. Retired/banked runs remain reviewable. The library keeps 12 recent runs and
8 best courses; co-drivers receive access to their shared recording.

Replay cameras: **cockpit, chase, orbit, director and freecam**. C cycles cameras;
P pauses; comma/period seek ±5 seconds. Use the timeline and 0.25–4× playback.
RMB looks/orbits, wheel zooms/adjusts freecam FOV, WASD moves freecam, Q/E changes
height, Shift moves faster and Alt moves precisely. The director holds roadside
shots and changes angle automatically. Freecam moves while playback is paused.
Camera/mouse state restores on exit. Replay memory, fetch queues and pages are bounded.
Older 11/14-field recordings remain readable by the codec; generation 3 runs use the
new handling/course comparison and old generation ghosts are not mixed with them.

Publish your own copy and enable Studio API access when testing cloud saves.
Only confirmed writes are labeled saved. Unpublished places skip DataStores entirely.
Settings and keybindings save with the expansion profile when storage is available;
the original game's private profiles/entitlements are not retrieved.

## Tuning and performance

`src/Shared/VehicleCatalog.lua` holds all 15 recovered car profiles. One
`src/Shared/Dynamics.lua` solver uses their mass, axle balance, torque curves, power,
gears, brakes, steering and suspension settings. `Dynamics.Tuning` controls the shared
model; a profile's `simulation` table can override individual tuning keys.
`Config.Climate` controls wetness, temperature effects and wind.
`Preferences.lua` defines safe user settings and default bindings.

This is a deterministic four-contact approximation with anchored visual assemblies.
It is not the original force-based chassis or a Dirt Rally 2.0 physics recreation.
Some original profile fields are retained for calibration without a solver equivalent.
The two chassis test uploads were inspected as references; their dependent code and
private assets were not installed or executed.

Fixed 60 Hz simulation, four wheel states, capped step catch-up, bounded road windows,
part recycling, queued generation, origin rebasing and capped replay pages limit work.
Low/medium/high quality controls scenery and shadows; automatic quality can be disabled.
Rain uses at most 24 reused streaks (8 on low). Cockpit/effects allocate no objects per
frame. No DataStore writes run synchronously on the simulation heartbeat. Final GPU
performance and multiplayer latency require Studio/device testing.

## What is preserved and repaired

The Sakura build retains all **132,961** original objects; Backseat retains **82,861**.
No original object is removed or moved. Every original binary chunk except the parent
table is retained byte-for-byte, and all original parent pairs remain in that table.
Fourteen original script Sources receive narrow fixes: Zone's self-require guard,
PlayerModule input-context lookup and DataController initialization/warning behavior.
Their exact originals are kept as inert modules in
`ServerStorage.BackseatLegacySourceBackups`. Every other original property is unchanged.
The preservation JSON lists each intentional Source change and its before/after hashes.

A copy of the supplied 109-object native input graph provides the fallback missing at
runtime. A session-only compatibility bridge supplies fresh original profile/settings
values through the actual exported ReplicaClient protocol. This addresses the reported
recursive Zone require, missing settings, duplicate listeners and input graph waits.
It does not rebuild the original game's entire absent server backend or prove all
original scene rendering faults resolved. **Return to Original** restores its UI/view.

The `.rbxmx` installer remains an optional add-on for other places. Save a copy, insert
it into Workspace and run `require(workspace.BackseatRallyExpansion.Installer).install()`
in Studio's Command Bar. It adds its namespace, keeps the opt-in launcher and does not
apply ready-binary legacy Source repairs. Do not install twice into an extended DM place.

## Build and validate

```sh
python -m pip install -r backseat_rally_game/requirements-build.txt
python backseat_rally_game/build.py --base-place /path/to/original.rbxl
LUAU_BIN=/path/to/luau LUAU_COMPILE_BIN=/path/to/luau-compile \
BACKSEAT_BASE_RBXL=/path/to/original.rbxl \
python -m unittest discover -s backseat_rally_game/tests -v
```

See `VALIDATION.md` for checks and `ASSET_EXPORT_GUIDE.md` for authorized asset exports.
No Roblox Studio GUI is available in the build environment; automated tests use the
Luau CLI and a Roblox test double, not the Roblox renderer or production services.
