"""FROZEN_WORKER_ISOLATION_V1

C++ embedded Python proxy: ONLY stdlib + numpy. No torch imports in host!
Runs torch teacher in clean external Python 3.11 process to avoid Windows c10_cuda.dll
DLL collisions with an already-loaded GigaLearnCPP/LibTorch runtime.
"""
from __future__ import annotations
import atexit
import json
import os
from pathlib import Path
import subprocess
import sys
import numpy as np

HERE = Path(__file__).resolve().parent


class FrozenRotation:
    def __init__(self, paths, cpp_controls, teacher_device='cpu'):
        if teacher_device != 'cpu':
            raise ValueError('Frozen teacher only supports CPU for this bridge')
        if set(paths) != {'nexto', 'cycle9', 'wavedash'}:
            raise ValueError('Must provide nexto, cycle9, wavedash paths')
        controls = np.asarray(cpp_controls, dtype=np.float32)
        if controls.shape != (90, 8) or not np.isfinite(controls).all():
            raise ValueError('Expected finite 90x8 actions')
        python_exe = os.environ.get('GL_FROZEN_PYTHON_EXE', sys.executable)
        if Path(python_exe).name.lower() in ('gigalearnbot.exe', 'gigaleareval.exe'):
            raise RuntimeError('Set GL_FROZEN_PYTHON_EXE to Python 3.11 python.exe, not GigaLearnBot.exe')
        if not Path(python_exe).is_file():
            raise FileNotFoundError('GL_FROZEN_PYTHON_EXE missing: ' + str(python_exe))
        self.log_path = HERE / 'reports' / 'teacher_worker_stderr.log'
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self._stderr = self.log_path.open('a', encoding='utf-8')
        env = dict(os.environ)
        site = env.get('GL_FROZEN_SITE_PACKAGES', '')
        if site:
            if not Path(site).is_dir():
                raise FileNotFoundError('GL_FROZEN_SITE_PACKAGES does not exist: ' + site)
            env['PYTHONPATH'] = site + os.pathsep + env.get('PYTHONPATH', '')
            if os.name == 'nt':
                env['PATH'] = str(Path(site) / 'torch' / 'lib') + os.pathsep + env.get('PATH', '')
        env['PYTHONUNBUFFERED'] = '1'
        # stdout is exclusively machine-readable protocol. Logs go to stderr file.
        self._proc = subprocess.Popen(
            [str(python_exe), '-u', str(HERE / 'frozen_nexto_worker_main.py')],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self._stderr,
            cwd=str(HERE), env=env, text=True, encoding='utf-8', bufsize=1,
        )
        atexit.register(self.close)
        result = self._request({'op':'init','paths': {n:str(p) for n,p in paths.items()},
                                'actions':controls.tolist(),'device':teacher_device})
        self.hashes = result['hashes']
        self.name = 'nexto'
        print('[FrozenNexto] ISOLATED PYTHON WORKER ACTIVE (no torch in C++ process)', flush=True)
        for n, h in self.hashes.items():
            print('[FrozenNexto] actor', n, h[:16], flush=True)

    @staticmethod
    def _original_actions():
        # Must match RLGymCPP/DefaultAction and the native Nexto actor exactly.
        out = []
        for throttle in (-1,0,1):
            for steer in (-1,0,1):
                for boost in (0,1):
                    for handbrake in (0,1):
                        if boost and throttle != 1:continue
                        out.append([throttle or boost, steer, 0, steer, 0, 0, boost, handbrake])
        for pitch in (-1,0,1):
            for yaw in (-1,0,1):
                for roll in (-1,0,1):
                    for jump in (0,1):
                        for boost in (0,1):
                            if jump and yaw != 0:continue
                            if pitch == roll == jump == 0:continue
                            hb = int(bool(jump and (pitch or yaw or roll)))
                            out.append([boost,yaw,pitch,yaw,roll,jump,boost,hb])
        return np.asarray(out,dtype=np.float32)

    def _request(self, data):
        if self._proc.poll() is not None:
            raise RuntimeError(f'Frozen teacher worker exited with status {self._proc.returncode}; see {self.log_path}')
        try:
            self._proc.stdin.write(json.dumps(data, allow_nan=False, separators=(',', ':')) + '\n')
            self._proc.stdin.flush()
            response = self._proc.stdout.readline()
        except (BrokenPipeError, OSError) as e:
            raise RuntimeError(f'Frozen teacher worker IPC failed: {e}; see {self.log_path}') from e
        if not response:
            code = self._proc.poll()
            raise RuntimeError(f'Frozen teacher worker stopped without replying (code {code}); see {self.log_path}')
        try: reply=json.loads(response)
        except json.JSONDecodeError as e:
            raise RuntimeError(f'Frozen teacher invalid protocol response {response[:150]!r}; see {self.log_path}') from e
        if not reply.get('ok'):
            raise RuntimeError(f'Frozen teacher worker error: {reply.get("error", "unknown")}; see {self.log_path}')
        return reply

    def select(self, name):
        if name not in self.hashes:raise ValueError('Unknown teacher: ' + str(name))
        if name != self.name:
            self._request({'op':'select','name':name})
            self.name = name
            print('[FrozenNexto] teacher rotation ->', name, flush=True)

    def infer(self, frames, reset_flags, opponent_is_orange):
        arr = np.asarray(frames, dtype=np.float32)
        if arr.ndim != 2 or arr.shape[1] != 89 or len(arr)==0 or not np.isfinite(arr).all():
            raise ValueError('Invalid Nx89 finite game-state frames')
        flags = np.asarray(reset_flags, dtype=np.uint8).reshape(-1)
        if len(flags) != len(arr):raise ValueError('Mismatched reset flags')
        reply=self._request({'op':'infer','frames':arr.tolist(),
                             'reset_flags':flags.tolist(),
                             'opponent_is_orange':bool(opponent_is_orange)})
        actions=reply['actions']
        if len(actions)!=len(arr) or not all(type(v) is int and 0<=v<90 for v in actions):
            raise RuntimeError('Frozen teacher produced invalid action IDs')
        return actions

    def close(self):
        proc=getattr(self, '_proc', None)
        if proc is not None:
            try:
                if proc.poll() is None:
                    try:
                        proc.stdin.write('{"op":"exit"}\n')
                        proc.stdin.flush()
                        proc.wait(timeout=1.5)
                    except Exception:
                        proc.terminate()
                        try: proc.wait(timeout=2)
                        except Exception: proc.kill()
                if proc.stdin:proc.stdin.close()
                if proc.stdout:proc.stdout.close()
            except Exception:pass
            self._proc=None
        f=getattr(self,'_stderr',None)
        if f:
            try:f.close()
            except Exception:pass
            self._stderr=None
