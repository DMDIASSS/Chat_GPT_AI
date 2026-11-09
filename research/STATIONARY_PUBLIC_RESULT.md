# Stationary Chronos pilot: no demonstrated improvement

Both candidates started from public original Chronos, used Breakout, trained against frozen original Chronos for 393,216 collected learner decisions, and kept the actor trunk frozen. Only goal reward versus the same goal reward plus small potential-based shaping differed. Full configuration, source/native hashes, receipts, raw match records, logs and last complete optimizer checkpoints were retained.

The development screen used 128 games per actor: 64 versus original Chronos and 64 versus original Galactus; 135 simulated seconds per game, balanced colors, identical predeclared seed panel. These are development results, not an independent final confirmation.

| Actor | W | D | L | Draw-adjusted score | Difference from original panel |
| --- | ---: | ---: | ---: | ---: | ---: |
| Original Chronos | 53 | 16 | 59 | 47.66% | reference |
| Goal-only trained | 46 | 29 | 53 | 47.27% | -0.39 points |
| Goal + potential trained | 45 | 19 | 64 | 42.58% | -5.08 points |

The paired development difference intervals include zero for both candidates. Neither candidate improved the panel point estimate; neither was sent to the reserved 2,000-game confirmation, and no champion pointer changed. These small experiments do not establish that potential-based shaping can never help.

Separately, a compiled probe using the uploaded reward class and actual RLGymCPP all-player reward interface reproduced a broken adaptive counter: 100 goals scored only by Blue produced a reported 0.5 goal share. Normal signed goal reward still exists. Uploaded build metadata disagreed with two uploaded source files and the old executable was absent, so this does not prove exactly which edited reward the historical Windows executable ran.

The update supplies a verified new native build, rejects that invalid legacy adaptive objective for new training, records valid learner-only goals, adds signed seed guards, identity-checked evaluation caches, isolated/resumable pilot runs, pinned previews, report/watch/export launchers, and fixed final-test reservations. It is a correctness and research update, not a proven stronger bot release.

Next decision: retain the original; inspect critic/advantage calibration and first-goal-training versus timed-match-evaluation objectives before increasing training time or reward complexity. Do not leave this unchanged failed recipe running overnight. GPU throughput and live RLBot deployment were not measured on the user PC.
