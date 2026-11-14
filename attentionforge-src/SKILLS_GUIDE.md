# AttentionForge Skills 0.5

This is a separate complete project under `chat_gpt_ai/attention_skills`. Old AttentionForge, NovaForge and GigaForge runs are not modified. It trains a 1,091,163-parameter attention network with Octane in 1v1.

## Start

1. Pause other trainers. Extract the ZIP into `E:\Downloads`, giving `E:\Downloads\Chat_GPT_AI\attention_skills`.
2. Open `SKILLS.bat`. Setup reuses a compatible existing Python 3.11 x64 Torch environment, preferring CUDA. Existing Torch/CUDA installations and saved W&B credentials are reused, not replaced.
3. Choose **1**. First start learns basic ground approaches for 900 minibatches, tests actual contact in RocketSim, then starts PPO. No old model or replay cache is required. If the physical contact gate fails, it preserves bootstrap progress and prints the failure instead of launching endless PPO.
4. Training continues until you pause. **Ctrl+C** once, or `SKILLS_PAUSE.bat`, saves. Wait for `BOOTSTRAP_PAUSED` or `PAUSED_AND_SAVED`. The same menu resumes the appropriate phase.
5. After warm start, you can pause and choose **2** to watch latest versus the frozen warm-start network; both are Octane. Choose **8** for latest versus itself. RocketSimVis is reused from the sibling AttentionForge installation; if absent, the pinned viewer installs in an isolated GUI environment on first watch. This shows live simulation, not replay playback.
6. **3** runs real contact drills on fresh scenes, **4** creates the report ZIP to share, **5** exports, **6** runs 500 longer matches against the frozen parent. Never run watch/evaluation while training on this laptop.

Collision meshes are reused from your existing projects or installed RLGym. If setup cannot locate them, set `ATTENTIONFORGE_MESHES` to your existing Soccar `collision_meshes` directory or create `local_paths.json` with `{"meshes":"E:/your/path/collision_meshes"}`. Game assets and heavy ML libraries are not bundled.

## What changed and why

The prior bot rarely contacted the ball and spent about 84% of training time airborne. Rising reward and scoreless draws did not establish useful play. This version establishes an observable basic skill before PPO.

**Warm start:** an analytic ground pure-pursuit tutor supplies action labels on varied synthetic public states. The attention network learns those labels. This is explicitly synthetic driving imitation, not human replay imitation or a copy of Chronos/Galactus. The deployed bot always uses the network alone: no tutor, scripted kickoff, forced throttle, hidden search or scripted jump is active in watch/export.

**PPO stability:** an initial continuation pilot destroyed the warm start. The corrected configuration uses a 2e-5 learning rate, a critic head whose gradient does not modify shared policy features, a small ground-driving auxiliary loss that fades to zero by 10M PPO transitions, and legal-action-only label smoothing during warm start. Critic values still train; policy features learn from the actor and auxiliary loss. This protects initialization but can restrict adaptation and must be judged in matches.

**Contact curriculum:** 60% of training resets initially use varied approach drills, 35% after 3M PPO transitions and 15% after 10M. Other resets retain normal kickoffs and varied play. Both sides get comparable drill poses. Ten percent of drill balls are elevated to give jumping a useful target. The diagnostic trials are separate from these training resets; validation seeds are not presented as final test seeds.

## Rewards and combos

All rates below use elapsed simulation seconds. Physics remains 120Hz, decisions every eight ticks with one tick of action delay. The 90-action observation/deployment contract is preserved.

- Goal: +10/-10, always enabled.
- Positive car velocity toward the ball: rate 1 initially, fading linearly to 0.4 by 10M PPO transitions. This follows the time-normalized RLGym-tools definition.
- Actual contact: 1 initially, fading linearly to 0.2 by 10M. At most one boolean touch per car per decision, following `AdvancedTouchReward(use_touch_count=False)`. This is substantially stronger than the previous 0.02.
- Touch strength: 0.5 times ball velocity change / 6000 on a contact, as in AdvancedTouchReward acceleration mode.
- Face-and-approach: a small 0.05/s alignment signal, paid only while moving toward the ball. Standing still facing it earns none.
- Shot contact: up to 0.5 for a touch that sends the ball toward the opponent goal, scaled by projected ball velocity / 2300.
- Air contact: 0.5 for an actual touch with car and ball above 200 units after at least 0.15 seconds airborne. No reward for merely jumping or remaining airborne.

**Goal-gated combo:** a possession chain tracks distinct air-contact, flip-reset and recovery events. A real goal within eight seconds can add 0.5 for each distinct event, capped at 1.5; the opposing team gets the corresponding negative goal bonus. Opponent contact changes ownership; simultaneous opposing contact clears it. Repeating or alternating the same event types does not increase the bonus. A goal without a qualifying chain earns its ordinary goal reward.

Reset detection requires spent flip availability to return during a ball contact off the ground. Recovery detection means a landing after a flip with at least 80 units/s of horizontal speed gain during that physics tick; it is a conservative observable proxy, not a certified wavedash classifier. Flicks and mustys are not reliably identified by this implementation and are not falsely labeled as detected mechanics. No unlimited generic combo multiplier or free-standing dash/acceleration reward is enabled. These additions can still change behavior undesirably; contact and match checks remain necessary.

## Automatic checks and preservation

Every 250k consumed PPO transitions, the program runs repeatable physical contact validation on both colors. It retains `best_contact.pt` separately. This is a contact-selected checkpoint, not a proven match champion. Every 2M transitions it also runs a fresh 100-game match panel against the frozen warm start. Those panels are coarse diagnostics, not proof of small gains.

If contact falls below 30%, or below 60% of the best validation level, the failed checkpoint/config are archived. The runner restores the retained contact model and optimizer, halves the learning rate (floor 3e-6), preserves the current available history opponents and cumulative consumed-transition counter, and records the rollback in `recovery.jsonl`. It makes at most three recoveries before pausing with the restored policy. It does not silently claim that discarded training belongs to the restored model lineage. Reports preserve the recovery record and failed validation metrics. History self-play snapshots remain enabled.

A thousand scoreless matches are less useful than recognizing failed contact quickly. If the safety system pauses, send menu **4**'s report; it contains the actual failure evidence. No system can promise uninterrupted useful learning for days.

## Export

Menu **5** writes a new export directory without replacing existing exports:

- **RLBot v5:** `bot.bot.toml` + `actor.lt` + `run_v5.py`. `actor.lt` is a TorchScript model read directly by the Python v5 wrapper, not a GigaLearn native binary. Local TOML uses the exporting Python and needs `rlbot==2.0.0b56`. `DIAGNOSE_V5.bat` checks model/SDK loading without a game. If the SDK differs, `INSTALL_V5.bat` creates an isolated SDK environment that reuses the selected Torch stack; then import `bot.portable.bot.toml`.
- **RLBot v4:** `actor.pt` + `bot.cfg`. The v4 and v5 SDKs share the package name `rlbot`; keep them in separate environments. The v4 INSTALL launcher creates `.venv_v4`.

Export verifies loaded PT and LT logits and chosen actions against the source. The v5 packet adapter and action-delay clock have SDK-object tests. Actual Rocket League connection/gameplay still needs local verification. Both loadouts specify Octane. Training is currently 1v1 even though the public observation layout can encode larger balanced teams.

## Expectations and evidence

See `SKILLS_VALIDATION.json` for measured server results, including the failed first PPO pilot. Contact success on test scenes proves a basic learned approach skill, not overall match strength, aerial competence or rank. No current user checkpoint was available here for direct comparison. CUDA throughput and a live Windows RLBot match cannot be verified on this CPU-only server.

You can inspect useful movement immediately after warm start. During the first hour, assess actual contacts, goals, airborne fraction, retention checks and watch behavior. The package automates these checks; it does not guarantee a strong bot in 2–3 days. At roughly 3,000 learning transitions/s, 48–72 uninterrupted hours is about 518–778M transitions, before monitoring/checkpoint overhead. Published billion-step anecdotes used different hardware and configurations.

## Sources

- https://github.com/ZealanL/RLGym-PPO-Guide/blob/main/making_a_good_bot.md — staged basic contact learning and stronger early touch guidance; author's experimental advice, not a guaranteed recipe.
- https://github.com/ZealanL/RLGym-PPO-Guide/blob/main/rewards.md
- https://github.com/RLGym/rlgym-tools/blob/main/rlgym_tools/rocket_league/reward_functions/advanced_touch_reward.py
- https://github.com/RLGym/rlgym-tools/blob/main/rlgym_tools/rocket_league/reward_functions/velocity_player_to_ball_reward.py
- https://github.com/ZealanL/GigaLearnCPP-Leak — framework and action-mask reference. This project remains native RocketSim simulation plus PyTorch PPO, not a renamed GigaLearn integration.
- User code-review snapshot: https://github.com/DMDIASSS/Chat_GPT_AI_Code_Review_20261115_014523 — its AttentionForge Python files matched the prior release exactly. Historical replay-only handoff documents describe a separate older task; the current user explicitly requested reward-based training.
