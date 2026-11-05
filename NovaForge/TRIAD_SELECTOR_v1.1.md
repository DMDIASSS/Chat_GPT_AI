# TriadBot v1.1: an options selector, body settings and simpler v5 exports

The missing INSTALL step explained the reported v1.0 startup failure; the user confirmed TriadBot works after installation. New **local** exports use the exporting Python environment immediately, so adding bot.bot.toml no longer requires creating another venv. On another PC, run INSTALL.bat and use bot.portable.bot.toml. Startup information/errors go to startup.log; DIAGNOSE.bat verifies the models without a game.

## Exact experts and body choices

The unchanged teacher lock pins Chronos (KingJake3113/Chronos, commit 4f8fdd27e4802d977b33b9ade4759ff6aeaca5aa), **GalactusV2** (SoldierDoge/GalactusV2, commit 217324c2fc516048effe0407595fa61c2ebc6863), and **Ripple v1.1** (Rolv-Arild/Ripple-RLBot, bots/v1.1/ripple-v1.1.onnx, commit 7ca4273a891ab1d04d001b48cb86f1bc8914aa85). Models are hash-verified and stay frozen.

Chronos's pinned loadout specifies **Breakout, car ID 22**. GalactusV2 uses **Octane, car ID 23**; Ripple's requested body is Octane. The simulation now assigns native bodies to frozen opponents. New Chronos/selector configs use Breakout. Existing saved Chronos configs without an explicit body continue to use Octane, preserving the learner's prior physics. Main Chronos export loadouts now record the selected body explicitly.

One live car must keep one hitbox for a match: selecting another controller cannot turn that car into Octane or Breakout. Triad defaults to **Breakout** and supplies a separate Octane TOML for random mode. The learned selector is trained/exported for one fixed body and rejects a selector file labeled for the other body. No fake per-teacher car geometry is fed into its observations.

## What “like Opti” means here

Public source [Kaiyotech/Opti at 6e0acc36](https://github.com/Kaiyotech/Opti/tree/6e0acc36d89a23c78ad61a7131c3fd779d0f5573) implements a selector policy over specialist submodels, with option scheduling and its own observation/action interface. The inspected files were learner_selector.py, Constants_selector.py and CoyoteParser.py. This project uses that hierarchy as a design reference; it does not redistribute Opti code or weights, reproduce its trained selector, or claim its 2v2/3v3 capability.

Our **1v1** selector is a separate small PPO actor/critic. Its action space is three choices: Chronos, GalactusV2 or Ripple v1.1. It observes the current situation, previous expert, remaining commitment time and fixed body. The chosen expert stays selected for **eight decisions (~0.53 seconds)**. Stored masks force that commitment during PPO training and live inference. Expert networks never enter the selector's optimizer.

The router preserves each expert's native eight control values, including Ripple's finer action table; it does not average their controls or quantize Ripple to 90 actions. The older single-network fusion experiment still uses its original probability projection. Triad retains the common seven-tick execution delay and Ripple held-control queue approximation, so exact native Ripple timing is still a transfer limitation.

The initial selector greedily chooses Chronos. There is **no pretrained winning selector** in the source ZIP. PPO trains selection decisions on goal/concede reward with potential shaping, against frozen opponents. W&B reuses the saved local login. This selector run currently uses frozen opponents; fusion01's separate PPO phase retains snapshot self-play.

## TriadBot launchers

Update both source folders, keeping environments/assets/runs. Close active RLBot processes before replacing their source files.

| Launcher in triadbot | Action |
| --- | --- |
| 0 | Check/download the exact three experts |
| 1 | Watch weighted-random routing |
| 2 | Export weighted-random v5 bot, with Breakout and Octane variants |
| 3 | Timed W/D/L comparison of random routing vs original Chronos |
| 4 | Start/resume selector01 PPO until paused or a guard stops it |
| 5 | Watch the **latest** selector being trained |
| 6 | Export the **retained champion** selector with all three experts |
| 7 | Compare latest vs initial selector using timed W/D/L |
| 8 | Pause selector training |
| 9 | Show selector status |

Run 0, then 4. Pause with 8 before 7. Both the latest actor and protected champion live under triadbot/runs/selector01. Until a candidate passes the automatic comparisons, launcher 6 exports the initial Chronos-only routing policy. Watch 5 to inspect learning, rather than assuming the champion has changed.

Checks every 131,072 decisions use timed W/D/L on both colors against four frozen bots, clustering mirrored starts. Promotion requires a favorable screen and a fresh confirmation set. Two clear negative sets or one large clear drop stop selector training; the champion remains exportable. These practical safeguards are not a formal guarantee of improved play. First train a short pilot and inspect W/D/L before leaving a long run.

## Validation

Core checks cover body assignment, committed action masks, PPO updates to the selector while expert tensors remain unchanged, selector export/load parity and wrong-body rejection, and stop-on-regression behavior. A loopback core test launches the **actual generated export through its TOML command without an export-local .venv**, exchanges ConnectionSettings/InitComplete, and receives controls from typed v5 packets. It exercises both random and selector modes. This is protocol testing, not a live Rocket League GUI match. The user has confirmed the previous random v5 runtime works after installation.
