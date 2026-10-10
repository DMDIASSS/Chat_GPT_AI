# TAS ↔ Replay Context Link v1 (experimental)

This is **not** a mapping from raw TAS control channels to RocketSim controls. It does not know the exact TAS analog field meanings or recorded frame-by-frame physics states. It never reconstructs positions or uses trajectories.

It does **not** reuse the earlier `tas_input_memory.pt` model. The supplied report shows its best validation analog MAE (`0.4403`) was worse than a constant-input baseline (`0.4088`). That `.pt` is not a GigaLearn policy.

## What this actually teaches

Existing human replay analysis supplied actual **replay game-state observations** and low-confidence inverse-dynamics **action labels**. TAS supplies **the pace/pattern of analog changes and digital button changes**. We compute deliberately coarse, field-order-independent control-cadence signatures for each source. Replay rows with a matching TAS-style cadence get up to 20% additional training weight while keeping *the same replay action label*. The replay policy is fine-tuned on the resulting dataset and becomes a **new isolated native GigaLearn `.lt` policy**.

No TAS controller input is assigned to an arbitrary replay game state. Because field meanings are not verified, the model learns replay *contexts associated with TAS-like input rhythms*, **not exact TAS controller combinations or a demonstrated mechanic**. The low-confidence replay labels are still a limitation. The held-out validation file is copied without modification. Unchanged originals and previous checkpoints remain safe.

## First: actual input-following experiment (offline, no trajectories)

Run `0_TRAIN_INPUT_FOLLOWING.bat`. It trains **two causal next-input models** on the real 7 analog + 7 flag TAS channels: one TAS-only, another with loosely matched replay action-cadence context. Each model uses the previous **4 TAS inputs** to predict the next input; no clip identity or fake trajectory features. The script evaluates on **entire held-out TAS files**, not the last few frames of training files. It also compares against a strong **copy-the-previous-input** baseline. `replay_context_helped` reports whether the replay-informed model did better than TAS-only. Both `.pt` outputs are **offline action predictors**, not native GigaLearn policies. They are not automatically promoted even if they beat baseline.

## Second: fine-tune the state-conditioned GigaLearn policy using matching TAS input cadence



1. Stop active training and back up your project/checkpoints before patching code.
2. Extract package at `E:\Downloads\Chat_GPT_AI`, keeping folder structure intact.
3. After `0_TRAIN_INPUT_FOLLOWING.bat`, run `1_BUILD_LINKED_DATASET.bat`. It chooses the latest extracted replay dataset from `Curriculum_V2\run_data` and uses the TAS clips from `data\tas`. It creates a new immutable linked dataset in `TAS_Replay_Link\linked_replays\linked_*`.
4. Run `2_INSTALL_READER.bat`. It only changes `GigaLearn_Project\upstream\src\HubReplayBC.cpp`; a `.before_tas_link_v1.bak` is created. It does not change the GigaLearn trainer or model files.
5. In **x64 Native Tools Command Prompt for VS 2022**, run `3_BUILD_REPLAY_BC.bat`.
6. Run `4_TRAIN_LINKED_REPLAY.bat`. It seeds from the *latest* `experiments\replay_foundation_01\checkpoints\<numeric>` and fine-tunes 3 epochs using learning rate `0.00002` (lower than original replay BC). The output lives in an isolated `Curriculum_V2\results\replay_bc_*` folder and is never promoted automatically.
7. Check `best_val_ce` vs `initial_val_ce` in the generated output. If no validation improvement, the BC executable safely rejects the run. If it improves, run a RocketSim visual comparison with the old replay foundation, inspect for useful touches/approaches, and **only then** create a Hub branch using `Curriculum_V2\CURRICULUM_4_BRANCH_TO_HUB.bat`.

## Limitations / scientific validity

- **Exact input copying:** replaying a TAS `.data` file verbatim reproduces its stored *bytes*, but a learned GigaLearn policy cannot faithfully imitate those precise input sequences as a function of gameplay state without the verified TAS input channel mapping and state alignment. This package intentionally does not fake that.
- **No score claims:** Validation loss measures fit to approximate replay actions, not match skill or successful mechanics. The native gameplay test on Windows is still required.
- **No Nexto opponent rotation yet:** Nexto, Cycle 9, and Wavedash `.pt` cannot be loaded into GigaLearn as frozen opponents without a bridge; this package does not simulate those matches.
- **No v1 TAS memory model compatibility:** `tas_input_memory.pt` is a time/clip-conditioned 14-output network. It cannot seed `.lt` actor models; don't rename it to `.lt`.
- **Source patch test:** The installer aborts if `HubReplayBC.cpp` isn't exactly the expected Curriculum v2 source or already patched source.

You may customize the dataset path via:

```cmd
python run_pipeline.py link --dataset "E:\path\to\extracted" --tas "E:\path\to\tas" --stride 8
```

The output manifest records all hashes and sample weights. Do not edit `replay_val.txt` or any original checkpoint.
