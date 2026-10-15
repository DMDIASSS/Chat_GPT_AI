# Freestyle checkpoint exporter for RLBot v5

This exporter supports Freestyle reward-version-2 checkpoints with the original
512-feature observation schema and 94-action table. It exports the existing
actor and never trains, modifies or deletes its checkpoint. Nexto/update271
actors use a different architecture and are deliberately refused.

## Windows steps

1. Extract `Slater_Freestyle_RLBot_V5_Exporter.zip` into
   `E:\Downloads\Chat_GPT_AI`. No native rebuild is needed. Training may continue:
   the exporter selects a completed checkpoint and verifies it stayed unchanged.
2. Run `FREESTYLE_EXPORT_V5.bat`, or use **Export RLBot v5** in the Freestyle app.
   Choose run `freestyle_rewards02`, update `latest` or a saved number such as
   `600`. Scripted kickoff is enabled by default; uncheck it for learned controls.
3. The exporter opens a new folder under `data\rlbot_v5_exports\`. It contains
   the actual callable network `policy.pt`, `bot.toml`, runtime code and
   `EXPORT_INFO.json`. A ZIP is also produced alongside the folder.
4. Run the exported folder's **INSTALL.bat** once. It creates its own `.venv`,
   installs `rlbot==2.0.0b56` (the RLBot v5 SDK) and reads Torch from your existing
   project installation. It does not upgrade or replace the training environment.
   Installation exercises the exported bot on 48 synthetic packets and writes
   `diagnostic.json`. Keep the original project Python installation available.
5. In RLBot v5, use its local-bot import/add action to select the exported
   **bot.toml**. Select the bot in a standard Soccar match. Use the Octane loadout
   included with the export and the standard gravity/physics settings.

Run `DIAGNOSE.bat` in the exported folder if startup or controls fail. This test
does not connect to Rocket League; inspect the actual RLBot logs for live errors.
Re-extracting a ZIP does not include its installed `.venv`; run INSTALL.bat after
extracting the exported bot ZIP. Installation is local to this PC and reuses the
project Python/Torch path recorded during export. It is not a standalone EXE.

For direct commands:

```bat
cd /d E:\Downloads\Chat_GPT_AI
.venv\Scripts\python.exe -u export_freestyle_rlbot_v5.py --run freestyle_rewards02 --update 600 --name Freestyle600
.venv\Scripts\python.exe -u export_freestyle_rlbot_v5.py --run freestyle_rewards02 --update 600 --name Freestyle600_Learned --learned-kickoff
.venv\Scripts\python.exe export_freestyle_rlbot_v5.py --run freestyle_rewards02 --list
```

`--checkpoint` accepts a completed checkpoint folder or its `POLICY.lt`, within
the chosen run. Unsaved updates are refused instead of silently substituted.
Exports are given unique names by default; an explicit existing name is refused.

## Runtime contract and limits

The model runs on CPU with one Torch thread. RLBot v5 supplies locations,
orientations, velocities, per-player touches, actual last controls, jump/dodge
flags and remaining dodge availability. Boost pad locations are matched to the
native canonical order; RLBot's elapsed pickup timer is converted to the
remaining cooldown used in training. Orange perspective, other-car ordering,
action masks, four-tick decisions and one-tick input delay match the training
contract. Use 120 physics packets per second where possible.

The ten privileged wheel/contact/reset features are zero with the visibility
mask disabled, matching training's optional-feature dropout path. They are not
invented from ball proximity. Ordinary jump timers and mechanic-history features
are reconstructed from observable packets; they are not exact simulator internals.
History uses the checkpoint's stage/difficulty and reward timing settings, and
restarts its logical 12-second episode context (or the configured duration)
without teleporting the real car. This approximation can affect behaviour.

The independent, basic scripted kickoff chooses one taker per team, steers to
the ball and uses a bounded front-flip sequence. It hands back to the policy
when play begins and the ball moves. It is not the Nexto kickoff. Toggle
`scripted_kickoff` in `runtime.json` to change it without retraining.

The adapter accepts 1..6 cars on the standard 34-pad Soccar layout. The current
Freestyle model learned solo mechanic drills; match strength and team play are
unverified. Exporting it does not grant abilities it has not learned.

## Validation and upstream references

The exporter strictly transfers all parameter tensors, adds a callable forward
method to the native archive's architecture, and reloads the result. Every
export checks logits and masked actions on 96 test inputs and retains source
and output hashes. Optional native reference tests compile against the original
GigaLearn/RLGym C++ implementation and compare all 512 observations, all 94
controls/masks, native logits and selected actions over 96 states, both teams
and rosters up to six cars. Actual v5 FlatBuffers packet tests cover action
timing, replay handling, kickoff handoff, cooldown mapping and jump resources.

Cloud validation exercised SDK installation and the exported bot's actual
initialize/get_output path with real v5 packet serialization. It did not run
Rocket League or the Windows launcher; those require a live test on the PC.

API references reviewed:

- [Official RLBot Python interface](https://github.com/RLBot/python-interface),
  revision `8a0850f20ff647d933566fb31cf060d87ab5ec35`.
- [Official Python example](https://github.com/RLBot/python-example), for the
  `Bot.initialize/get_output` API and `bot.toml` launch format.
- [RLBot SDK 2.0.0b56](https://pypi.org/project/rlbot/2.0.0b56/) and
  [FlatBuffers 0.19.0](https://pypi.org/project/rlbot-flatbuffers/0.19.0/).
