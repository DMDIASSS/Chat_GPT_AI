# Validation gates and safety checklist

| Gate | Required observable evidence | Before proceeding |
|---|---|---|
| A | C++ rebuild shows success with hub source patch | Experiment training |
| B | Runtime log shows correct `Research Hub mode`, blue/orange counts, CUDA, first PPO iteration | Longer C++ run |
| C | Safe stop leaves an intact numeric checkpoint with POLICY/SHARED_HEAD/CRITIC & optimizer & RUNNING_STATS | Automatic schedules |
| D | Restart same experiment loads latest checkpoint and advances total timesteps | Multi-hour runs |
| E | No NaN/inf, no degenerate ball-loop reward exploit, no runaway disk/VRAM, CPU/GPU thermal check | Expanded parallelism |
| F | Actual opposing-checkpoint RLBot/multi-agent games, paired seeds and holdout starts | Ranking/improvement claim |
| G | Clear defense, shot accuracy, air control and teamplay metrics with representative losses | Promotion as stronger |
| H | Native-compatible observations and supervised labels, state/input timing reproduction | TAS/replay training |
| I | Original Nexto, Cycle9, Wavedash preserved and regression-tested independently | Any deployment promotion |

**Current package supplies A–D workflows but those outcomes require the user's Windows run. E–I are not implemented as automatic hard gates.**

If a build fails, use the `.research_hub_original.bak` files to restore the two C++ source files, *not* to restore any `.pt` or `.lt` checkpoint. All C++ research training uses separate `Research_Hub/experiments/<name>/checkpoints/` folders. Original `GL_4_START_CPP_TRAIN.bat` uses a different working directory and does not control new research branches.
