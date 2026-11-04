# NovaForge v1.0.1

An isolated, laptop-sized 1v1 Rocket League training lab: RLGym v2 + RocketSim, PPO, frozen self-play, Nexto/Ripple trainers, mechanics resets, replay starting positions, teacher imitation, evaluation, and RLBot v5 export.

**Begin with [START_HERE.md](START_HERE.md).** It contains the Windows installation, numbered launchers, exact training/resume/evaluation commands and replay workflow.

Updating after a Windows `Bad file descriptor` save error? See [the v1.0.1 update instructions](HOTFIX_v1.0.1.md). Extract over the existing NovaForge source and rerun `1_CHECK.bat`; no dependency reinstall is needed.

Designed for an i5-10300H, GTX 1650 Ti Mobile and 16 GB RAM. CPU/two-worker defaults. Experimental new student; no competitive pretrained student is bundled.

- [Research on the named bots](BOT_RESEARCH.md)
- [Implemented features and next experiments](PLAN.md)
- [Validation and limits](VALIDATION.md)
- [Licenses and attribution](THIRD_PARTY.md)

The ZIP extracts to a single `NovaForge` folder inside an existing `Chat_GPT_AI`. The original project is not modified by the trainer.
