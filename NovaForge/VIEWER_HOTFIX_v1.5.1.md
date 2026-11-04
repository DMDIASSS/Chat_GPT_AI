# Fix the RLViser oversized memory-allocation crash

The v1.5 camera build used RLViser's newer FlatBuffers protocol, while the project's pinned `rlviser-py==0.6.13` still emitted legacy packets. A legacy packet header could be interpreted as an enormous allocation length, producing `memory allocation of 72057594037927944 bytes failed`. This was an integration bug in the update, not a request for additional PC RAM.

## Update

1. Close the failed viewing console and all open RLViser windows.
2. Merge the v1.5.1 ZIP's `chat_gpt_ai/novaforge` into your project. Keep your environment, assets and runs.
3. Run **31_SETUP_RLVISER.bat**. It installs `rlviser-py==0.6.14` into NovaForge's own environment before importing the native sender. The checked camera executable is reused.
4. Run **1_CHECK.bat**, then **24_WATCH_COPY.bat**.
5. Continue your existing `copy02` using **21** when ready.

Manual equivalent from Command Prompt inside `novaforge`:

```bat
.venv\Scripts\python.exe -m pip install --only-binary=:all: --no-deps rlviser-py==0.6.14
.venv\Scripts\python.exe run.py viewer-setup
```

Automatic watch/setup checks the sender version and updates it before the DLL is loaded. If an incompatible DLL is already loaded, the process stops with restart instructions before streaming. Fresh installs pin the matching sender in requirements. Manual viewer mode bypasses these checks and is intended for externally managed compatible viewers.

Regression coverage captures real native Connection/GameState/Quit UDP datagrams without a GUI and validates their length prefixes and FlatBuffer message tags. Windows visual rendering still needs confirmation on the user's GPU. The camera executable's SHA256 remains valid; the fix is the sender/version pairing.
