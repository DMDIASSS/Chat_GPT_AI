# Validation — 2 November 2026

- 42 automated tests passed using the Luau CLI and Python unittest.
- Every authored Luau source compiles.
- Road continuity, grade and curve bounds checked across 1,000 seeds.
- Manual control simulation reaches a finite finish and updates a personal best.
- Banked endless replay and ghost data survive a new storage session in the test double.
- Replay seeking, recovery gaps, controls, bookmarks and bounded stream/cache behavior checked.
- Storage failures preserve session access and are not reported as confirmed cloud saves.
- Studio installation preserves existing scripts, bot models, service children and settings.
- Ready places open the new menu automatically; optional installations and closing restore the original view.
- The full RBXL preserves all 82,861 original instances and original hierarchy relationships.
- Every original INST, PROP, SSTR and metadata chunk is byte identical.
- An independent robloxapi/rbxfile decoder reads all 82,861 original instances unchanged,
  followed by the 25 additions. Original script counts remain 490 ModuleScripts,
  6 Scripts and 4 LocalScripts; the expansion adds 13, 1 and 1 respectively.
- Artifact hashes and embedded sources are checked against the reviewable source files.

- Default startup reaches the working menu and creates a road without the original garage.
- The car preview has a complete native body independently of mesh downloads.
- Failed and timed-out meshes preserve a complete body; successful late skins align to the current pose.
- Imported scenery failures retain generated trees and a continuous road.
- Legacy fog, atmosphere and blur are isolated during a run and restored on return.

- An unpublished place initializes and spawns a complete visible server car without calling store APIs.
- A throwing GetDataStore call cannot abort server setup or spawning.
- A slow cloud profile does not block the starter car.
- Offline input capture drives the car, then banking and replay playback work in session.
- Missing-server requests display a visible start failure and release the button.
- The clean binary standalone has a native floor/spawn, the proper LocalScript container,
  and no imported mesh or sound instances.
- The Sakura Pass build retains all 132,961 original instances and their hierarchy.

No Studio GUI or live Roblox server is available in this environment. Renderer/device
behavior, permissions for reused mesh/audio assets, production DataStores and real
multiplayer latency still require a Studio playtest. The supplied original server
scripts are placeholders; the new modes use their own authored backend.

All 15 recovered profiles are checked through the same solver. New checks cover axle
load contact poses, deterministic bumps/climate, and suspension pose replay round trips.
The old Sakura renderer has not been reproduced in Studio; overlap/rebase changes
apply to the new rally renderer. See ASSET_EXPORT_GUIDE.md for calibration limits.
