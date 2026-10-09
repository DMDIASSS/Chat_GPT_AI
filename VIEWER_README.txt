Chat GPT AI - Watch your smoke-test checkpoint
=============================================
1. Extract BOTH watch.py and WATCH_AI.bat directly into your existing
   E:\Downloads\Chat_GPT_AI folder (alongside train.py).
2. Leave your existing data\checkpoints folder completely unchanged.
3. Double-click WATCH_AI.bat.
4. First start installs the RLGym viewer extra, downloads RLViser v0.8.7
   from its official GitHub release, and opens the live visualizer.
5. If the camera doesn't move, press Esc to close the initial RLViser menu.
   Keys 1-8 focus on a car; 9 director view; 0 free camera.
6. Ctrl+C in the CMD window stops playback.

You can also run this manually:
cd /d E:\Downloads\Chat_GPT_AI
.venv\Scripts\python.exe watch.py --preset smoke

Optional:
.venv\Scripts\python.exe watch.py --preset smoke --speed 0.5
.venv\Scripts\python.exe watch.py --preset smoke --sample

This performs INFERENCE only and does not resume or change training.
If you switch training presets, use the same --preset here to compare
similar starting scenarios. It always loads the latest PPO_POLICY.pt
unless you pass --checkpoint FULL_PATH_TO_PPO_POLICY.pt.

Note: Two cars share the same trained policy, but receive different
observations. After only 100,000 steps, expect largely random play.
RLViser v0.9.x may not be compatible with rlviser-py 0.6.x; the launcher
installs the previously working v0.8.7 version.
