# Chat GPT AI — Camera + Tactical Balance + RLBot Export v1

This is an **overlay**. Unzip into the original `E:\Downloads\Chat_GPT_AI` directory. It adds files, but does not replace any training code or models.

## 1. Rocket League-style camera (optional browser viewer)

Run `CAMERA_1_CYCLE09.bat` for Cycle 9 vs original Nexto, or `CAMERA_2_CHAMPION.bat` for champion vs Nexto. The viewer should open in your browser at `http://127.0.0.1:8765/` (or 8766 for champion). Keep its CMD window open; press Ctrl+C there to stop. No elevated/Admin rights needed.

* `C`: ball-cam on/off, `Tab`: select blue/orange, `1`/`2`: team, `H`: hide settings.
* Change distance, height, camera angle, FOV and stiffness with live sliders. Settings are saved in your browser.
* The physics are the same RocketSim states as the source bot; the visuals are **stylized 3D**, not the actual Rocket League assets. RLViser is **not changed**. This is a supplementary alternative when adjustable camera settings matter.
* The viewer uses a local HTTP server **bound to 127.0.0.1 only**; no remote connections, external JS or telemetry.
* The model decisions and camera rendering use the original project's Python packages. If startup fails, paste the entire terminal output. Do not run as administrator.

## 2. Tactical balance experiment (experimental PPO, not a gameplay override)

What it does: reward sensible boost pickup only when reserve is actually low and goal danger is low; tiny penalty for clearly pointless boost use near supersonic speed; tiny reward for redirecting a real goal threat after touching the ball; tiny penalty for our touches that create an immediate own-goal threat. The existing strong reward/penalty for goals remains. This does **not** force defensive positioning, forbid high-risk challenges or waste boost by overriding the policy. All new signals are small, heuristic proxies and may fail to improve real performance.

It uses Cycle 9 SHA256 `50f34d4a3723...`, copies its policy parameters, starts a separate PPO critic and uses the **existing AutoLeague training loop** with a strong KL anchor to Cycle 9. General offense/finishing and grounded/defense scenarios are mixed to reduce forgetting. The original Cycle 9 checkpoint, AutoLeague champion and AutoLeague state are never intentionally overwritten.

**Pause/stop ALL other AutoLeague, AFK v2, and Finishing Lab training before running training or diagnostics**. Then:

1. `BALANCE_0_CHECK.bat`: one real RocketSim physics and inference preflight. No weights changed.
2. `BALANCE_1_SMOKE.bat`: tiny independent training and evaluator smoke test. Saves only under `data\tactical_balance_smoke`.
3. `BALANCE_2_TRAIN.bat`: conservative 8192-decision experiment. Resumable at PPO rollout checkpoint boundaries using the same command.
4. `BALANCE_3_EVAL.bat`: read-only comparison with original Nexto and Cycle 9.

Outputs: `data\tactical_balance\candidate.pt`, `progress.json`, `reports\*.json`. **No automatic promotion**. Before promoting, compare on a larger held-out set, replay observed gameplay, general shooting tests, defense, and kickoff quality; reject regressions. The usual model gate is just an initial screen, not a final go/no-go verdict.

## 3. RLBot export

`RLBOT_0_EXPORT_CYCLE09.bat` exports the **current Cycle 9 native checkpoint** to `data\rlbot_exports\ChatGPT_AI_Cycle09`, including `bot.cfg`, upstream game adapter and independent TorchScript weights. `RLBOT_1_EXPORT_BALANCE.bat` exports the tactical candidate, if trained.

This is a **RLBot v4 (legacy)** bot package, based on the original Necto project's RLBot v4 adapter. It is **NOT compatible directly with RLBot v5** (`bot.toml` / the v5 Python API). To try it you need a working, separately configured RLBot v4 environment and `rlgym-compat`; modern Python may require a separate older compatible interpreter. For a production RLBot v5 export, we need to adapt the v5 NectoFamily runtime and test it in an actual RLBot v5 installation.

The exported directory uses a modified native policy; no training data, critics, optimizer states, or other saved weights are transferred. No original `.pt` model is overwritten, and a repeated export with the same name refuses to overwrite. You can manually archive the export folder if desired.

The original Nexto model and derived work are under **CC BY-NC-SA 4.0**; preserve attribution, don't commercialize without appropriate permissions, and follow the RLBot rules. Run only through RLBot-supported offline/private matches—not ranked online matchmaking. RLBot v5's public botpack also has a competitive skill ceiling around Nexto.

## Tests and limitations

10 automated unit/integration tests passed locally, including an actual TorchScript export-and-reload round-trip using unmodified original Nexto weights. JavaScript syntax also passed (`node --check`). We cannot run the full RLBot game, browser against live RocketSim or PPO on this computer because RLBot/RLGym/RocketSim aren't installed. **Use the preflight and smoke-test launchers before a long experiment.** Do not treat offline unit tests as proof a new policy plays better.
