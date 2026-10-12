# Slater v0.3.6t: TAS input extractor (offline, read-only source)

The 6 `.data` files you supplied appear to be Rocket League TAS input sequences. This is **not** an observation dataset, and it is **not** model weights. The parser uses the identical validated binary structure for all 6 files:

- bytes 0..3: little-endian unsigned version `1`
- bytes 4..7: little-endian unsigned frame count
- each recorded frame: 32 bytes = little-endian unsigned 32-bit raw button flags + 7 little-endian float32 channels
- final 128 bytes: preserved opaque binary trailer, probably saved setup state. Exact fields are **not verified**.

All six files have the exact expected file length and all channels are finite and between -1 and 1. The CSVs retain input records; the manifest retains the raw trailer bytes and SHA-256. **We have not verified the analog channel ordering, button-bit meanings or playback tick rate.** The file names, including `2 player tas`, do not establish two independent streams in this format.

## Use in your Windows project

Unzip into `E:\Downloads\Chat_GPT_AI`. The `data\isolated\v036t_tas_converted\` directory already contains converted CSVs and a manifest; nothing runs automatically and no checkpoints are changed.

To convert another directory of `.data` TAS files, run:

```bat
cd /d E:\Downloads\Chat_GPT_AI
.venv\Scripts\python.exe -m pytest slater_v036t_tests -q
.venv\Scripts\python.exe slater_tas_decoder_v036t.py --input-dir "E:\Folder\With\TAS" --out-dir data/isolated/v036t_my_new_tas_01
```

The target directory **must not exist**. Never overwrite prior experiments.

## Next research stage (not implemented here)

1. Confirm that Blaku TAS Plugin v1 exposes the same raw `ControllerInput` field ordering, button-bit mapping and ticks per second; validate a known 1-second throttle + jump recording.
2. Recover correct controlled action vectors and saved initial car/ball state; replay in a controlled RLBot or RocketSim scenario. Verify final pose and touch event. Compare positive examples against idle/boost-only baselines.
3. Expand the 90-action space or train a continuous-input mechanics head if the recorded inputs cannot be represented discretely. Avoid teaching policy to imitate a wrong nearest discrete action.
4. With aligned physics observations, train a **gated** mechanic rather than copy an open-loop sequence into every kickoff. Include success/failure and recovery gating. Validate independently on actual RLBot matches.

### Caveats

TAS files may be perfectly executed and potentially superhuman mechanics, not GC2-level tactics. A flip reset demonstration does not teach when to attempt a flip reset. Training from TAS alone cannot learn bump positioning, defense or fake-kickoff recognition because the files do not provide opponent observations and feedback. Do not pass the `.data` files directly into a PPO checkpoint loader.
