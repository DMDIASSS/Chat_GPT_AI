# Changes

## Skills 0.5

Problem: previous training produced rare ball contact, excess airborne motion and mostly scoreless evaluations.

Changes: native/skills.h and native/core.cpp add distinct-event goal-gated combos, contact reward shaping, configurable drill mixture and controlled pose injection. skills.py adds learned ground warm start, validation, checkpoint retention, bounded recovery and menu. train.py adds fading ground auxiliary learning and skill telemetry. model.py supports detached critic-feature gradients for the new profile. rlbot5_agent.py/export_v5.py add SDK-tested v5 deployment with unique per-export agent IDs; cli/viewer/runtime support complete workflow and existing dependency reuse. Old profiles and checkpoints remain separate.

Tests: 41 passed, one CUDA-only skip. Windows CPython 3.11 native build passed action/observation/chain smoke checks. Physical learned-model pilots, 128-arena continuation, save/resume, exported PT/LT logit/action parity, actual v5 SDK/model diagnosis, headless watch, report creation and regression recovery were exercised. Quantitative results and the failed pilot are in SKILLS_VALIDATION.json and validation/.

Limits: server has no CUDA or Rocket League client. Contact competence and a promising but uncertain parent match panel do not establish competitive rank or a guaranteed training duration. Ground tutor is used in training only; inference always uses the network.
