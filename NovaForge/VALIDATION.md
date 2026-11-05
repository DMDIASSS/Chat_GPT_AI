# Validation evidence and limits

**v1.5.3:** Local teacher-enabled checks: 82 passed, 1 intentionally skipped native UDP integration. The opt-in actual sender check passes separately. Held-port checks safely skip for both fixed ports. The old watch test was reproduced failing with the real project lock held; the fixed test passes under the same condition and separately preserves duplicate-session rejection. A Windows CI workflow checks the core suite, actual packets and occupied ports. See [the hotfix](CHECK_HOTFIX_v1.5.3.md).

**v1.5.2:** Added regression checks for ground-scorer goals on both team sides, routing behind the ball, retained nonkickoff reset coverage, mixed opponents, teacher-only labels after student prefixes, preserved upgrade state/backup/idempotence, and contact-aware goal counts. An actual two-round four-teacher run collected 8,000 decisions, including 12 takeover episodes in the second round; this checks execution, not playing strength. A separate real collection sampled all five configured opponents and all four actual teachers (1,200 attempted decisions, 983 compatible labels). No Windows native-backend speed or 271 comparison is claimed. The teacher-enabled suite passes (82 tests), including the contact-score tie-break; the final release archive is also checked with its core suite.


**v1.5.1:** 75 teacher-enabled tests pass after updating the viewer sender to rlviser-py 0.6.14. Added checks cover pre-import upgrading, rejecting an already loaded incompatible native sender, and actual Connection/GameState/Quit datagrams emitted by the native extension. A headless loopback test verifies the FlatBuffer framing and union tags used by the pinned viewer. The old 0.6.13 source emits the incompatible legacy two-datagram format. Visual Windows/GPU confirmation is still required.

**v1.5:** 72 teacher-enabled tests pass. New regression cases retain native-style control transitions, verify that previous-action changes cannot affect the corrected actor, check censored returns and first-touch resets, cover all standard kickoff spawns, and verify that gameplay selection can prefer contacts over a smaller copying loss. Camera tests cover parent-folder discovery, checked downloads, backups, fallback behavior, learner ID ordering and watch cleanup. Report checks cover the current CoreWeave Forge URL and missing/small validation categories.

A fresh corrected student was exercised through two real 50,000-decision teacher rounds. Its development monitoring reached 6/12 scripted-opponent trials with a learner touch. A separate 50-trial screen still had no first-goal wins against the strong bots and only two scripted-opponent trials with a learner touch. These are early development checks, not competitive-strength evidence. The final monitor uses five kickoff starts on both sides and is selection feedback, so independent screening/full matches are still required.

The camera-only RLViser Windows build passed GitHub Actions, and its 54,104,064-byte executable was downloaded and verified against its pinned SHA256/Windows PE signature. It imports standard Windows/runtime DLLs and does not require a separate Bevy DLL. Automatic launch and camera appearance on the user's Windows/GPU still need visual testing; this Linux environment cannot provide that check. The source patch and MIT license are included. The user's original copy01 remains an inspectable baseline, but legacy transition-filtered training is not resumed by the corrected trainer.

**v1.4:** 55 teacher-enabled tests pass. New checks exercise supervised fitting without PPO calls, unchanged teacher/value parameters (including TorchScript teachers), fixed separate validation rollouts, saved partial collection, pause/resume during fitting, teacher-lock changes, bounded return weighting, discounted return/censoring alignment, selected-field report exports, TOML parsing, package preservation, unsupported/tampered actor rejection and full-checkpoint → .lt actor parity.

Real all-four-teacher collection and supervised training completed across multiple rounds, including teacher takeovers after student prefixes. A short 12,000-decision copying check reached 64.5% unweighted held-out action agreement on 1,678 accepted labels; this was a small pre-return-weighting pipeline check, not a playing-strength result. The final reward-weighted path was separately exercised for 4,000 training and 1,000 validation decision attempts across two rounds. W&B's real offline SDK recorded a resumed copying session without a logging error. Online Windows credentials remain a local check through launcher 17.

An actual copying checkpoint was exported to .lt + .bot.toml + runtime and zipped. Its TorchScript actor loads through a separately compiled C++ LibTorch program, and native logits match Python inference. Copy-report HTML executes with a simulated DOM. No native browser visual check, Windows launcher execution or actual RLBot match was available here. The exported network is LibTorch TorchScript for the included NovaForge adapter; it is not a drop-in replacement for the teachers' native architectures.

**v1.3:** the teacher-enabled suite passes **43 tests**, including five reporting cases for selected-field export, exclusion of sentinel secrets/raw paths/model weights, disjoint early/late windows, partial log lines, evaluation/checkpoint matching and CSV retention across resumes. A real two-worker checkpoint resume for 128 decisions preserved the previous CSV. Real mixed-run reports and an earliest/current comparison against all four teachers were generated. The small comparison used two-second trials and timed out; it verifies the pipeline and provides no playing-strength evidence. Offline report JavaScript is also checked with a simulated DOM; a native browser visual check and Windows launcher execution are still outstanding. Raw Discord transcripts are excluded from the release. The extracted ZIP also passes 32 core tests, with 11 optional teacher cases skipped because teacher weights are downloaded separately.

**v1.2:** continuous training and optional W&B integration add five focused tests, bringing the teacher-enabled suite to 38 passing tests. Actual W&B offline event logging, multiple real mixed-bot PPO segments, STOP-based pause, checkpoint resume and stored tracking-ID reuse were exercised with two workers. Online login/upload using the user's Windows account is not accessible from this cloud environment; `17_WANDB_SETUP.bat` performs that check locally. See [WANDB_AND_CONTINUOUS.md](WANDB_AND_CONTINUOUS.md).

**v1.1 mixed-bot update:** 33 teacher-enabled tests pass. Both Chronos and Galactus networks match the original C++ GigaLearn model loader/forward on 32 random input rows and 14 scenario inputs each. Original C++ feature/mask/action code is compared against the ports on blue and orange across all seven practice types (14 cases per bot); Galactus fixtures provide identical external prediction samples. The captured numeric fixtures are included in `tests/fixtures/giga_reference.json`.

All four named bots pass actual simulator diagnostics. A 1,024-decision mixed-league PPO run completed. A 2,000-decision mixed-teacher collection against Galactus retained 1,725 exact-action labels: Nexto 458, Ripple 636, Chronos 331 and Galactus 300. It excluded 269 windows with control changes during the four-tick student window and 6 incompatible quantizations. These are pipeline checks, not playing-strength evidence. World-contact normals and live prediction/trajectory parity remain limitations of the native ports; see [MULTI_BOT_GUIDE.md](MULTI_BOT_GUIDE.md).

**v1.0.1 update:** the user reported a Windows `fsync` failure when saving a PPO checkpoint. The checkpoint and actor-export paths now open completed temporary files with write access. Two regression cases reproduced the failure under Linux before the fix. The updated teacher-enabled suite passes 24 tests; the core ZIP passes 19 with 5 optional teacher cases skipped. See [HOTFIX_v1.0.1.md](HOTFIX_v1.0.1.md) for installation and remaining Windows verification. The table below records the original v1.0 build checks, which did not detect this platform-specific bug.

This package was built and exercised in a **Linux cloud environment**. Windows 10, a GTX 1650 Ti Mobile and Rocket League itself were unavailable. The laptop preset is a conservative starting point, not a measured optimum for that machine.

## Original v1.0 build checks

| Check | Result |
| --- | --- |
| Python 3.12 tests with downloaded real teacher models | 22 passed |
| Python 3.11 tests with downloaded real teacher models | 22 passed |
| Actual two-worker PPO smoke | 512 decisions, checkpoint, resume for another 128, 640 total |
| Optimizer restoration and actor/PPO action parity | Passed |
| Frozen exported actor as an opponent in actual RocketSim physics | Passed |
| Mixed Nexto/Ripple/self-play PPO integration | 512 actual decisions completed |
| BC model → fresh PPO run with a Ripple opponent mix | 128 actual decisions completed |
| Teacher diagnostics | 120 simulator decisions each against scripted, Nexto and Ripple, split over both sides |
| Ripple delayed queue | First six controls remain queued; seventh equals the first plan |
| V2 simulator versus live-adapter V1 observation features | Matched on both teams across all seven practice types |
| Goal/horizon precedence and timeout accounting | Passed |
| Model hash mismatch, incomplete checkpoint and interrupted pointer handling | Passed |
| Serialized replay reset bank → actual simulator | Passed |
| Replay parser imports and bundled executable | Imports succeed; bundled `carball --version` returns `carball 0.1.1` |
| RLBot v5 adapter | Imports and actor export succeed; actual game not available |
| RLViser | State packet encoding exercised; standalone application unavailable for visual inspection |

The teacher collection check generated **6,000 actual Ripple decisions against Nexto**, across 18 episode groups (17 completed episodes). All labels matched the student's action table exactly; no quantization skips were needed.

A three-epoch BC check used **4,993 training samples** and **1,007 validation samples**, separated by episode IDs. Held-out cross-entropy decreased from **5.6203 to 4.1603**; held-out top-1 action accuracy increased from **0.20% to 16.58%**. This confirms that the imitation path trains, while the low action accuracy also makes its limits clear. It is not a competitive-strength result.

Evaluation plumbing was exercised with both team sides, real teachers and matched candidate/baseline seeds. The two-second screening fixtures timed out without goals. They validate reporting only; they provide no evidence of beating Nexto, Ripple, Chronos, Galactus or a Pulsar bot. No pretrained student or validation dataset is included in the ZIP.

## Upstream packaging detail

RocketSim 2.2.1 advertises ABI3 wheels. The inspected internal Windows wheel metadata instead names CPython 3.11, so `0_INSTALL.bat` selects **Python 3.11 x64**. The Linux wheel's internal metadata names CPython 3.9 and can make `pip check` report an unsupported platform under 3.11/3.12, despite the actual module and physics tests succeeding. Dependency resolution otherwise completed. This package does not modify upstream wheel metadata. A Windows `pip check` and real smoke remain part of installation verification.

## Still needs user verification

- Windows launchers, Windows dependency installation and laptop throughput/temperatures.
- CUDA installation and optimization performance on the GTX 1650 Ti.
- An actual raw `.replay` file through the full parsing/conversion path. No replay fixture was supplied.
- RLViser visual output and real RLBot v5 1v1 matches, including kickoff transitions and packet timing.
- Longer training, repeatable held-out evaluations, full-match strength and transfer from simulator to the real game.
- Broader Chronos/Galactus port validation with live matches and full prediction traces, and identification of the intended Pulsar deployment model if one is provided.

The full guide gives short tests before long runs and lists the files to send back when a check fails.
