"""Persistent local CPU workers; only the parent owns the Torch model/GPU."""
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import os
import subprocess
import sys
import threading
import time
import numpy as np
from replay_il_pipe import read_frame,write_frame


class ForecastProcesses:
    def __init__(self,book,workers):
        if not 1<=workers<=8:raise ValueError('Forecast processes must be 1..8')
        self.processes=[];self.logs=[];self.log_threads=[];self.log_locks=[]
        self.closed=False;self.executor=ThreadPoolExecutor(max_workers=workers);self.groups=None
        env=os.environ.copy()
        for key in ('OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS','NUMEXPR_NUM_THREADS'):env[key]='1'
        worker=Path(__file__).resolve().with_name('replay_il_cpu_worker.py')
        if not worker.is_file():raise FileNotFoundError('Missing lightweight CPU forecast worker: '+str(worker))
        try:
            for index in range(workers):
                process=subprocess.Popen([sys.executable,'-u',str(worker),'--private-forecast-worker'],stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,stderr=subprocess.PIPE,bufsize=0,env=env,
                    creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
                self.processes.append(process);self.logs.append(deque(maxlen=8));self.log_locks.append(threading.Lock())
                thread=threading.Thread(target=self._drain_log,args=(index,),daemon=True)
                self.log_threads.append(thread);thread.start()
            ready=self._collect([self.executor.submit(read_frame,p.stdout) for p in self.processes],30.)
            if any(row.get('status')!='ready' or row.get('torch_loaded') for row in ready):
                raise RuntimeError('CPU forecast worker startup failed or unexpectedly imported Torch')
            self.worker_info=ready
            self._request([{'command':'book','book':book} for _ in self.processes],30.)
        except BaseException:
            self.close();raise

    def _drain_log(self,index):
        for line in iter(self.processes[index].stderr.readline,b''):
            with self.log_locks[index]:self.logs[index].append(line.decode('utf-8','replace')[-1000:])

    def _collect(self,futures,timeout):
        deadline=time.monotonic()+timeout
        try:return [future.result(timeout=max(.01,deadline-time.monotonic())) for future in futures]
        except BaseException as error:
            messages=[]
            for index,log in enumerate(self.logs):
                with self.log_locks[index]:tail=''.join(log).strip()
                if tail:messages.append(f'worker {index}: {tail}')
            self.close()
            if isinstance(error,(KeyboardInterrupt,SystemExit)):raise
            raise RuntimeError('CPU forecast worker failed or timed out: '+str(error)+'\n'+'\n'.join(messages)) from error

    def _roundtrip(self,index,message):
        process=self.processes[index]
        write_frame(process.stdin,message);reply=read_frame(process.stdout)
        if reply.get('status')!='ok':raise RuntimeError(f'worker {index}: '+reply.get('error','invalid reply'))
        return reply

    def _request(self,messages,timeout=10.):
        if self.closed:raise RuntimeError('CPU forecast pool is closed; create a new planner')
        if len(messages)!=len(self.processes):raise ValueError('Forecast worker request count differs')
        return self._collect([self.executor.submit(self._roundtrip,index,message)
                              for index,message in enumerate(messages)],timeout)

    def prepare(self,state,previous,ours,choices,sign):
        self.groups=[group.tolist() for group in np.array_split(np.arange(len(choices)),len(self.processes))]
        self._request([{'command':'prepare','state':state,'previous':previous,'ours':ours,'sign':sign,
                        'indices':group,'tokens':[choices[index] for index in group]} for group in self.groups])

    def step(self,tokens,ticks,retain_state):
        if self.groups is None:raise ValueError('Prepare CPU forecast branches before stepping')
        return self._request([{'command':'step','tokens':[tokens[index] for index in group],
                               'ticks':ticks,'retain_state':retain_state} for group in self.groups])

    def close(self):
        if self.closed:return
        self.closed=True
        # End children before closing pipe readers: a blocked reader otherwise
        # owns the stream lock and could make shutdown hang after a worker fault.
        for process in self.processes:
            if process.poll() is None:process.terminate()
        for process in self.processes:
            try:process.wait(timeout=2.)
            except subprocess.TimeoutExpired:process.kill();process.wait(timeout=2.)
        self.executor.shutdown(wait=True,cancel_futures=True)
        for thread in self.log_threads:thread.join(timeout=.5)
        for process in self.processes:
            for stream in (process.stdin,process.stdout,process.stderr):
                if stream is not None:stream.close()

    def __del__(self):
        try:self.close()
        except Exception:pass
