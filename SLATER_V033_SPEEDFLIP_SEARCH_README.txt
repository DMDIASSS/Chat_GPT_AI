SLATER v0.3.3 -- A PHYSICS-SEARCH EXPERIMENT, NOT A NEW BOT
============================================================
Purpose: automate search for speedflip-style 120 Hz control sequences instead
of trying to teach the restricted 90-action Nexto policy an impossible action.

1. Extract the package into E:\Downloads\Chat_GPT_AI
2. cd /d E:\Downloads\Chat_GPT_AI
3. .venv\Scripts\python.exe -m pytest slater_v033_tests -q
4. Run 24-trial integration pass (real RocketSim required):
   .venv\Scripts\python.exe slater_speedflip_search_v033.py --trials 24 --train-seeds 2 --holdout-seeds 3 --out data/isolated/v033_speedflip_smoke01.json
5. If that works, use 128 new trials / more training seeds:
   .venv\Scripts\python.exe slater_speedflip_search_v033.py --trials 128 --train-seeds 4 --holdout-seeds 5 --seed 20261012 --out data/isolated/v033_speedflip_search02.json

This uses ONE RocketSim car on the field; it does NOT run a trained opponent.
The optimizer tunes jump timing, diagonal dodge, pitch cancellation, and roll.
It compares forward progress with ordinary boosting (matched kickoff seed).
To pass HOLDOUT VALIDATION, the car must exceed pure boost by >=35 uu at 2s,
be on the wheels, face forward, remain upright, and have >=1400 uu/s forward
speed, on EVERY previously unused validation seed.

This is NOT proof of an optimal speedflip; it is an experimental macro search.
If none passes, the output says UNVALIDATED_EXPERIMENT -- don't deploy it.
The search has not been tested on your installed RocketSim; only offline
logic is tested. It does not edit ANY model checkpoint or installed RLBot bot.

IMPORTANT:
* Existing v0.3.1 kickoff u40 has NOT shown better Nexto kickoff win rate.
* This report is not a new TorchScript actor / RLBot executable skill.
* We must eventually add a timed skill controller to training AND RLBot,
  and test real 1v1 kickoff collisions and fake kickoffs.
* 2v2 and 1v2 need later team-aware training, not this tool alone.
