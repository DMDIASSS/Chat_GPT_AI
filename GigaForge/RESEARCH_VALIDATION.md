# Public CPU pilot and validation

This is a correctness/feasibility pilot, not proof of stronger Rocket League play. Source: b665b466474afb8dc69d95016968df061d61518c; GigaLearn 86e11c3881a21225a43c36b14af40f0b3c87e7dd; Python 3.11.17, Torch 2.9.1+cpu. Bitwise trajectories are not guaranteed, especially demo respawns.

Four sequential trials tested control and attack for both families. Each used 16384 collected decisions, 4096-sample rollouts, two PPO epochs, batch/microbatch 256, original full networks and fixed-rollout bootstrapping. Attack froze the pretrained shared trunk. WDL used four seeds per opponent, both colors, 30-second timed matches against original Chronos and Galactus, with a matched retained-parent baseline. These are shorter/smaller budgets than the shipping default.

| Candidate | Candidate W/D/L | Baseline W/D/L | Paired match-score difference | Result |
|---|---|---|---:|---|
| chronos control | 5/2/9 | 8/2/6 | -0.188 | uncertain |
| galactus control | 5/8/3 | 3/8/5 | +0.125 | uncertain |
| chronos attack | 5/4/7 | 7/4/5 | -0.125 | uncertain |
| galactus attack | 2/10/4 | 3/8/5 | +0.000 | uncertain |

No candidate passed the improvement screen. No candidate was promoted. This pilot supports neither a universal gain nor choosing one reward profile as best. All 65536 collected learner decisions entered prepared PPO batches. Both families applied 192 actor optimizer steps across their two trials. Total wall time was approximately 110 seconds on this cloud CPU, including training and evaluation; it is not a laptop benchmark.

Native integration tests separately exercised all four reward profiles for both families; two 512-sample rollouts each; exact collected/prepared equality; actor warmup; actual policy updates; unchanged shared trunks for frozen profiles; multi-call resume; and original feature/mask/network parity. Controller tests inject positive/negative evaluation decisions to verify branch retirement, confirmation gating and champion copy protection. Those injected decisions are not evidence of wins. An exported promoted test actor matched its native core logits, and the protected copy survived removal of the training checkpoint directory.

Mathematical native checks verify terminal versus truncation bootstrap ordering and discounted shaping telescoping with terminal potential zero. Windows validation and the packaged binary are recorded in the release metadata. Tests cannot establish general strength.
