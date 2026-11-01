# Backseat Rally / Expedition

An optional driving expansion added to the uploaded Backseat Rally place, plus a standalone preview.
Solo play with an optional human co-driver, four game modes, continuous seeded roads,
checkpoint recovery, a replay library, and saved personal-best ghosts. It contains no
executor code or live-game injection. The full DM place retains the supplied original content.

## Download and play

Open **DM_Backseat_Rally_v1.1.1.rbxl** (or the identical **DM_Backseat_Rally.rbxl**
inside the ZIP) in Roblox Studio. This is the uploaded place with the
expansion appended. Press **Play**: the working rally menu opens automatically. Select
a mode, car and optional numeric seed, then **Take the Road**. No installer command is
needed for this file. The procedural road appears when you start a run, not in Edit mode. **Return to Original**
banks/retires an active run and restores the original UI, camera, lighting and
character location. Bots and other files in the repository are unchanged.

**DM_Backseat_Rally.zip** contains the ready place, standalone preview, Studio
installer, source code, tests, hashes and preservation report. Extract it first.
**Backseat_Rally_Expedition.rbxlx** is an additional preview with lightweight fallback
assets and the same automatic start menu. No plugin or HTTP access is needed.

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
LUAU_BIN=/path/to/luau LUAU_COMPILE_BIN=/path/to/luau-compile python -m unittest discover -s backseat_rally_game/tests -v
```

Omit `--base-place` to rebuild only the standalone preview and installer. An already
extended base is rejected. `--output-dir` selects a different artifact directory.
The original file is read without modification. Tests cover 1,000 seeded routes,
manual driving to a finish, replay and persistent ghost retrieval, storage failures,
streaming limits, additive installation, automatic startup, failed/slow mesh downloads,
optional installation, lighting isolation and restoration to the original.
Actual Studio rendering, device controls, asset loading, production DataStores and
multiplayer latency still need a Studio/Roblox playtest; headless tests do not measure FPS.
