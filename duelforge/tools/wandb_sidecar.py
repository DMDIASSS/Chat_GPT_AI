"""Read saved metrics in a separate process. Never import the trainer/Torch."""
import argparse,contextlib,json,os,secrets,sys,tempfile,time
from pathlib import Path

STAGES=('01_contact','02_possession','03_trajectory')

def atomic(path,value):
    fd,temp=tempfile.mkstemp(dir=path.parent,prefix=path.name+'.')
    try:
        with os.fdopen(fd,'w',encoding='utf8') as f:json.dump(value,f,indent=2);f.flush();os.fsync(f.fileno())
        os.replace(temp,path)
    finally:
        if os.path.exists(temp):os.unlink(temp)

def active(root):
    file=root/'curriculum.json'
    if not file.is_file():return None
    state=json.loads(file.read_text(encoding='utf8'))
    for index in range(state['stage_index'],-1,-1):
        folder=root/STAGES[index]
        if (folder/'config.json').is_file() and (folder/'latest.pt').is_file():return folder
    return None

def rows(path,offset):
    """Only consume complete JSONL records; preserve partial writes for retry."""
    if not path.is_file():return [],offset
    if path.stat().st_size<offset:offset=0
    output=[]
    with path.open('rb') as f:
        f.seek(offset)
        for _ in range(2000):
            start=f.tell();line=f.readline()
            if not line or not line.endswith(b'\n'):f.seek(start);break
            try:output.append(json.loads(line))
            except (ValueError,UnicodeError):print('UPLOADER_BAD_METRIC_LINE:',start,flush=True)
        return output,f.tell()

@contextlib.contextmanager
def exclusive(path):
    f=path.open('a+b')
    try:
        f.seek(0);f.write(b'0');f.flush();f.seek(0)
        if os.name=='nt':
            import msvcrt
            try:msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
            except OSError:raise RuntimeError('Uploader already running. Keep the existing uploader window.')
        else:
            import fcntl
            try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except OSError:raise RuntimeError('Uploader already running. Keep the existing uploader window.')
        yield
    finally:f.close()

def run(root,wandb_module=None,max_polls=None,interval=3.):
    root=Path(root).resolve();polls=0;current=None;wb=None;offset=0;remote_floor=0;sessions={}
    print('WANDB_UPLOADER: waiting for curriculum; training writes local metrics independently.',flush=True)
    # The trainer creates this directory atomically. Do not create it first.
    while not (root/'curriculum.json').is_file():
        if max_polls is not None:return
        time.sleep(1)
    status=root/'external_wandb_status.json';idsfile=root/'external_wandb_ids.json'
    ids=json.loads(idsfile.read_text()) if idsfile.is_file() else {}
    with exclusive(root/'external_wandb.lock'):
        try:
            while max_polls is None or polls<max_polls:
                polls+=1
                try:
                    folder=active(root)
                    if folder is None:time.sleep(interval);continue
                    if folder!=current:
                        if wb is not None:sessions[current]=(wb,offset,remote_floor)
                        current=folder
                        wb,offset,remote_floor=sessions.get(folder,(None,0,None))
                    if wb is None:
                        cfg=json.loads((folder/'config.json').read_text())
                        if not cfg.get('wandb',{}).get('enabled'):time.sleep(interval);continue
                        if wandb_module is None:import wandb as wandb_module
                        hint=folder/'wandb_status.json'
                        old=json.loads(hint.read_text()) if hint.is_file() else {}
                        run_id=ids.get(folder.name) or old.get('id') or secrets.token_hex(4)
                        ids[folder.name]=run_id;atomic(idsfile,ids)
                        wb=wandb_module.init(project=cfg['wandb']['project'],name=cfg['wandb'].get('name',folder.name),id=run_id,
                            resume='allow',reinit='create_new',config=cfg,dir=str(folder),
                            mode=os.environ.get('WANDB_MODE','online'),
                            settings=wandb_module.Settings(init_timeout=15))
                        remote_floor=None;offset=0
                        print('UPLOADER_CONNECTED:',folder.name,getattr(wb,'url',''),flush=True)
                    if remote_floor is None:
                        remote_floor=int(getattr(wb,'step',0))
                        if os.environ.get('WANDB_MODE','online')=='online':
                            # SDK Run.step can still be zero after resume in 0.31.
                            # Query acknowledged server history before replaying.
                            try:
                                api=wandb_module.Api(timeout=15)
                                remote=api.run(f'{wb.entity}/{cfg["wandb"]["project"]}/{ids[folder.name]}')
                                remote_floor=max(remote_floor,int(remote.lastHistoryStep)+1)
                            except Exception:
                                remote_floor=None
                                raise
                    batch,next_offset=rows(folder/'metrics.jsonl',offset)
                    sent=0
                    for row in batch:
                        step=int(row.get('logging_step',row['learning_transitions']))
                        if step<remote_floor:continue
                        wb.log({k:v for k,v in row.items() if isinstance(v,(int,float,bool))},step=step)
                        remote_floor=step+1;sent+=1
                    offset=next_offset
                    atomic(status,{'state':'running','stage':folder.name,'id':ids[folder.name],
                        'url':getattr(wb,'url',None),'read_offset':offset,'last_queued_step':remote_floor-1,
                        'note':'Queued is not server acknowledgement. On restart replay metrics from start and use W&B resumed server step to skip uploaded rows.','training_started':False})
                    if sent:print('UPLOADER_SENT:',sent,'rows;',folder.name,'through',remote_floor-1,flush=True)
                except Exception as ex:
                    print('UPLOADER_RETRY:',type(ex).__name__,str(ex),flush=True)
                    atomic(status,{'state':'retrying','error':str(ex),'training_started':False})
                    # Retry without finish(): SDK/network waits stay in this worker.
                    # Unconsumed rows remain on disk and offset is committed only
                    # after the full read batch is queued successfully.
                    pass
                if max_polls is None or polls<max_polls:time.sleep(interval)
        except KeyboardInterrupt:print('UPLOADER_STOPPING: trainer is unaffected.',flush=True)
        finally:
            if wb is not None:sessions[current]=(wb,offset,remote_floor)
            print('UPLOADER_CLOSING: flushing runs in this console only; trainer remains independent.',flush=True)
            for saved,_,_ in sessions.values():saved.finish()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[1]/'runs/contact01');a=p.parse_args()
    try:run(a.root)
    except RuntimeError as ex:print(str(ex),flush=True);sys.exit(1)
