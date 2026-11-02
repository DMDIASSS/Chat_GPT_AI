# 1.5.0

- Original saved stages are the default: actual Sakura hairpins/scenery and the available Pine Forest section; generated maps are an explicit alternative.
- Reuse native road/shoulder/verge shapes with reversible local appearance repairs. No original scenery duplication or movement.
- Original car interiors, driver-eye attachments, steering, wheels and gauge data are reused; optional texture failures no longer reject a complete car.
- Keep usable original native parts when external meshes fail; suppress the portable cockpit when an original interior exists.
- Dedicated camera ownership, maintained Focus, finite-frame checks, and car replication focus address sky-only rendering paths.
- Static original maps never use generated-lane offsets or rebasing. Progress/physics map through real hairpins; obstacle casts use the original scenery.
- Cleaner inset HUD and collapsible utility controls.
- Audit the supplied DM_Collection.rbxm; it confirms empty original server containers and an incomplete Pine road snapshot, not recovered server code.

# 1.4.0

- First-person cockpit driving, instruments, headlights, adjustable camera/motion, safe rebinding and saved settings.
- Fifteen shared car profiles gain per-wheel pressure/heat/wear/punctures, load-sensitive grip, keyboard assists, brake fade and component damage.
- Checkpoint service bays, visible tyre deflation and optional red/severe-blackout crash effects; no soft-body destruction.
- Shared-seed friend race rooms, readiness barrier, synchronized countdown, live standings and retirement handling in separate collision lanes.
- Human co-driver roadbook and distance-aware calls.
- Five replay cameras including director/freecam; bounded scrubbing and 35-field condition recordings, old codec support.
- Targeted Zone, DataController and PlayerModule fixes, exact Source backups and cloned native input graph; session original profile/settings bridge.
- Preservation checks detect unauthorized original property overrides and explicitly list fourteen permitted Source repairs.

# DM / Expedition 1.3.0

- Recover 15 vehicle profiles from uploaded Cars, CarSelect and Parts.Rating.Rig tables.
- Share one configurable handling solver across all cars; enable original visual reuse.
- Add torque curves, gearing, mass/power limits, axle traction and combined grip demand.
- Add sprung body motion, wet/thermal grip, wind and weather telemetry.
- Add short-wave road bumps, advance turn arrows and roadside turn markers.
- Record sprung pose in replay frames; increment road generation to 2.
- Reduce road slab overlap and shift completed chunk parts directly on origin rebases.
- Normalize imported bodies about wheel geometry and include suitable interiors.
- Preserve original scenes and provide a guide for complete authorized asset exports.

# DM / Expedition 1.2.0

- Fix server startup when GetDataStore throws or the place is unpublished.
- Keep spawning independent from slow cloud profile reads for the starter car.
- Spawn a complete visible car on the server and seat the driver.
- Capture driving input even when default controls mark the event processed.
- Display spawn errors in the garage and reset unacknowledged start requests.
- Use native geometry by default; imported skins and external audio are optional.
- Add clean standalone RBXL/RBXLX files and a preserved Sakura Pass build.
- Verify offline driving, banking and replay playback with store APIs disabled.

# DM / Expedition 1.1.1

- Open the working rally menu automatically in the ready-to-open place and preview.
- Keep the optional launcher for Studio installations into other games.
- Add a complete car preview built with native geometry.
- Keep complete car bodies visible until optional external meshes finish loading.
- Preserve fallback bodies on failed or timed-out asset loads; attach late skins at the current pose.
- Use generated trees and scenery while imported meshes are unavailable.
- Apply clear local daylight and fog settings, restoring original effects on close.
- Add regressions for automatic startup, scene visibility, mesh failures and slow downloads.

# DM / Expedition 1.1.0

- Continue the uploaded unfinished expansion from the latest repository commit.
- Add Rally Sprint, Expedition, Daily Roadbook and bankable Endless Journey.
- Add reproducible roads across four biomes, checkpoint recovery and garage unlocks.
- Add replay playback, timeline seeking, bookmarks, recorded controls and saved ghosts.
- Reuse suitable original visual assets while preserving all source instances.
- Make the expansion optional; return the player to the original view and location.
- Replace the draft's archive/disable installer with an additive, idempotent installer.
- Fix road banking/grade alignment and early readiness/bank actions.
- Retain all original binary object/property chunks and original parent relationships.
- Leave every pre-existing repository file, including bots and training tools, unchanged.
