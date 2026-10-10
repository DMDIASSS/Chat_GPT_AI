Cycle9 FUSION v1 — experimental RLBot v4 only
===============================================

PURPOSE
A safe, separate 3-model RLBot controller, focusing on the user's observed
problem: two independently aggressive Cycle9 clones bump and double-commit
against two Nextos. All three source models remain frozen and unchanged.
This version is a heuristic ensemble, NOT a newly trained policy, and has NOT
been validated in a live RLBot match in the authoring environment.

INSTALL
1. Ensure the previous 4.5-hour AFK experiment printed "PAUSED" in its
   original training CMD window. Keep original checkpoints and backups.
2. Extract this zip INTO E:\Downloads\Chat_GPT_AI (beside auto_league.py,
   export_rlbot_v4.py, data\, rlbot_v4_template\, and .venv\).
3. Double-click FUSION_0_TESTS.bat (pure decision/controller tests).
4. Double-click FUSION_1_PREFLIGHT.bat (reads 3 source weights and checks template).
5. Double-click FUSION_2_EXPORT_RLBOT4.bat.
6. The standalone export appears under:
   data\rlbot_exports\Cycle9_Fusion_v1\bot.cfg
   Import bot.cfg in RLBot v4 alongside original Cycle9 and two Nextos.
7. For two Fusion clones, choose the same exported bot twice. Both compute
   which car is first man from the same game packet using deterministic roles.

WHAT THIS VERSION DOES
- Aggressive first man: original Cycle9 unless a specific alternate role applies.
- In a favorable attacking shooting lane: original AutoLeague champion model.
- If the ball threatens own net: Wavedash model.
- Second man in 2v2: goal-side support control, avoiding simultaneous challenges.
- Role choice is calculated from approximate approach time and tie-breaking ID.
- Kickoff: closest-to-ball goes; ties use the left-goes convention.
- Model choice has a short switching cooldown (0.55 seconds) except under danger.
- The steering support controller has conservative speed, boost, and teammate
  collision precautions; doesn't guarantee no bumps or smart rotations.
- No hardcoded dribbles, no physics manipulation, and no modification of weights.

LIMITATIONS (IMPORTANT)
- This first version is intentionally conservative. The second car may be too
  passive; first-man selection and shadow positioning are only approximations.
- Champion's shooting advantage and Wavedash's defense are based on gameplay
  observations, not formally verified for all 2v2 situations.
- Local policy switching may cause discontinuities. Three models increase CPU
  inference/memory use. Verify bots reach full decision rate with both copies.
- RLBot v4 ONLY, not RLBot v5. Requires compatible working v4 environment and
  rlgym-compat dependencies. This exporter does not install RLBot for you.
- Kickoff rule requires near-synchronous game packets for both bots; no shared
  IPC/blackboard is implemented, so some transient role disagreement remains.
- No RocketSim PPO team training is performed by this package.
- Created folders aren't replaced. To regenerate, use a distinct --name.
- Offline/private games only. Respect upstream Necto/Nexto CC BY-NC-SA 4.0.

MEASURE V1 VS BASELINE
Use standard 5-minute matches, swapping blue/orange and opponent slots.
BASELINE: Cycle9 + Cycle9 versus Nexto + Nexto.
EXPERIMENT: Fusion + Fusion versus Nexto + Nexto.
Measure goals for/against, double-commits, bumps, open-net concessions,
second-man field positioning, and successful shots. Test at least 5 full
matches each; 10+ preferred. Save a replay if possible.
If Fusion is worse, do not replace original Cycle9. We can adjust role logic
based on concrete replay situations, then design learned 2v2 rewards.

CHECKPOINT SECURITY
The exporter enforces the previously verified Cycle9 and champion SHA256 hashes,
records source SHA256 hashes, verifies TorchScript parameter parity, and refuses
to overwrite an existing export folder. A failed export cleans up only the
freshly created Fusion folder. Existing RLBot exports and training files remain.

If a command fails, send its complete text output; do not run as administrator.
