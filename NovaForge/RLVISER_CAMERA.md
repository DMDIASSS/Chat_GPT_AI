# Automatic RLViser with the learner's ball camera

Run **24_WATCH_COPY.bat** after pausing copying with **22**. RLViser is found and opened automatically on the first simulator frame. **Ctrl+C** stops viewing and sends the viewer its quit signal.

The search starts at **`chat_gpt_ai\rlviser.exe`**, then checks common names in the project and viewer folders. The earlier `rilviser.exe` spelling is accepted too. An explicit `--viewer-exe` path is available for unusual locations.

The camera build requires **rlviser-py 0.6.14**. Setup checks/updates that sender before importing its native extension. If you saw an enormous memory-allocation error with v1.5, follow [the protocol hotfix](VIEWER_HOTFIX_v1.5.1.md).

## Camera preset

- Horizontal FOV **110°**, adapted to the window aspect ratio.
- Camera distance **270**, height **100**, pitch offset **−4°**.
- **Ball cam enabled**, following the learner rather than the opponent.
- Fixed world-up camera with **no added camera shake**; packet interpolation enabled.
- The viewer starts with its menu closed. **Esc** opens the menu.

The pitch is an offset while tracking the ball, so the view naturally tilts as the ball moves. This is an RLViser camera preset, not a reproduction of every detail of Rocket League's camera spring/zoom model.

Stock RLViser v0.9.3 hard-codes its geometry and does not expose these numeric controls. NovaForge therefore installs a small camera-only modification of the pinned MIT-licensed RLViser release. The first automatic setup downloads its checked Windows executable once (about 52 MiB). The original viewer in `chat_gpt_ai` is preserved; a compatible local executable is prepared at `novaforge\rlviser.exe` for rlviser-py's built-in first-frame launcher. An old local viewer/settings file is backed up under `viewer\backups` before replacement.

The download URL and SHA256 are pinned in `viewer.lock.json`. A bad download is never installed. If the download is unavailable but your existing viewer is present, NovaForge can use the stock viewer with ballcam/follow and explicitly reports that the full numeric preset could not be applied.

## Controls and alternatives

**31_SETUP_RLVISER.bat** performs the same discovery/download/configuration ahead of time. Launcher 24 does this itself, so setup 31 is optional.

From Command Prompt inside `novaforge`:

```bat
.venv\Scripts\python.exe run.py watch --model runs\copy02 --config runs\copy02\config.json --opponent nexto --scenario kickoff
.venv\Scripts\python.exe run.py viewer-setup --exe ..\rlviser.exe
```

To use only the existing stock viewer, without downloading the camera build:

```bat
.venv\Scripts\python.exe run.py watch --model runs\copy02 --config runs\copy02\config.json --viewer-mode existing
```

`--viewer-mode manual` skips NovaForge setup for externally managed viewers; rlviser-py's ordinary launcher behavior still applies. Automatic camera-build installation currently targets Windows x64. Close an old manually opened viewer before the first upgrade if Windows reports its executable is in use.

Only one watch session per project is allowed, preventing two NovaForge watchers from fighting over the UDP port. Rendered car ID 1 is always the learner, including orange-side and reordered-state starts. Camera settings affect viewing, not policy observations or training rewards.

Upstream: [VirxEC/rlviser](https://github.com/VirxEC/rlviser/tree/a4e524085cdb1601cf9c0af2f815591fb696db54), MIT license included at [viewer/RLVISER_LICENSE.txt](viewer/RLVISER_LICENSE.txt). The camera patch is in [viewer/patch_rlviser.py](viewer/patch_rlviser.py). Actual visual inspection on the user's Windows/GPU remains part of testing.
