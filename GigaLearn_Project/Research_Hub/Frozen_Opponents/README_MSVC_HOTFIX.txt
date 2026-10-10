FROZEN NEXTO ROTATION BRIDGE v1 - MSVC BUILD HOTFIX

Symptom:
  error C2440 in FrozenNextoBridge.h line 80 for pybind11::array_t<float>
  followed by cascading C3536/C2059/C3312 errors.

Fixes:
  1. Build Python NumPy array shape with an explicit std::vector<py::ssize_t>.
     The original initializer mixed py::ssize_t and int, confusing MSVC.
  2. Query actual DefaultAction parser action count instead of the
     potentially uninitialized EnvSet.numActions member.

INSTALL
1. Extract ZIP into E:\Downloads\Chat_GPT_AI (merge directories).
2. In GigaLearn_Project\Research_Hub\Frozen_Opponents,
   double-click FIX_MSVC_BUILD.bat.
   It changes ONLY two FrozenNextoBridge.h copies:
     - local template in Frozen_Opponents
     - installed header in upstream/GigaLearnCPP/src/public/GigaLearnCPP/Util
   Each modified header gets a .before_msvc_fix_v1.bak backup.
3. Open "x64 Native Tools Command Prompt for VS 2022" and run:
     cd /d "E:\Downloads\Chat_GPT_AI\GigaLearn_Project\Research_Hub\Frozen_Opponents"
     2_BUILD.bat
4. If build succeeds, run 3_CREATE_BRANCH.bat, then 4_SMOKE_NEXTO.bat.
   DO NOT start extended training until the real match and checkpoint
   output from the first bounded Nexto smoke run are verified.

This hotfix does NOT modify Learner.cpp, PPO weights, checkpoints,
trainer config, historical models, or your training data.
The patcher refuses unknown/edited headers instead of overwriting them.
The patcher is safe to re-run (idempotent).

This patch is validated via source/test checks; Windows compilation must
still be confirmed on your machine.
