# Native file-read checker update

[Download the small update](https://github.com/DMDIASSS/Chat_GPT_AI/raw/refs/heads/codex/novaforge-v1/downloads/GigaForge-File-Read-Fix.zip)

Close trainers and archive/extraction windows. Merge chat_gpt_ai into the existing folder, then run 16_CHECK_NATIVE_ACCESS.bat. The executable, release metadata, models, checkpoints and environments are preserved. This update retries ordinary read access with compatible Win32 sharing and reports the precise Windows error if access still fails. It does not override exclusive locks or permissions; the full release SHA256 must match before any unblock/self-test.

If NATIVE_LAUNCH_PASS appears, run 9_VERIFY, then 3_START_OR_RESUME. Errors 32/33 mean a file lock: close the holding app, or save work and restart Windows before retrying. Other read failures need the new native_access_report.json, which now includes exact Windows error codes and registered antivirus names where available.

[Details](GigaForge/FILE_READ_FIX.md) · [Passed Windows tests](https://github.com/DMDIASSS/Chat_GPT_AI/actions/runs/42371193730)

ZIP SHA256: `3e1aef7d5df0af9fde320ff24d6660eeb50945694519f53c64184f2433cf5665`.
