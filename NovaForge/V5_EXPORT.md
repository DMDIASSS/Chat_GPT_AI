# Export your student as .lt + .bot.toml for RLBot v5

Run **25_EXPORT_COPY.bat** for the best frozen-teacher copying student, or **29_EXPORT_DIVERSE_V5.bat** for your earlier `diverse01` policy. Pause the corresponding trainer first and wait for its save/exit.

Each export creates:

```text
novaforge/exports/<bot-version>/
    policy.lt
    policy.lt.json
    bot.bot.toml
    bot.py
    README.txt
```

A matching ZIP is created beside the bot folder. The `.lt` is a **LibTorch-readable TorchScript archive** containing the complete student's actor. Export loads/reserializes the model and checks its logits; it does not merely change a filename. `bot.py` supplies the NovaForge observations, action mapping and live packet timing. The TOML tells RLBot how to launch it.

## Import and compare

1. Open the [RLBot v5 GUI](https://rlbot.org/).
2. Add the **printed `exports\...\bot.bot.toml`** path. Keep its `.lt`, metadata and Python launcher together in that folder.
3. Select your exported student on one team, and an installed v5 version of Chronos, Galactus, Ripple or Nexto on the other.
4. Start an **offline 1v1**. Alternate team colors and play several full matches.
5. Export again after more training to create a separately named version. Earlier exports are preserved.

The generated bot uses the enclosing NovaForge `.venv` and adapter. Keep it at `novaforge\exports\<bot-version>`. On another PC, install NovaForge there and extract the bot ZIP into its `exports` folder. The package does not bundle Python or Rocket League.

## Export any NovaForge checkpoint

From Command Prompt inside `novaforge`:

```bat
.venv\Scripts\python.exe run.py export-v5 --model runs\copy02 --name "My Teacher Copy"
.venv\Scripts\python.exe run.py export-v5 --model runs\diverse01 --name "My PPO Bot"
.venv\Scripts\python.exe run.py export-v5 --model models\mixed_bc.zip --name "My BC Bot"
```

Run folders resolve to their published checkpoint. For the copying mode this is the published student selected using kickoff monitoring and copying loss, while resume restores the most recent optimizer state.

## Convert an exported actor

Launcher **28_PT_TO_TOML.bat** accepts a dragged `.pt` file or opens a file picker. Its default output is now **`.lt` + `.bot.toml` + runtime**, matching this workflow:

```bat
.venv\Scripts\python.exe run.py pt-to-toml rlbot\policy.pt --name "Imported Student"
```

It supports NovaForge's exported 100-feature / 276-action TorchScript actors. A bare actor missing its metadata requires `--assume-novaforge`, explicitly declaring those feature/action meanings. See [PT_TO_TOML.md](PT_TO_TOML.md) for details. Other architectures and raw state dictionaries need their original model/observation/action code.

## About the other bots' .lt files

RLBot v5 does not require every bot to use the same weight format. Chronos/Galactus `.lt` files are native LibTorch module archives used with their specific architectures, feature builders and compiled launchers. NovaForge exports a LibTorch TorchScript actor with its own v5 adapter. These can compete in the same RLBot match, but their weight files cannot be swapped into each other's executables. A `.toml` file alone cannot supply an absent network or adapter.

Simulator/export parity is tested. Actual Windows RLBot gameplay and timing still need verification on the user's PC.
