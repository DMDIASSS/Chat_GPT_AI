# Why v1.4 copying accuracy did not predict gameplay

The supplied report showed 86.4% teacher action agreement, including 99.5% for Chronos, but the matching student evaluation had **zero touches in 50 kickoff trials**. That was a real failure, not evidence that more of the same training was necessarily helping.

A collector bug contributed: native teacher controls change inside some four-tick windows. Those windows were filtered out. In reproduced collector data, essentially every retained Chronos/Galactus target equaled the previous-action features. A student could score highly by repeating its controls, while failing to choose useful controls from a cold start. Randomly dropping those features on 15% of fitting rows was insufficient.

## Corrections

1. Retain control transitions using the last executed command in mixed windows. This is a documented timing approximation; stable windows remain exact.
2. Remove previous-action inputs structurally from the copying actor and preserve that property in exported actors.
3. Skip initial all-zero queue warmup and give changed-control examples additional supervised attention.
4. Start a fresh `copy02` with new seeds, data and validation rollouts. All positive-weight scenarios rotate through validation so a missing dribble category is visible rather than silently assumed to be covered.
5. Begin with first-contact kickoff demonstrations, then expand after the student actually reaches the ball reliably.
6. Monitor the student's own controls/contacts after rounds, and select the published model using that feedback before using copying loss as a tie-breaker. Independent evaluations and full matches remain necessary.

The copying-loss optimum and the gameplay-selected model are tracked separately. Reports identify the published checkpoint and its matching monitoring/evaluation results, and flag incomplete validation coverage. W&B links on `forge.coreweave.com/wandb/...` are now accepted without copying query strings or credentials.

## Start the corrected fresh run

Pause the old process, update the source from the v1.5 ZIP and run **1_CHECK.bat**, then **21_START_OR_RESUME_COPY.bat**. It creates `copy02` from random weights. Run **22** to pause/save, **24** to watch, **25** for `.lt` + `.bot.toml`, and **26** to export a report. **27** compares gameplay against the named bots and the old `copy01` when available; **30** screens mechanics.

A short development run reached ball contact in 6/12 scripted-opponent monitoring trials after 100,000 teacher-decision attempts. This is a preliminary development check, with different seeds/opponents from the user's 50-trial failure; it is not a comparable win rate or proof of competitive strength. A separate 50-trial screen still had no wins against the named strong bots, and only two trials with a learner touch against the scripted opponent. The student is still weak; this check supports continued measured development rather than a strength claim. The final monitoring set covers five standard kickoff starts on both sides. Validate the fresh student's behavior on the user's PC before drawing stronger conclusions.

The earlier run/checkpoints remain available for inspection. Their old copying percentages are not directly comparable with the corrected label distribution. No user weights or datasets are bundled in the source ZIP.
