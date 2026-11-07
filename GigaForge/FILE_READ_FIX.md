# Native file-read diagnosis and compatibility fix

The uploaded report showed an existing executable, the correct expected release
hash, and a PermissionError while reading. No hash comparison was actually made.
Normal read permissions were displayed, and no matching Defender detection was
reported. Those facts do not identify the blocker or rule out another security app.

Merge this small update into Chat_GPT_AI. Close trainers and archive/extraction
windows, then run 16_CHECK_NATIVE_ACCESS.bat. This update preserves the executable,
release metadata, all runs, models and environments.

The checker first reads normally. If Python's file opening fails, it tries normal
Win32 read access with read/write/delete sharing. That can accommodate compatible
existing handles; it cannot override a lock, deny permission or security filter.
The complete contents must still match the expected SHA256 before any download
mark can be removed or the self-test started. No permission resets, elevation,
security exclusions or alternative executable locations are used.

If reading fails, HASH_MATCH says NOT_CHECKED. The report now includes the actual
Win32 error and registered antivirus display names where available.

- Error 32/33: another process holds the file open. Close extraction windows,
  trainers and viewers, then retry. A normal Windows restart can release stale
  handles; save your work first.
- Error 5 or another access/security error: review the listed security app alerts
  and share the updated native_access_report.json. The checker changes no file
  permissions or security settings.
- NATIVE_LAUNCH_PASS: run 9_VERIFY, then 3_START_OR_RESUME.
