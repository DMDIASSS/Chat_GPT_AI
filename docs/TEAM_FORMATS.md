# Isolated attention-policy team experiments

`slater_team_env.py` keeps the protected update180 attention actor and its
original observations/actions. It supports all nine learner-team/opponent-team
sizes: 1v1, 1v2, 1v3, 2v1, 2v2, 2v3, 3v1, 3v2, and 3v3. Sizes are relative to
the learner. For example, orange 1v3 creates three blue cars and one orange car.
Each format is checked with the learner on blue and orange.

The new files are separate from the running update180 continuation trainer.
They do not change an existing run, delete checkpoints, or turn a native MLP
into update180. An attention checkpoint must be complete before it is read.
Evaluation reads model weights; it does not train or automatically promote them.

## Observation and controller contract

The original actor receives query `(1,32)`, entity features `(41,24)`, and mask
`(41,)`. The first six entity positions are car slots, followed by the ball and
34 boost pads. Actual car slots include one self token, the correct teammate
count, and the correct opponent count from each individual car's perspective.
Orange perspectives are normalized using the original Nexto transformation.
Previous controls are included in the query.

Active entity masks are zero. Absent car masks are **-10000**, because the
bundled attention model adds its mask to attention logits. A positive boolean
mask would favor missing players. Absent car feature rows are explicitly zero
after relative-position conversion, so they cannot affect a correctly masked
critic pool either.

All cars receive controls every physics tick. The learner's action is held for
eight ticks using the existing RocketSim RLBot-delay configuration. Every
nonlearner car uses a frozen policy and the source-matched Nexto kickoff clock.
Teammates can use a distinct protected reference actor; opponents use the named
frozen rival. Cars sharing an actor are inferred together in one batch rather
than launching one model call per car. The caller must supply frozen, independent
reference policies, rather than reuse the trainable actor object as a teammate.

Learner scripted kickoff is off by default. Frozen teammates and opponents have
scripted kickoff enabled, with the original taker selection. A non-taker remains
policy controlled. The simulator uses an explicit standard-kickoff proxy; this
is not a claim of exact live RLBot packet parity. Scripted-learner evaluations
must be saved and interpreted separately from learned-kickoff evaluations.

## Training objectives and measurements

Supported starts are normal match kickoffs, ground play, teamplay, defense,
recovery, and low boost. Replay states are not expanded into fake asymmetric
rosters. A replay-specific team curriculum needs correctly parsed team replays.

Scoring is credited to the learner's **team**, including goals scored by a
teammate. Conceding gives the opposite reward. Team goals dominate small bounded
potential shaping; driving speed and repeated contacts do not have direct
rewards. A defensive clear is reported as a proxy, and is not a certified save
count. Recovery measures an upright landing. Match success means a team goal,
not moving or touching the ball.

Use paired candidate/reference matches on the same format, side, seed, frozen
teammates, and rivals. Look at goals and concessions for **each format**, keeping
1v1 retention visible. An aggregate can hide regressions in disadvantaged sizes.
A nine-format screening result is exploratory. Confirm promising candidates on
fresh seeds and longer matches before selecting them; no simulator test proves
an SSL rank or guarantees a universally best model.

## Read-only audit and paired evaluation

From CMD inside `E:\Downloads\Chat_GPT_AI`, audit your protected baseline:

```bat
.venv\Scripts\python.exe slater_team_eval.py audit --source data\isolated\mechanics_curriculum\selected7_mechanics01\update_000180.pt
```

The audit creates a timestamped JSON under
`data\isolated\team_observation_audits`. It checks every car in all nine formats
on both colors, first at reset and then after actual controls. It reports raw
unpadded/padded logit differences, action agreement, team counts, and source
hash preservation. This checks the observation contract, not playing strength.

After choosing a complete saved attention checkpoint, compare it with update180:

```bat
.venv\Scripts\python.exe slater_team_eval.py evaluate --candidate "PATH_TO_COMPLETE_CHECKPOINT.pt" --formats all --seeds 4 --seconds 30 --out data\isolated\team_evaluation\screen01_raw.json
```

Reference defaults to update180 and the rival defaults to original Nexto.
`--reference PATH` and repeated `--rival name=PATH` allow explicit frozen
policies. Both candidates receive the same frozen reference teammates. The
report includes exact model hashes, observation/control code hashes, runtime,
raw paired games, per-format goals/concessions, and paired seed-cluster
intervals. Repeating the same command resumes only if the pinned inputs match.
Use a fresh output name when changing models, seeds, runtime, or code.

For a separate scripted-learner check, add `--scripted-learner` and choose a
different output file, such as `screen01_scripted.json`. Confirm promising
finalists on fresh seeds (`--seed-base`), at least 8–16 seeds, and longer matches.
The evaluator is read-only and does not automatically replace your playing bot.

## Verification performed in the cloud

The original vendored Nexto actor and real installed RocketSim were used to
check all nine formats with both learner colors. The tests verify complete
rosters, every car's teammate/opponent counts, masks, finite policy logits and
controller vectors, batched frozen inference, original unpadded-versus-padded
actor output parity, previous inputs, and roster ordering. Actual simulated
goals verify shared team credit on both colors without learner contact.

A mirrored-state test checks team normalization and attention permutation
invariance. The unchanged historical Nexto boost-coordinate table contains one
3310/3308 discrepancy; that known two-unit table asymmetry is accounted for in
the mirror test without changing the original policy contract.

These are integration checks, not evidence that your latest local update180
continuation is stronger. The local audit/evaluation must use your actual
checkpoint and retain its path and SHA-256 in the report.
