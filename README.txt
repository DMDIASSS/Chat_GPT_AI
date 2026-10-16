IMPORTANT v4.2.7 BUG FIX
------------------------
- Fixed popup init crash (three missing DOM constants in v4.2.6).
- Empty model dropdown and stuck Checking... were caused by that crash.
- This version has NO connection to 127.0.0.1 and DOES NOT need a BAT file.
- Close any old cmd importer window. If it starts automatically on Windows,
  remove the old Windows Startup entry: press Win+R, run shell:startup,
  and delete CarSoccerModelImporter.vbs if present.
- If any popup still says "Check .pt importer" or "START_MODEL_IMPORT.bat",
  that popup belongs to an older installed extension or installation folder.
- In chrome://extensions verify the version is 4.2.7 and disable old copies.

CAR SOCCER AI TRAINER v4.2.7 — DIRECT .PT UPLOAD (NO BAT)
========================================================

What's new
----------
- Upload compatible .pt, .zip, or .bin models directly from the extension popup.
- Entire conversion runs inside your browser. No local Python server, BAT, command prompt, or network upload.
- Supports standard native Nexto PyTorch ZIP state_dict checkpoints and TorchScript .pt files.
- Supports .zip exports containing one or more identical compatible .pt models.
- Rejects incompatible actor architectures with a clear explanation; this runner expects the native Nexto 44-tensor actor. Generic PyTorch models won't work without an architecture adapter.
- Keeps the v4.2.5 F7 in-game model picker, model rename, saving, and switching.
- Keeps the previously tested Car Soccer physics compatibility patches.

Update/install
--------------
1. Quit the Car Soccer tab.
2. IMPORTANT: Unzip these files into the EXISTING unpacked extension folder,
   replacing code files without deleting your current .bin weight files.
   Moving to a new folder or installing as a separate extension may change
   the Chrome extension ID and isolate your previously saved imported models.
3. Go to chrome://extensions, and click Reload on the existing extension.
4. Open car-soccer.com, select Enable + reload in the extension popup.
5. Use '+ Upload a model...' in the popup. Select your .pt, .zip or .bin file.
   Import and name your model; the file is converted and saved locally.
6. In-game, press F7 to release cursor lock and open the model picker.
   Select the model and press Give Control. F8 returns control to you.

Restore Original Nexto
----------------------
- The code-only ZIP does NOT include copyrighted/third-party original trained weight binaries.
- To restore the Original Nexto slot, click 'Install Original Nexto weights...'
  and choose a compatible native Nexto .pt or .bin checkpoint.
- If the original nexto-weights.bin was already in your existing extension folder,
  you can leave it there; no import is needed.
- If G9 u0073 previously worked via g9-weights.bin, retain that file too.
- You may still import either model as a custom named model.

Supported model data
--------------------
- .bin: exactly 1,776,128 bytes / 444,032 finite float32 values in Nexto layout.
- .pt: standard PyTorch ZIP serialized state_dict or TorchScript module
  containing all 44 expected tensors with the native Nexto shapes.
- .zip: standard ZIP export containing compatible .pt files; the importer
  rejects different actors in the same archive to prevent silent mis-selection.
- Original ZIP checkpoints up to 256 MiB; uncompressed archive safety limit 512 MiB.
- This is not a generic PyTorch interpreter; legacy pickle-only .pt, custom
  architectures, certain Python-specific serialization methods, and other
  tensor layouts may not be compatible.
- Files remain on your PC; the extension does not send model bytes to an API.

Troubleshooting
---------------
- Error 'Incompatible model architecture': your model's tensors don't match
  the native Nexto 44-tensor actor. Upload the .pt in chat for further adapter work.
- Error 'Not a supported PyTorch ZIP archive': model uses a legacy format or is not a standard ZIP-based PyTorch save.
- Error 'Missing weights for ...': reimport the .pt/.bin through the popup.
- Error 'Failed to fetch' for Original Nexto: install its weights through the
  popup or restore nexto-weights.bin to the existing extension folder.
- If the game updates and the patcher reports a hook mismatch, provide the
  latest main-*.js bundle from the Network panel; direct upload is separate.
- The old auto-importer BAT is NO LONGER USED by this extension. If you set up
  the old Windows startup entry you may remove it with the prior
  REMOVE_AUTO_IMPORTER.bat file from the old version.

Testing
-------
The .pt reader was tested against torch.save(state_dict), torch.jit.trace
TorchScript, float16 checkpoints, dict-wrapped checkpoints, deflated .pt
archives and compressed .zip exports. Output matched the existing Python
converter byte-for-byte for all samples. Model storage, restore and game
patch synthetic tests pass on the supplied game bundles. Actual gameplay
and the user's individual checkpoint are not tested in this environment.
