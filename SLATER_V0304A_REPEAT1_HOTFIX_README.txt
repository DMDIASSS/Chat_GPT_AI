SLATER v0.3.0.4a: ONE-REPEAT BENCHMARK CLI HOTFIX

WHY: v0.3.0.4 evaluator already supports repeats=1 internally, but CLI incorrectly demanded 2-5.
This patch permits 1-5 repeats and leaves all other match, worker, SHA and report rules intact.

Extract slater_stochastic_benchmark_v0304a.py into E:\Downloads\Chat_GPT_AI.
Keep the original v0304 script unchanged.

TESTS:
  .venv\Scripts\python.exe -m pytest slater_v0304a_tests -q

RUN 16 *INDEPENDENT* KICKOFF SEEDS, ONE TRIAL PER SIDE AND POLICY:
  .venv\Scripts\python.exe slater_stochastic_benchmark_v0304a.py --checkpoint data/isolated/slater_v027_campaign01_u0060.pt --seeds 16 --repeats 1 --seed 1700420699 --regulation-seconds 300 --overtime-seconds 120 --out data/isolated/v0304a_fullmatch_u60_16seeds01.json

This schedules 16 seeds x 1 repeat x 2 sides x 2 policies = 64 matches.
Do not use an output path that already exists; output creation is create-only.

VERIFY LIMITATIONS:
 - Read-only versus models, only creates .json report.
 - Not a real RLBot game; no evidence yet of 90% in RLBot.
 - Repeated kickoff patterns after goals need independent inspection.
 - Offline mocked tests cannot verify real Windows RocketSim behavior.
