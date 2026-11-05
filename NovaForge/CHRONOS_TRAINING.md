# Chronos as the starting policy: NovaChronos

This is a separate **chronos01** run initialized from the actual pinned Chronos policy and shared-head weights. It is reward-driven PPO, not the copy02 classifier. The original downloaded Chronos weights stay frozen and hash-verified; copy02 is preserved.

## Start on your Windows laptop

1. Pause copy02 with **22** and wait for its console to exit. Stop an existing watch session with Ctrl+C.
2. Extract this ZIP into the parent of chat_gpt_ai, for example E:\Downloads, merging chat_gpt_ai/novaforge. Keep .venv, assets and runs. Existing v1.5.4 installations use the same dependencies.
3. Run **1_CHECK.bat**. Expected skips include optional teacher/native checks. It now includes the shared-kickoff-template regression check.
4. Run **35_START_OR_RESUME_CHRONOS.bat**. It verifies/fetches the four pinned opponents, starts from Chronos weights on a fresh chronos01, and resumes the saved optimizer on subsequent launches. W&B uses your SDK's existing login. If login is missing, launcher 17 configures it locally.
5. Let the first checkpoint appear. Pause with **36_PAUSE_CHRONOS.bat** and wait for the console to finish. **37_CHRONOS_STATUS.bat** shows timesteps, update counts, opponent metrics and the W&B status/link.
6. **42_WATCH_INITIAL_CHRONOS.bat** shows the unchanged initialization. **38_WATCH_CHRONOS.bat** shows the latest learner. Both auto-find RLViser and use the requested learner ballcam settings. Blue/orange can change; rendered car 1 is the learner.
7. After the first **32,768 learner decisions**, pause and run **39_EVALUATE_CHRONOS.bat**. It compares current and initial policies on identical seeded starts and both team sides, across scorer/Chronos/Galactus/Nexto/Ripple and kickoff/shot/defense. The default is 150 trials per policy and can take several minutes. It generates a metrics report ZIP automatically. Send that ZIP before extending training substantially.
8. **40_EXPORT_CHRONOS_V5.bat** exports the current learner; **41_CHRONOS_REPORT.bat** exports the latest selected metrics for review. Resume training with 35.

Training continues until 36 or Ctrl+C. Source models are not overwritten. The branch retains its permanent step-0 checkpoint plus three recent full checkpoints by default; the self-play pool keeps six active snapshots plus the initial actor. This limits model storage growth. Full optimizer resume does not restore the exact live arena/RNG state; environments start fresh after resume.

## What is preserved from Chronos

- Actual policy/shared-head tensor values, not action imitation of them.
- 225 input features, 90 discrete actions, and the original LayerNorm/ReLU architecture.
- Chronos's team-relative mirror convention and deployed boost-timer ordering.
- Decisions every eight physics ticks, with seven ticks of held controls before the new command; the simulator's existing one-tick action delay remains enabled.
- The native action mask as implemented by the existing port. The original world-contact-normal exception cannot be reproduced from RLGym's public state and remains a known port limit.

PPO observations have 315 numbers: the 225 actor inputs followed by the decision-time 90-action mask. The extra mask is not fed into the pretrained network. It is retained with each rollout sample so PPO evaluates the same valid action distribution that produced that sample.

The new critic is separate because the public deployment files do not contain Chronos's training critic/optimizer. The first two rollout updates train only this critic. Then actor updates use a small 1e-5 rate, critic updates use 3e-4, PPO clipping is 0.1, and a frozen copy of the initial Chronos policy supplies a KL penalty. These are conservative starting settings, not a proven optimal recipe.

## Opponents and rewards

Default episode probabilities:

| Opponent | Probability |
| --- | ---: |
| Frozen original Chronos | 20% |
| Frozen GalactusV2 | 15% |
| Frozen Ripple | 10% |
| Frozen Nexto neural | 10% |
| Latest saved learner | 25% |
| Historical saved learner | 20% |

Self-play uses frozen snapshots, keeping one opponent fixed throughout an episode. New snapshots are published after completed rollout updates at checkpoint boundaries. A neural opponent never receives a scripted kickoff override. The pools are headless simulator ports, not a claim of exact full-match RLBot deployment behavior for every bot.

The new reward is **+10 for scoring / -10 for conceding**, plus discount-consistent potential shaping for ball progress and closing distance. It does not pay a flat reward for repeated touches or merely staying airborne. Four-tick shaping and its aggregation into eight-tick PPO steps use matching discount factors, so potential shaping telescopes rather than paying for a loop. The original Chronos training reward is unknown; this is a new fine-tuning reward.

The model starts capable because it inherits Chronos's policy. Any gain over that initialization must be shown in gameplay. Anchor KL, reward, touch count and SPS alone are insufficient.

## Important kickoff reset fix

The old reset code assigned shared float32 kickoff template arrays directly to cars, then modified them in place when rotating teams. An orange reset could therefore alter the template used by a later reset. Even the same seed could produce a different field half on the next call.

This update copies pose arrays before rotation. Tests require unchanged templates and repeatable positions on repeated blue/orange resets. Paired evaluations now assert identical initial observations before running both policies. Old kickoff comparisons from affected versions were not reliably paired and should not be used to rank the old students. The new Chronos branch collects fresh trajectories after the fix.

## Export to RLBot v5

Launcher 40 creates exports/novachronos_<hash>_<id>/ containing:

- **actor.lt**: the combined 225->90 TorchScript actor used by the included Python v5 runtime.
- **SHARED_HEAD.lt** and **POLICY.lt**: separately scripted components with Chronos's original architecture.
- **bot.bot.toml**, bot.py, integrity metadata and README.

Keep the folder under novaforge/exports, add bot.bot.toml to the v5 GUI and select an offline 1v1. The TOML launches the matching adapter; it is not a weight format. Each export has a distinct agent ID. To package the initialization separately for a live comparison:

```bat
.venv\Scripts\python.exe run.py chronos-export --run chronos01 --initial
```

The two native components can also be used with a separately configured copy of the original Chronos native runtime. Its observation builder, mask and timing must still match. The Python runtime and serialization are tested, but a live full-game Windows transfer test remains necessary. The source ZIP contains no model weights and does not grant new rights over the original Chronos weights; original attribution is preserved.

## CPU/GPU and throughput

The default is two environment workers, one Torch thread per worker and device auto. CUDA is used if available in the installed PyTorch; otherwise training uses CPU. Your existing CPU environment works. A CUDA speed/VRAM check on the 1650 Ti is still a user-side test. Do not change network widths: that would discard compatibility with pretrained weights.

This release uses the validated Python/RocketSim path. It does not claim GigaLearn's native SPS. Metrics count **eight-tick learner decisions**, not all physics ticks, teacher inferences or every car in the simulator. Native multi-game integration remains a separate parity/performance task; see [the upstream review](UPSTREAM_REVIEW.md).

## CLI alternatives

```bat
.venv\Scripts\python.exe run.py chronos-train --run chronos01 --forever --wandb offline
.venv\Scripts\python.exe run.py chronos-train --run chronos01 --resume --forever --wandb offline
.venv\Scripts\python.exe run.py chronos-evaluate --run chronos01 --pairs 2 --seconds 20
.venv\Scripts\python.exe run.py chronos-watch --run chronos01 --initial --opponent scorer
```

For an additional mechanics screen, pass --scenarios kickoff,shot,defense,dribble,aerial,recovery,wall to chronos-evaluate. Keep final evaluation seeds separate from repeated development screens, and compare full offline matches on both teams before claiming a stronger bot.
