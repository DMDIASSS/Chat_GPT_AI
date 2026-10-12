SLATER v0.2.7 — FIRST SUSTAINED CYCLE 9 TRAINING RUN
====================================================

What this does
--------------
- Builds a trainable student from the ORIGINAL SHA-protected Cycle 9 actor.
- PPO on normal RocketSim 1v1 kickoffs with both Blue and Orange episodes.
- Mixes FROZEN Cycle 9 and the ORIGINAL FROZEN Nexto TorchScript policies
  as opponents. An immutable Cycle 9 teacher supplies a KL anchor.
- Periodically creates new numbered checkpoints (never replaces existing).
- Can resume FROM an existing v0.2.7 checkpoint with a NEW run name.
- Compares both policies against real frozen Nexto on matched kickoff seeds,
  both team sides, before training and every checkpoint interval.
- Does NOT touch Cycle9, champion, teacher, original Nexto, or replay NPZ files.

Important scope
---------------
This is actual PPO training, NOT another preflight; however, it is only the
FIRST stage of a longer training campaign. It is 1v1, not 2v2/3v3. It uses
short goal-or-timeout games, not regulation 5-minute full-match evaluation.
The baseline '58% vs Nexto' from another benchmark CANNOT be directly compared
to v0.2.7 short match win rates. Goals within 30s are sparse; a higher return
or more touches may not mean a stronger bot. No auto-promotion.
Source replay data is NOT yet in this phase: its currently verified windows
are too short and sparse to train all of Slater's mechanics and teamplay.

Requirements
------------
- Run from E:\Downloads\Chat_GPT_AI on the SAME Python .venv that passed v0.2.5
- Existing slater_cycle9_native_ppo_v025.py
- Existing slater_cycle9_paired_eval_v026_fixed.py
- Existing Slater project modules and vendor/nexto/nexto-model.pt
- Extract THIS ZIP into project root; it adds a script and tests only.

Run tests:
  .venv\Scripts\python.exe -m pytest slater_v027_tests -q

Launch real training (163,840 PPO decisions, periodically checkpointed):
  .venv\Scripts\python.exe slater_cycle9_train_v027.py --run slater_v027_campaign01 --updates 80 --rollout-steps 2048 --checkpoint-every 20 --max-episode-steps 450 --eval-seeds 8 --eval-max-steps 450

The checkpoints will be created under data/isolated at updates 20, 40, 60, 80:
  slater_v027_campaign01_u0020.pt  (plus .json report)
  slater_v027_campaign01_u0040.pt
  slater_v027_campaign01_u0060.pt
  slater_v027_campaign01_u0080.pt

If interrupted between checkpoints, resume from the LAST completed checkpoint
in a NEW run name, for example:
  .venv\Scripts\python.exe slater_cycle9_train_v027.py --resume data/isolated/slater_v027_campaign01_u0020.pt --run slater_v027_campaign02 --updates 60 --rollout-steps 2048 --checkpoint-every 20 --max-episode-steps 450 --eval-seeds 8 --eval-max-steps 450

Every UPDATE prints training rewards, entropy, teacher KL, goals, episode
side/opponent counts. Every EVAL_VS_REAL_NEXTO compares ORIGINAL vs candidate.
The previous failed v0.2.5 checkpoint is intentionally NEVER resumed.

Guardrails
----------
- Source checkpoint and vendor Nexto file are SHA verified at startup and
  each checkpoint. Frozen teacher and Nexto weights checked for equality.
- Only create-new files in data/isolated, under a new run prefix.
- No automatic champion promotion. No original checkpoints overwritten.
- If goals/rewards collapse, STOP and inspect. Scaling the update count is not
  a substitute for correct reward design and realistic matchmaking.

Next after the FIRST campaign
-----------------------------
- Use frozen checkpoints for controlled comparison to Cycle9 and Nexto on
  FULL 5-minute matches, both team sides, multiple seeds, distinct opponents.
- Add pool self-play / more diverse starting states / parallel simulation.
- Add 2v2 (and later 3v3) to learn passes, rotations and team positioning.
- Integrate replay scenarios ONLY when longer windows and interaction
  fidelity are validated, with no held-out evaluation leakage.
- The 90% vs Nexto target is an aspirational performance goal, NOT an
  expected result of this first 163,840-decision run.
