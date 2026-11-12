# RocketHive v4.15 replay BC + live hive search

[Download the in-place update](https://github.com/DMDIASSS/Chat_GPT_AI/raw/refs/heads/codex/novaforge-v1/downloads/RocketHive_v4_15_REPLAY_BC_LIVE_HIVE_IN_PLACE.zip)

Extract directly into the existing RocketHive project folder and open V415_MENU.bat. Existing configs, model weights, replay data, saved keys, and the ML environment are preserved. Full instructions are in README_V4_15_REPLAY_BC_LIVE_HIVE.md inside the ZIP.

The new path learns 32-tick reconstructed replay controls with four learned residual codebooks and an autoregressive proposal/value model. Search runs during live play: 12–64 joint teammate proposals, then three conditional modal continuations. Opponents are simulated from current state, without reading their actual selected plan. Dedicated team workers run asynchronously, reject expired plans, and reuse the exporting ML Python for RLBot. A separate RocketSimVis GUI environment avoids downgrading the ML NumPy installation.

No pretrained strong replay brain is bundled. Without one, the controller visibly runs a geometric/native-search diagnostic. Reconstruction/diversity/value gates are not match-strength proof.

SHA256: `d2b19a87a3b9f9da9b907d4c7ce28c0ab9cc6150f2c910d2e9443357aa004cde` (358316 bytes).

Local checks: 166 tests; actual native 1v1/2v2/3v3 rollouts; separate asynchronous 2v2 workers; actual X11/OpenGL RocketSimVis rendering live UDP simulation frames; short training/optimizer-resume fixture; export construction. Windows CI verifies this exact archive and the source/controller tests. No actual Windows Rocket League match or stronger-bot result is claimed.
