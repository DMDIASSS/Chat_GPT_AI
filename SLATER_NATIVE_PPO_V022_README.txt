Slater v0.2.2 -- isolated PPO, heading correction

CHANGES FROM 0.2.1
- Fix car reset yaw: angle from +X toward ball uses atan2(dy,-dx),
  rather than atan2(-dx,dy). At ball directly +Y, yaw must be pi/2.
- Fail fast if real RocketSim reset yields heading alignment below 0.94.
- Separate filename and new output checkpoint; original remains untouched.
- Still only a from-scratch solo PPO integration/learning diagnostic.
  Not Cycle 9 compatible; no teacher, replay or self-play training.

INSTALL
Extract at project root E:\Downloads\Chat_GPT_AI, alongside v0.2.1.

TESTS
.venv\Scripts\python.exe -m pytest slater_v022_tests -q

REAL SIMULATOR HEADING CHECK
.venv\Scripts\python.exe -c "import numpy as np; from slater_native_ppo_smoke_v022 import SoloShootingEnv; e=SoloShootingEnv(seed=123); e.reset(); c=e.state.cars[e.aid].physics; d=e.state.ball.position-c.position; cosine=float(np.dot(c.forward[:2],d[:2])/(np.linalg.norm(c.forward[:2])*np.linalg.norm(d[:2]))); print('INITIAL_ALIGNMENT_COSINE',round(cosine,4)); e.close(); assert cosine>0.94"

TRAIN (only after tests/check)
.venv\Scripts\python.exe slater_native_ppo_smoke_v022.py --updates 20 --rollout-steps 2048 --eval-episodes 32 --device cpu --out data/isolated/native_ppo_v022_facingfix_01.pt

SAFETY
Cannot output outside data/isolated or overwrite existing checkpoint.
No change to Cycle 9, teacher, original replays, or previous v0.2.1 .pt.

INTERPRETATION
You want touches >0 in training and then held-out evaluation.
Policy parameter updates alone are NOT success.
