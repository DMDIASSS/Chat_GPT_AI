All-model first-goal tournament (from the uploaded Round_Robin_50 addition)

Install these code files into your existing E:\Downloads\Chat_GPT_AI folder.
Keep .venv, models, replays, and data. Use the current Slater environment.

1. ROUND_ROBIN_0_LIST.bat: inventory all compatible .pt actors.
2. ROUND_ROBIN_2_SMOKE_TEST.bat: two actors, two 10-second first-goal games.
3. ROUND_ROBIN_1_RUN_50.bat: all unique compatible actors, 50 games per pair.

All these launchers enable the same Nexto scripted kickoff proxy for every actor.
Each pair uses 25 shared seeds with both sides. Games stop at the first goal or
180 simulated seconds. D is a censored timeout rather than a full-match draw.
Rankings are screening results.

Supported: native Nexto checkpoints, compatible Nexto TorchScript, and project
feedforward policies with 92 inputs/90 actions. Deduplication uses actual actor
weights plus kickoff mode, ignoring critic, optimizer, and metadata. Inventory
records incompatible, corrupt, nonfinite, and oversized files. Default maximum
checkpoint size is 256 MiB; --max-checkpoint-mib can override it.

Outputs in round_robin_reports:
  inventory.csv
  games.jsonl                    finished games and crash-resume cache
  leaderboard_TIMESTAMP.csv
  head_to_head_TIMESTAMP.csv
  results_TIMESTAMP.json         full ranking and model-selection input

Stop processes modifying the scanned checkpoints. Input hashes are checked.
Rerun the same command to reuse finished games. Cache identities include code,
runtime versions, delay, kickoff mode, and weights. Models are read-only.

Work grows as 50*N*(N-1)/2 games: 20 actors require 9,500 games. Use repeated
--include "repository/relative/*.pt" globs to restrict a long run. Other options:
--games-per-pair (positive even), --seconds, --seed, --report-dir, and --limit
(installation smoke only). Use forward slashes in include globs.

For per-model kickoff modes, map relative globs to "none" or "nexto_v4" in
ROUND_ROBIN_KICKOFFS.json and omit --all-scripted-kickoffs. Native/feedforward
actors use their own control tables. RocketSim enables RLBot delay. Kickoff pause
is an explicit simulator proxy, so this does not certify live behavior or rank.

Confirm leading native actors in continuous full matches:

.venv\Scripts\python.exe -u slater_mechanics_trainer.py compare --tournament "round_robin_reports/results_TIMESTAMP.json" --finalists 3 --seeds 8 --seconds 300

Replace TIMESTAMP with the actual report filename. The output defaults to
data/isolated/mechanics_comparison01.json. Matched full games compare common
rivals on both sides and provide a provisional native starting actor. Close or
inconclusive results call for fresh seeds or live offline matches.

If a feedforward actor leads the tournament it still leads the displayed ranking.
The native trainer recommendation explicitly picks only a compatible native actor;
feedforward weights cannot transfer into Nexto.

See SLATER_MECHANICS_README.md for the full selection/training workflow.
