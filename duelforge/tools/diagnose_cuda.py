"""Read-only selected-runtime CUDA probe. Never installs or changes libraries."""
import json,os,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import torch
from duelforge.runtime import atomic_json,load

def probe():
    out={'python':sys.executable,'torch':str(torch.__version__),'torch_file':torch.__file__,'python_prefix':sys.prefix,'cuda_visible_devices':os.environ.get('CUDA_VISIBLE_DEVICES'),'torch_cuda_build':torch.version.cuda,'cuda_available':torch.cuda.is_available(),'execution_override':os.environ.get('DUELFORGE_DEVICE'),'training_started':False,'checkpoint_modified':False}
    file=ROOT/'runs/potential01/latest.pt'
    if file.is_file():
        ck=load(file);out['checkpoint_device_config']=ck['config'].get('device','auto');out['checkpoint_transitions']=ck['learning_transitions'];del ck
    if torch.cuda.is_available():
        try:
            x=torch.ones(16,device='cuda');y=(x*x).sum();torch.cuda.synchronize();out.update(gpu=torch.cuda.get_device_name(),cuda_tensor_test=float(y)==16.)
        except Exception as ex:out['cuda_tensor_error']=str(ex)
    else:
        try:torch.cuda.init()
        except Exception as ex:out['cuda_initialization_error']=str(ex)
    exe=shutil.which('nvidia-smi')
    if exe:
        try:
            p=subprocess.run([exe,'--query-gpu=name,driver_version,memory.total,utilization.gpu','--format=csv,noheader'],capture_output=True,text=True,timeout=8);out['nvidia_smi']={'returncode':p.returncode,'output':p.stdout.strip(),'error':p.stderr.strip()}
        except Exception as ex:out['nvidia_smi_error']=str(ex)
    else:out['nvidia_smi']='not found'
    atomic_json(ROOT/'cuda_diagnostic.json',out);print(json.dumps(out,indent=2),flush=True);print('CUDA_DIAGNOSTIC:',ROOT/'cuda_diagnostic.json',flush=True)
    return out
if __name__=='__main__':probe()
