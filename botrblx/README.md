# Update271 Roblox adapter

## Local Lua mode: remove the file round trip

**Use this mode for JJSploit/WRD.** The supplied diagnostic measured 1.2–1.3
seconds per file exchange. Local mode runs the actual two-block attention policy
inside Lua and sends inputs with the executor's keyboard/mouse functions. There
is no file exchange, HTTP request, or Python process during driving.

1. Close the old Roblox bot panel and stop `START_FILE_BOT.bat` with Ctrl+C.
2. Extract the [folder-only ZIP](https://github.com/DMDIASSS/Chat_GPT_AI/raw/refs/heads/codex/native-quality-campaign/downloads/botrblx.zip)
   into `E:\Downloads\Chat_GPT_AI`, replacing `botrblx` application files.
3. Double-click **`EXPORT_LOCAL_BOT.bat`** once. It reads the existing update271
   with the project's existing Python, exports all policy weights at float32
   precision, and installs **`botrblx_standalone.lua`** in the saved JJSploit
   workspace. Wait for **`READY STANDALONE`**. You can then close CMD.
4. In freeplay, execute:

   ```lua
   loadstring(readfile("botrblx_standalone.lua"))()
   ```

5. Wait for **`LOCAL v2 ready | model self-test passed`**, then press **F6**.
   The first start briefly tests W/A/S/D/Q/E/Shift and chooses a keyboard method
   only when Roblox observes both keydown and keyup for every key. Then it drives.
   **F6** pauses and **F8** stops and releases the inputs. Keep default controls:
   WASD, Q/E air roll, LMB boost, RMB jump, Shift powerslide. Disable mouse
   steering, pitch inversion, and aerial safety.

The generated file is the complete standalone bot, including your model. It is
also saved as `botrblx\botrblx_standalone.lua`. **Keep it private:** it contains
your model weights. It is ignored by Git and excluded from the public download.
The download contains the exporter and runtime source, not anyone's weights.
Re-export only when changing the model or updating this runtime.

The panel reports inference time, executor input-call time, actual decisions per
second, the keyboard method, requested keys, and keyboard keys Roblox actually
sees. Requested keys alone are not proof that an executor delivered them.
It targets 15 decisions/second and samples
poses at up to 30 Hz. Startup runs four saved PyTorch reference cases and refuses
to drive if local logits/actions differ or inference exceeds 200 ms. F8, focus
loss, chat, invalid poses, missing boost HUD, and errors release owned inputs.
Goal/reset waits resume after valid car/ball poses return.

This removes the measured file-transfer delay; inference and frame/input timing
still take time. The cloud Luau interpreter averaged about 10 ms/inference with
the supplied actor, matching all four reference actions within 0.000016 maximum
absolute logit error. This is **not** a Windows/JJSploit speed measurement. The
runtime checks and panel report the result on your PC. No executor input was
sent during cloud validation.

This version also fixes the float attention mask: unavailable boost pads now
receive **-10000**, rather than **+1**, in the Python bridge. Local mode omits
those masked rows, which is checked against the complete PyTorch observation.
Neither change retrains the model. Car/ball physics differ from Rocket League;
wheel/flip state is still estimated, and other cars and pad availability remain
unverified. Start with freeplay when judging the improvement.

Local mode requires `mouse1press`, `mouse1release`, `mouse2press`, `mouse2release`,
and Roblox's buffer API. Keyboard v2 first tests normal Roblox enum key events;
if those are disallowed or ineffective it tests executor `keypress`/`keyrelease`
with virtual-key and scan-code mappings. Shift uses generic VK_SHIFT (0x10)
in the virtual-key mapping. No thread identity or game-module access is changed.
If no method changes observable key state, it stays paused with the failure
reason. A later silent keyboard failure stops the bot and requires a retest.
Keep Roblox focused, chat closed, and release physical movement keys during the
brief test. F8 cancels and releases test inputs. A passed test verifies Roblox's
input state; it does not prove that custom game controls use those inputs.

Missing functions are named in the panel. Loading the script does not press keys;
the keyboard test starts only with F6/the Start button. It reads rendered poses and HUD
values; it does not require game modules or change execution identity/remotes.

Optional exporter overrides:

```bat
EXPORT_LOCAL_BOT.bat --workspace "C:\Users\almas\AppData\Roaming\jjsploit\workspace"
EXPORT_LOCAL_BOT.bat --model "D:\Models\update.pt"
```

## External bridge modes (fallback)

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

## One-shot connection diagnostic

For file errors, run this before changing the transport again:

1. Close the bot panel and stop the bridge CMD with Ctrl+C.
2. Double-click **`DIAGNOSE.bat`** in the updated `botrblx` folder. It uses the
   saved workspace or `%APPDATA%\jjsploit\workspace`. Wait for **`READY DIAGNOSTIC`**.
3. Execute this in JJSploit:

   ```lua
   loadstring(readfile("botrblx_diagnose.lua"))()
   ```

4. Wait for **`DIAGNOSTIC COMPLETE`** in CMD. Send the single file
   **`botrblx\DIAGNOSTIC_REPORT.txt`**. The Lua tests normally take about 10–30
   seconds; CMD allows five minutes for launching the script and transferring it.

If loading the installed script fails, open
`C:\Users\almas\AppData\Roaming\jjsploit\workspace\botrblx_diagnose.lua` in
Notepad and execute its complete contents. That is the configured script;
`JJSploit_Diagnose.lua` in this folder is its source template.

The tool tests flat and nested paths, `/` and `\`, short and long filenames,
file/directory metadata, Python-created versus Lua-created files, overwrite
visibility, immutable replies, two fresh generations and timing. It records API
errors individually and compares them with Python's actual filesystem view.
It does not import Torch, run the model, load game modules or send game inputs.
Only dedicated diagnostic files are written and cleaned up; the report remains
on your PC. It contains source fingerprints and test outcomes, with credentials
redacted and live mailbox contents excluded.

If report export fails, the Roblox panel keeps a copyable report: click its text,
Ctrl+A, Ctrl+C. CMD also saves a partial report on timeout or Ctrl+C. Optional
workspace override: `DIAGNOSE.bat --workspace "C:\path\to\workspace"`.

## JJSploit / WRD: file mode

### Normal start (WRD compatibility profile)

1. Stop old bridge/diagnostic CMD windows and close old bot panels. Extract the
   folder-only ZIP into `E:\Downloads\Chat_GPT_AI`, replacing the application files.
2. Double-click **`START_FILE_BOT.bat`**. It reuses the saved workspace or finds
   `%APPDATA%\jjsploit\workspace` automatically. Wait for **`READY FILE MODE v3.2 WRD`**.
3. In freeplay, execute `loadstring(readfile("botrblx_client.lua"))()` in JJSploit.
4. Press **F6** to start/pause; **F8** stops Windows inputs immediately.

The supplied diagnostic measured working paths with **1.2–1.3 second file round
trips**. Client v3.2 waits four seconds for a response, and file-mode input expiry
is three seconds. Focus loss, F8 and Ctrl+C still release inputs immediately;
duplicate requests do not refresh expiry. Pose sampling runs independently on
Heartbeat, so a slow reply does not invalidate every car/ball velocity sample.
The panel displays link latency separately from model inference time.

This profile fixes the measured timeouts; it cannot remove WRD's underlying
transfer delay. Reaction speed is limited by that delay. HTTP mode keeps its
0.4-second telemetry expiry and still requires a working localhost API.

The reported WRD HTTP request returned **403, Wrd Server Error: Connection
Failed**, without reaching Python. Loading Lua locally alone does not fix that:
telemetry also needs a working transport. File mode replaces HTTP entirely.
It requires working executor `readfile` and `writefile` functions.

1. Replace the complete `botrblx` folder in `E:\Downloads\Chat_GPT_AI` with this
   version. Stop the old bridge with Ctrl+C and close its Roblox panels.
2. Run **`START_FILE_BOT.bat`**. The first launch opens a folder picker.
   Select **JJSploit's workspace root**: the folder its `readfile` and `writefile`
   functions use. This is not automatically your training project folder.
3. Wait for **`READY FILE MODE v3.2 WRD`**. Python installs `botrblx_client.lua` in that
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
Reply waits are four seconds; file-mode telemetry expires after three seconds.

**Upgrade both Python and Lua together for v3.** Stop the old bridge and close
its Roblox panel, replace the complete `botrblx` folder, restart the BAT, then
execute `JJSploit_File_Launch.lua` again. Older clients use one shared reply file
and cannot communicate with v3. Session and request-ID checks remain required;
an older reply never substitutes for the current response.

Client revision **v3.2** includes the measured-delay profile and independent sampling;
it also removes the `isfile` gate that could stop every read.
Update Python and Lua together for the WRD compatibility profile. Restarting
`START_FILE_BOT.bat` installs the matching client in the executor workspace;
the file launcher loads that installed copy.

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
