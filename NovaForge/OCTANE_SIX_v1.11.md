# Six frozen experts, fixed Octane

This is a new selector06 experiment, not an in-place conversion of selector04. Expert order is Chronos, Galactus V2, local frozen Fusion, Ducky, Rain 1v1, Megabyte. Ripple is excluded from its experts, opponents and export. Previous three/four-way projects still work. The gate has 240 inputs and six choices, so the old 236-input gate cannot be resumed into it.

Every learner condition uses Octane in training, diagnostics, watching and the RLBot v5 loadout. An individual car keeps the same hitbox when experts change. Opponent original Chronos retains Breakout; the new bots, Galactus, Nexto and the frozen Fusion opponent use Octane. Choosing Octane is the requested experiment, not a verified claim that every expert becomes stronger on it.

Pause selector04 with 19 and wait for its saving console to finish. Stop watch consoles, then copy the ZIP's chat_gpt_ai/novaforge and chat_gpt_ai/triadbot folders into the existing Chat_GPT_AI, replacing program files. Keep .venv, assets, runs and exports. No dependency reinstall is needed.

| Launcher in triadbot | Action |
| --- | --- |
| 26_CREATE_OCTANE_SIX | Verify/download about 32 MB of new model assets; copy the exact frozen Fusion from selector04; create selector06 |
| 27_TRAIN_OCTANE_SIX | Start/resume the new selector with W&B using the existing SDK login |
| 28_PAUSE_OCTANE_SIX | Request a pause; wait for 27 to finish saving |
| 29_WATCH_OCTANE_SIX | Watch latest on Octane; print active expert and true gate probabilities |
| 30_DIAGNOSE_OCTANE_SIX | After pausing, compare latest and all six fixed experts in 98 short, matched games |
| 31_EXPORT_OCTANE_SIX_V5 | Export retained champion and all six frozen experts, with Octane loadout |
| 32_REPORT_OCTANE_SIX | Shareable research report including latest six-expert diagnostics |

Run 26 once, then 27. For an initial sanity check, pause after one saved 32768-decision segment with 28, run 29, then 30. Share the selector06_six_diagnostics_*.zip from triadbot/reports before leaving a long run. A new gate starts from zero and is biased toward Fusion, so the initial greedy champion uses the preserved Fusion. This is an initialization choice, not a claim of a stronger trained selector. The source ZIP contains no saved user models; selector04 must be present locally.

Training continues until paused or the regression guard stops it. All six expert networks stay frozen; only the selector/critic train. Seven equally weighted frozen opponents are Chronos, Galactus, Nexto, Ducky, Rain, Megabyte and the same local Fusion. This run does not add selector snapshot self-play or team play. The source Fusion's earlier refinement/self-play remains a separate workflow.

The existing goal/potential-v2 reward is retained: goals plus discount-consistent field/distance shaping, once per eight-tick transition. Two-tick simulation batches preserve that eight-tick reward and timeout boundary. Automatic greedy W/D/L checks run after 131072 additional decisions since the last completed guard check: 112 games (seven opponents, both colors, four pairs, candidate/champion), with 112 fresh confirmation games only if promising. Promotion requires confirmation; regression stops protect the retained champion. Wall time depends on hardware and episodes. Pausing during an evaluation can leave no completed check.

Exports go to triadbot/exports. On this PC import bot.bot.toml immediately; it uses the exporting Python installation. On a different PC run the exported INSTALL.bat and import bot.portable.bot.toml. Models remain separate .lt archives plus the owned Fusion/selector .pt actors; TOML launches their Python runtime. This is not one weight-merged model. The v5 export has a fixed Octane loadout for both team colors.

Implementation and practical limits:

- Rain uses its 231-input 1v1 checkpoint, six-tick query period and five-tick planned delay. Chronos/Fusion/Galactus/Ducky/Megabyte use eight/seven. The simulator's extra one-tick input delay remains enabled. Only the selected expert is inferred; switching cancels outgoing pending controls and holds actual controls until the incoming command is due.
- Ducky uses its 295-input DuckyObs_V2_01 layout and 512/512/512/256 policy. Its native V3 ball-prediction backend is unavailable in this runtime; installed RocketSim predicts the requested .3/1/3-second ball samples instead. Native playing-strength parity is not established.
- Megabyte is neural, with a 233-input ByteObs and shared/policy networks. Its external difficulty manipulation, temperature controller and scripted kickoff helper are omitted. The new adapters use deterministic full-strength neural actions. Earlier training also omitted external scripted kickoffs.
- Rain's goal feature convention and legacy boost timer order, Byte's legacy timer order and slot shuffling, and Ducky's local features/pad scoring are preserved. C++ observation and network fixtures test both colors and seven scenarios. C++/NumPy shuffle streams need not be identical.
- The public state lacks world-contact normals for the original turtle jump masks. Demo respawns still contain native randomness. Short simulator tests and a TCP handshake do not establish live playing strength. Actual RLViser graphics and full RLBot matches require user testing.
- The gate observes game/context features, not a new learned team coordinator. Runtime and training remain 1v1.

Additional model/source URLs and hashes are stored in extra_teachers.lock.json, separate from the original lock so old selector checksums remain valid. Downloads preserve upstream readmes and the Megabyte license. No original new model weights or C++ source are bundled in the public source ZIP.
