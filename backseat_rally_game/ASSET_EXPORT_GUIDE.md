# Export the existing cars and scenery

In a Studio place you have permission to edit, use Explorer and save these selections
as separate `.rbxm` files with **right-click → Save to File…**:

1. `ReplicatedStorage.Assets.Cars` — the entire folder, including every car's Body,
   Wheels, Interior, Exterior, seats, attachments, attributes and physical properties.
2. `ReplicatedStorage.Assets.Stage` — the scenery templates.
3. `ReplicatedStorage.Balancing` — the configuration tables.

Keep the hierarchy intact. Send the files here. A copy where the cars already look
correct in Studio is most useful. The supplied Output log identifies private media, a recursive Zone require and
missing runtime profiles/settings/input lookups. The ready 1.4.0 binary repairs the
identified script faults. Geometry disappearance still needs a Studio reproduction;
please identify whether it happens in the new rally or the original scene if it persists.

RBXM preserves asset references; exporting it does not grant access to private meshes
or textures. Missing private geometry requires developer-granted access or a geometry
export they authorize. Public asset IDs/Creator Store links you want used are also useful.
This assistant cannot enumerate a developer's private asset library.

# Shared vehicle configuration

`src/Shared/VehicleCatalog.lua` contains all 15 recovered car profiles. One Dynamics
solver uses every profile. The catalog preserves engine curves, ratios, suspension,
tyre, steering, braking and drag data from the uploaded tables. Implemented effects
include torque/power-limited acceleration, axle-load traction, combined grip demand,
thermal/wet and load-sensitive grip, pressure loss, punctures, component damage,
sprung heave/pitch/roll, bump/rebound damping, ABS/TCS and wind influence. Some original settings
are retained for future calibration and do not yet drive a corresponding solver term.

`rearShare` comes from `Parts.Rating.Rig.Rear`: it is a starting calibration, not a
measurement of the original running assembly. The solver uses a mathematical center
of mass. Car assemblies remain anchored for the server-authoritative driving model;
this is not a recreation of the original force-based Roblox chassis. Accurate physical
assembly behavior and tyre/road calibration require Studio measurements.

Climate parameters live in `Config.Climate`; the current model includes ambient
biome temperature, wetness, wind and tyre heating. It does not simulate a complete
meteorological system, tyre carcass deformation, aquaplaning, or a full thermal engine.

Generation 3 adds per-wheel pressure/wear/puncture replay state, shared damage
and handling rules, and first-person driving. Short-wave road elevation and
suspension poses remain in the renderer/replays. Bump the generation when changing the road/handling model incompatibly.
Original models are normalized about the wheel axle center, with the per-car balance
offset applied when placing a loaded skin. Native models stay visible when assets fail.
