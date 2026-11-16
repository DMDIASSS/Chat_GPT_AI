# Rebuild the native module

The release includes `_native.cp311-win_amd64.pyd` for CPython 3.11 x64. It was built in Windows GitHub Actions and passed native import, action-table and feature/mask parity checks. `VALIDATION.json` records the exact build and binary hash. Linux wheels are not bundled.

For development use MSVC 2022 x64 / CMake on Windows, or GCC/Clang on Linux. Use a separate build environment if installing build tools; the normal setup never installs them into the user's existing Torch runtime.

```
python -m pip install pybind11==2.13.6 cmake ninja
python tools/fetch_rocketsim.py
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release -Dpybind11_DIR=<python-site-packages>/pybind11/share/cmake/pybind11
cmake --build build --config Release
```

CMake uses the hash-checked RocketSim source fetched into `third_party`. Copy the resulting `_native*.pyd` or `_native*.so` into `duelforge/`. Set `DUELFORGE_MESHES` to your existing collision meshes and run `python run.py verify`. See the pinned repository workflow `.github/workflows/duelforge-native.yml` for the actual Windows build commands. A different interpreter ABI needs its own binary. Source/Python changes do not justify reusing a binary with a different physics/feature contract.
