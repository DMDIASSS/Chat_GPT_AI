# Slater v0.3.7a — PyTorch teacher hotfix + TAS mixed-folder recovery

**Status:** local offline regression tested (21 tests across v037a, v037, v036t). **RocketSim PPO not runnable here** because the Windows project-specific `rlgym`, `afk_team_research`, and checkpoints are not installed in the build container. No physical win-rate guarantees. No training checkpoints have been created by this patch.

Two NEW filenames, keeping existing v037 and v036t scripts untouched:
- `slater_nexto_kickoff_v037a.py`: v037 clone with fresh independent TorchScript teacher, no `deepcopy(actor)` and no `requires_grad_(False)` on non-leaf teacher parameters; explicit source/teacher equality and storage independence checks. Old Nexto script 168-tick lookup is byte-for-byte unchanged. PPO teacher is outside optimizer and inferred under `torch.no_grad()` as already implemented in v025 `base.update`. Outputs are create-only. A caution field was added to benchmark JSON.
- `slater_tas_decoder_v036t2.py`: mixed-directory TAS parser. Exports only verified nonempty v1 frames; records a SHA256 and concrete reason for every unsupported/zero-frame file in `manifest.json` under `skipped`. All inputs remain unchanged. If all files fail validation, refuses output and prints reasons. All outputs create-only.
- `slater_v037a_tests/test_hotfix.py`: six local regression tests.

## Run

Extract ZIP directly into `E:\Downloads\Chat_GPT_AI`. Keep the original files.

```bat
cd /d E:\Downloads\Chat_GPT_AI
.venv\Scripts\python.exe -m pytest slater_v037a_tests -q
.venv\Scripts\python.exe -m pytest slater_v037_tests slater_v036t_tests -q
```

### TAS mixed directory recovery

Your `data\tas` exists, but at least one file starts with binary header `version=1, frames=0`. This cannot be treated as a demonstration. Original v036t aborted on it. The patched scanner exports other recognized frames and logs the bad file in `manifest.json` instead:

```bat
.venv\Scripts\python.exe slater_tas_decoder_v036t2.py --input-dir data/tas --out-dir data/isolated/v036t2_tas_recovery01
```

If this reports `No supported nonempty .data files`, no useful raw TAS frames were found in that folder. Your already converted six files can be used for analysis, but they remain `not_training_ready`: button-bit / analog semantics and saved initial states are still unverified.

### First longer scripted Nexto ablation

The user's earlier **180-decision / 12-second** comparison produced eight pure-NN timeouts; its scripted portion was limited (Cycle 9 2/4 wins, u60 0/4). That does **not** identify a better real-match bot. Try a new, larger but still short *first-goal* evaluation:

```bat
.venv\Scripts\python.exe slater_nexto_kickoff_v037a.py benchmark --from-checkpoint data/isolated/slater_v027_campaign01_u0060.pt --seeds 4 --episode-steps 600 --seed 20261013 --out data/isolated/v037a_scripted_600steps01.json
```

`600` decisions = 40s of physics, 4 seeds x 2 sides x 2 opponents x 2 policies = 32 episodes. This remains a **single-goal/timeout** evaluation, not five-minute match evaluation; high timeout percentage means the experiment remains underpowered.

### Optional: smoke PPO after benchmark, not a real training campaign

Only if the longer benchmark successfully confirms nonzero scripted decisions and the setup is behaving reasonably, run a **separate, never-reused** isolated experiment name:

```bat
.venv\Scripts\python.exe slater_nexto_kickoff_v037a.py train --from-checkpoint data/isolated/slater_v027_campaign01_u0060.pt --updates 2 --rollout-steps 512 --max-episode-steps 600 --checkpoint-every 2 --eval-seeds 2 --eval-steps 600 --seed 20261013 --run v037a_script_nexto_smoke01
```

The resulting experiment is expected to write `data\isolated\v037a_script_nexto_smoke01_u0062.pt` and `.json`, with full provenance. **Do not deploy** or assume it is better. Training needs a trustworthy stock-Nexto 1v1 evaluation across entire games and an observation parity check. There is also a subtle remaining mismatch: in v037 the simulator's kickoff predicate is derived from `ball.y`, not Rocket League's actual `is_kickoff_pause` flag and kickoff-taker arbitration.

## Report files

Send `v037a_scripted_600steps01.json`, and if PPO was run, the new u0062 `.json`. For TAS, send `data\isolated\v036t2_tas_recovery01\manifest.json`, especially its `skipped` section.

Do not re-run completed jobs using the same `--out` path; existing paths intentionally fail to protect results.
