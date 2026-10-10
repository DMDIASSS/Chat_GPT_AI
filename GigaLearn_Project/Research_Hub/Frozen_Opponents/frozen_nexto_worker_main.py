"""Isolated teacher worker. Use stdin/stdout JSON lines, stderr for debugging only."""
from __future__ import annotations
import contextlib
import json
import sys
import traceback


def respond(body):
    sys.stdout.write(json.dumps(body,allow_nan=False,separators=(',', ':')) + '\n')
    sys.stdout.flush()


def main():
    model=None
    while True:
        line=sys.stdin.readline()
        if not line:break
        try:
            msg=json.loads(line)
            op=msg['op']
            if op=='exit':
                respond({'ok':True})
                break
            if op=='init':
                if model is not None:raise RuntimeError('Already initialized')
                # Keep PyTorch/LibTorch entirely in this independent Python process.
                with contextlib.redirect_stdout(sys.stderr):
                    import numpy as np
                    from frozen_nexto_worker_core import FrozenRotation
                    model=FrozenRotation(msg['paths'], np.array(msg['actions'],dtype=np.float32),msg['device'])
                respond({'ok':True,'hashes':model.hashes})
            elif op=='select':
                if model is None:raise RuntimeError('Worker not initialized')
                with contextlib.redirect_stdout(sys.stderr):model.select(msg['name'])
                respond({'ok':True})
            elif op=='infer':
                if model is None:raise RuntimeError('Worker not initialized')
                with contextlib.redirect_stdout(sys.stderr):
                    actions=model.infer(msg['frames'], msg['reset_flags'],msg['opponent_is_orange'])
                respond({'ok':True,'actions':actions})
            else:raise ValueError('Unsupported op: '+str(op))
        except Exception as e:
            traceback.print_exc(file=sys.stderr)
            respond({'ok':False,'error':f'{type(e).__name__}: {e}'})
            if msg.get('op')=='init':break
    return 0

if __name__=='__main__':
    sys.exit(main())
