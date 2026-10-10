MODEL TOURNAMENT v1 (READ-ONLY)
================================

INSTALL
Unzip all files into the original E:\Downloads\Chat_GPT_AI folder beside auto_league.py,
independent_nexto_benchmark.py, data\ and .venv\.
No existing project code is overwritten except if you previously added files under these SAME tournament filenames.

BEFORE RUNNING
1) Stop AUTO_1_START / AutoLeague with Ctrl+C and wait until it is stopped.
2) Keep your existing backups; preferably copy champion.pt and league_state.json to an external safe place.
3) Do not start a second trainer or modify checkpoints while evaluating.
4) You do NOT need Administrator permissions.

USAGE
MODEL_TOURNAMENT_0_LIST.bat : inventory every .pt file under data\ and distinguish native Nexto actors,
                              duplicates and other model formats; no simulator.
MODEL_TOURNAMENT_1_RUN.bat  : default tournament, screens all unique compatible native actors,
                              selects up to 8 semifinalists and 4 finalists, then 6 pairwise matchups.
MODEL_TOURNAMENT_2_THOROUGH.bat : much slower, more reliable larger episode counts.

MORE OPTIONS (PowerShell in project root):
.\.venv\Scripts\python.exe -u model_tournament.py --help
.\.venv\Scripts\python.exe -u model_tournament.py --list-only
.\.venv\Scripts\python.exe -u model_tournament.py --limit 20
.\.venv\Scripts\python.exe -u model_tournament.py --finalists 2

SEEDING & EVALUATION
Every model in a stage fights original unmodified Nexto from identical paired-seed scenarios;
we always evaluate both blue and orange sides. Early results are noisy and ONLY rank candidates
for progressively stronger tests. Each finalist is tested on a separate held-out seed and
fights every other finalist. A fresh original Nexto vs itself control is included.
Default: screening 16 first-goal episodes/model; semifinal 48/model; final 160/model;
each head-to-head 80 episodes. Thorough: 40, 120, 360, 200 episodes, respectively.
MAX_DECISIONS=750. THESE ARE NOT FULL FIVE-MINUTE ROCKET LEAGUE MATCHES.

REPORTS
model_tournament_reports\inventory.csv : EVERY scanned .pt file and duplicate source
model_tournament_reports\eval_cache.jsonl : each completed evaluation, to resume after interruption
model_tournament_reports\tournament_<time>.json : complete report
model_tournament_reports\tournament_<time>_leaderboard.csv : top 2-4 ranked finalist table

The final ranking heuristic weighs score vs original Nexto 65% and head-to-head score 35%.
This is a provisional ranking, NOT statistical proof of general superiority. Small score
margins should be considered a tie and retested with more matches or new evaluation seeds.

SUPPORTED / UNSUPPORTED
- Native Nexto actor checkpoints containing an 'actor' state dict that matches vendor/nexto/nexto-model.pt:
  champion, candidate, AutoLeague backups, rejected/inconclusive archives, native fine-tuning,
  any other compatible saved .pt checkpoints under data\.
- Older 92-feature student, imitation, PPO_POLICY.pt, and BC models may be listed as
  OTHER_FORMAT or OTHER_ARCHITECTURE and are NOT evaluated by this native tournament.
  Those need a proper observation/action adapter before fair mixed-architecture matches.
- A .pt file larger than 256 MiB is listed as TOO_LARGE and not opened by default.
  (Adjust via --max-checkpoint-mib only after verifying it is a model checkpoint.)
- Duplicate copies are deduplicated by SHA256 so identical champions/backups are not replayed.

SAFETY
Does not write under data\; all new output goes under model_tournament_reports\.
Never promotes, copies, deletes, or overwrites any model. The champion hash is checked
before and after simulations, and selected checkpoint hashes are rechecked.
If interrupted, restart with the SAME parameters: previous completed evaluations are reused.
Do not transfer tournament_results as training targets. First choose winners with evidence.

Upstream original/derived Nexto weight license: CC BY-NC-SA 4.0. Keep license/attribution.
