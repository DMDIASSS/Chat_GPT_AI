# Optional C++ backend migration — compatibility gates

This upgrade ships a **source-checkout helper** for [ZealanL/RLGymPPO_CPP](https://github.com/ZealanL/RLGymPPO_CPP), not a compiled C++ trainer. The upstream implementation includes its own C++ observation builder, state setter, action parser, and reward system. It cannot safely load our Python policy unless all relevant designs match and a checkpoint converter has been validated.

## Step A: checkout upstream source

Run `BOOTSTRAP_CPP.bat`. It runs `git clone --recurse-submodules` to `cpp_backend/RLGymPPO_CPP`; it neither runs untrusted build scripts nor downloads CUDA.

## Step B: build upstream (advanced, not automated)

Follow [upstream installation instructions](https://github.com/ZealanL/RLGymPPO_CPP): a C++ desktop toolchain/Visual Studio, CMake RelWithDebInfo, matching LibTorch/CUDA 11.8 if using NVIDIA, appropriate RocketSim `collision_meshes`. Be careful with conflicting CUDA runtimes in the same process. No change to the existing Python `.venv` is needed.

## Step C: before transferring the policy

1. **Observation equivalence:** implement the exact 92-value `DefaultObs` that Chat GPT AI uses in Python (scaling coefficients and blue/orange inversion, boost pads, car order). Unit-test with 20 synthetic and 20 RocketSim sampled states, requiring numeric near-equality.
2. **Action equivalence:** assert every one of the 90 control vectors and its action ID matches Python exactly.
3. **Policy layer equivalence:** verify the C++ policy architecture equals our DiscreteFF: inputs 92, hidden [512,512], outputs 90, activation functions, output distribution. Critic architecture may differ if restarting critic from scratch.
4. **Checkpoint converter:** run upstream `tools/checkpoint_converter.py`, compare layer tensor shapes and a battery of 100 model inference results across Python and C++. No meaningful PPO training until these agree.
5. **Reward and reset equivalence:** port the grounded state mutators and rewards; compare outputs on identical states, watch for policy collapse after reward switches.
6. **Performance:** measure end-to-end effective timesteps/sec on the **same laptop** and GPU/CPU thermal profile. A faster engine is not necessarily faster if its larger batches exhaust 4 GB VRAM or throttle the i5-10300H.

**If any compatibility gate fails, stay with Python PPO and teacher distillation.** Even exact model conversion doesn't transfer the Python optimizer state unless explicitly handled; a new C++ PPO run may require conservative initial learning rates.

## Important training decision

The most useful first acceleration is **knowledge transfer from Nexto**, because it avoids learning ground driving from zero. Only migrate to C++ when speed is worth the additional engineering cost and the exact checkpoint-compatibility tests pass.
