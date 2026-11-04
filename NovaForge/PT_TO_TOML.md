# Package a NovaForge actor for RLBot v5

The primary workflow is now **[.lt + .bot.toml export](V5_EXPORT.md)**: launcher **25** exports the frozen-teacher student, and **29** exports `diverse01`. Each includes the Python live adapter and a ZIP package.

**28_PT_TO_TOML.bat** accepts an already-exported `.pt` actor through a file picker or drag/drop. Its default output is `policy.lt`, metadata, `bot.bot.toml`, `bot.py`, README and a ZIP under `exports`. Keep the generated folder inside `novaforge/exports`.

Supported input is NovaForge's TorchScript actor: 100 NovaForge features in, 276 action logits out, with the same action ordering/timing. It does not convert another bot's arbitrary state dictionary or feature representation. Original Nexto or Chronos/Galactus weights need their own architectures and adapters.

From Command Prompt inside `novaforge`:

```bat
.venv\Scripts\python.exe run.py pt-to-toml rlbot\policy.pt --name "My Teacher Copy"
```

For a bare actor genuinely trained with NovaForge features/actions, declare the missing metadata contract explicitly:

```bat
.venv\Scripts\python.exe run.py pt-to-toml "C:\models\my_actor.pt" --name "My Bot" --assume-novaforge
```

That flag cannot infer feature meanings or convert a different architecture. A present sidecar must pass contract/hash checks. To retain a `.pt` weight archive instead of the default `.lt`, add `--weights-format pt`.

The `.lt` output is reserialized as a LibTorch-readable TorchScript archive and checked for logit parity. It is used by the included NovaForge adapter; it is not a replacement for the teachers' native network files. Add the generated `.bot.toml` in the RLBot v5 GUI and play an offline 1v1. Existing packages are preserved across repeated conversions.
