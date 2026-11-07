# Windows refused to start the native executable

WinError 5 from CreateProcess happens before the native program starts. The traceback alone cannot distinguish a downloaded-file block, security product, application-control policy or file/folder permissions. It is not a model/checkpoint problem.

Merge this update's chat_gpt_ai/gigaforge files into the existing folder. Run 16_CHECK_NATIVE_ACCESS.bat. It checks native/GigaForge.exe against the published hash in native_release.json, inspects file permissions and matching Windows Security detection records, and writes native_access_report.json. It removes the download-zone mark only from a hash-verified executable, and stops if it finds a matching Windows Security detection. It then attempts the research self-test using the selected Torch/Python runtime DLL paths.

If it prints NATIVE_LAUNCH_PASS, run 9_VERIFY.bat, then 3_START_OR_RESUME.bat. If access is still denied, share native_access_report.json and check Windows Security Protection history and the executable's Properties/Security tab. If the file is missing, unreadable or has a different hash, re-extract the native folder from the verified research ZIP. Preserve runs, models and environments.

This repair does not elevate to administrator, disable antivirus, add exclusions, reset permissions, move execution to another location or modify training data. A security-policy block may require a local diagnosis and cannot be guaranteed fixable by this patch.
