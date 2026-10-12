Slater Research v0.2.1 -- first isolated native RocketSim PPO smoke experiment

PURPOSE
Validate a full, isolated reinforcement-learning loop: real RocketSim episode
resets, action controls, rewards, PPO gradient updates, measured before/after
performance, and a safely saved NEW checkpoint.

THIS IS NOT:
- 1v1 self-play or competitive Slater training.
- replay imitation or PPO replay curriculum training.
- a continuation of Cycle 9's Nexto-style policy architecture.
- proof of a better bot just because parameters changed.

FIRST WINDOWS CMD RUN (from E:\Downloads\Chat_GPT_AI)
1. Extract the zip directly to your project root. It contains:
   slater_native_ppo_smoke_v021.py
   SLATER_NATIVE_PPO_V021_README.txt
   slater_v021_tests/test_native_ppo_v021.py
2. Confirm your prior RLGym installation is still working:
   .venv\Scripts\python.exe -c "from rlgym.rocket_league.sim import RocketSimEngine; print('RocketSim import OK')"
3. Run fast Python-only tests (no RocketSim dependency):
   .venv\Scripts\python.exe -m pytest slater_v021_tests -q
4. Start a small experiment using two PyTorch CPU threads (8 logical CPU cores
   on this machine; GTX1650 present but batches are initially tiny):
   .venv\Scripts\python.exe slater_native_ppo_smoke_v021.py --updates 2 --rollout-steps 768 --eval-episodes 8 --device cpu --out data/isolated/native_ppo_v021_smoke_01.pt
5. Send the PRE_EVAL, UPDATE, POST_EVAL, POLICY_WEIGHT_DELTA_L2, and SUMMARY lines.

IF YOU ALREADY RAN IT:
Never delete or overwrite the checkpoint accidentally. For a new experiment
choose a new output name, e.g. native_ppo_v021_smoke_02.pt.

CHECKPOINT SAFETY
- Only accepts new output paths under data/isolated/.
- Refuses existing output and partial files.
- Does not import the old slater_research training modules.
- Does not load, read, write, or change Cycle 9, Nexto, teacher, champion,
  original clips, or validation/test replays.

EVALUATION
PRE and POST evaluate the policy against exactly the same fresh level seeds,
but action sampling introduces noise. With just 8 episodes, the estimates are
rough smoke-test signals, not a statistical claim of improved skill.
We require multiple runs and stronger heldout evaluations before interpreting
results as gains. Performance can initially worsen while PPO plumbing works.

INTEGRATION NOTES
The checkpoint model is a small 20-feature/15-discrete-action policy. It is
NOT loadable into the existing Cycle 9/Nexto actor. If the pipeline is healthy,
next implement a training run around the frozen teacher/student policy and
competitive self-play, with new isolated checkpoints and rigorous evaluations.

RUNTIME NOTE
RLGym+RocketSim isn't installed inside the assistant's local execution
container, so native simulator integration remains unverified there. Local
unit tests and a full train/save smoke test with a simulated surrogate passed;
the Windows run is required to confirm the real RocketSim integration.
