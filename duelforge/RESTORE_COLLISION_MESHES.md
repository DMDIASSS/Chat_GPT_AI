# Restore deleted Soccar collision meshes

Extract into `E:\Downloads`, merging `Chat_GPT_AI\duelforge`.
Run **70_RESTORE_COLLISION_MESHES.bat**, then retry
**63_START_NO_BOOST_FLIP.bat**.

The repair downloads the official `rlgym-rocket-league==2.0.1` source archive
from PyPI's file host (about 79 kB), checks its pinned SHA-256, and extracts
only the 16 Soccar `.cmf` data files into `duelforge\assets\collision_meshes`.
No package code is executed and no pip installation is performed.
The package is the same mesh source used by the tested project.

The repair updates the `meshes` entry in `local_paths.json`, preserving other
entries and saving a timestamped backup of existing settings. If an incomplete
asset folder exists, it is preserved as a timestamped backup. A complete,
identical folder is reused. `collision_mesh_repair.json` records file hashes.

Models, run folders, training counters, native binaries, Torch and CUDA are
unchanged. The repair does not start training. The normal 63 startup checks
the simulator and resumes the saved flip experiment.

If the download cannot run, restore `collision_meshes` from Windows Recycle Bin
or share the repair console output. Internet access to `files.pythonhosted.org`
is needed only for this small asset download.

Source: https://pypi.org/project/rlgym-rocket-league/2.0.1/
Archive SHA-256: `3be8e9d2f1cfb6514e0e3d455fb33ff95e26eb7c399f819fff0258025cf4d501`
