# Mechanics integration evidence — 2026-10-12

Cloud: Python 3.12, CPU PyTorch 2.14.1, RLGym 2.0.1, RocketSim 2.2.1.
This is integration evidence; no mechanic or competitive rank is established.

- Focused mechanics/v025/v040/v041 suite: 111 tests passed.
- Broad suite: 476 passed, 1 skipped, 2 existing failures. Both failures require
  `data/rlbot_exports/slater_v036_nexto_modes/Nexto_NN_Greedy/bot.py` or `bot.cfg`,
  which are missing from this checkout. They failed before these changes too.
- All seven real simulator drill starts produced finite, mirrored states without
  granting success at reset. The four-wheel test regained a previously spent
  flip through actual RocketSim ball contact and qualified the reset event.
- Native PPO accepted a 128-decision smoke update from uploaded u0071. Exact
  rollout-policy KL was 0.003738 against a 0.015 limit. The frozen opponent used
  168 scripted kickoff physics ticks in the retention world. Drill success was
  zero; a smoke run has insufficient seeds for the real gates by design.
- A bounded two-update pilot exercised actual retention failure and restored the
  starting actor. Resume continued from that saved state to update 3 / 384 total
  decisions. Persistence tests additionally verify the reverted actor and empty
  restored actor Adam state, a real changed raw PPO actor, and changed-config
  refusal. Originals were untouched.
- A two-game round-robin smoke ran native and feedforward actors through their
  own observations/control tables. Both games timed out; this is no ranking
  evidence. Discovery tests cover native TorchScript and deduplication by actor
  weights, independent of optimizer/metadata.
- A short matched comparison of the two uploaded actors (2 seeds, both sides,
  2 common rivals, 8-second clocks: 16 matches) returned `CLOSE_OR_INCONCLUSIVE`.
  All matches were 0:0. Run the documented full comparison with local models.

Protected SHA-256 values verified after training/evaluation:

| Input | SHA-256 |
| --- | --- |
| Original Nexto | `bf5343b5eeacac6bf7cdb75dac4a5c14ba0f94d820eae75f00a211b6119d69fa` |
| Uploaded smoke seed | `f20b37576a7eb154882f7ee86bfcfe5c1398964300d66a101efbe1625bc2a9e8` |
| Uploaded u0071 | `92598327608850024c00aed05d1284480873630ac7d0d04f09faf67638b07a26` |

The October 11/12 copies of each actor have identical hashes. Raw Discord exports,
checkpoints, logs, and generated evaluation outputs are not committed.
