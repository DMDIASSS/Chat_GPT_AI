# Research log — Phase 1

## H1: prefer native collection on a weak CPU, but measure the whole learner

Surveyed pinned RocketSim, GigaLearn, RLGymPPO_CPP, rlgym-learn and current Rust PPO sources. Outcome: a native C++ baseline is practical with existing LibTorch/v5 export infrastructure; Rust is a credible alternate, not dismissed based on language. No full-stack target-laptop comparison is complete. Author-machine speed claims are recorded as claims, not forecasts.

## H2: existing archive code must pass return-target tests before training

Ran exact GigaLearn GAE source in a real LibTorch/sanitizer harness. Reproduced two concrete faults; small repair fixed the isolated fixtures. Decision: stock archive cannot be the unexamined baseline. Audit fixed rollout/tail/timeout and opponent boundaries before any lengthy run. No unsupported attribution to earlier projects.

## H3: a 1–2M dense policy is a useful 1v1 starting point

Implemented disposable synthetic dense512 (1,216,091 params), dense768 (2,610,523) and four-token attention (1,231,451) comparators. Two-thread CPU probe favored dense512 for both batched inference and optimizer throughput. These measurements are not a learning or GTX benchmark. Decision: propose dense512 first, include bounded local CUDA probe, keep attention as a later equal-budget ablation.

## H4: small fresh reward hypotheses can be tested without a mechanics checklist

Defined goal outcome, bounded goal-position potential and an optional contact-gated impulse term. Eight model/mathematical tests passed, including terminal handling, color symmetry, discounted telescoping and no jump/airtime bonus. Decision: first pilot changes only impulse weight, three paired seeds, fixed compute budget. No claim of improved game skill yet.

## H5: reuse visualizers, keep telemetry outside the learner

Read RocketSimVis's UDP schema and GGL's pacing renderer. RewardServer source supplies a Windows/BakkesMod reward/debugging route with one stateful client, not a training dashboard. Decision: separate watch scene plus native reward-frame telemetry, optional RewardServer using the actual reward classes. Live server/plugin/GUI and throughput overhead are untested.

## Outstanding before the pilot

Windows compilation and dependency/runtime compatibility; actual laptop CUDA/memory profile; selected native collector correctness; source/export feature/action/delay agreement; native fixed-opponent adapters; bounded recording and monitor hooks. The 90-minute pilot is conditional on these gates and explicit approval, not automatically started by this package.
