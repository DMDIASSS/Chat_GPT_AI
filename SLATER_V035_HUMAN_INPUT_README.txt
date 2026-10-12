SLATER v0.3.5 — REAL HUMAN ROCKET LEAGUE CONTROLLER INPUT CAPTURE

PURPOSE
Record your own or a consenting GC2 friend's REAL game-resolved local
controller signals at ~120 Hz. The Input Bridge BakkesMod plugin streams these
signals from YOUR car. It works for keyboard+mouse as well as controller.
No global keyboard hook, no OS-level logging, no network beyond 127.0.0.1.

INSTALL INPUT BRIDGE
https://bakkesplugins.com/plugin/875
BakkesMod is required. Install and activate Input Bridge, then play in Freeplay.
The plugin exposes ws://127.0.0.1:49200 by default. It cannot retrieve remote
players' controls or recover controls from an existing replay.

INSTALL PYTHON CLIENT DEPENDENCY
cd /d E:\Downloads\Chat_GPT_AI
.venv\Scripts\python.exe -m pip install websockets

TEST
.venv\Scripts\python.exe -m pytest slater_v035_tests -q

RECORD (your friend runs this on the computer where THEY are driving)
.venv\Scripts\python.exe slater_human_input_v035.py record --seconds 120 --out data/isolated/human_demos/GC2_freeplay_01.jsonl

ANALYZE
.venv\Scripts\python.exe slater_human_input_v035.py analyze --input data/isolated/human_demos/GC2_freeplay_01.jsonl

NOTES
- The trainer needs paired observation/action samples to perform behavior
  cloning. Input Bridge records actions, own-car velocity/rotation/boost and
  dodge state; NOT ball position, other cars, all boost pads etc. Synchronize
  a second state-telemetry source or implement a combined BakkesMod plugin
  before interpreting this capture as a full training dataset.
- The existing 90-action Nexto table cannot represent all human mechanics
  precisely (especially diagonal jump + yaw). Any BC trainer needs an
  expanded/continuous action head or mechanic-specialist controller.
- This intentionally refuses to overwrite the same output file.
- Ask the driver for consent. Keep files private unless they agree to share.
- Suggested demos: 3-5 min each, varied ground approach, shadow defense,
  recoveries, aerials, power shots and kickoff speedflip sequences.
