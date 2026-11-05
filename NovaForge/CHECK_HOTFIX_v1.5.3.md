# Windows viewer check hotfix v1.5.3

The reported output was 2 failed / 69 passed / 11 skipped. Both failures came from viewer tests:

- The mocked watch test acquired the installed project's real work/rlviser-watch.lock. An active watch session correctly held that lock, so the test failed before reaching its fake renderer. The test now uses its own temporary project root. A separate test verifies the real single-session guard still rejects a second watcher.
- The native UDP protocol check probed only the loopback interface without Windows exclusive socket ownership. That could succeed while a conflicting sender existed, then the Rust sender aborted when binding its wildcard port (Windows error 10048). Native socket integration now requires an explicit --viewer-udp flag; its preflight uses wildcard binds and SO_EXCLUSIVEADDRUSE on Windows. An exact bind conflict in the remaining close/rebind race is skipped; malformed packets and other native failures still fail the check.

## Install and proceed

1. Stop watching with Ctrl+C before merging the source update. Pause training with 22 if it is running.
2. Extract this ZIP into E:\Downloads (or the parent of your existing chat_gpt_ai folder), merging chat_gpt_ai/novaforge. Keep your .venv, assets and runs.
3. Run **1_CHECK.bat**. A skipped native UDP check is expected in the normal suite.
4. Once CHECK_PASS appears, run **32_UPGRADE_COPY_LEARNING.bat** if you have not upgraded copy02 yet. Running it again is a no-op.
5. Resume with **21_START_OR_RESUME_COPY.bat**. The saved student remains in place.

You do not need to reinstall PyTorch or reset the student for these errors. The v1.5.2 [learning correction](LEARNING_UPDATE_v1.5.2.md) remains included.

## Optional native protocol diagnostic

This is not required before training. Stop all watch/sender processes and close viewers first, then run from novaforge:

```bat
.venv\Scripts\python.exe -m pytest tests/test_viewer_protocol.py -q -rs --viewer-udp
```

It uses rlviser-py 0.6.14 to send actual FlatBuffers datagrams in a temporary folder. No viewer executable is provided there; a native stderr message about the missing ./rlviser.exe can appear without failing the packet test. Occupied ports skip the test rather than aborting the check. A narrow race remains because the native sender uses fixed ports and cannot inherit the preflight socket; normal training checks never invoke it.

## Verification

The old and fixed watch tests were compared while a separate process held the project lock: the old version failed and the fixed version passed. Local teacher-enabled checks pass (82 passed; the native UDP test is skipped by default). The explicit native protocol check passes separately; holding either fixed UDP port makes it skip safely. The GitHub Windows workflow additionally checks the core suite, real packet framing, and occupied-port behavior on windows-2022 / Python 3.11. Its result is separate from visual camera validation on the user's GPU.
