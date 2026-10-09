# Chat GPT AI — Quality Benchmark

Your 10,000-decision native Nexto fine-tuning checkpoint should be evaluated **before** more PPO training.

## How to install

Copy `native_quality_eval.py` and `RUN_NATIVE_QUALITY_AUDIT.bat` into your existing `E:\Downloads\Chat_GPT_AI` project, next to `native_nexto.py`. This package **does not replace** existing source code or weights.

Double-click `RUN_NATIVE_QUALITY_AUDIT.bat`.

Or PowerShell:

```powershell
cd E:\Downloads\Chat_GPT_AI
.\.venv\Scripts\python.exe native_quality_eval.py --games 20 --episode-decisions 750 --seed 123
```

First the script evaluates original Nexto against frozen original Nexto. Then it evaluates your latest native `data/native_nexto/last.pt` against the same frozen Nexto, alternating Blue/Orange and using the same seeds. It prints scores and metrics and saves a JSON report under `data/evaluations/`.

To check generalization, run again with `--seed 234` and `--seed 345`. To evaluate non-kickoff scenarios, pass `--scenarios grounded` (requires the grounded curriculum previously installed).

## What metrics mean

- **First-to-score outcomes**: goals before the first score or episode timeout; not full 5-minute match win rate. Favor this over touch-count improvements.
- **Productive touch**: after our touch, the ball's velocity towards the opponent's goal exceeds 450 uu/s and increases by at least 150 uu/s. It is a *proxy*, not an xG/shot model. It misses useful sideways touches and soft dribbles.
- **Dangerous touch**: ball's movement toward our own goal increases to at least 450 uu/s after a touch; proxy for a misclear.
- **Controlled-ball seconds**: last touching agent stays within 450 uu of a low ball, relative velocity below 650 uu/s; proxy for controlled possession, not true possession. Must be interpreted cautiously during 50/50s or when both cars touch simultaneously.
- **Controlled sequences**: distinct runs of at least ~0.53 seconds under the same proxy.
- **Offensive-half time**: percentage of steps the ball spends on the opposing half, regardless of last toucher; territorial pressure proxy.
- **Defensive threat time**: own-third, centrally located ball moving towards our net. Low is usually better; not an actual save counter.
- **Jump/boost/handbrake rates**: frequency of commanded actions, useful for diagnosing excessive flipping or boost use.

These metrics are diagnostic. **Never add all of them directly as PPO reward** without ablation and scale checks. Rewarding raw touches and velocities frequently incentivizes bad ball-chasing and ping-pong.

## What we should use for actual learning

Keep goals and opponent goals the dominant outcome. Consider a low-weight **potential-based shaping** term for threat/progress and carefully time-limited transition rewards for controlled touches. Focus on *change* in score-relevant state, not absolute ball speed or contact count. For specialized mechanics use separate success/failure evaluators: kickoff first-touch/timing, recovery time, air-dribble carry duration, legal flip-reset contact, double-tap completion, and pinch shot velocity/accuracy. Each must be validated with actual physics and the intended hitbox/collision checks.

For extra rigor, maintain frozen model checkpoints and benchmark against an opponent pool, not only a single Nexto. Avoid scaling to long training unless paired goal results across multiple seeds are consistent.

References:
- RLGym reward functions: https://rlgym.org/Rocket%20League/Configuration%20Objects/reward_functions/
- Advanced touch reward (ball acceleration): https://github.com/RLGym/rlgym-tools/blob/main/rlgym_tools/rocket_league/reward_functions/advanced_touch_reward.py
- Nexto source: https://github.com/Rolv-Arild/Necto

## Limitations

The code passed local static/unit tests, but its actual RocketSim execution on your Windows laptop is **not yet verified**. If you see an exception, please send the full traceback. Dataset/model files are not modified.
