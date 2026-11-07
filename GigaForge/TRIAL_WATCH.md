# Watch the exact +4.7-point Chronos candidate

Keep training paused. Merge the ZIP's chat_gpt_ai into the existing folder,
including BOTH gigaforge and novaforge. No runtime, native executable or CUDA
installation changes are included. Open **18_WATCH_CHRONOS_TRIAL_62.bat**.

The requested model is research02 Chronos trial 62, evolved_40 at 1,048,576 branch
decisions. Its fresh confirmation match-score difference was +4.6875 percentage
points; it did not pass promotion. Chronos uses Breakout. RLViser shows this
candidate as BLUE/car 1 and original Galactus as ORANGE. Ctrl+C stops viewing.

The launcher obtains the two exact model hashes from the trial's evaluation
jobs, then checks saved checkpoints, policy versions, shortlist, previously
pinned models and this run's exports. A found actor is copied into watch_pins
so future checkpoint rotation cannot remove the selected copy. It never changes
champions, the active training candidate, optimizer state or training status.

If it says weights were not found, the exact model is unavailable in the searched
locations. It will not show a different +4.7 screening result, an original bot,
the latest candidate, or an adjacent checkpoint as if it were trial 62.
Statistics and reports cannot recreate neural-network weights. The current
shortlist in the uploaded report contains trials 42 and 38, not 62, so this
snapshot may already have rotated out. Existing exports could still preserve it.

If lookup fails, share runs/research02/watch_requests/trial_00062_chronos.json,
or run 8_REPORT, which includes that file. A backup containing BOTH original
model files, or an existing export with matching provenance, can be used.

Future positive confirmation-test candidates now have a separate bounded archive
of two actors per family, ranked by match-score point estimate. These remain
UNVERIFIED; promotion and exports still require the existing full guards. This
fixes a retention gap: the earlier shortlist ranked development screens and did
not guarantee preserving the best confirmation-test result. It cannot recover
an already deleted model.

Generic command: selected project Python, then
`python run.py watch --run research02 --family chronos --trial 62`.
Buttons 5/6 still select retained actors, and 10/11 select latest candidates.
Console viewer labels now state which kind of actor is selected.
