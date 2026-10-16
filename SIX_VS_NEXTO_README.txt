Studio settings preset: 205, 266, 271, 164, 296 and180 versus Nexto only.

1. Pause/finish any current Studio job; export your current settings if needed.
2. Extract this ZIP into E:\Downloads\Chat_GPT_AI.
3. Open Studio -> All settings -> Import settings ->
   STUDIO_COMPARE_205_266_271_164_296_180_VS_NEXTO.json.
4. Find best models -> Start comparison.
5. Results -> Refresh reports when it finishes.

Default: 1v1, eight matched seeds, both colors, 120 simulated seconds/game:
96 games if all six actors have different weights. Identical actors are tested
once. Each checkpoint uses its learned kickoff; Nexto's scripted kickoff is ON.

Only the six exact update_000NNN.pt files are required, in:
data/isolated/mechanics_curriculum/selected7_mechanics01
All six are protected anchors, so a missing required checkpoint fails rather
than quietly substituting a model or leaving it out. No models are modified.

Ranking compares goal difference/minute against update180's result versus the
same Nexto, seed and color. update180's relative score is always zero; zero does
not mean zero goals. Positive scores beat its measured goal difference; read
W/D/L and goals in stages/screen/ranking.json alongside the confidence interval.
This is an exploratory Nexto-duel ranking, not a guarantee of overall strength.

Report folder:
data/isolated/model_selection/runs/compare_six_vs_nexto01
SHORTLIST.md, shortlist.json, stages/screen/ranking.json.

Pause/resume keeps completed games. For additional evidence keep the run name,
change Stop after stage to refine, finalists or confirm and Resume comparison.
Those stages use fresh seeds, retain all six and still face only Nexto (no peer
head-to-head or extra bots). They take longer. Native binaries/source unchanged
by this settings-only package; use the currently compatible Studio build.
