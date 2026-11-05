# Licenses and provenance

NovaForge's original source code is licensed under the included MIT license. Third-party libraries and downloaded bot materials retain their own terms. The downloadable core ZIP excludes teacher models, upstream source caches, collision meshes, datasets, trained weights and virtual environments.

## Teacher materials downloaded on request

- **Ripple**, by **Rolv**: [Rolv-Arild/Ripple-RLBot](https://github.com/Rolv-Arild/Ripple-RLBot), pinned to `7ca4273a891ab1d04d001b48cb86f1bc8914aa85`. Its code/models use **CC BY-NC-SA 4.0**. The installer preserves `LICENSE` and `NOTICE`. Ripple's upstream `obs.py`, `act.py` and model are downloaded unchanged. NovaForge's adapter is separate. Collision meshes are copied locally from the installed RLGym package for the upstream observation module's expected asset path.
- **Nexto/Necto**, by **Rolv and the Necto contributors**: [RLBot/RLBotPack](https://github.com/RLBot/RLBotPack/tree/0033a98d4e060670f334f60f7f8dc5ee21ba93bb/RLBotPack/Necto), pinned to `0033a98d4e060670f334f60f7f8dc5ee21ba93bb`. Necto/Nexto materials use **CC BY-NC-SA 4.0**. The installer preserves `LICENSE` and the original observation source. It creates an import-only adaptation pointing to RLGym-tools' V1 types; the source records the modification. The stock scripted kickoff is omitted from the adapter.
- **Chronos**, by **KingJake3113**: [deployment repository](https://github.com/KingJake3113/Chronos/tree/4f8fdd27e4802d977b33b9ade4759ff6aeaca5aa), pinned to `4f8fdd27e4802d977b33b9ade4759ff6aeaca5aa`. The installer downloads the two native weight archives and upstream README. The inspected repository does not include a top-level license grant for those weights; do not assume NovaForge's MIT code license grants redistribution rights to them. The ZIP excludes those archives and original C++ source. The new adapter implements the published interface and is attributed here; numeric reference fixtures were generated with the original runtime components.
- **GalactusV2**, by **SoldierDoge**: [deployment repository](https://github.com/SoldierDoge/GalactusV2/tree/217324c2fc516048effe0407595fa61c2ebc6863), pinned to `217324c2fc516048effe0407595fa61c2ebc6863`. The same download/provenance boundaries apply: two native weight archives and README are fetched separately; no top-level weight license was found in the inspected deployment repository, and no native weights/C++ source are bundled in this ZIP.

`teachers.lock.json` lists immutable source URLs and hashes. Fetching verifies the upstream bytes; loading verifies the installed files against the lock. Keep their source, attribution and applicable terms with any adapted materials you share. Generated demonstration datasets and teacher-derived student checkpoints may also be subject to upstream terms; they are not relicensed by the MIT source-code license.

## Training dependencies

- RLGym v2 and RLGym-tools: Apache-2.0. The student's advanced action table is provided by RLGym-tools, with bins selected to match the 276 Ripple controls.
- RocketSim: MIT. Bundled collision assets supplied through dependencies retain their own provenance.
- Stable-Baselines3: MIT.
- PyTorch: BSD-style project license and its dependency notices.
- ONNX Runtime: MIT.
- NumPy: BSD-3-Clause.
- The optional Weights & Biases Python SDK: MIT. Its license and dependency notices apply; authentication is handled by the SDK on the user's machine.
- RLBot and rlgym-compat: their upstream package licenses/notices apply.
- RLViser/rlviser-py: upstream license/notices apply.

The Pulsar repository remains a linked research reference and is not an active trainer. No deployment identity or compatible checkpoint for the intended Pulsar bot has been established.

## RLViser camera build

The optional automatic viewer is built from MIT-licensed VirxEC/rlviser commit `a4e524085cdb1601cf9c0af2f815591fb696db54`. The included patch adds configurable horizontal FOV, boom distance/height/pitch, initial car-follow ballcam and no artificial shake. License: [viewer/RLVISER_LICENSE.txt](viewer/RLVISER_LICENSE.txt). The separately downloaded executable and its checked SHA256 are pinned in `viewer.lock.json`.

## Chronos fine tuning in v1.6

The new student loads the pinned Chronos deployment weights directly on the user's machine; no model weights are bundled in the source ZIP. The separate components retain their original architecture. The public source has no explicit root model license; this project does not grant new rights over those weights. Source credit and the exact commit are retained in exported packages.

The PPO rollout/checkpoint machinery uses Stable-Baselines3 2.9.2 (MIT, DLR-RM/stable-baselines3). The custom clipped PPO update follows its public algorithm with a separate critic, critic warmup and a frozen-reference KL term. Research repositories and their reported license metadata are listed in UPSTREAM_REVIEW.md and upstream_pins.json; reviewing them does not vendor their code or imply their licenses agree.
