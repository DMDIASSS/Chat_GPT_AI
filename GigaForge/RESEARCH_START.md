# Start the new reward research system

For the current **research02** update, use [AUTONOMOUS_RESEARCH.md](AUTONOMOUS_RESEARCH.md)
and start **17_START_AUTONOMOUS_RESEARCH.bat** once. Button 3 now resumes the active
research run. The instructions below describe the earlier research01 study,
whose saved configuration and checkpoints remain supported.

Pause older trainers. Merge this update into Chat_GPT_AI, preserving existing environments, models, runs and exports. This update needs the NEW native executable included in the Windows ZIP; an old executable is rejected by the research self-test.

1. Run 1_SETUP_GPU.bat if your runtime is not already selected/working. Compatible libraries are reused. CPU alternative: 0_SETUP_CPU.bat.
2. Run 3_START_OR_RESUME.bat. This starts a SEPARATE research01 run. It seeds both families from protected native01 champions when available, otherwise from original teachers; it never seeds from a halted bad candidate. Chronos uses Breakout; Galactus uses Octane.
3. By default the coordinator runs for approximately five hours, finishing a current block/evaluation before stopping. Ctrl+C or 4_PAUSE requests a safe pause. Resume with 3. A rejected experiment branch does not stop the whole search: the next branch continues automatically. Nonfinite/device/corrupt-state errors stop the coordinator.
4. Watch retained champions with 5/6. They may still be original models until an improvement passes. Watch unverified candidates with 10/11. Export both retained champions with 7; package diagnostics with 8.

The active research pointer makes pause/report/watch/export target research01. For the older native01 run, use explicit --run native01; 13_START_LEGACY_NATIVE01.bat preserves its existing regression halt. Do not erase its halt flag to continue the old failing experiment. Other older projects remain available.

Four initial profiles explore baseline, attack, defense and possession shaping. New coefficient mutations are bounded and recorded. Training branches retain optimizer state while they remain eligible; retired branch checkpoints can be pruned to bound disk use, while current candidates and accepted champions remain protected. Keep donor library environments in place if runtime discovery reused them.

Every fixed rollout uses all collected learner samples, including unfinished paths with bootstrapping. The network sizes, FP32, PPO epochs and optimizer batch remain unchanged. Some profiles freeze the pretrained shared trunk to test whether policy adaptation can preserve established representations. This is a controlled variant, not an assertion that frozen trunks are universally better.

W&B charts now include prepared/collected data fraction, actual optimizer sample uses, candidate and baseline match score, paired difference/interval and goal difference. Those complement collection SPS. More speed and a rising training counter do not establish stronger play.

Training remains a research process. The system can discover no confirmed improvement within a session; it then keeps the starting champion. The mathematical collector/reward tests establish correct accounting and boundary behavior, not guaranteed Rocket League strength. Read RESEARCH_PAPERS.md for the paper-to-code mapping and limitations. No 100% improvement promise is made.
