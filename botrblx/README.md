# Update271 Roblox bridge

Local freeplay inference: rendered Roblox state → update271 in Python → normal
Windows keyboard and mouse events. The model stays in your existing training
project; model weights, logs and recordings are not included in this folder.

## Download only this folder

[Download botrblx.zip](https://github.com/DMDIASSS/Chat_GPT_AI/raw/refs/heads/codex/native-quality-campaign/downloads/botrblx.zip)
contains only the `botrblx` folder, including the Python bridge, Lua clients,
launchers and templates. Extract it into `E:\Downloads\Chat_GPT_AI`, replacing
the existing folder's application files after stopping the bridge. Your existing
training environment and model stay in the project. This ZIP is stored separately
from full-repository archives and can be downloaded for bridge updates.

## JJSploit / WRD: file mode

The reported WRD HTTP request returned **403, Wrd Server Error: Connection
Failed**, without reaching Python. Loading Lua locally alone does not fix that:
telemetry also needs a working transport. File mode replaces HTTP entirely.
It requires working executor `readfile` and `writefile` functions.

1. Replace the complete `botrblx` folder in `E:\Downloads\Chat_GPT_AI` with this
   version. Stop the old bridge with Ctrl+C and close its Roblox panels.
2. Run **`START_FILE_BOT.bat`**. The first launch opens a folder picker.
   Select **JJSploit's workspace root**: the folder its `readfile` and `writefile`
   functions use. This is not automatically your training project folder.
3. Wait for **`READY FILE MODE v3`**. Python installs `botrblx_client.lua` in that
   workspace and creates its own `botrblx_exchange` subfolder. Keep Python open.
4. In freeplay, execute the complete **`JJSploit_File_Launch.lua`** file.
   It loads the installed Lua client from that workspace without a download.
5. The panel should show **Connected / PAUSED**, and Python should log
   **`CLIENT_HELLO`**. Then press **F6** to drive; **F8** stops inputs.

The folder choice is saved in local, ignored `file_connection.json`. To choose
again, run `START_FILE_BOT.bat --reset-workspace`. If the picker is unavailable,
use `START_FILE_BOT.bat --workspace "C:\path\to\executor\workspace"`.

If you do not know the workspace location, execute this file-function test:

```lua
writefile("botrblx_workspace_probe.txt", "botrblx workspace test")
```

Locate that file in your JJSploit installation/workspace and select its containing
folder. The script creates only that text file; it does not send controls.
`function function` from `print(type(readfile), type(writefile))` confirms the
functions exist, but the handshake above verifies the actual shared folder.

**File not found** in the launcher means the selected workspace differs from
the executor's workspace. A **No matching file reply** message includes the last
read/decode failure, a mismatched request ID, or another client's reply.
`CLIENT_HELLO` in Python confirms a request arrived; `FILE_REPLY: hello ... written`
confirms Python wrote the response. `FILE_REPLY_BLOCKED` reports an OS write error.
Look for `request.json` under `botrblx_exchange` and request-specific JSON replies
inside its `replies` subfolder. Do not paste full replies into a report because
they contain a local session token.

Version 3 publishes a separate reply file for each session/request ID. Once
published, its contents are not updated; a reader caching bytes by filename can
still obtain each new response from its new filename. Lua polls `readfile`
directly and retries missing/incomplete replies; existence metadata never gates
the read. Python retains the newest 16
replies and removes older ones; files held open by Windows are retried for cleanup.
The handshake can wait four seconds; the live-input timeout stays at 0.4 seconds.

**Upgrade both Python and Lua together for v3.** Stop the old bridge and close
its Roblox panel, replace the complete `botrblx` folder, restart the BAT, then
execute `JJSploit_File_Launch.lua` again. Older clients use one shared reply file
and cannot communicate with v3. Session and request-ID checks remain required;
an older reply never substitutes for the current response.

Client revision **v3.1** removes the `isfile` gate that could stop every read.
It is compatible with the running v3 Python bridge. Close the old bot panel and
execute the updated `JJSploit_File_Client.lua` directly to update only Lua; the
file launcher instead loads the client last installed by Python at startup.

File mode exchanges bounded JSON requests and replies, with per-client sessions,
fresh tokens, sequence checks and a stale-frame limit. It does not execute code
received from a request file. Python still performs inference and Windows input.
The Lua model is not embedded in the loader. No HTTP server is opened in this mode.

## HTTP mode (requires working localhost requests)

1. Update/download the complete `botrblx` folder into
   `E:\Downloads\Chat_GPT_AI\botrblx`.
2. Double-click `START_BOT.bat` and wait for `READY`. Keep its console open.
   It uses the project's existing `.venv`; no native rebuild is required.
3. Enter freeplay as `Deadline_coolgun` in place `101880234193261`.
4. Execute the contents of `JJSploit_Launch.lua` in JJSploit.
5. Close menus/chat and press **F6** to start or pause. **F8** stops inputs.

Copy the Lua file as plain text using GitHub **Raw**, your editor, or a code
block's Copy button. Do not include Markdown such as `**f**`, backtick fences,
or `[http://...](http://...)` in the executor; those are not Lua source.

`JJSploit_Launch.lua` first displays a **botrblx launcher** panel, then fetches
the client. Download, compilation and client-start errors stay visible in its
copyable text box. On successful startup, this panel closes and the main
**Update271** control panel remains. Execute the launcher file, not the Python
file or a browser's rendered text.

If the launcher reports **no response body**, the HTTP function did not return
usable source code. The adapter tries distinct `request` and `http_request`
functions and remembers the working one. It accepts raw body strings, common
response fields and APIs returning `(success, response)`. Failure messages show
the response type, field names/types, status and error message; header values
and session tokens are not printed. The same adapter handles live telemetry.

You can skip the code download completely: close the launcher panel, then open
`client271.lua` from this folder and execute its full contents directly in
JJSploit. That file is the standalone client and creates the main control panel.
It still needs an HTTP connection to Python for game state and model decisions;
an empty `/hello` or `/frame` reply is reported in that panel with the API details.

If the executor supports `readfile`, the launcher also tries the local workspace
paths `botrblx/client271.lua` and `client271.lua` after an HTTP download failure.
These paths refer to the executor's workspace, not the Python project directory.
Place the client there explicitly to use this optional local loading fallback.
`templates/http_compat.lua` is an internal source template, not an entry point.

Use the default bindings: WASD, Q/E air roll, Shift powerslide/free roll,
left mouse boost, right mouse jump. Disable mouse steering, pitch inversion
and aerial safety. Buttons hide during driving so injected boost clicks cannot
activate them; F6/F8 brings the controls back.

Focus loss and stalled telemetry release inputs and require Start again.
Goal/reset waits release inputs and resume when valid poses return.
Ctrl+C in the Python console exits and releases inputs.

## Files and startup errors

- `launcher.log` is created immediately, before Python is invoked. A missing
  interpreter or missing bridge/client file is reported here and in the console.
- `bridge.log` is created by Python before importing Torch/NumPy or loading the
  model. Dependency, checkpoint, or port errors are reported here.
- Neither log requires executing the JJSploit client first.

The Python console logs `CLIENT_DOWNLOAD` when the launcher requests `/client`
and `CLIENT_HELLO` when the Lua client connects. The read-only `/` and `/health`
routes return model/client status without starting, pausing, or reconfiguring
the bot. `model_loaded: true` with `client_connected: false` means Python is
ready but the Lua client has not begun streaming. Older versions returned
`Unknown route` at `/`; that response did not indicate a model-loading failure.

The launcher tries the checkout containing `botrblx`, then the existing
`E:\Downloads\Chat_GPT_AI` project. It also works when the whole folder is copied
elsewhere while that training project remains at its known path. An interpreter
path error in the old launcher meant Python never started, so there was no
`bridge.log` to inspect.

Optional overrides in Command Prompt:

```bat
set "BOTRBLX_PROJECT_ROOT=D:\MyFolder\Chat_GPT_AI"
set "BOTRBLX_PYTHON=D:\MyFolder\Chat_GPT_AI\.venv\Scripts\python.exe"
START_BOT.bat
```

The default checkpoint is
`data/isolated/mechanics_curriculum/selected7_mechanics01/update_000271.pt`
under the selected project root. The native checkpoint loader uses the existing
`vendor/nexto/nexto-model.pt` wrapper. Both native actor dictionaries and
TorchScript exports are supported. Checkpoints are read without modification.

To verify setup without sending inputs or opening the server:

```bat
START_BOT.bat --self-check
```

## Scope and validation

This adapter currently targets freeplay. Rendered-pose velocities and wheel/flip
state are estimates. Other cars are omitted and boost pads are masked because
their verified state is unavailable. WASD couples controller axes. These limits
can affect policy performance compared with Rocket League or the browser
extension; this is not a claim of equivalent match strength.

The client reads rendered poses and HUD values. HTTP mode posts JSON only to
`127.0.0.1:28771`; file mode uses the chosen local workspace instead.
Neither mode requires game modules or changes game remotes,
execution identity, or server code. The HTTP server binds only to loopback and
rejects browser origins; there is no external model service or API key.

Development checks use Python's standard unittest runner:

```sh
.venv/bin/python -m unittest discover -s botrblx/tests -v
```

Model/HTTP tests use temporary synthetic checkpoints. An additional integration
case exercises the bundled Nexto actor when that local asset exists. Set
`LUAU_BIN` to a Luau interpreter to run the mocked Roblox client cases; those
cases are explicitly skipped if Luau is unavailable. Windows/JJSploit execution
still requires validation on the user's PC.

`JJSploit_File_Client.lua` is a generated standalone copy of `client271.lua` with
`templates/file_transport.lua` substituted for the HTTP block. The installer
generates the same source when copying it to the executor workspace. The tests
check that both copies share the same telemetry and control code.
