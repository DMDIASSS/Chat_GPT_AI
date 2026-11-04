# NovaForge v1.2 — mixed-bot training

**Continuous training and W&B:** see [WANDB_AND_CONTINUOUS.md](WANDB_AND_CONTINUOUS.md). After teacher/BC setup, run **17** once and use **18** for automatic start/resume until paused. Launchers 13/14 now request continuous online tracking. The CLI examples below remain finite unless `--forever` is added.

This update includes the Windows save fix and adds **Chronos and GalactusV2 simulator ports** alongside **Nexto neural, Ripple v1.1, latest self-play and historical self-play**. Pulsar is omitted because the intended bot/checkpoint has not been identified.

The project remains 1v1: each arena has one opposing car. Two workers can run different opponents concurrently, and the opponent is resampled after each episode. This gives variety within one training run without requiring many game instances or all bot networks to run simultaneously every step.

## Update an existing install

Extract the new ZIP into `Chat_GPT_AI`, allowing replacement of the NovaForge source files. Keep `.venv`, `assets`, datasets, models and runs. They are excluded from the ZIP. Core training keeps the existing dependencies; the optional W&B SDK is installed separately by launcher 17. Run `1_CHECK.bat` again; then follow the mixed-bot steps below.

For a fresh install, first follow steps 1–2 in [START_HERE.md](START_HERE.md).

## Mixed-bot launchers

1. **`10_MIXED_CHECK.bat`** downloads all four public bots, verifies hashes, runs the complete tests and teacher diagnostics, then runs a short real mixed-opponent PPO/save/resume smoke. Expected markers: `DOCTOR_PASS`, `SMOKE_PASS`, `MIXED_CHECK_PASS`.
2. **`11_MIXED_COLLECT.bat`** collects 40,000 teacher decisions against Nexto. The controlling teacher rotates among all four bots at episode boundaries. The dataset report records kept samples per teacher.
3. **`12_MIXED_PRETRAIN.bat`** trains the new student on that mixture, with episode-disjoint validation. It writes `models\mixed_bc.zip` and its BC report.
4. Run **`17_WANDB_SETUP.bat`** once, then **`18_START_OR_RESUME_WANDB.bat`** to start `diverse01` from that model and continue until paused. Alternatively **`13_MIXED_TRAIN.bat`** starts a fresh continuous run with online W&B and 100,000-decision segments.
5. Use **`14_MIXED_RESUME.bat`** to continue, **`15_MIXED_PAUSE.bat`** to request a saved stop, and **`16_MIXED_STATUS.bat`** for progress. These target `diverse01`; the original launchers 7–9 target `laptop01`.

Names are deliberately fresh. To rerun collection, BC or a new configuration, use new filenames/run names through the CLI; existing outputs are not replaced automatically.

## Opponent mixture

`configs\diverse.json` uses:

| Opponent type | Episode sampling weight |
| --- | ---: |
| Nexto neural | 12.5% |
| Ripple v1.1 | 12.5% |
| Chronos simulator port | 12.5% |
| GalactusV2 simulator port | 12.5% |
| Latest frozen student | 20% |
| Historical frozen students | 20% |
| Scripted baseline | 10% |

These are episode probabilities, not equal counts or equal wall-clock time. The frozen opponent stays fixed during the episode. `episodes.jsonl` records which one was used. Unknown/missing named models fail rather than silently using a different bot.

The two-worker/CPU preset remains appropriate as a starting point for your i5-10300H and 16 GB RAM. The extra networks use more CPU/RAM and download about 38 MB of additional weight files. If throughput is low, use a fresh run with `--workers 1` or reduce the native-bot weights in a copied config.

## CLI alternatives

```bat
.venv\Scripts\python.exe run.py fetch-teachers --names nexto,ripple,chronos,galactus
.venv\Scripts\python.exe run.py smoke --run mixed_smoke01 --config configs\diverse.json
.venv\Scripts\python.exe run.py collect --teacher nexto,ripple,chronos,galactus --opponent nexto --samples 40000 --out datasets\mixed40k.npz
.venv\Scripts\python.exe run.py pretrain --dataset datasets\mixed40k.npz --out models\mixed_bc.zip --epochs 5
.venv\Scripts\python.exe run.py train --run diverse01 --config configs\diverse.json --init models\mixed_bc.zip --steps 100000
```

If you already have a NovaForge student, you can skip new imitation training and initialize a **new** run with `--init models\ripple_bc.zip` or `--init runs\laptop01`. The new league preserves the student's existing observation/action contract. Existing runs resume with their saved configurations; use a new run to change the opponent pool.

Pause before evaluation, then compare against the starting model:

```bat
.venv\Scripts\python.exe run.py evaluate --model runs\diverse01 --baseline models\mixed_bc.zip --opponents nexto,ripple,chronos,galactus --pairs 10 --seconds 30 --out reports\diverse01_eval01.json
```

Look for improvement across opponents; a gain against one with losses against the others can indicate specialization. Timeouts remain separately reported. Repeat with fresh seeds before choosing a model for full offline RLBot matches.

## What was verified, and what remains

- Both native bots use their actual public `.lt` weights. The C++ archive's lack of a callable forward method is handled by reconstructing the published network and loading named parameters strictly.
- Python logits match the original C++ model loader/forward on the comparison fixtures. Feature construction, action masks and action-table ordering are compared against original C++ implementations on both teams across seven practice starts.
- The simulator now accepts per-physics-tick opponent controls. The native bots decide every eight ticks and apply the queued controls at tick seven; the student's four-tick windows no longer round that delay to four or eight.
- Mixture collection skips windows whose native teacher controls change partway through the student's four-tick action. It also filters incompatible action quantizations. This keeps retained labels consistent with the controls actually applied.
- Galactus uses a ball-only RocketSim forecast with five time samples and a 32-tick refresh. Feature parity covers the original external-prediction branch given identical samples. This does not establish equality between simulated forecasts and Rocket League's live predictions.
- RLGym's public car state lacks the world-contact normal used by the native turtled-car mask exception. That exception is unavailable in these ports. NumPy also supplies the player-slot randomization, so individual random choices differ from the C++ RNG.

These are tested interoperability ports with the limits above. Windows live-game timing, longer match strength and the benefit of the larger training mixture still need your testing. Their simulator scores should be labeled as ports rather than official stock-bot rankings.
