Original mechanics checkpoint scan 1-400

Finish/pause the current three-model comparison before starting this separate scan.
Export your current Studio settings if you want to restore them afterward.
Extract this ZIP into E:/Downloads/Chat_GPT_AI.
All settings -> Import settings -> STUDIO_SCAN_MECHANICS_1_TO_400.json.
Find best models -> Start comparison. Run name: mechanics400_scan01.
Results -> Refresh reports after the first stage completes.

Inventory reads exactly update_000001.pt through update_000400.pt and accepted*.pt.
Missing optional files are absent from inventory, not replaced. Identical actor
weights are compared once. The protected 180/278/native197 paths must exist.
No source, native code, executable, previous comparison or model is overwritten.

Fast first pass: four 20-second 1v1 games per distinct candidate against Nexto
and update180, using the same seed and both colors. 400 distinct models would
require 1600 games, plus any extra distinct accepted/native197 actors. This is
not all-vs-all and does not train models. Runtime depends on actual inventory,
GPU load and thermal/power settings; a large scan is not an instant comparison.

The first pass prioritizes duel ability in this original mechanics family.
A specialist that is poor at duels could be missed; it is not a best-team-model
verdict. Exact cutoff ties and protected anchors are retained. Up to 16
leaders plus up to 8 uncertain neighbors progress; exact ties can enlarge this.

When done, keep the run name and change Stop after stage to refine, then click
Resume comparison. Refine tests fresh seeds, longer games and 1v1/2v2/3v3.
Later choose finalists then confirm, resuming each time. Later stages can be
substantially longer, especially if many models tie. Fresh confirmation is
needed before treating an exploratory screen leader as a replacement for180.
Pause/resume preserves completed games. Do not edit this run's pinned protocol.

Reports: data/isolated/model_selection/runs/mechanics400_scan01/SHORTLIST.md,
shortlist.json, inventory.json and stages/<stage>/ranking.json.

The native197 path is update180_attention02/checkpoints/checkpoint_000197/actor.pt.
Cycle9 is not included without its actual compatible .pt checkpoint path.
