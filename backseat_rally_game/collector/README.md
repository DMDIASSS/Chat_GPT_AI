# Studio project collector

This inspects the copy you can open in Studio. It does not run inside someone else's
live experience, recover non-replicated server code, decompile scripts, call gameplay
remotes, or grant private-asset permission. A collector in an incomplete copy cannot
make that copy complete. Short script Sources are flagged for inspection, not proven missing.

1. Download DM_Collector.rbxmx from GitHub and drag it into Workspace in your Studio copy.
2. Open View > Command Bar and run:

```lua
require(workspace.DM_Collector).capture()
```

3. Find `ServerStorage.DM_Collection_Project_...`. Right-click that folder > Save to File
   > `.rbxm`, then attach that file here. Also save the place with File > Save to File
   > `.rbxl`; that preserves Terrain voxels and place/service settings which folder
   cloning does not fully capture. Keep the source place as your original backup.

The folder contains readable manifests and copies of accessible models, scripts,
configuration Values, attributes, asset IDs, attachments and constraints. Source
instances are unchanged. Script copies are disabled and retain their original
Disabled state in a DM_OriginalDisabled attribute. Non-Archivable objects are reported
instead of modifying their original properties. Export size can be large.

If a car can spawn in a Studio playtest, select its whole Model in Explorer. In the
**Server** command context, run:

```lua
require(workspace.DM_Collector).start(game:GetService('Selection'):Get()[1])
```

Drive for up to three minutes, then run:

```lua
require(workspace.DM_Collector).stop()
```

Export `ServerStorage.DM_Collection_Runtime_...` as `.rbxm` **before stopping Play**.
This records up to 1,800 samples at roughly 10 Hz: mass, center of mass, transforms,
velocities, exposed controls/Values and suspension/motor properties (up to128trackedobjects).
It cannot measure a working original car from an already-broken copy. Roblox's normal
player client provides no Command Bar for inserting this into another person's game.

Send the project collection, runtime collection if available, and the RBXL. They can
help distinguish usable native geometry/configuration from missing implementation or
inaccessible assets. JSON is stored in numbered StringValues; concatenate in Name order.
