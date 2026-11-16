#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PY="${DUELFORGE_PYTHON:-$(command -v python)}"
echo "DUELFORGE ROOT: $ROOT"
"$PY" - <<'PY_CHECK'
import sys,torch,numpy
print('Python:',sys.version.split()[0], 'Torch:',torch.__version__, 'NumPy:',numpy.__version__)
print('CUDA:',torch.cuda.is_available())
if torch.cuda.is_available(): print('GPU:',torch.cuda.get_device_name())
PY_CHECK

# Reuse the runtime's installed packages, and add only missing build utilities.
if ! command -v cmake >/dev/null; then "$PY" -m pip install -q 'cmake>=3.20'; fi
if ! command -v ninja >/dev/null; then "$PY" -m pip install -q ninja; fi
if ! "$PY" - <<'PY_PYBIND'
import importlib.metadata as m
from pathlib import Path
try:
  from packaging.version import Version
  assert Version(m.version('pybind11'))>=Version('2.13.6')
except Exception:raise SystemExit(1)
PY_PYBIND
then
  "$PY" -m pip install -q 'pybind11>=2.13.6,<4'
fi

if ! "$PY" colab/meshes.py --save; then
  echo 'Installing only missing RLGym collision-mesh package (not CUDA/PyTorch).'
  "$PY" -m pip install -q 'rlgym-rocket-league==2.0.1'
  "$PY" colab/meshes.py --save
fi

if ! "$PY" - <<'PY_NATIVE'
import sys,importlib
from pathlib import Path
from duelforge.runtime import CONTRACT
try:
  from duelforge import _native
  assert _native.contract==CONTRACT
  assert hasattr(_native,'predictive_estimate'), 'Updated predictive native module is required'
  assert '_native' in Path(_native.__file__).name
  assert Path(_native.__file__).suffix=='.so'
  print('Using existing native Linux module:',_native.__file__)
except Exception as e:
  print('Needs native Linux build:',type(e).__name__,str(e))
  raise SystemExit(1)
PY_NATIVE
then
  if [[ ! -f "third_party/RocketSim-c2baacb8f4b441dd8505e63c2aeb5a1679b60b02/CMakeLists.txt" ]]; then
    "$PY" tools/fetch_rocketsim.py
  fi
  PYBIND_DIR="$("$PY" -m pybind11 --cmakedir)"
  cmake -S . -B build/colab -G Ninja \
    -DCMAKE_BUILD_TYPE=Release \
    -DPython_EXECUTABLE="$("$PY" -c 'import sys;print(sys.executable)')" \
    -Dpybind11_DIR="$PYBIND_DIR"
  cmake --build build/colab --parallel "${DUELFORGE_BUILD_JOBS:-2}"
  "$PY" - <<'PY_COPY'
from pathlib import Path
import importlib.machinery, shutil
root=Path.cwd()
build=root/'build/colab'
suffixes=importlib.machinery.EXTENSION_SUFFIXES
candidates=[p for p in build.rglob('_native*.so') if any(p.name.endswith(s) for s in suffixes)]
if not candidates:raise RuntimeError('No ABI-compatible _native Linux .so was built')
target=root/'duelforge'/candidates[0].name
shutil.copy2(candidates[0],target)
print('NATIVE_INSTALLED:',target)
PY_COPY
fi
echo 'Verifying physics, observations and policy actions...'
"$PY" -u run.py verify
echo 'COLAB_SETUP_PASS'
