# Validation — 2 November 2026 — 1.5.0

115 automated tests passed with the Luau CLI and Python unittest. Every authored
Luau source and all fourteen repaired legacy Sources compile. These are headless
checks using a Roblox test double; they are not a Studio or GPU benchmark.

## Driving and presentation

- All 15 recovered car profiles use the same bounded driving solver.
- Manual steering can finish varied courses; braking, reverse, recovery and right-turn direction checked.
- Road continuity, curve/grade bounds and rendered/contact height agreement checked across 1,000 seeds.
- Per-wheel load, pressure, temperature, wear, punctures, grip consequences, component damage and repair verified.
- Tyre deflation changes wheel height/body pose; different axle balances affect contact pose.
- Original map checks cover Sakura's native route, hairpins/backtracking and source-aligned frames; a simulated driver completes the saved course within its road corridor.
- Native original Road/Shoulder/Verge parts are reused without duplication; local appearance restores on exit.
- Original-stage spawns use saved world coordinates and correct length; streaming replication focus follows the car and restores on exit.
- Original world obstacle casts stop the car and generate recorded impacts.
- Original native interiors remain usable after an external mesh failure; optional private textures do not block confirmed geometry.
- Original driver-eye, steering and gauge attributes/parts are reused; a second dashboard never covers an original interior.
- Detailed peer car copies render locally from compact pose packets; the server retains lightweight proxies.
- Cached old-camera writes, foreign camera switches, removed cameras and invalid numeric poses cannot replace the managed view in the test double.
- Checkpoint/rebase boundary checks cover the screenshot region around 768 studs and finite Focus/pose retention.
- Live driving stays inside the adjusted cockpit after repeated camera changes; FOV/seat adjustments apply.
- Opaque fallback cabin/windows are hidden locally; original skins retain their source instances.
- Replay cockpit/chase changes restore exterior visibility; headlights switch and respect quality shadow settings.
- Cockpit, rain and impact effects allocate no instances while updating; rain has a fixed cap.
- Impact effects fade; severe blackout is optional and replay impact screens are suppressed.

## Friends, settings and recordings

- Actual server race actions exercise room creation, joins, ready states, shared rules/seed,
  separate slots, all-player road-ready barrier, common countdown and synchronized clocks.
- Live rankings, finish/DNF ordering, early finisher departure, host transfer, disconnects,
  loading timeout/retirement and partial-launch rollback tested. Standings broadcasts are capped.
- Service requires a stopped car near a bay, adds 15 seconds, repairs condition and applies pressure;
  moving/out-of-bay attempts and repeated service are rejected.
- Human co-driver input cannot steal the car; joined participants receive shared replay access.
- Settings validation rejects nonfinite/out-of-range/unknown data; binding collisions swap safely.
- CAS/UIS duplicate events do not duplicate actions; rebinding works, old keys stop driving,
  settings clear held controls, and replay freecam input suspends while settings are open.
- Settings changes coalesce into one queued write per player; saves retain existing rewards;
  session values survive failed cloud writes and successful settings load in a fresh storage session.
- Replay codec round-trips controls, suspension, tyre conditions, gear/RPM, health and impact events;
  punctures/repairs do not appear before their timestamps. Legacy 11/14-field data remains readable.
- Replay caches, pages and scrub queues remain bounded; director cuts, paused freecam movement,
  FOV/distance limits, origin rebasing and camera/mouse cleanup checked.

## Startup and preservation

- Unpublished places spawn a complete native server car without opening DataStores.
- Throwing/slow store setup cannot abort starter spawning; missing-server starts show a failure/reset.
- Banking, replay playback and rewards work in-session without storage. Failed writes are not called cloud saves.
- Failed/timed-out/unconfirmed imported meshes leave a complete native car; late valid skins align to its current pose.
- Bounded road streaming retains generated scenery on asset failure; inherited fog/blur and UI/view restore on close.
- The original exported ReplicaClient runs against the session profile/settings bridge in tests:
  handshake, readiness, independent defaults, OnSet, validation and cleanup verified.
- Zone self-reference, DataController duplicate initialization/warning throttle, and native input resolution tested.
- A 109-object copy of the supplied native InputContext/Action/Binding graph retains exact property data and hierarchy.
- The Backseat place retains all 82,861 original objects; Sakura retains all 132,961.
  Each adds 160 objects, including the expansion, input graph copy and inert Source backups.
- All original objects and parent relationships are retained. Exactly fourteen original Sources
  have listed repairs, with exact original backups and before/after hashes. Other original properties remain unchanged.
- Effective property verification rejects hidden overrides; artifact hashes/embedded authored Sources match the repository.
- Independent robloxapi/rbxfile decoding checks original instance paths and all non-Source properties;
  Python separately verifies the fourteen permitted Source changes and backups.

The collection was captured in Studio edit mode; no original driving telemetry or missing server code was recovered. Its input hash and static findings are recorded in COLLECTION_AUDIT.json.

Roblox Studio is unavailable here. Original-scene disappearing/rendering faults, imported
asset permissions, exact handling feel, real network latency, production DataStore behavior
and device frame rates still require a Studio playtest. Private media permissions cannot be
changed by this build. The original full backend is incomplete; its session compatibility
bridge does not restore private player data or reconstruct every original game service.

The driving model uses deterministic four-contact handling and anchored visuals. It does
not simulate soft-body destruction, deformable tyre carcasses, a full meteorological system
or every original chassis field. Public/native fallback geometry remains necessary when
Roblox does not grant access to an imported skin.
