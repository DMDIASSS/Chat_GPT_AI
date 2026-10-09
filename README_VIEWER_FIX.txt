CHAT GPT AI - Viewer repair, 2026-10-09

Copy these files into E:\Downloads\Chat_GPT_AI (beside train.py), replacing WATCH_LATEST_AI.bat and watch_latest_ai.py if asked.
No checkpoints are modified. The code is inference only.

1) WATCH_LATEST_AI.bat: newest saved trained checkpoint by file-modification time (may be weak distilled student V2).
2) WATCH_NATIVE_NEXTO_SELFPLAY.bat: original Nexto vs itself (strong baseline).
3) WATCH_NATIVE_TUNED_SELFPLAY.bat: fine-tuned native Nexto vs itself, ONLY if data\native_nexto\last.pt exists.
4) WATCH_CURRENT_PPO_SELFPLAY.bat: highest checkpoint in active data\checkpoints\chat_gpt_ai.
5) WATCH_STUDENT_V2_SELFPLAY.bat: latest distilled student; NOT equivalent to Nexto.

Unlike the old WATCH_LATEST_AI.bat, launchers no longer run a silent import check / pip installation / viewer EXE download. Your old PPO viewer already worked, proving the RLViser dependencies are installed. Errors and exact checkpoint paths stay visible in the command window.

PowerShell diagnostics if viewer fails:
  cd E:\Downloads\Chat_GPT_AI
  .\.venv\Scripts\python.exe -u watch_latest_ai.py --model student --actions sample --show-every 15
Copy the FIRST traceback and SELECTED CHECKPOINT lines; do not paste private tokens.

Native baseline you posted: 6-6 with 8 draws and 2042 versus 2046 touches. This is a parity test of ORIGINAL Nexto weights, not a Nexto-beating trained model. The 120000 PPO checkpoint is merely the highest step in the currently active PPO directory; your previous million-step checkpoints may have been moved to a backup during fresh training.

If a viewer binary must be started separately, launch the same rlviser.exe that your working WATCH_LATEST_PPO.bat uses. Avoid replacing that binary with an incompatible release.
