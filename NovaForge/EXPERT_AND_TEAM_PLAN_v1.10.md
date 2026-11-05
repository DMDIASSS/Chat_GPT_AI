# Expert pool, opponent pool, and team-coordination plan

## How many experts?

Start with four verified choices and treat five as an initial practical cap for
this laptop, not a mathematical optimum. Each extra expert adds transfer tests,
memory/inference cost and another choice to learn. A strong bot that duplicates
an existing expert may add less value than a complementary specialist. Measure
conditional gains from adding/removing each candidate, not just top-five solo
win rates. Include a latency budget and repeated comparisons per game format.

The **opponent pool** can be broader than the **expert pool**. Retain varied
strong opponents plus some easier opponents, self-play where implemented and a
small demo-chasing stress component. Use compatible pinned adapters rather than
assuming an RLBot executable is a RocketSim training policy. No new opponent is
enabled simply because its public package contains a `.lt` file.

## Inspected candidates

Exact public botpack submodule commits and source URLs are recorded in
`configs/bot_candidates_v1.json`. The metadata below is an inspection of those
packages, not a strength ranking or a completed adapter implementation.

| Candidate | Verified package facts | Next integration check |
| --- | --- | --- |
| Chronos / GalactusV2 | Existing pinned native-feature ports and C++ parity fixtures | Preserve parity; benchmark switching effects |
| Ripple v1.1 | Existing ONNX policy and native opponent adapter; common selector uses a held-queue approximation | Audit native queue/history/timing before interpreting weak selector-adapter scores |
| Dice / Kira | Pinned GGLBot C++ sources with policy/shared-head `.lt` files | Port and validate each exact observation, action mask and control schedule |
| Ducky | Pinned RocketForge inference sources/policy; author documents team batching | Verify model setup, observation/action/history and physics bridge before training use |
| Megabyte | ByteBotpack documents full-strength Megabyte and separate Kilobyte difficulty profile, 1s/2s/3s | Select the actual Megabyte policy/profile; validate native observation/action/timing |
| Rain | Author documents 231 inputs, six-tick decisions, five-tick delay and separate 1s/2s/3s checkpoints | A generic eight-tick wrapper is not native Rain scheduling; validate correct format and timing |
| Wisp v2 | Python model/observation/action code and RocketSim adapter; author documents 1s/2s/3s | Validate adapter state/history compatibility and team observations |
| Willo 24k | Python model/observation/action code and RocketSim adapter; primarily 3s, positioning/possession | Evaluate in its intended team format rather than exclude on duel results |
| Adversity | Not identified under that name in the linked botpack during this audit | Identify exact source/version first; current scripted demochaser is explicitly a different implementation |

Dice, Ducky, Ripple, Galactus, Chronos and Megabyte all remain serious candidates.
No result from a mismatched adapter is used here to declare a native bot weak.
Rain/Megabyte/Dice/Ducky/Wisp/Willo/Kira are **not yet installed headless policies
in this release**. They are not included as fake names in training configurations.

A correct port needs more than matching tensor dimensions: tick cadence, delay,
queued previous actions, team/slot permutations, car hitbox and policy version can
all change behaviour. First verify a fixed expert alone against its native
implementation on identical inputs and trajectories. Then test transitions into
and out of that expert. A source's team batching or RocketSim adapter is useful
evidence, but not proof of compatibility with this project's current engine.

Priority after the four-way experiment: preserve/investigate native Ripple
timing/history, then validate Dice/Ducky/Megabyte candidates and the Wisp/Willo
team-oriented ports. Pick a fifth expert only if it improves the current set on
held-out starts/formats at acceptable latency. A larger verified pool can be used
as opponents even when those bots are not selector choices.

## 2v2 first, then 3v3

The current implementation is still 1v1. `hivemind=true` is process ownership and
batching, not learned strategic coordination. The live runtime rejects unsupported
player counts with neutral controls; do not present it as a team bot.

A separate 2v2 experiment should use a shared team observation and coordinator
which selects both experts together. With five experts there are 25 ordered
expert pairs. Possible roles such as attacker/cover are useful diagnostics, not
proof that an assignment is tactically correct. Two independent gates selecting
the same strongest solo bot can still double-commit or leave the goal uncovered.

Required stages:

1. Extend state/observation adapters to real teammates and multiple opponents,
   preserve native permutations and timing, and compare to native references.
   The current `build_features` 1v1 guard is deliberate and must not simply be removed.
2. Build a separate team environment with shared goal/concede outcomes, symmetric
   observations, stable car IDs and explicit per-car fixed bodies. Keep original
   1v1 checkpoints and export contracts separate.
3. Train a central coordinator/shared critic over joint expert assignments,
   with a baseline of independent expert selection. Synchronize commitment and
   control clocks. It may batch per-car inference while sharing the full game
   state, but each frozen expert still needs its own valid observations/history.
4. Evaluate team W/D/L, goal differential, double commits, uncovered-net events,
   passes/receives, latency and robustness with new partners/opponent teams.
   Use team performance to accept improvements; proxy metrics alone are insufficient.
5. Only after replicated 2v2 gains, test 3v3 with a coordinator scalable to three
   cars. Five experts give 125 ordered triples; factorized/autoregressive choices
   may reduce learning cost, but should be compared with simpler baselines.

Fusion could later fine-tune in team play using verified team observations and a
separate critic/curriculum. A single-car value function or an exported actor-only
file is not automatically a team strategy network. Models do not acquire shared
memory or communication merely by being loaded in one process.

These team stages are a roadmap, not implemented capabilities of v1.10. The
working new experiment in this release is selected/refined frozen Fusion as a
fourth expert for the existing 1v1 framework.

## Research discipline

Use the objective registry and archived experiments to compare one hypothesis
at a time. The controlled Fusion tournament/refinement, fixed-expert ablations,
free-choice probabilities and small scripted demo stress are concrete steps.
Autonomous objective invention, counterfactual full-state branching and learned
team coordination remain unimplemented until their prerequisites are validated.
Avoid increasing reward complexity to compensate for a broken observation/timing
port. Keep scoring/conceding outcomes as independent validation and retain better
champions. Do not infer superiority from throughput or a single short match set.
