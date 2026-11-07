# GigaForge autonomous native research

Two independent pretrained actors: Chronos on Breakout, Galactus V2 on Octane.

[Start research02](AUTONOMOUS_RESEARCH.md) | [Paper-to-code mapping](RESEARCH_PAPERS.md) | [Dependency reuse](RUNTIME_UPDATE.md) | [Earlier research01](RESEARCH_START.md)

Merge the ZIP into your existing Chat_GPT_AI folder after pausing older trainers.
Run **17_START_AUTONOMOUS_RESEARCH.bat** once. Then **3_START_OR_RESUME** resumes
whichever research run is active. The update preserves environments, models,
earlier runs and exports. Install the NEW paired-evaluation native binary.

Research02 automatically compares reward/learning-rate profiles with longer
resumable training branches, hard-opponent sampling and self-play. It screens
128 games per actor, confirms promising gains on 512 fresh games per actor with
the initial two opponents, checks scoring/conceding and individual opponent
regressions, and keeps promising actors outside checkpoint rotation. Exported
champions must pass independent confirmation. Shortlisted actors are unverified.

Default session budget: approximately five hours, finishing the current work
before stopping. 4 pauses; 8 reports; 5/6 watch retained champions; 10/11 watch
unverified candidates; 7 exports retained independent .pt/.lt and v5 TOML bundles.
W&B uses the existing selected runtime and login. No API keys are bundled.

Fixed-rollout data accounting and native feature/action/network parity were
validated separately from strength. Python/simulator tests and short pilots do
not establish a stronger bot. Confidence intervals are approximate and apply to
the tested native opponent panel. There is no guaranteed improvement or laptop
SPS multiplier. See AUTONOMOUS_RESEARCH.md for exact decisions and limitations.

Current update: [paired evaluation repair and automatic training focus](PAIRED_REPAIR.md). Existing research02: pause with 4, install this update, run 9_VERIFY, then 3 to resume the same checkpoints.

[200-game candidate versus original test](HEAD_TO_HEAD.md): run 20_WDL_BEST_VS_ORIGINAL_200x100.bat with training paused.
