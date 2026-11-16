# Visualization and RewardServer feasibility

## Checked upstream behavior

- RocketSimVis's documented protocol is JSON over UDP, default port 9273. It accepts ball/car positions, forward/up orientation vectors, linear AND angular velocity, controls, boost and several state flags. Ball rotation is therefore supported by the protocol; a viewer failing to show it is not proof that spin is absent from physics. Hitbox-accurate overlays, reward attribution and candidate branches are not supplied by the listed basic features.
- RocketSimVisWeb is a Three.js browser rewrite with a local Python server. Its existence does not establish feature parity or compatibility with every version of RocketSimVis/rlviser.
- Current rlgymppo_rs uses the newer rocketsim_viewer/RocketSim v3 integration, not the old RLViser UDP format. These transports cannot be interchanged by pointing an executable at the wrong port.
- GigaLearn's stock RenderSender calls a Python module and sleeps for real-time pacing. It is useful for a separate WATCH process, but enabling that render loop in the high-throughput collector would throttle training.

Pinned sources: research/repositories.json; [RocketSimVis protocol](https://github.com/ZealanL/RocketSimVis/blob/074a4368f31668ccd651087eebf6a1b459564ad7/networking-format.md), [GGL RenderSender](https://github.com/ZealanL/GigaLearnCPP-Leak/blob/86e11c3881a21225a43c36b14af40f0b3c87e7dd/GigaLearnCPP/src/public/GigaLearnCPP/Util/RenderSender.cpp), [Rust migration](https://github.com/VirxEC/rlgymppo_rs/blob/c774b3095e52679025d711aa06842128672ceaa9/MIGRATING_DOWNSTREAM.md).

## Proposed integration

Prefer the original RocketSimVis initially, connected to a separate single-arena policy evaluation/watch process. Use one shared versioned telemetry schema for training samples, watch sessions and clip files. Put reward/decision timelines in a lightweight local inspector rather than recreate 3D rendering.

The collector must only enqueue a bounded selected-arena snapshot at a wall-clock rate; never await a viewer or server. A separate telemetry thread/process serializes and sends data. Queue capacity is fixed; drop old visualization frames and report drop counts instead of blocking simulation. Record true simulated tick and snapshot sequence numbers. A separate watch match runs an explicitly identified frozen checkpoint at real time and never substitutes an analytic ball-chasing controller.

A frame contains model hash, episode/arena/seed/color, physics tick, public observations/masks, chosen action, top action probabilities and value, car/ball pose/linear velocity/angular velocity, previous controls, boost, jump/flip/contact state, terminal/truncation event, and each reward's raw formula inputs, weight and weighted contribution. Compute acceleration from valid consecutive samples with actual elapsed ticks; do not divide across resets.

| Requested capability | Existing component | Project work and verification needed |
| --- | --- | --- |
| Live car/ball scene, orientations, boost | RocketSimVis | Test current schema and coordinates, viewer auto-start/handshake |
| Ball spin and velocity vectors | Protocol has angular/linear velocity | Verify render behavior, add optional overlays where missing |
| True hitboxes and contacts | Simulator exposes state/config | Add explicit overlays and label actual versus inferred contacts |
| Reward activation and simultaneous terms | Native reward registry + telemetry | Build frame-scrubbable inspector; verify sum equals trainer reward |
| Physics history and actual trajectories | Bounded frame recorder | Plot recorded positions; do not label straight-line extrapolation as simulated prediction |
| Counterfactual ball/car paths | Complete RocketSim clones | Restore full jump/flip/contact history and RNG, test clone parity first |
| Policy decision explanation | Actor logits, legal mask, critic | Display top-k and uncertainty; these do not prove strategic intent |
| Search branches | None in baseline | Add only if a planner wins its latency and match-strength ablation |
| Replay/clip review | Event-selected telemetry clips | Save goals, concessions, whiffs and recoveries, with model/config hashes and scrub time |

Retention targets: sample one arena, cap the in-memory clip buffer at 32 MB and a saved clip at 64 MB, cap session recording on disk. Measure telemetry-off versus sampled telemetry-on overhead with the same policy/seed; initial acceptance target is <3% throughput loss. This has NOT been measured for the new trainer yet.

## RewardServer source audit

Inspected README, INTEGRATION.md, PROTOCOL.md, ARCHITECTURE.md, CMakeLists.txt and the supplied smoke client at commit fbc3a307112d7bc2ef2d4641fe43213fe963f905.

It supplies a BakkesMod plugin, a local C++ reward evaluation server, raw/weighted reward rows, `.rlpr` clip recording/playback, offline reward replay and shot-task bookkeeping. The server expects an existing GigaLearnCPP-compatible target and project integration through `CreateUserReward` / `IRewardSource`, with optional `IEvalExtension`. This is relevant to the proposed C++ stack. It is not a learner, not an automatic reward discovery system, and not already a drop-in training telemetry dashboard.

Protocol: newline-delimited JSON, default 127.0.0.1:42069, version 1, one client at a time, `hello` capability negotiation, `load`, `eval`, `capture`, `reset` and clip/task commands. The `eval` message can include car/ball kinematics including angular velocity/rotation, prior actions, jump/flip/contact flags and boost-pad state/timers.

Important integration details:
1. Reuse the trainer's actual reward classes, not a second approximation with different episode history. Call state updates once per tick before evaluating players, and preserve independent reward state per session.
2. Do not interleave plugin and training states through a single stateful server/client. Use separate sessions/processes/ports if both are active.
3. The plugin's arena mirror reconstructs contacts/jump/flip state where game data lacks them. Label those fields inferred; they are not authoritative native-training contact events.
4. Calls belong in the watch/debugging process, not a synchronous network request per training arena/step.
5. The current server CMake links Windows ws2_32 and expects MSVC/framework includes. The Linux research machine cannot establish live Windows/BakkesMod compatibility.

Verification status: source-level integration and protocol were checked. The supplied server/plugin were NOT built or run, a live game connection was NOT tested, and no runtime-overhead result is claimed. Next test on the selected Windows build: use the upstream `tests/smoke_client.py` against the real compiled server, require `hello`, config load/eval row counts, finite totals, reset and clip tests to pass, then compare native frame reward values to trainer output. Only after this is it an integrated feature.

Sources: [integration](https://github.com/HappyBavarian07/RewardServer/blob/fbc3a307112d7bc2ef2d4641fe43213fe963f905/docs/INTEGRATION.md), [protocol](https://github.com/HappyBavarian07/RewardServer/blob/fbc3a307112d7bc2ef2d4641fe43213fe963f905/docs/PROTOCOL.md), [architecture](https://github.com/HappyBavarian07/RewardServer/blob/fbc3a307112d7bc2ef2d4641fe43213fe963f905/docs/ARCHITECTURE.md).
