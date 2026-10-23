"""Local-first scalar telemetry with optional resumable W&B API logging."""
import json
import math
import queue
import threading
import uuid
import os,netrc,sys
from pathlib import Path
from slater_v041_core import atomic_json,read_json

def scalars(value,prefix=''):
    out={}
    for key,item in value.items():
        name=prefix+str(key)
        if isinstance(item,dict):out.update(scalars(item,name+'/'))
        elif isinstance(item,(float,int)) and math.isfinite(item):out[name]=item
    return out

class Monitor:
    def __init__(self,folder,settings,config,*,prompt=False):
        self.folder=Path(folder);self.folder.mkdir(parents=True,exist_ok=True)
        self.file=self.folder/'events.jsonl';self.statefile=self.folder/'wandb_state.json'
        self.state=read_json(self.statefile,{})
        self.index=0
        if self.file.exists():
            with self.file.open(encoding='utf8') as stream:
                for line in stream:
                    try:self.index=max(self.index,json.loads(line)['event'])
                    except (ValueError,KeyError):pass
        self.sdk=None;self.thread=None;self.failed=False;self.queue=queue.Queue(maxsize=256);self.mode=settings['mode']
        if self.mode=='disabled':return
        try:
            import wandb
            configured=bool(os.environ.get('WANDB_API_KEY') or os.environ.get('WANDB_IDENTITY_TOKEN_FILE'))
            if not configured:
                try:configured=bool(netrc.netrc().authenticators('api.wandb.ai'))
                except (OSError,netrc.NetrcParseError):pass
            if self.mode=='online':
                try:
                    if not (configured or prompt and sys.stdin.isatty()) or not wandb.login(verify=True,timeout=20):self.mode='offline'
                except Exception:self.mode='offline'
            if self.mode=='offline':print('W&B: recording offline. REPLAY_IL_WANDB_LOGIN.bat connects your PC to the dashboard.',flush=True)
            run_id=self.state.get('run_id') or uuid.uuid4().hex[:8]
            self.sdk=wandb.init(project=settings['project'],entity=settings.get('entity') or None,
                id=run_id,name=self.folder.name,dir=str(self.folder),mode=self.mode,
                resume='allow' if self.mode=='online' else None,config=config,
                settings=wandb.Settings(init_timeout=30,quiet=True))
            self.sdk.define_metric('train/*',step_metric='train/update')
            self.sdk.define_metric('skill/*',step_metric='train/update')
            self.sdk.define_metric('evaluation/*',step_metric='train/update')
            self.sdk.define_metric('validation/*',step_metric='train/update')
            self.sdk.define_metric('learning/*',step_metric='train/update')
            self.state.update(run_id=run_id,mode=self.mode,url=self.sdk.url if self.mode=='online' else None)
            atomic_json(self.statefile,self.state)
            print('W&B:',self.state['url'] or 'offline spool in '+str(self.folder),flush=True)
            self.thread=threading.Thread(target=self._worker,daemon=True);self.thread.start()
            # Online resume replays locally durable events not yet given to the SDK.
            last=self.state.get('last_'+self.mode+'_event',0)
            if self.file.exists():
                with self.file.open(encoding='utf8') as stream:
                    for line in stream:
                        try:row=json.loads(line)
                        except ValueError:continue
                        if row['event']>last:self.queue.put(row)
        except Exception:
            # SDK exceptions can include authentication details; do not print them.
            self.sdk=None;self.mode='disabled'
            print('W&B unavailable. All metrics remain in events.jsonl; training continues.',flush=True)

    def emit(self,update,kind,metrics):
        self.index+=1;row={'event':self.index,'update':update,'kind':kind,'metrics':scalars(metrics)}
        with self.file.open('a',encoding='utf8') as stream:
            stream.write(json.dumps(row,allow_nan=False)+'\n');stream.flush()
        if self.sdk and not self.failed:
            try:self.queue.put_nowait(row)
            except queue.Full:self.failed=True;print('W&B queue full; events remain in the local log for the next session.',flush=True)

    def _worker(self):
        while True:
            row=self.queue.get()
            try:
                if row is None:return
                if self.failed:continue
                payload={'train/update':row['update'],**row['metrics']}
                self.sdk.log(payload,step=row['event'])
                self.state['last_'+self.mode+'_event']=row['event'];atomic_json(self.statefile,self.state)
            except Exception:self.failed=True;print('W&B upload interrupted; local metrics are retained for resume.',flush=True)
            finally:self.queue.task_done()

    def close(self):
        if self.thread:
            self.queue.put(None);self.thread.join(timeout=35)
        if self.sdk:
            try:self.sdk.finish()
            except Exception:print('W&B finish interrupted; keep the local run folder.',flush=True)
