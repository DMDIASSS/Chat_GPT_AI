# Update271 Roblox bridge

Local freeplay inference: rendered Roblox state → update271 in Python → normal
Windows keyboard and mouse events. The model stays in your existing training
project; model weights, logs and recordings are not included in this folder.

## Start on Windows

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

The client reads rendered poses and HUD values and posts JSON only to
`127.0.0.1:28771`. It does not require game modules or change game remotes,
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
