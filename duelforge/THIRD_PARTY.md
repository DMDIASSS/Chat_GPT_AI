# Third-party provenance

RocketSim by ZealanL and contributors is linked into the included native binary. Pinned revision `c2baacb8f4b441dd8505e63c2aeb5a1679b60b02`; full MIT notice is in ROCKETSIM_LICENSE.txt. The GGL-style feature and controller table reference is ZealanL's GigaLearnCPP-Leak / RLGymPPO_CPP source, pinned in research/repositories.json. Its archived learner is audited but not used as this project's PPO implementation. Research source excerpts and upstream README text retain their original authorship; links/pins are in research/.

RocketSimVis by ZealanL and contributors is optionally fetched at `074a4368f31668ccd651087eebf6a1b459564ad7`; its source/archive hash and upstream notices are preserved in its own folder. GUI libraries install only into its isolated environment.

Nexto by Rolv-Arild and contributors, distributed in RLBot/RLBotPack, is optional and not bundled. The fetcher pins revision `0033a98d4e060670f334f60f7f8dc5ee21ba93bb`, checks model/observation/LICENSE hashes and retains its MIT notice alongside fetched assets. Native/Python features, logits and selected actions were checked against that pinned observation builder. It is an opponent, never an imported initialization for DuelForge.

Pybind11, PyTorch, NumPy and the optional RLBot v5 SDK are independent upstream dependencies. Only the native module is bundled; existing Torch/NumPy are reused for training. The game collision meshes remain the user's existing assets.
