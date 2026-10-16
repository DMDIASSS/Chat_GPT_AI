AFK Improved scripted kickoff export update

Close the AFK Improved desktop app before extracting.
Extract this ZIP directly into E:\Downloads\Chat_GPT_AI and replace included files.
Open AFK_IMPROVED_DESKTOP.vbs. In the Viewer tab, find RLBot export.
Browse to your native actor .pt checkpoint. Leave Scripted Nexto kickoff checked.
Export selected model to RLBot v4 and choose a new folder name.
Exports are written to data\rlbot_exports\NAME. Add bot.cfg to RLBot v4.
Keep the complete exported folder: the script is in bot.py, not the weights.
Raw update checkpoints can be exported but are not necessarily validated improvements.
Training configs/checkpoints are not included or overwritten by this patch.

Validation: desktop export command wiring checked for selected/original with
scripted kickoffs ON/OFF; real TorchScript export roundtrip passed.
Windows launcher and live Rocket League gameplay require local verification.
