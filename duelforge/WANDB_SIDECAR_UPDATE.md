# Separate W&B uploader and trajectory regression pause

Pause training and close its console, then extract into E:\Downloads, merging
chat_gpt_ai/duelforge. Checkpoints, optimizer state, objectives and stage pointers
are preserved. No package install or engine rebuild is needed.

33_START_CONTACT_CURRICULUM.bat now opens a second console for W&B. The trainer
writes local metrics.jsonl and performs no W&B initialization, logging or network
upload. The uploader polls those files separately, resumes each existing stage's
W&B ID, and follows stage transitions. Closing the uploader does not stop training;
40_START_WANDB_UPLOADER.bat restarts it and replays any backlog. Only one uploader
may run. It reads configs/metrics, never model tensors or GPU state. Credentials
are handled by W&B's existing login. Network retries remain in that console.

W&B is already partly asynchronous internally, so this change is process isolation,
not evidence of a specific SPS gain. Local metric writes, evaluation, report creation
and CPU simulation still consume time. Rate comparisons need measurements.

The previous controller printed failed trajectory skill gates but kept training.
It now saves and pauses after a failed gate, and refuses to resume an existing
trajectory with a recorded failed last gate. It does not roll back or discard weights.
Review both stages with these launchers while training stays paused:

* 41_WATCH_POSSESSION_VS_PARENT.bat: blue = possession student, orange = frozen
  curriculum-start parent. Both Octane; no training.
* 42_EVALUATE_POSSESSION_VS_PARENT.bat: 200 games, 100 seconds, balanced colors.
* Existing 37_EVALUATE_CONTACT_CURRICULUM.bat: same evaluation for active trajectory.
* Existing 36_REPORT_CONTACT_CURRICULUM.bat: one combined report to share afterward.

The submitted report shows possession completed 1.54M stage steps and passed its
first-touch gate. Trajectory later failed contact latency despite reaching the ball
in many trials. One recorded orange goal followed blue's last touch, consistent with
the reported own goal. These are skill/discovery results, not a match-strength
promotion. No reward change is bundled without a controlled match comparison.

Validation: physical shots into both home nets across all three stages give the
correct +1/-1 goal rewards; uploader partial-line handling, existing-ID resumption,
server-step deduplication and trainer bypass are tested. Full training tests retained.
Actual online uploads and Windows console launch need the existing user runtime.
