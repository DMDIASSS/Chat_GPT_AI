# Testing Chat GPT AI against Nexto (offline only)

This project does **not** package Nexto weights. Obtain a legitimate Nexto build from:
https://github.com/Rolv-Arild/Necto or from an RLBot-approved bot pack.

1. Train until `data/checkpoints/chat_gpt_ai/<step>/PPO_POLICY.pt` exists.
2. `python evaluate_policy.py` confirms a policy can be reconstructed and used for inference.
3. Install RLBot v5 for Windows: https://wiki.rlbot.org/v5/framework/v5/
4. Install `requirements-extra.txt` in your project venv.
5. Import this project's `bot.toml` into RLBot's GUI. Verify its `run_command` points to your `.venv` environment in the project root.
6. Add Nexto as opponent on orange, **Chat GPT AI** as blue; select a standard 1v1 Soccar map and play a five-minute game. Repeat with team colors swapped.
7. Play at least 20 games per checkpoint, preferably more. Record scores, wins, kickoff results, boost usage and whether touches/defenses/aerials are functional.
8. Calculate win percentage: `wins / games`. Ties should be resolved by overtime, or reported separately.

Never infer Nexto win rate from PPO loss/reward or from imitation validation accuracy. Save match records and compare checkpoints. Nexto is a strong baseline; a random-initialized policy will initially be very weak. RLBot is an **offline bot framework**, not an online matchmaking cheat tool.

## Mechanic acceptance tests (not implemented as automated tests)

- Kickoff: diagonal/side/straight positions; measure first-touch, kickoff-goal concessions, speed; assess true speed flip and a working wavedash, not merely button presses.
- Air dribble: repeated controlled ball touches while aerial; position ball into goal with multiple touches.
- Double tap: intentional backboard hit followed by your second touch.
- Flip reset: recover a flip from wheel-to-ball contact, then successfully apply it.
- Ground/ceiling/Kuxir pinches: measurable high-velocity launch from correct surfaces, not random touches.

The supplied mechanics reset mix supports exploration, but **does not yet implement targeted, verified mechanic-specific episode scripts or learned mechanic benchmarks**. Those are needed before declaring any of these skills present.
