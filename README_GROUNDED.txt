CHAT GPT AI: grounded experiment (NOT Nexto transfer)
==================================================

What is included:
- A new --preset grounded, optimized for simple ground control while preserving
  your existing 92-feature observations, 90-action parser, and 512x512 policy.
- 10% kickoff, 65% ground, 25% defense state distribution.
- Reward for improving ball distance, ball movement toward net, touches, and goals.
- Very small disincentive for airborne time when far from a low ball.
- No Nexto trained weights are copied. This does not promise Nexto-level play.

INSTALL:
1. STOP training. Keep your existing `data/checkpoints` folder.
2. Extract this whole ZIP into E:\Downloads\Chat_GPT_AI, keeping folders.
3. Double click INSTALL_GROUNDED.bat; it backs up overwritten Python files.
4. The TRAIN_GROUNDED_TEST.bat launcher automatically backs up old checkpoints.
   If you run the command manually, BACK UP your existing 1m checkpoint tree, e.g.:
   Copy-Item 'data\checkpoints\chat_gpt_ai' 'data\checkpoints\chat_gpt_ai_before_grounded' -Recurse
   (Make sure the destination doesn't already exist.)
5. Double click TRAIN_GROUNDED_TEST.bat, or execute manually:
   .\.venv\Scripts\python.exe train.py --preset grounded --steps 1250000 --workers 2 --batch 10000 --minibatch 2000 --save-every 50000 --device cuda:0
   IMPORTANT: DO NOT use --fresh or --init-policy. It RESUMES the checkpoint.
6. Watch with watch.py --preset grounded --sample.

CHECK RESULTS:
- Evaluate 20+ full matches from same saved starting policy before and after.
- Record actual touches, goals, kickoff time-to-first-touch, jumps/minute and
  boost consumption. You cannot determine quality from reward alone.
- Existing presets remain accessible.

LIMITATIONS:
- This is an engineering experiment, not confirmed to improve playing skill.
- Potential shaping can still be exploited in self-play; match tests matter.
- New reward function resets at episode start. Long-run training requires
  benchmarking and potentially more sophisticated episode curricula.
- Strictly a local/offline bot; do not use in ranked matchmaking.

NEXTO MODEL NOTES:
The Necto-master.zip you provided includes rlbot-support/Nexto/nexto-model.pt,
but it is a TorchScript entity-attention policy, not the DiscreteFF model used
by Chat GPT AI. Directly calling train.py --init-policy with that file will not
work. Necto uses CC BY-NC-SA 4.0; check its license if distributing derivatives.
