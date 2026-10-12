SLATER v0.3.6: REAL-RLBOT NEXTO KICKOFF ABLATION
===============================================

Purpose
-------
Our Slater u60 checkpoint beat the **greedy Nexto policy** 31/32 times in
RocketSim. The actual RLBot Nexto bot has other kickoff behavior that the
RocketSim evaluator did NOT implement. We need a controlled real-game test to
find out whether scripted kickoff and stochastic kickoff choices explain any
of the discrepancy. Do not deploy hardcoded kickoffs to Slater by default.

This package includes FOUR ready-to-select bot folders, derived from the
RLBotPack-master.zip supplied by the user. All use exactly the same Nexto
TorchScript checkpoint as the RocketSim test and the same original Nexto code
except for the two constructor flags, bot display name and a read-only logger.

Model SHA256 for all variants:
bf5343b5eeacac6bf7cdb75dac4a5c14ba0f94d820eae75f00a211b6119d69fa

Variant                  hardcoded    stochastic
Nexto_NN_Greedy           False        False       <- sim's Nexto policy mode
Nexto_NN_Stochastic       False        True        <- only stochastic during kickoff pause
Nexto_Script_Only         True         False       <- only hardcoded kickoff movement
Nexto_Stock               True         True        <- official default config

CAUTION: "sim's Nexto policy mode" means only action selection and kickoff
flags; RLBot NextoObsBuilder vs RocketSim TeamObserver are NOT established
identical. Identical opponent model does not imply identical game dynamics.

Install
-------
1. Extract this ZIP directly into E:\Downloads\Chat_GPT_AI without deleting
   or overwriting your original Slater or Nexto folders.
2. In Windows CMD:

   cd /d E:\Downloads\Chat_GPT_AI
   .venv\Scripts\python.exe -m pytest slater_v036_tests -q
   .venv\Scripts\python.exe slater_v036_build_verify.py

Expected: five tests passed, four V036_VERIFY_PASS rows, exact Nexto SHA.

Run matches (no need to choose bot.cfg)
---------------------------------------
Your launcher selects bot FOLDERS. Keep Slater at:
  data\rlbot_exports\V60

Select ONE Nexto opponent folder from these:
  data\rlbot_exports\slater_v036_nexto_modes\Nexto_NN_Greedy
  data\rlbot_exports\slater_v036_nexto_modes\Nexto_NN_Stochastic
  data\rlbot_exports\slater_v036_nexto_modes\Nexto_Script_Only
  data\rlbot_exports\slater_v036_nexto_modes\Nexto_Stock

Set normal 1v1 match, 5-minute game, no mutator acceleration, 120 FPS if
stable (VSync off), same arena/settings and Slater model for comparisons.

Suggested FIRST experiment: 1 match as Slater blue + 1 match as Slater
orange, against each of Greedy and Stock (4 matches). If results differ,
run 1 match per side against Stochastic and Script-Only (4 more). Repeat to
reduce randomness before strong conclusions.

IMPORTANT: The two bots must be on opposite teams. Do not run Nexto in
Rocket League competitive/online matchmaking. These are offline RLBot bots.

Logging
-------
The Nexto bots save unique .jsonl logs in their own folders, e.g.
  data\rlbot_exports\slater_v036_nexto_modes\Nexto_Stock\kickoff_logs_v036\

Log events: kickoff_start, occasional snapshots for up to 5 seconds after
kickoff, first_touch if GameTickPacket.latest_touch exposes a usable update,
score changes, match_end. There is NO injection or override of controllers.
Every run creates its own unique file; originals and old logs are retained.
Logger exceptions are reported and don't stop the bot. The log does not
record Slater's policy internals; Nexto's packet includes basic ball/car
state. Goal / win stats are only from completed matches.

After playing:
  .venv\Scripts\python.exe slater_v036_analyze.py --out data/isolated/v036_kickoff_ablation01.json

Upload v036_kickoff_ablation01.json and optionally the newest .jsonl per
variant. If report path already exists, use ...02.json. For missing match_end
signals, the summary explicitly marks that session as unfinished; note actual
final scores manually when sending the report.

Interpretation
--------------
If Greedy is much easier than Stock in actual RLBot, opponent kickoff config
is a strong suspect for u60's simulation-vs-game discrepancy. If all 4 are
similarly difficult, prioritize next phase: exact observations at equivalent
states, physics/action timing and learned mechanics. Avoid overinterpreting a
few games. Scores can depend on spawn location/first touch and opponent style.

No training. No model/checkpoint changes. No modification to Slater/V60.
Real RLBot integration and telemetry were NOT executable in our offline test
environment; static validation and mocked packets are covered by tests.
