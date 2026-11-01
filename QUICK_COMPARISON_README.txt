Quick comparison of update180, update278 and native attention checkpoint197

1. Pause training and wait for it to finish saving.
2. Extract STUDIO_COMPARE_180_278_197.json into your Chat_GPT_AI folder.
3. Open TRAINING_STUDIO.vbs.
4. All settings -> Import settings -> choose this JSON.
5. Find best models -> Start comparison.
6. When complete, Results -> Refresh reports.

First pass: 72 matched 30-second games, three models, Nexto and update180,
two seeds, both colors, and 1v1/2v2/3v3. Candidate-policy squads are used.
Learner kickoff script OFF; frozen teammates/rivals ON, as in training evaluation.
Only these three checkpoints are scanned. No models are deleted or trained.

For stronger evidence, keep the same selection run, change Stop after stage
to confirm and click Resume comparison. Completed games stay cached.
Later stages include all three models as opponents plus Nexto, fresh seeds
and longer games. A confirmed-stage ranking may still be inconclusive.

Report:
data/isolated/model_selection/runs/compare_180_278_197_01/SHORTLIST.md

If this run name exists from another setup, choose a fresh name before starting.
The 197 path assumes native run update180_attention02/checkpoint_000197.
If your 197 is elsewhere, update its path in selector.anchors.attention197,
selector.families.known_strong and selector.rivals.attention197.
Cycle9 needs its exact compatible .pt path before it can be added.
