Car Soccer AI Trainer v4.2 - local model imports + scripted kickoffs
===================================================================

INSTALL THE CODE PATCH (GitHub download)
1. Close/disable the old extension while replacing its code.
2. Extract the code patch directly into your EXISTING v4.1 extension folder,
   replacing the included files. Keep its existing nexto-weights.bin.
3. Double-click START_MODEL_IMPORT.bat. It uses your Slater .venv and, when
   available, prepares G9 from the exact u0073 checkpoint you supplied:
   E:\Downloads\Chat_GPT_AI\data\isolated\v041_overnight\overnight01\trials\g00009_leader_small_2\g00009_leader_small_2_u0073.pt
   Keep this console open when importing .pt/.zip models.
4. chrome://extensions -> Reload your extension. Alternatively Load unpacked
   and choose this folder. Disable any other versions of the trainer.
5. Open car-soccer.com -> extension popup -> Enable + reload.
6. In the popup choose G9 u0073, Original Nexto, or import your own model file.
7. Join a team, choose the selected Nexto model in the in-game trainer, and
   press Give Control. F8 restores your original controls.

FULL ZIP (local download)
The full ZIP includes original Nexto weights and converted G9 u0073 weights.
Extract it to a separate folder and Load unpacked. Run START_MODEL_IMPORT.bat
only when importing PyTorch .pt/.zip files. Built-in G9 and .bin imports need
no Python server.

IMPORTING YOUR PC MODELS
- .pt: compatible native Nexto TorchScript, full PPO checkpoints containing
  actor, or matching raw/state_dict/model_state_dict actor tensors.
- .zip: an RLBot export containing .pt files. Learned/scripted variants of the
  same actor are deduplicated. A ZIP with different actors asks you to select
  the individual checkpoint instead of guessing.
- .bin: native browser weight layout (1,776,128 bytes). No converter required.
- Other architectures, including unrelated feedforward/ONNX models, require
  their own observation/action adapters and are rejected clearly.

Use the file picker in the extension popup. PyTorch/ZIP conversion happens
through the local Python helper at 127.0.0.1:8765. Files are converted in memory
on your PC; nothing is uploaded to a remote server. Models are never overwritten.
One imported model is saved in Chrome extension storage and survives popup/tab
reopening. Importing another replaces that saved browser copy; PC originals stay
intact. Failed validation leaves the previous model selected.

Changing models restores player control and discards the old worker. Press Give
Control again. Grand Champion is a separate native fallback, not the imported
model. The in-game display shows the loaded imported model's name.

SCRIPTED KICKOFFS
Always enabled for the selected Nexto/G9/imported actor. The exact standard
168-tick Nexto action sequence runs in the game runtime, outside async neural
inference, so stage boundaries and jump pulses are not rounded to 8-tick requests.
Old neural replies cannot overwrite the scripted controls. The imported neural
policy resumes when the ball moves or the script ends. Airborne center-ball
starts do not trigger the kickoff. Closest teammate takes kickoff, with left-side
priority on ties. The debug panel shows ON (waiting) / ACTIVE.

Car Soccer does not expose RLBot's authoritative kickoff-pause packet. Its
center-ball kickoff detection is a simulation-specific approximation. It does
not establish parity with Rocket League or guarantee the same playing strength.

The original multiplayer input expression is preserved until manual takeover;
room creation and joining use the existing v4.1 architecture. F8 remains the
emergency override. Live site patching still depends on the site's bundle
signatures; if it reports a signature mismatch, stop and provide the error.

Checks are documented in TEST_REPORT.txt. Live Car Soccer and WebRTC play must
still be tested locally. Only model compatibility, inference equivalence,
runtime control behavior, and the import UI were validated here.
