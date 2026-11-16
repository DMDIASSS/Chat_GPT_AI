"""Find an existing Torch runtime in bounded project locations; no installs."""
import argparse,json,subprocess,sys,time,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def candidates(explicit=None):
    out=[Path(explicit)] if explicit else []
    for parent in (ROOT.parent,ROOT.parent.parent):
        for project in ('gigaforge','attention_skills','attention_forge','novaforge','NovaForge'):
            folder=parent/project
            for env in ('.venv_native','.venv','.venv_gpu'):
                out.extend([folder/env/'Scripts/python.exe',folder/env/'bin/python'])
            hint=folder/'runtime_python.txt'
            if hint.is_file():
                value=hint.read_text(encoding='utf-8-sig').strip()
                if '\n' not in value and value:out.append(Path(value))
    out.append(Path(sys.executable));unique=[]
    for p in out:
        if p.is_file() and p not in unique:unique.append(p)
    return unique[:18]

def run(explicit=None):
    rows=[];chosen=None;cpu=None
    for exe in candidates(explicit):
        try:
            cmd=[str(exe),'-c',"import json,torch; print(json.dumps({'torch':torch.__version__,'cuda':torch.cuda.is_available(),'gpu':torch.cuda.get_device_name() if torch.cuda.is_available() else None}))"]
            r=subprocess.run(cmd,capture_output=True,text=True,timeout=12)
            if r.returncode:continue
            info=json.loads(r.stdout.strip().splitlines()[-1]);rows.append({'python':str(exe),**info})
            if info['cuda']:chosen=exe;break
            if cpu is None:cpu=exe
        except (OSError,ValueError,subprocess.TimeoutExpired):continue
    chosen=chosen or cpu
    if chosen is None:raise RuntimeError('No existing Python with Torch found. Provide --python E:/.../python.exe. Nothing was installed.')
    output=ROOT/'results/local_model_probe.json';output.parent.mkdir(exist_ok=True)
    print('SELECTED_RUNTIME:',chosen,flush=True)
    (ROOT/'results/runtime_selection.json').write_text(json.dumps({'candidates_tested':rows,'selected':str(chosen),'scope':'Existing runtimes only; no libraries moved or installed'},indent=2))
    subprocess.run([str(chosen),str(ROOT/'tools/model_probe.py'),'--quick','--seconds','1','--threads','2','--output',str(output)],check=True,cwd=ROOT)
    target=ROOT/f'DuelForge_preflight_{time.time_ns()}.zip'
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
        for file in (output,ROOT/'results/runtime_selection.json'):z.write(file,file.name)
    print('REPORT_ZIP:',target,flush=True)
    print('No game training was started. CPU results do not predict GTX 1650 throughput.',flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--python');a=p.parse_args();run(a.python)
