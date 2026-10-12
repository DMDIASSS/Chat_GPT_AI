SLATER v0.3.4: INFERENCE / ACTION PARITY + SAFE RLBot v4 LIVE OBSERVATION CAPTURE
================================================================================
This package does NOT train, alter original checkpoints, overwrite bot models,
or claim identical TeamObserver vs NextoObsBuilder observations.

WHY THIS VERSION
Your RocketSim 16-seed five-minute benchmark ended 31/32 u60 wins (vs 7/32
original Cycle9), but the actual RLBot result was much less convincing. The
first necessary next step is to exclude wrong model export/deployment, action
lookup differences, and TorchScript inference differences. The second step is
to record the ACTUAL RLBot NextoObsBuilder input vectors for inspection.

FILES (extract into E:\Downloads\Chat_GPT_AI)
  slater_parity_v034.py
  slater_rlbot_copy_v034.py
  slater_rlbot_capture_v034.py
  slater_v034_tests/test_slater_v034.py
  SLATER_V034_PARITY_README.txt

STEP A: UNIT TESTS
  cd /d E:\Downloads\Chat_GPT_AI
  .venv\Scripts\python.exe -m pytest slater_v034_tests -q

STEP B: CHECK EXACT u60 WEIGHTS, LOOKUP TABLE AND SIMULATOR OBS INFERENCE
Find the actual folder containing your manually exported bot files. It needs
bot.py, agent.py, nexto_obs.py, bot.cfg and nexto-model.pt. Example:
  .venv\Scripts\python.exe slater_parity_v034.py ^
    --checkpoint data/isolated/slater_v027_campaign01_u0060.pt ^
    --exported data/isolated/slater_u60_RLBOT_nexto-model.pt ^
    --rlbot-dir "E:\PATH\TO\YOUR\SLATER_u60_BOT" ^
    --sim-seeds 3 ^
    --out data/isolated/v034_parity_first01.json

If your exported model lives under another name, replace --exported with the
actual .pt path. --exported must be the real TorchScript you installed.

Expected PASS status contains PASS_WEIGHTS_ACTIONS_AND_SIM_INPUT_INFERENCE,
with model_weights.identical=true, action_table.identical=true,
deployed_same_as_exported=true, and allclose_1e-5 for every test observation.
Report is create-only under data/isolated.

OPTIONAL NEXT0 OPPONENT FLAGS INSPECTION
  Add: --opponent-bot "E:\PATH\TO\ACTUAL\NEXTO\bot.py"
This only detects __init__ DEFAULT flags, not whether match configuration
changes them at runtime. Do not use the Slater/Cycle9 bot.py for this.

STEP C: MAKE A SEPARATE RLBot v4 COPY THAT LOGS REAL-GAME OBSERVATIONS
  .venv\Scripts\python.exe slater_rlbot_copy_v034.py ^
    --source-bot "E:\PATH\TO\YOUR\SLATER_u60_BOT" ^
    --out-bot data/isolated/slater_v034_livecapture_u60_01

Open RLBot v4 GUI, add the NEW bot from:
  E:\Downloads\Chat_GPT_AI\data\isolated\slater_v034_livecapture_u60_01\bot.cfg
Play 1v1 vs real Nexto, both sides ideally. The bot continues to use the
EXACT SAME neural-network decisions and model; logging occurs every 20
NN decisions, at most 50 files per RLBot process by default.
Live capture path:
  E:\Downloads\Chat_GPT_AI\data\isolated\slater_v034_livecapture_u60_01\capture_v034
No network upload. Stores anonymized game physics and policy features only.
Logging may slightly affect performance; use this for diagnostics, not
competitive FPS-sensitive win-rate evaluation.

STEP D: AUDIT ACTUAL RLBot OBS INFERENCE AGAINST TRAINED PPO WEIGHTS
  .venv\Scripts\python.exe slater_parity_v034.py ^
    --checkpoint data/isolated/slater_v027_campaign01_u0060.pt ^
    --exported data/isolated/slater_u60_RLBOT_nexto-model.pt ^
    --rlbot-dir "E:\PATH\TO\YOUR\SLATER_u60_BOT" ^
    --capture-dir data/isolated/slater_v034_livecapture_u60_01/capture_v034 ^
    --sim-seeds 3 ^
    --out data/isolated/v034_parity_live01.json

Send us BOTH v034 JSON reports, and if easy send a couple of capture_*.npz files.
Those results establish exact weight/action/inference parity on real RLBot
input vectors. They do NOT YET establish input SEMANTICS parity between
TeamObserver and NextoObsBuilder on the same physical state. That needs a
separate same-state conversion/fixture experiment. A PASS here makes that
next, harder problem worth isolating.

The validator deliberately exits 2 if weights/actions/outputs differ.
Do not change any baseline models or retrain u60 during these diagnostics.

IMPORTANT: the two terminal commands above for Step B and D use carets (^)
for CMD line continuation, not PowerShell. Or join onto a single line.

The duplicated bot.cfg gets a distinct display-name suffix [v034 capture],
so you can distinguish it from the real Slater in the RLBot GUI.
The live capture checks whether the selected 8-control vector matches the
90-action greedy table when beta==1; non-greedy decisions are labeled but not
compared to argmax.
