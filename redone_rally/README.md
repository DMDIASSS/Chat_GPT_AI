This patches the latest **“Redone with poor car and codrive…”** place directly.
Download `downloads/Backseat_Rally_Redone_Fixed.zip`, extract it, open the included
`.rbxl` in Roblox Studio, and press Play. [START_HERE.txt](START_HERE.txt) has the
controls and tuning locations.

The base already has a server, raycast suspension, tyre physics, five cars and a
seeded spline generator. This build retains that architecture and its supplied
models. It does not install the earlier Expedition game into this place.

Steering uses one persistent rack position with configurable angular speed. A
reversal travels through the current position and center; overlapping keyboard
directions use the last press. The steering-rate setting changes the rate without
resetting the rack. Front-wheel Ackermann geometry still applies.

The co-driver uses a cached polyline in ReplicatedStorage and road distance rather
than the car's facing direction. Signed curvature fixes left/right classification;
smoothing and minimum turn length/deflection suppress tiny calls. Corner length and
entry/exit curvature produce long/tightens/opens modifiers. Crest calls are spaced.
The scheduler includes speed/braking lead, repeat suppression, reset handling,
distance countdowns and into/then chains. Speech uses Roblox's AudioTextToSpeech
when available; it does not require a new private audio upload. The existing cue
and visual notes remain available if speech fails.

The supplied wheel's tyre/rim mesh rotation differs from the earlier matching
Backseat assets. The builder restores that orientation, uses its X axle, mirrors
the right wheel, and scales the visual tyre diameter to each profile. Wheelbase,
track and axle offset come from the corresponding saved GroupB/Sedan/Saloon/Hybrid/
Coupe wheel centers. Suspension attachments and wheel visuals share the same
mounts. Driver-eye offsets also come from those saved models. See
[CALIBRATION.json](CALIBRATION.json).

The existing control-point generator, seed, road types and scenery selection remain.
Road banking now uses the correct sign and eight-degree cap. Unbanked roadside
banks follow the road grade and props are planted on that plane. Missing scenery
references use the supplied HayBale. This generator has no water-generation path;
it does not inherit the high-water placement from the older Expedition generator.

The missing-map toggle is guarded, and stage switching restores original collision
and transparency values, including invisible triggers. Initial spawning no longer
mistakes the first request for a rapid repeat. Regeneration brings all connected
players to the new shared road. Client fallback selects its own car. Driving stays
in the cockpit; replay cameras follow a separate local clone rather than moving the
live chassis. Camera Focus and car ReplicationFocus are maintained, with bounded
stream requests when replay cameras move through streamed sections.

Settings added to the existing O menu are steering rate, co-driver lead time and
speech on/off. These settings last for the session. Existing physics parameters
remain available in CarProfiles and SurfaceConfig; this change does not make every
previously stored tuning field into a complete physical simulation. This build
does not claim a full Dirt Rally 2.0 simulation or soft-body destruction.

All 14,091 original saved objects, parent relationships, class/property chunks and
non-Source values remain. Thirteen original Sources have explicit overrides and
exact inert backups in ServerStorage.DM_RedoneSourceBackups. Two shared modules and
one backup folder are added, giving 14,107 objects. No original script is disabled,
moved or deleted in the saved file. BASE_MANIFEST.json hashes the original Sources;
the packaged PRESERVATION.json lists each change and backup.

Build from the repository root with `python redone_rally/tools/build.py`. This
checks the base hash before patching and verifies all original properties and
Sources afterward. It uses the existing `backseat_rally_game/tools/rbxl_addon.py`
reader and Python `zstandard` / `lz4` packages. Run
`LUAU_BIN=/path/to/luau python redone_rally/tests/test_redone.py` for the behavior
suite; place `luau-compile` beside that executable. The test fixture extends the
existing shared headless mock.

Validation covers compilation of all 26 sources, steering across four frame rates,
keyboard overlap/reversal, all five axle layouts, airborne steering and contact
visuals, actual corner direction, route projection, co-driver resets, generation,
missing-map/trigger restoration, multiplayer regeneration, replay isolation and
binary Source/backups. An independent Go decoder also compares original instance
paths and non-Source properties. Studio rendering, rigid-body integration, media
permissions and real multiplayer transport still require a Studio playtest.
