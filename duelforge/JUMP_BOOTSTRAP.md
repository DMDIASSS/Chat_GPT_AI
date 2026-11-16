# Jump-and-contact bootstrap, separate supervised candidate

The air01 reports show three normal completions, 1.55M additional RL steps, no
jumps or elevated contacts in controlled checks, and one significant match
regression. More runs of 43 are not the prescribed recovery. The update also blocks resuming
an unchanged air01 checkpoint after a completed zero-jump/zero-contact result. Preserve air01
results and the original confirmed trajectory; this tool creates runs/jump01.

Pause other trainers. Extract into E:\Downloads, merge chat_gpt_ai/duelforge,
and run 50_BOOTSTRAP_JUMP_SKILL.bat. It starts from the pinned confirmed 61.22M
trajectory reference, not the failed air01 latest actor. No original model is
modified. It runs a bounded supervised warmup and then tests and stops normally.

The tool collects real RocketSim trajectories for a simple jump, release and
second jump into low elevated balls. It retains only sequences with actual
high-ball contacts and asserts that every demonstration action was legal under
the deployed action masks. The teacher's neutral control is found by matching
all-zero controls in the action table, rather than assuming an index. Failed
demonstrations are discarded. This is a training teacher, not the exported bot.

Train only the actor's last block and output head. Freeze the early actor layers
and the whole critic. Mix demonstration cross-entropy with a KL retention loss
on ordinary low-ball states collected from the confirmed actor. Keep the best
controlled validation contact result with mean ground-state KL <=0.05. Record
progress every 25 updates and save the supervised optimizer/RNG for resume.
Default is 300 updates, not 500k RL steps. The inherited RL transition counter
stays unchanged; bootstrap updates have their own W&B logging_step and metrics.
Do not interpret that unchanged RL counter as a stalled process.

The new candidate keeps the original observation/action/hitbox/timing contract,
critic, early actor parameters and unaffected PPO Adam moments. Clear PPO moments
only for the actor tensors changed by supervised learning. Seed the new frozen
history pool with the source actor; the original history and source artifacts
remain in their existing run. No PPO is automatically started after bootstrap.
Scoring +1/conceding -1 remain in the original reward configuration; supervised
fitting does not replace the game objective with a jump-button reward.

After fitting, evaluate 64 unseen easy launch cases, the wider original aerial
probe and 200 balanced-color 100-second matches against the exact frozen source.
Write DuelForge_jump01_report_*.zip. No automatic promotion occurs. Restored
jump/contact ability and retained match strength must be assessed together.
This teaches basic jump strikes, not flip resets, arbitrary aerials or pro play.

50 start/resume the bounded fit; 51 watch the neural student versus its source
in native elevated open play; 52 report; 53 export; 54 match evaluation;
55 request pause. Do not rerun 43 to run this experiment. Repeating 50 resumes
saved supervised updates and does not overwrite the confirmed source. It does
rerun the final evaluations if fitting is already complete.

W&B stays in a separate uploader process using the existing credentials. Its
run is named jump01_supervised_contact. The uploader supports logging_step for
supervised metrics, and still uses learner transitions for ordinary PPO runs.
It can be restarted with the existing selected Python and:
  tools\wandb_sidecar.py --root runs\jump01

Preparation evidence: a small 64-wide CPU model with jump logits deliberately
suppressed had 0/64 easy-launch contacts; a clean-label 200-update bootstrap
reached 63/64 unseen easy contacts, with 24/64 on the wider aerial probe. Its
200 source matches were all draws without goals, so that match check provides
no useful evidence about stronger play. These are regression-test results,
not the user's 1.22M actor. The actual model's gains require its saved report.
An early prototype's invalid neutral-action labels were rejected by tests and
are not used in this release. Demonstration legality is also checked at runtime.

No dependency reinstall, native-engine rebuild or change to existing bot weights
is required. A live Windows/RLBot match and online upload are not verified on the
CPU preparation machine; native collection, supervised fit, resume, export path
compatibility and match evaluation are covered by local tests and smoke runs.
