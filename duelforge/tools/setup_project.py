"""Existing-runtime selection with visible rejection reasons and CUDA admission."""
import argparse,json,os,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from tools.preflight import candidates

PROBE=r'''import sys,struct,json,os
try:
 import torch,numpy
 d={'python':sys.version.split()[0],'bits':struct.calcsize('P')*8,'torch':str(torch.__version__),'torch_file':torch.__file__,'python_prefix':sys.prefix,'cuda_visible_devices':os.environ.get('CUDA_VISIBLE_DEVICES'),'torch_cuda_build':torch.version.cuda,'cuda':torch.cuda.is_available(),'gpu':None}
 if d['cuda']:
  try:
   x=torch.ones(16,device='cuda');torch.cuda.synchronize();assert float(x.sum())==16
   d['gpu']=torch.cuda.get_device_name();d['tensor_test']=True
  except Exception as e:d['cuda']=False;d['cuda_error']=str(e)
 else:
  try:torch.cuda.init()
  except Exception as e:d['cuda_error']=str(e)
 print(json.dumps(d))
except Exception as e:
 print(json.dumps({'import_error':type(e).__name__+': '+str(e)}))
 sys.exit(2)
'''

def setup(explicit=None,require_cuda=False):
    start=time.monotonic();rows=[];choices=[];selected=None;paths=candidates(explicit or os.environ.get('DUELFORGE_PYTHON'))
    report=ROOT/'runtime_probe_report.json'
    for exe in paths:
        remaining=90-(time.monotonic()-start)
        if remaining<2:break
        print('PROBING_PYTHON:',exe,flush=True);row={'path':str(exe)}
        try:
            result=subprocess.run([str(exe),'-c',PROBE],capture_output=True,text=True,timeout=min(30,remaining))
            lines=result.stdout.strip().splitlines();data=json.loads(lines[-1]) if lines else {};row['probe']=data
            if result.returncode or 'import_error' in data:
                row.update(status='rejected',reason=data.get('import_error','probe exited '+str(result.returncode)),stderr=result.stderr[-3000:])
            elif not data.get('python','').startswith('3.11.') or data.get('bits')!=64:
                row.update(status='rejected',reason='Windows native ABI requires 64-bit CPython 3.11')
            elif require_cuda and not data.get('cuda'):
                row.update(status='rejected',reason=data.get('cuda_error','CUDA unavailable in this runtime'))
            else:
                row.update(status='accepted',reason='CUDA tensor test passed' if data.get('cuda') else 'CPU runtime allowed for non-CUDA setup');choices.append((exe,data))
                if data.get('cuda'):selected=(exe,data)
        except subprocess.TimeoutExpired:row.update(status='rejected',reason='probe timeout; no package was changed')
        except (OSError,ValueError,IndexError) as e:row.update(status='rejected',reason=type(e).__name__+': '+str(e))
        rows.append(row);print('RUNTIME_PROBE:',row['status'],row['reason'],flush=True)
        if selected:break
    selected=selected or (choices[0] if choices and not require_cuda else None)
    payload={'require_cuda':require_cuda,'probes':rows,'candidate_count':len(paths),'not_probed':max(0,len(paths)-len(rows)),'selected':str(selected[0]) if selected else None,'scope':'Bounded known project paths and runtime hints. No libraries installed/moved; no models modified. Unprobed candidates are not declared unusable.'}
    report.write_text(json.dumps(payload,indent=2)+'\n',encoding='utf8')
    if selected is None:raise RuntimeError('No usable '+('CUDA ' if require_cuda else '')+'CPython 3.11 runtime among tested paths. See runtime_probe_report.json. Existing runtime hint and models were preserved.')
    exe,data=selected
    print('DUELFORGE_PYTHON:',exe,'DEVICE:','cuda' if data['cuda'] else 'cpu','GPU:',data['gpu'],flush=True)
    subprocess.run([str(exe),str(ROOT/'run.py'),'verify'],cwd=ROOT,check=True)
    (ROOT/'runtime_python.txt').write_text(str(exe.resolve())+'\n',encoding='utf8')
    if data['cuda']:(ROOT/'runtime_python_cuda.txt').write_text(str(exe.resolve())+'\n',encoding='utf8')
    (ROOT/'runtime_selection.json').write_text(json.dumps({'selected':str(exe.resolve()),'runtime':data,'scope':'Existing runtime reused; CUDA admission checked with a real tensor operation'},indent=2)+'\n')
    print('SETUP_PASS: runtime verification passed; no training started. Probe report:',report,flush=True)
    return exe,data

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--python');p.add_argument('--require-cuda',action='store_true');a=p.parse_args();setup(a.python,a.require_cuda)
