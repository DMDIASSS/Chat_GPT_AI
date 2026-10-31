# What the uploaded update180 continuation actually achieved

The supplied reports contain 60 updates, 122,880 learner decisions, three cycles and about 974 seconds of session time including evaluation. None passed the complete promotion protocol. The three-cycle plateau stop was reached. The retained `initial.pt` contains the starting update180 actor plus the fresh versatile critic and optimizer state; a different file hash does not mean a different starting policy.

| Candidate | Screen candidate goals/concessions | Baseline goals/concessions | Result |
| --- | --- | --- | --- |
| update_000020 | 1 / 2 across eight short games | 4 / 3 | Screen failed; lower overall goal difference |
| update_000040 | 4 / 0 across eight short games | 5 / 2 | Screen passed, confirmation failed |
| update_000060 | 5 / 3 across eight short games | 4 / 3 | Overall slightly positive, Nexto-specific regression guard failed |

Update40's independent confirmation used 12 fresh seed clusters, both colors, two opponents and 60-second matches: 48 games for each policy. Candidate scored40/conceded30; baseline scored54/conceded44. Both had total goal difference +10. The paired difference interval included zero (about −0.458 to +0.521 goal difference/minute), and Nexto-specific mean was negative. This supports no confirmed net improvement, rather than proof that every candidate degraded.

The `confirmed: true` field inside a verdict denotes confirmation **mode**, not a successful verdict; `passed: false` and the cycle decision determine rejection. Skill retention checks were not reached for these candidates.

All these supplied screens had learner scripted kickoff ON, while training learner kickoff was OFF. That is a deployed-script screen, not a direct measurement of learned kickoff. New team checks default to raw learned kickoff and can separately enable scripted learner kickoff. Frozen supporting teammates/rivals use scripts in both modes.

After a rejected cycle, `cycle_0003_resume.pt` contains the restored champion actor. It is not the trained update60 candidate. Use explicit `update_000040.pt` or `update_000060.pt` to investigate those policies. New `check-current` chooses `progress.candidate`, not the latest rollback checkpoint, and reports the choice.

Do not weaken promotion rules to manufacture progress. Keep update180 as the playing baseline, retain the candidates and change one training variable in a separate experiment. The positive short screens did not reproduce as an overall confirmation win. Human replay gradients were disabled in this run. Its teacher, source weights and opponent contracts were intact; the result identifies a learning/evaluation gap rather than an idle native-policy failure.
