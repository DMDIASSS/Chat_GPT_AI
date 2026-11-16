# Separate aerial-contact recovery experiment

The previous reports already had almost-zero jump-button use before the contact
curriculum. Ground-only contact drills reinforced that bias; later native masks
restore jump controls but do not themselves teach useful jumping. This update
preserves the match-confirmed bot and trains a separate air01 experiment.

Pause 33 with 34 first. Extract into E:\Downloads, merging chat_gpt_ai/duelforge.
Run 43_START_AERIAL_CONTACT_RECOVERY.bat. It first diagnoses the preserved actor
on 64 controlled cases. If at least half use jump and half make a valid raised
contact, it stops without training and reports AIR_SKILL_PRESENT. This indicates
a match-usage/generalization issue rather than a broken jump mask. Otherwise it
runs ONE bounded +500k learner-step trial.
It starts from the pinned confirmed trajectory reference (currently 61.22M),
not whatever unverified latest weights might exist after continued training.
The original contact01 and reference remain untouched. The new run lives at
runs/air01/03_trajectory; that subfolder name is for uploader/report compatibility.
Its actual objective is elevated_contact_rehabilitation_v1.

The actor and its Adam moments transfer unchanged. The critic resets once for
new mixed returns. Resuming air01 does not reset it again. All jump controls
remain available; no scripted jump controller is deployed or used as a teacher.
Forty percent of training episodes are short elevated-ball trials, with balls
300–500 units high, upward velocity, nearby aligned ground cars and sufficient
boost. A bonus is paid for an actual ball contact while the car is lifted and
ball is above 220 units; ground touches after waiting for the ball to fall do
not earn that bonus. A small velocity-toward-ball signal guides approach.
These trials end after success or 1.4 seconds. There is no reward merely for
pressing jump, staying airborne, spinning or repeatedly flipping. The remaining
60% use ordinary self-play and the existing trajectory possession/goal objective.
The source actor is seeded into the frozen opponent pool so 25% frozen/history
opponent sampling works from the first update, providing a retained baseline
opponent rather than waiting for the first new snapshot.
A conceding car receives no same-frame contact bonus, so that bonus cannot
cancel its -1 goal penalty. Entropy coefficient is 0.01 in this separate run to encourage exploration.

At +500k (one rollout may overshoot), compare source and student on the same
64 full-control elevated-contact cases, then run 200 balanced-color matches
against the preserved source. Create DuelForge_air01_report_*.zip automatically
and stop. Increased jump count alone does not qualify as success: elevated
contact and match results must be assessed together. No auto-promotion occurs.
The first trial is deliberately bounded, rather than endlessly modifying the
confirmed bot. Actual learning improvement is not guaranteed by a button/mask fix.

43 start/resume another bounded +500k air01 trial; 44 pause/save;
45 watch the student against its source in native elevated open-play scenes;
46 combined air report; 47 extra match evaluation; 48 export the experimental
student via the existing RLBot v5 wrapper. Do not run ground and air trainers
concurrently on the laptop. The air uploader is separate and uses the name
'air01_jump_recovery'. Closing it does not stop training.

Validation: full native jump masks, a scripted physical jump used only in tests
that makes a genuine elevated contact, denial of bonus for low/ground contacts,
source/actor preservation, two real PPO updates, full-control skill probes, and
the existing suite. CPU pilot results use a small model, not the user's confirmed
checkpoint; live Windows GPU/RLBot and improvement of that model require the trial.

The preparation 500k small CPU pilot increased match score against its weak
starting model but reduced controlled elevated-contact rate from 51.56% to 18.75%;
both models used jump in these cases. This is a rejected skill-recovery result,
not evidence of an improved aerial bot. It motivated the baseline precheck, seeding the frozen source opponent, and
strict separation from your confirmed model. Its recorded result is included.
The first production action is diagnosis, not blind retraining.
