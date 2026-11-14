# Small standard-reward baseline

`laptop_config.json` selects `rlgym_simple_v1`. Its rewards are **native ports of existing definitions**, not imports of the Python reward classes inside the simulation loop. Porting these few computations avoids reconstructing RLGym Python objects for every arena/decision. Tests compare outputs against the actual installed upstream classes, including a goal, contact, resets and elapsed simulation ticks.

- RLGym `GoalReward`, rlgym-rocket-league **2.0.1**: +1 to the scorer's team and -1 to the opposing team when a goal occurs; otherwise zero. Weight **10**. Source: https://github.com/RLGym/rlgym/blob/main/rlgym/rocket_league/reward_functions/goal_reward.py
- RLGym-tools `VelocityPlayerToBallReward(include_negative_values=False)`, **2.6.5**: `max(0, dot(car_velocity, normalized(ball_position-car_position))/2300) * elapsed_seconds`. Weight **0.2**. This uses the car's velocity, not a new possession/distance-potential formula. Source: https://github.com/RLGym/rlgym-tools/blob/main/rlgym_tools/rocket_league/reward_functions/velocity_player_to_ball_reward.py
- RLGym-tools `AdvancedTouchReward(touch_reward=1, acceleration_reward=0, use_touch_count=False)`, **2.6.5**: one when that car touched during the transition; zero otherwise. Weight **0.02**. Source: https://github.com/RLGym/rlgym-tools/blob/main/rlgym_tools/rocket_league/reward_functions/advanced_touch_reward.py

At 15Hz, the two guidance terms together are bounded by about 0.0334 per decision (car speed capped at 2300 and one boolean touch/decision). This keeps their scale modest relative to a goal reward of 10; it does not prove that reward farming or weak play is impossible.

The three definitions are established library components. **The weights are our starting configuration, not an official proven preset.** Only the goal reward is zero-sum. Approach and touch rewards belong to the acting car and do not subtract the opponent's progress.

A zero-distance normalization guard returns zero in an impossible/coincident-center state instead of dividing by zero. Native contact telemetry comes from RocketSim's per-tick hit data; each car gets at most one touch reward per decision. No .25-second touch cooldown is applied in this profile, matching the boolean upstream touch configuration. The legacy profile is retained for old runs and keeps its original behavior.

The old custom approach potential and controlled-ball/possession formula have **zero influence** on the laptop profile. Goal rewards are active from the start. There is no staged automatic reward search, replay imitation, teacher switching or reward-controller AI.

RLGym/RLGym-tools use Apache 2.0. See `LICENSES/RLGym-Apache-2.0.txt`. These native adaptations are attributed here; existing upstream implementations remain under their original licenses. Python RLGym packages are required to run the parity tests, but not to train with this native profile. No new Torch, CUDA or RLGym installation is required for the update.
