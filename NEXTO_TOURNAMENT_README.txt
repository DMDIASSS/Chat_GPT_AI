Nexto-only staged comparison for mechanics update_*.pt

The current Studio and native executable already support this preset. No source
update or native rebuild is needed. It does not modify or delete checkpoints.

1. Pause the current comparison safely and wait until it stops. Export current
   Studio settings if you want to restore them later.
2. Download this ZIP and extract it into E:\Downloads\Chat_GPT_AI.
3. Studio -> All settings -> Import settings ->
   STUDIO_NEXTO_TOURNAMENT_1_TO_400.json.
4. Find best models -> Start comparison. The preset automatically runs all
   four stages; Results -> Refresh reports shows the current stage.

Each stage faces Nexto only, both colors, 1v1/2v2/3v3, with the candidate
policy controlling its whole team. Scripted kickoff is ON for every car.

Stage       Models                 Seeds  Match length
Screen      all distinct updates   2      30 seconds
Refine      ~32 plus anchors/ties  4      60 seconds
Finalists   ~8 plus specialists    6      120 seconds
Confirm     leaders/anchors        8      300 seconds

The checkpoint inventory de-duplicates identical actor weights. update180,
update019, update271, update205 and update266 are protected anchors in every
stage. All original checkpoints remain. Exact ties and borderline candidates
can enlarge the shortlist substantially; it is deliberately not a hard cap.
The quick screen can also miss an unknown specialist; no short screen can
certify the best model. Per-format leaders are reported in later stages.

The 400-model initial screen schedules 4,800 games. If shortlists remain small,
the subsequent stages schedule hundreds, rather than giving all 400 models
40 rounds in every format. Games are longer in later stages. This can be much
faster overall, but is not a measured speed multiplier. If many models tie, it
can take longer. It uses the same native C++ evaluator, not a new physics
framework. Read SHORTLIST.md and stages/<stage>/ranking.json under:
 data/isolated/model_selection/runs/nexto_tournament400_01/

Your existing nexto_rounds400_01 or nexto_rounds400_fast01 run remains saved.
This new run cannot reuse first-goal records because it tests timed matches
with different seeds and rules. Resume the old run with its original settings
if you want to finish it later. Once this tournament starts, its own pause and
resume reuse its completed games, provided its code/native binary/settings
are unchanged. Do not rebuild the engine while a run is active.
