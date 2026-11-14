# AttentionForge 0.4 — distance control and clean-shot experiments

This update adds **two experiments**, starting from the same trained standard-reward checkpoint. It preserves your current run and does not claim to reproduce Catalyst's unpublished reward or its reported results.

## What is reused and what is new

The existing native ports of RLGym GoalReward, RLGym-tools VelocityPlayerToBallReward and AdvancedTouchReward remain unchanged. Their weights, model, PPO, observations, action delay, hitbox and reset mixture are inherited from the parent. New terms are implemented in the existing C++ worker; no extra Python reward objects or new ML dependencies are installed.

Sources inspected:

- RLGym rewards: https://github.com/RLGym/rlgym/tree/main/rlgym/rocket_league/reward_functions
- RLGym-tools AdvancedTouchReward: https://github.com/RLGym/rlgym-tools/blob/main/rlgym_tools/rocket_league/reward_functions/advanced_touch_reward.py
- RLGym-tools BallTravelReward: https://github.com/RLGym/rlgym-tools/blob/main/rlgym_tools/rocket_league/reward_functions/ball_travel_reward.py
- RLGym-tools GoalProbReward/GoalViewReward: https://github.com/RLGym/rlgym-tools/blob/main/rlgym_tools/rocket_league/reward_functions/goal_prob_reward.py
- Zealan's rewards and training guide: https://github.com/ZealanL/RLGym-PPO-Guide/blob/main/rewards.md and https://github.com/ZealanL/RLGym-PPO-Guide/blob/main/making_a_good_bot.md

The guide is advice from its author's experiments, not a universal proven reward recipe. Some examples use older RLGym versions and per-step weights; their numeric weights are not directly interchangeable with time-normalized RLGym-tools rewards. The GGL example includes strong-touch rewards, but those reward a touch's strength, not the exact requested goal/floor condition. Public author/repository references such as VirxEC and Rolv-Arild remain useful architecture/framework sources; their names alone do not establish Catalyst's formula.

The supplied Discord excerpts are research leads, not instructions or verified experiments. They discuss reach-time possession, bugs, ball chasing and reward farming; they do not supply a reproducible Catalyst reward implementation. No private logs are copied into this package or posted elsewhere.

## A. control01: bounded distance-control advantage

Let `d_blue` and `d_orange` be each team's nearest non-demoed car's **3D distance to the ball**. Define:

```
P_blue = exp(-min(d_blue, d_orange) / 1000)
         * (d_orange - d_blue) / (d_blue + d_orange + 100)

control reward for blue = 0.2 * elapsed_seconds * P_blue
control reward for orange = -blue_control_reward
```

This is a bounded version of the requested opponent-distance / own-distance idea. It is symmetric, approaches zero when both teams are far away, and does not divide by a near-zero own distance. If either team has no non-demoed car, this component is zero, avoiding a free control reward from an opponent's demo alone. In team modes it uses the nearest teammate and is team shared; **the current experiment is still 1v1**.

**This measures proximity advantage, not true possession or interception ability.** It omits turning time, boost-limited flight, future ball motion and steering constraints. It can still encourage ball chasing, hovering or maintaining control instead of shooting. Its bounded rate is a starting hypothesis, not an anti-farming proof. It is a continuous reward, **not potential-based shaping**; it changes the training objective.

At 15Hz its maximum magnitude is about 0.0133 per full decision. At a goal the actual elapsed physics ticks are used. The parent's goal reward stays enabled; with your current parent that is +10/-10. The new reward is not automatically substituted into the parent run.

## B. control_shots01: the same control term plus actual-goal bonuses

The default additions, per scoring team:

```
clean-flight goal bonus = 1.0 if no floor contact occurred since its last touch
fast-goal bonus         = 0.5 * clip(speed_at_goal / 6000, 0, 1)
```

Both require an unambiguous last touch by the **scoring team within six simulated seconds**. Own-goal/opponent-last-touch and no-known-touch goals get the original goal reward but no extras. The opposing team receives the negative of these goal bonuses, like the ordinary goal reward.

- Floor contact is read from **Bullet ball/static-world contact manifolds at every 120Hz physics tick**, not just once per 15Hz policy decision and not inferred solely from ball height.
- Ceiling/wall/car contacts do not count as floor. Flat ground and goal-floor contacts do. Floor mesh margin is accommodated by the contact-point test.
- A touch and floor contact in the same physics tick are conservatively disqualified. This can reject some legitimate strikes near takeoff; sub-tick ordering is not reconstructed.
- A newer touch starts a new shot history; an opposing touch changes ownership. Simultaneous opposing touches clear ownership until a new unambiguous touch.
- Ball speed is captured in the native **goal callback**. There is no fast-ball bonus for a miss or a ball merely flying quickly around the arena.
- A ground pop that then travels into goal without bouncing can qualify. This is a **clean-flight goal** bonus, not proof of an aerial, flip reset or musty.

For your parent's goal weight 10, extras total at most 1.5 (15%). A bounced goal still receives its full ordinary goal reward and can receive the speed bonus when correctly credited. In A both style weights are zero; floor tracking is disabled to avoid unnecessary work.

AdvancedTouchReward already supports **ball acceleration on a touch**, measured from ball velocity changes. That is not the same as a general car-acceleration reward. No new acceleration, boost-usage, in-air or dash bonus is enabled here; the current bot already spends substantial time airborne, and rewarding acceleration/braking cycles can create another farming opportunity. Add that as a separate measured experiment if there is evidence it helps.

## Install and run

1. Pause all trainers and wait for `PAUSED_AND_SAVED`. Close Python trainer/watch/menu windows before replacing the native `.pyd`.
2. Extract this ZIP into **E:\Downloads**, merging `chat_gpt_ai\attention_forge`; overwrite included program files. Existing runs, configs, environments and exports are not included or overwritten.
3. Run **SETUP.bat** to verify the new native runtime.
4. Run **REWARD_SETUP.bat**. It reads the latest completed `laptop01` checkpoint and creates **control01** and **control_shots01**, with the same actor/critic, Adam moments, step values, history, counters and hyperparameters. They receive new W&B IDs and record the exact parent model hash. It refuses to overwrite existing experiments.
5. Open **CONTROL_RUN.bat → 1** first. Run only one trainer at a time. After the first 1–2 million additional transitions, pause and use menu **4** for a report; this is a health check, not enough to promise new skills.
6. Use menu **3** to evaluate against its **pinned pre-change parent** (`reward_parent.pt`), not a moving current opponent or the much earlier first snapshot. Results record fresh seeds and hashes. A 100-game panel is a coarse screen, not a small-effect proof.
7. **CONTROL_SHOTS_RUN.bat** opens the second experiment, initialized from the same parent. Test it for a comparable amount of new experience and wall time, then evaluate and report. Do not train both simultaneously on this laptop.

If your active model is `laptop01_gpu`, create the forks with:

```bat
_RUN.bat reward-setup --run laptop01_gpu
```

The default REWARD_SETUP.bat uses laptop01 explicitly; it does not assume the run with more steps is better. Existing target folders are preserved. Both experiments start from the chosen trained checkpoint, **not random weights**. Their counters therefore begin at the parent's count.

Existing LAPTOP/GPU_RUN menus continue to address the original runs. New menus display their run names, and menu 3 automatically chooses the pinned parent for reward experiments. Watching and PT/CFG export use the unchanged public observation/action contract. RLBot v5/TOML/LT export is not added by this update.

## What to measure

Reports add control score magnitude, signed and absolute control reward, clean-flight goal count, goal speed, credited-shot count and the separate goal bonuses. Signed blue sums can cancel in symmetric self-play; the absolute magnitude helps confirm a signal exists. Floor-contact detections are only those used by the active shot tracker, not all arena contacts. Physics/action contracts are unchanged and regression-tested against the standard profile.

Look for more actual ball contacts, successful kickoffs, goals and held-out parent wins. Rising reward alone is insufficient. Keep the stronger baseline if the new profiles lose matches or become passive ball holders. Rewards can encourage useful behavior, but this package contains correctness tests and short smoke runs, **not evidence of a stronger trained bot or guaranteed aerial/boost-management learning**.
