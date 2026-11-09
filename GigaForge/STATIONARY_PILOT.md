# Stationary Chronos pilot

This is a controlled learning experiment, not a stronger model release. Existing champions and research01–research06 stay unchanged. The new run is runs/stationary01. Do not use 3_START_OR_RESUME for this pilot.

## What was found in the uploaded source

WinRateDominanceGoalPotential updates globalGoalsFor/globalGoalsAgainst inside GetReward(player). RLGymCPP Reward::GetAllRewards calls that function for BOTH players, including the frozen opponent. A single goal therefore adds both a goal-for and a goal-against. A compiled regression with 100 goals scored only by Blue still reports 0.5. The reward's scaling is not a valid learner win-rate objective; shared rolling-counter updates can also depend on thread interleaving. New native code rejects this legacy training flag instead of silently changing an old study's reward.

The uploaded experimental recipes also changed opponent between the old control and defensive treatment. The new pilot keeps opponent, initialization, learning parameters, seed, and kickoff distribution matched. Source/report bundles do not include trained weights; no private candidate is bundled or claimed improved.

## Start and pause

1. Close trainers and viewers. Merge the update into Chat_GPT_AI, including gigaforge/native. Keep runs and environments. No compiler, CUDA download, or pip installation is required for an existing compatible setup.
2. Run `9_VERIFY.bat` to check existing feature/action contracts, or `_RUN.bat pilot verify` to check the new objective contract and counter reproduction.
3. Run `36_START_STATIONARY_PILOT.bat`. This creates/resumes the separate stationary01 experiment. It never changes active_research.json or champion pointers.
4. Let it run until PILOT_COMPLETE or PILOT_PAUSED. Each invocation has a 30-minute wall-time budget. The same button resumes completed native checkpoints and validated evaluation jobs. Changing objectives, executable or controller/config requires a new run name.
5. Use `37_PAUSE_STATIONARY_PILOT.bat` or Ctrl+C for a safe pause. Wait for native checkpoint completion before merging another update.
6. Use `39_REPORT_STATIONARY_PILOT.bat` and share the resulting ZIP. This is the first useful follow-up; do not run a final 2,000-game test on an unchanged unsuccessful candidate.

Saved interpreter/device selection is reused through _RUN.bat and runtime_bootstrap.py. Direct equivalent:

```bat
".\.venv_native\Scripts\python.exe" -u stationary_pilot.py train --run stationary01 --minutes 30
```

## Experiment

Both arms start from original Chronos, Breakout, with a fresh identically seeded critic and fixed original Chronos opponent:
- goal_only: +10/-10 goal outcome, no potential or event bonuses.
- goal_potential: the same goal reward plus bounded gamma*Phi(next)-Phi(current) using [.12,.05,.10,.08,.08].

Both use temperature .25, gamma .999, lambda .97, two epochs, clip .05, actor LR 3e-6, critic LR 3e-4, guiding KL .04, fixed actor trunk, eight initial critic-only rollouts and 393,216 collected learner decisions per arm. Rollout is 8,192, 64 arenas, optimizer batch and GPU minibatch both 256. Removing the four 64-sample GPU subdivisions reduces launch overhead without dropping samples or epochs; no measured GPU speed multiplier is claimed. Training still uses first-goal episodes; it is not claimed to optimize an exact timed-match win-probability objective.

Each arm and the frozen original reference are screened against original Chronos and Galactus on the same predeclared development seeds: 32 seed pairs/opponent, 135 seconds, 128 scored games/model. Fresh development and optional confirmation ranges are reserved before training, checked against readable saved historical evaluation requests/results. This does not mean that all physical states are novel. The final confirmation range is excluded from development.

Results include paired candidate/reference panel differences and per-opponent scores. The highest development panel score selects an UNVERIFIED preview, including when all candidates failed to improve. A candidate is not promoted automatically.

## Watching and export

After both arms and development evaluation finish:
- `38_WATCH_STATIONARY_PREVIEW.bat`: selected preview vs original Chronos, both Breakout. Blue=preview; orange=original. RLViser uses the existing auto-discovery/camera setup.
- `40_EXPORT_STATIONARY_PREVIEW.bat`: exports the pinned actor through the installed NovaForge exporter, with its required runtime and explicit unverified label. No universal extension conversion is attempted.
- `41_CONFIRM_STATIONARY_2000.bat`: one frozen development finalist vs original Chronos, 2,000 new 135-second games, 1,000 per color, in resumable 100-game batches. It refuses to spend a final test if the selected actor did not improve the development panel point score. Repeated invocation reuses the same fixed test, not new seeds until success. No champion pointer changes even if the primary confidence bound passes; broader regression and real RLBot deployment still need review.

## Integrity and resources

Evaluation jobs are keyed by BOTH complete model identities, native executable hash, seeds, duration, opponent, scenario and device. Reused raw results must match their saved content hash and exact seed/color/count/outcome checks. Failed or interrupted attempts remain on disk. Out-of-range seeds such as 2200000000 are rejected before model loading; the native interface uses a conservative signed range.

The pilot stops safely on its wall-time budget, available RAM below 2 GiB, combined pilot/native resident memory at 12 GiB, NVIDIA GPU memory at 3584 MiB, or GPU temperature at 86 C, where those sensors are available. It does not claim CPU temperature coverage. Do not train while gaming if responsiveness suffers. The pilot does not start any old trainer or install a monitor. Native checkpointing gets time to finish; if unresponsive for 120 seconds after a stop, the process is terminated and incomplete saves are not accepted.

The resource thresholds are guardrails, not a guarantee against every thermal or operating-system issue. Report missing/unsupported telemetry honestly. Model/optimizer checkpoints resume, but simulator arenas restart between native invocations; no bitwise uninterrupted-world-state restoration is claimed.

## Validation scope

Native objective tests reproduce the old all-player counter cancellation and verify stationary goal signs for both teams and zero non-goal bonuses. Integration checks use public original models, verify real actor updates, frozen trunks, complete learner sample accounting, checkpoint/optimizer resume, pause between arms, unchanged old STOP/champion selection, cached evaluation validation, and exported TorchScript/native logit agreement. These validate implementation, not playing strength. Windows CI uses a CPU wheel; GPU throughput and live RLBot matches require the user's PC.
