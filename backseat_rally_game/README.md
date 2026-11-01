# Backseat Rally / Expedition

An optional driving expansion added to the uploaded Backseat Rally place, plus a standalone preview.
Solo play with an optional human co-driver, four game modes, continuous seeded roads,
checkpoint recovery, a replay library, and saved personal-best ghosts. It contains no
executor code or live-game injection. The full DM place retains the supplied original content.

## Download and play (1.3.0)

Start with **DM_Rally_Standalone_v1.3.0.rbxl**. It contains only the new driving game,
fallback car/map geometry and its own server logic. Open it directly in Studio, press
**Play**, keep **Orso 4** selected, then **Take the Road**. Publishing, cloud-save
access and imported meshes are optional. The same file is available as `.rbxlx`.

**DM_Sakura_Pass_v1.3.0.rbxl** adds this driving system to the latest Sakura Pass upload,
preserving all 132,961 original objects. **DM_Backseat_Rally_v1.3.0.rbxl** does the same
for the earlier Backseat Rally upload. Both start the new rally menu automatically.
The procedural road appears when a run starts. **Return to Original** restores the
supplied scene and UI; its absent original backend is not reconstructed.

**DM_Sakura_Pass.zip** / **DM_Backseat_Rally.zip** include the respective preserved place,
clean standalone files, installer, sources, tests, hashes and preservation report.
The Studio `.lock` file is not needed. Existing bots and other repository files remain
unchanged. No installer command is needed for a ready-to-open place.

- **Rally Sprint:** a 1.72 km stage with a final timing gate.
- **Expedition:** 4.59 km across pine, alpine, mesa and coastal scenery.
- **Daily Roadbook:** a 2.29 km road shared by everyone on that UTC date.
- **Endless Journey:** keep driving, then **Bank Run & Save** whenever you want.

A friend can join the spare seat through **Refresh Open Seats → Join**. The passenger
can make left/right/caution calls and can leave without ending the driver's run.

Keyboard: **W** throttle; **S** brake/reverse; **A/D** steering; **Space** handbrake;
**R** recover at the last checkpoint (+5 s); **B** bookmark a replay moment; **C**
change camera. Arrow keys and touch driving buttons are supported. Gamepad left
stick steers, R2 accelerates and L2 brakes.

## Reuse the uploaded place's cars and props

Save a COPY of the original place first. Open that copy in Studio edit mode. Drag
**Backseat_Rally_Expansion.rbxmx** from your computer into Workspace, then run this
in Studio's **Command Bar**:

```lua
require(workspace.BackseatRallyExpansion.Installer).install()
```

The installer only adds `BackseatExpedition`, `BackseatExpeditionServer` and
`BackseatExpeditionClient` under ReplicatedStorage, ServerScriptService and
StarterPlayerScripts. It never moves, disables or deletes existing instances or
changes Workspace/Lighting settings. Running it again leaves the existing install
alone. The imported package remains in Workspace for inspection; only its cloned
runtime scripts are enabled. Studio installations into another game keep the optional
EXPEDITION launcher (`ReplicatedStorage.BackseatExpedition.AutoOpen` attribute is false).
Do not run the installer in the already extended DM
place. Visual copies of the existing car exteriors and selected scenery are reused
when suitable; scripts and constraints are removed only from these new visual copies.

The ready binary copies every original instance/property chunk verbatim and retains
all original parent relationships. `DM_PRESERVATION.json` records input/output hashes,
object counts and the added object manifest. The supplied export has placeholders
instead of original server code; this update supplies the new modes' server systems.
It cannot reconstruct the old game's missing backend. The original assets and scripts
remain present. The original map's performance is unchanged; the new road renderer
uses the bounded streaming system described below.

## Spawning without cloud or asset access (1.3.0)

The previous build opened DataStores before connecting spawn handlers. An unpublished
place can throw during `GetDataStore`, aborting that server script. Initialization now
skips cloud storage for unpublished places and catches store-creation errors elsewhere.
The starter car can also spawn while a published game's profile is still loading.
Replays and rewards remain usable in this server when cloud saves are unavailable.

The server now creates a visible native car model and seats the driver. Client visuals
smooth its movement; they are not the only evidence of a spawned car. Driving captures
its input directly through ContextActionService, including events marked processed by
the default controls. Start requests have a visible failure message and reset the
button if no car is acknowledged.

Imported visual skins are **on by default**; external audio stays off. Cars, scenery and
road geometry are built from native parts. The original source assets stay untouched.
To keep only native fallback skins, set `ImportedVisuals=false` in Config;
external audio has its own flag. No private-asset permission change is needed to drive.

## Startup and visual assets (1.1.1)

The original export's garage waits for server code absent from that export. The ready
DM place now opens the working expansion automatically, so no original garage selection
is needed. The original garage and all its models remain available via Return to Original;
this preserves the supplied content and does not reconstruct its missing backend.

The new menu shows a complete native car preview. Driving always starts with a complete
built-in body. Imported exteriors replace it only after ContentProvider confirms their
assets loaded; a failure or an eight-second timeout keeps the built-in body. A late mesh
attaches at the car's current position. Imported trees use the same loading check, with
native trees and rocks available immediately. The original assets are not edited.

The new modes apply a local daylight/fog profile and temporarily suspend inherited blur
and color effects, preventing the old scene's haze from hiding the road. Closing restores
the original values. Mesh/audio access still depends on Roblox asset permissions; this
update handles unavailable content with complete geometry rather than requiring it.

## Replays, ghosts and cloud saves

All runs record automatically, including driver inputs. Finishing a stage updates
its personal best when faster. Endless runs can be banked; retired runs can still be
reviewed. The library retains the latest 12 runs plus up to 8 personal-best course
records. Replay pages use immutable server-generated IDs and are scoped to the
participant's library. Co-drivers receive access to the run they joined.

Replay controls: play/pause, 0.25×/0.5×/1×/2×/4× speed, timeline seeking, ±5 seconds,
chase / hood / orbit / free cameras, saved bookmarks and pedal/steering telemetry.
Hold RMB to orbit; scroll to zoom. In the replay's free camera, use WASD and RMB.
The saved ghost uses the same recorded frames and road seed; **Same Road Again**
races that personal best. Changing the seed or car creates a different comparison.

To persist across servers, publish YOUR copy of the place and enable **Game Settings →
Security → Enable Studio Access to API Services** when testing saves in Studio.
Production servers use normal Roblox DataStores. Wait for a confirmed cloud save
before leaving. Without storage access, the game remains playable and labels saves
**Session only**; those recordings disappear with the server. It never claims they
were saved to cloud. Long runs are paged while driving; memory and pending writes are
bounded. A storage outage can leave only cached pages available. Older replay data
is retained in DataStores even after it leaves the visible library.

## Performance design

The client builds a bounded window of road chunks, yields during construction and
recycles simple parts. It never constructs an entire endless map. Route coordinates
are rebased every 4096 studs to limit rendering precision loss. Scenery is kept outside
the drivable corridor; tunnels maintain clearance and bridges have protected edges.
No NPC crowds, physics stacks, synchronous cloud writes or scene-wide per-frame scans
are used. Quality can be changed manually and reduces automatically after sustained
slow frames. This changes new chunk decoration, not the course or timing gates.

The server runs a bounded fixed-step driving simulation and owns checkpoints,
completion, rewards and replay frames. Clients predict/interpolate for responsiveness.
This is a rally-focused four-contact driving model with tyre slip, braking, handbrake,
rough shoulders and barrier contacts; it is not the original game's full suspension
solver. Public fallback cars and scenery use authored primitives for portability.

## Validation and development

From the repository root:

```sh
python -m pip install -r backseat_rally_game/requirements-build.txt
python backseat_rally_game/build.py --base-place "/path/to/original.rbxl"
python backseat_rally_game/build.py --name Sakura_Pass --base-place "/path/to/Sakura Pass.rbxl"
LUAU_BIN=/path/to/luau LUAU_COMPILE_BIN=/path/to/luau-compile python -m unittest discover -s backseat_rally_game/tests -v
```

Omit `--base-place` to rebuild the clean standalone files and installer. An already
extended base is rejected. `--output-dir` selects a different artifact directory.
The original file is read without modification. Tests cover 1,000 seeded routes,
manual driving to a finish, replay and persistent ghost retrieval, storage failures,
streaming limits, additive installation, automatic startup, failed/slow mesh downloads,
optional installation, lighting isolation and restoration to the original.
Actual Studio rendering, device controls, asset loading, production DataStores and
multiplayer latency still need a Studio/Roblox playtest; headless tests do not measure FPS.

## Vehicle and asset update

Version 1.3.0 uses all 15 uploaded vehicle profiles through one configurable solver.
See ASSET_EXPORT_GUIDE.md for supported physics effects, current approximations, and
which Studio folders to export for a closer visual match. Original private assets
remain dependent on their permissions. The original Sakura renderer still needs a
Studio Output trace to diagnose any remaining disappearing-scene errors.
