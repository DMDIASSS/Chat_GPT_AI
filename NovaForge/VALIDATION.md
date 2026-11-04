# Validation evidence and limits

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
