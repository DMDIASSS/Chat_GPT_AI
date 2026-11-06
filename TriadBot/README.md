# TriadBot v1.6.0

**New in v1.6.0:** install sibling NovaForge v1.13.0. Pause existing training with 28, then leave 35_LEAVE_RUNNING.bat open. It resumes selector06 in one continuous PPO session, backs up, reports and exports the retained champion automatically. 36 benchmarks environment speed while training is paused. See novaforge/UNATTENDED_v1.13.md.

**New in v1.5.0:** install sibling NovaForge v1.12.0. Pause selector06 with 28, enable adaptive training opponents with 33, then resume the existing model with 27. Launcher 34 restores base sampling. Report 32 now includes sampling weights and detailed future automatic W/D/L checks. See novaforge/ADAPTIVE_OPPONENTS_v1.12.md.

**New in v1.4.0:** install sibling NovaForge v1.11.0. Launchers 26–32 create, train, pause, watch, diagnose, export and report the separate six-expert Octane selector06. It preserves selector04's frozen Fusion, removes Ripple from this new run, and adds Ducky, Rain 1v1 and full-strength Megabyte neural policies. Earlier runs remain available. See novaforge/OCTANE_SIX_v1.11.md.

**New in v1.3.1:** install sibling NovaForge v1.10.1 and run 25 after pausing selector04 with 19. It compares greedy versus sampled expert routing in 40 short games and writes its own report ZIP. Watch/export defaults and training remain unchanged. See novaforge/ROUTING_TEST_v1.10.1.md.

**New in v1.3.0:** install sibling NovaForge v1.10.0. Launchers 14–24 select a tested Fusion, refine a copy for a bounded budget, then create/train/watch/diagnose/export a separate four-expert selector04. Original selector01 remains available. See novaforge/FOUR_EXPERTS_v1.10.md. Learned watch logs now show actual actor probabilities. This release remains 1v1.

**New in v1.2.1:** launcher 13 runs read-only selector diagnostics and writes its own report ZIP. Update sibling NovaForge to v1.9.1 too. Watch 1/5 now run from the prepared viewer directory, fixing the second-project RLViser launch path.

**Research tools:** update sibling NovaForge to v1.9.1. Launchers 10/11/12 save a checkpoint backup, evaluate on a separate validation seed bank, and create a shareable research report. Evaluations retain the exact tested actors and full optimizer checkpoint; repeated use of a seed bank is recorded. See novaforge/RESEARCH_v1.9.md.

**Launcher 7 fix:** included in NovaForge v1.9.0. Evaluation now limits Torch to one thread and prints loading phases, every game, running progress and the final wdl.json path. Its default is 32 games. Ctrl+C cancels without editing weights.

Update the sibling NovaForge to v1.9.0 first. Your working v1.0 export can remain installed while you prepare a new one; each export has a distinct agent ID. This is a 1v1 experiment with exact pinned Chronos, GalactusV2 and Ripple v1.1 models.

A fixed car uses Breakout by default. Random exports also include an Octane variant. It cannot switch its hitbox when a different expert is chosen.

| Launcher | Action |
| --- | --- |
| 0 | Fetch/verify and check all three experts |
| 1 | Watch fair weighted-random selection |
| 2 | Export a random v5 bot |
| 3 | Compare random routing vs original Chronos with W/D/L |
| 4 | Train/resume the new PPO selector (selector01), until paused or stopped by a guard |
| 5 | Watch the latest selector |
| 6 | Export the retained selector champion |
| 7 | Compare latest selector vs initialization with W/D/L; pause first |
| 8 | Pause selector training |
| 9 | Show selector status |
| 10 | Save a complete checkpoint backup; pause first |
| 11 | Validation W/D/L on a separate seed bank: 64 games total; pause first |
| 12 | Shareable research report ZIP without weights/logs; pause first |
| 13 | Free-choice probabilities and fixed-expert/body diagnostics; pause first |

The learned selector chooses a frozen expert and holds it for about half a second. Initially it chooses Chronos; no trained winning selector is bundled. Training updates only the selector, not the experts. Automatic W/D/L checks and fresh confirmation protect its deployment champion and stop substantial regression. Until promotion, launcher 6 exports initial Chronos-only routing. Watch 5 to see actual training progress.

Exports appear under triadbot/exports. On this PC add **bot.bot.toml** directly: it uses the existing Python environment and needs no new INSTALL. On another PC run INSTALL.bat, then add **bot.portable.bot.toml**. DIAGNOSE.bat loads all models; startup.log records startup errors. Random variants have different IDs and explicit Breakout/Octane loadout files. Selector variants keep their training body.

Triad preserves native control vectors including Ripple's fine controls. Common execution delay and Ripple's held-control queue approximation remain transfer limitations. This is an independently implemented Opti-inspired hierarchy, not Opti's code or trained policy. See novaforge/TRIAD_SELECTOR_v1.1.md for source references, training details and limitations.

Source ZIPs contain no weights. Exports bundle your locally downloaded models, notices and hashes; no new rights over the original weights are granted. Full offline game strength still needs measurement.
