# Versatile trainer validation — 2026-10-12

The cloud uses Python 3.12, CPU PyTorch 2.14.1, NumPy 1.26.4,
RLGym Rocket League 2.0.1, RocketSim 2.2.1, RLGym Tools 2.6.5,
Pandas 2.3.3 and PyArrow 21.0.0. The local user's update 180/full private
champions were not available; tests used protected original Nexto.

## Checks completed

- `tests/test_versatile_trainer.py`: **21 passed**. Real simulator scenarios,
  2v2 roster support, finite native observations/rewards, tick-level rival and
  optional evaluation-student kickoffs, exact capture reconstruction and rejection
  of wrong controls, dataset hash/leakage checks, real BC optimization and complete
  Adam/actor rollback, matched confirmation tests, cached/pauseable evaluation,
  real hybrid save/restore/resume, source protection, and padded/unpadded actor
  observation parity. Promotion bookkeeping was also tested with mocked match/skill
  verdicts; those mocks do not supply evidence of competitive improvement.
- Existing relevant suites: **54 passed** (`tests/test_addon.py`,
  `test_replay_tas_learning.py`, `slater_mechanics_tests`,
  `slater_v041_tests/test_ppo.py`). These retain the existing exporter/mechanics
  workflow and its persistence behavior.
- Desktop command construction verified for prepare, preflight, start, resume,
  status, pause and smoke with mocked widget values. Tk display/Windows VBS launch
  was not available in the cloud.
- A real public replay, Boxcars `assets/replays/good/b2a19.replay`, SHA256
  `5e110fac85a2ff9233948ad9de51ca4481d5149e1ce5bea5d6d0902c44bab1ce`, was parsed
  using RLGym Tools/carball. It is 3v3 with 8,540 parser frames. The importer
  produced 96 native samples, 16 in each of six categories; 629 uncertain mappings
  were rejected. Source grouping uses its replay game ID. This is not asserted
  to be an SSL/pro match, and the replay is not redistributed in the update.
- End-to-end preparation used **synthetic, exact simulator captures**: 14 clips,
  336 examples, 11 train / 1 validation / 2 test source groups. This validates the
  aligned-capture import and sharding path, not human skill learning.
- An eight-world mixed smoke exercised match, ground, teamplay, replay, defense
  and air-dribble starts. Update 1 collected 256 decisions, accepted a PPO epoch
  at policy KL `0.00213473` under `0.015`, accepted two replay BC updates at KL
  `0.00000735` and `0.00000791`, and executed 168 scripted rival physics ticks.
- That run was resumed for update 2 / 512 total decisions. It accepted a PPO
  epoch at KL `0.00471269` and two BC updates. Both tiny eight-second screens
  were 0:0 ties, so the initial champion stayed selected and restored state was
  committed. **No competitive improvement was established or promoted.**
- Source Nexto remained SHA256
  `bf5343b5eeacac6bf7cdb75dac4a5c14ba0f94d820eae75f00a211b6119d69fa`.
- The reusable cloud installer was rerun successfully with added pinned replay
  preparation dependencies. A cloud configuration draft was saved. Publication
  and fresh-environment restoration were not performed.

## Observation correction

The traced Nexto attention module adds its mask to attention logits. Passing
positive 1s for padded fake players increases their attention. The new pipeline
maps placeholder masks to finite negative values and excludes them from critic
pooling. Its real model logits match unpadded 1v1 Nexto observations within the
`1e-5` parity tolerance. This change is isolated to the versatile pipeline;
earlier mechanics training code/protocols are unchanged.

## Limits

The pipeline runs real CPU simulator optimization; it is not a C++ collector,
GPU pipeline, independently trained inverse-dynamics model, or verified elite
bot. Physics worlds run serially with batched actor inference. Small smoke
throughput is not a hardware-independent speed benchmark.

Replay controls/hidden state are reconstructed, with filters rather than ground
truth certification. Aligned TAS import checks local eight-tick consistency; it
does not turn legacy control-only .data files into state/action demonstrations.
RLGym Tools can reject unsupported/malformed replay versions; parsing errors are
recorded and there must be sufficient independent groups before training.

The historical RocketSim wheel reports an old cp39 wheel tag under Python 3.12
in `pip check`, although its installed bindings import and pass real simulator
checks. No verification was disabled or packaging metadata changed in this work.
This does not establish a fresh Python 3.12 wheel installation on every platform.

Full confirmation/promotion and fresh raw-human-dataset training remain to run
on the user's checkpoints/data. Actual Windows desktop launch, RLBot export
play, long matches, skill retention outside sampled seeds and live Rocket League
mechanics must be validated locally. No SSL/Zen result or guaranteed continual
improvement is claimed.
