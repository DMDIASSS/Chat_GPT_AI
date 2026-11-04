# NovaForge v1.5

An isolated, laptop-sized 1v1 Rocket League training lab: RLGym v2 + RocketSim, PPO, frozen self-play, Nexto/Ripple trainers, Chronos/GalactusV2 simulator ports, mechanics resets, replay starting positions, teacher imitation, evaluation, and RLBot v5 export.

**v1.5 corrects a copying shortcut.** Start a fresh `copy02` with **21**. Control transitions are retained, the actor cannot read previous controls, and deployment selection includes the student’s own kickoff monitoring. See [the correction](COPY_CORRECTION_v1.5.md). **24** now automatically finds `chat_gpt_ai\rlviser.exe` and prepares the requested camera preset; see [RLViser setup](RLVISER_CAMERA.md).

**Begin with [START_HERE.md](START_HERE.md).** It contains the Windows installation, numbered launchers, exact training/resume/evaluation commands and replay workflow.

**New: [copy frozen teachers](FROZEN_TEACHER_COPYING.md).** Launcher **21** continuously gathers demonstrations and fits a student to frozen Nexto/Ripple/Chronos/Galactus controls. **22** pauses, **23** shows status, **24** watches, **25** exports, **26** reports, and **27** evaluates. This mode uses supervised learning with mild shared-return weighting and no PPO updates.

**[Export .lt + .bot.toml for RLBot v5](V5_EXPORT.md):** launcher **25** exports the copied student, **29** exports the old PPO student, and **28** packages a supported actor. The ZIP layout is `chat_gpt_ai/novaforge`; merge it at your project folder’s parent.

**New: [progress reports and checkpoint comparisons](PROGRESS_REPORTS.md).** Run **19** to export a small report ZIP to upload in the chat. For stronger evidence, pause with **15** and run **20** to compare the earliest and current saved checkpoints, then resume with **18**. See [technical archive findings and proposed experiments](ARCHIVE_RESEARCH.md).

**New: [continuous training with W&B](WANDB_AND_CONTINUOUS.md).** Run **17** once to install/check the dashboard SDK and reuse your saved local login. Run **18** to start/resume the mixed league until paused. Existing environments, models and runs can be kept.

For the requested mixed-opponent league, follow [MULTI_BOT_GUIDE.md](MULTI_BOT_GUIDE.md): launchers **10–16** download/check all four bots, collect mixed demonstrations, pretrain and train `diverse01`. The original launchers remain available for simpler experiments.

Updating after a Windows `Bad file descriptor` save error? See [the v1.0.1 update instructions](HOTFIX_v1.0.1.md). Extract over the existing NovaForge source and rerun `1_CHECK.bat`; no dependency reinstall is needed.

Designed for an i5-10300H, GTX 1650 Ti Mobile and 16 GB RAM. CPU/two-worker defaults. Experimental new student; no competitive pretrained student is bundled.

- [Research on the named bots](BOT_RESEARCH.md)
- [Implemented features and next experiments](PLAN.md)
- [Validation and limits](VALIDATION.md)
- [Licenses and attribution](THIRD_PARTY.md)

The ZIP contains `chat_gpt_ai/novaforge`. Extract into the parent of your existing project folder and merge. The original project is not modified by the trainer.
