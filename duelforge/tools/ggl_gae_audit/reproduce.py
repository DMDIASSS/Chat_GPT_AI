"""Optional isolated Linux/LibTorch audit, NOT a game learner or Windows setup."""
import argparse,difflib,hashlib,json,os,shutil,subprocess,sys,urllib.request
from pathlib import Path

REV='86e11c3881a21225a43c36b14af40f0b3c87e7dd'
REL='GigaLearnCPP/src/private/GigaLearnCPP/PPO/GAE.cpp'
EXPECTED='8c1c8d622457ab9c6488edefa96c039474ba00f5fd0e2e08752afa1ff80c8459'

def main():
    if sys.platform!='linux':raise SystemExit('This optional sanitizer harness is Linux-only; no changes made. Use RUN_BENCHMARK_ONLY.bat for the Windows model probe.')
    import torch
    ap=argparse.ArgumentParser();ap.add_argument('--build',default='results/gae_audit_build');args=ap.parse_args()
    folder=Path(args.build).resolve()
    if folder.exists():raise FileExistsError('Choose a new --build path; existing audit results preserved')
    folder.mkdir(parents=True);root=Path(__file__).resolve().parent
    body=urllib.request.urlopen(f'https://raw.githubusercontent.com/ZealanL/GigaLearnCPP-Leak/{REV}/{REL}',timeout=30).read()
    if hashlib.sha256(body).hexdigest()!=EXPECTED:raise RuntimeError('Source hash mismatch; refusing to compile different code')
    original=body.decode();(folder/'GAE.cpp').write_bytes(body)
    fixed=original.replace('nextValPred = _truncValPreds[truncCount];','nextValPred = _truncValPreds[numTruncs - 1 - truncCount];').replace('''\t\t} else {\n\t\t\tnextValPred = _valPreds[step + 1];\n\t\t}''','''\t\t} else if (done) {\n\t\t\tnextValPred = 0;\n\t\t} else {\n\t\t\tif (step + 1 >= valPreds.size(0))\n\t\t\t\tRG_ERR_CLOSE("Nonterminal rollout tail requires an explicit bootstrap value");\n\t\t\tnextValPred = _valPreds[step + 1];\n\t\t}''')
    if fixed==original:raise RuntimeError('Expected source pattern missing')
    (folder/'GAE_patched.cpp').write_text(fixed)
    for name in ('GAE.h','main.cpp'):shutil.copy2(root/name,folder/name)
    torchroot=Path(torch.__file__).parent;lib=torchroot/'lib';compiler=shutil.which('g++')
    if compiler is None:raise RuntimeError('g++ with AddressSanitizer is required; no compiler installed by this tool')
    base=[compiler,'-O0','-g','-fsanitize=address','-fno-omit-frame-pointer','-std=c++17',f'-D_GLIBCXX_USE_CXX11_ABI={int(torch.compiled_with_cxx11_abi())}',f'-I{torchroot/"include"}',f'-I{torchroot/"include/torch/csrc/api/include"}']
    env={**os.environ,'ASAN_OPTIONS':'detect_leaks=0'};rows=[]
    for variant,source in [('original','GAE.cpp'),('patched','GAE_patched.cpp')]:
        binary=folder/variant
        cmd=base+[str(folder/'main.cpp'),str(folder/source),f'-L{lib}',f'-Wl,-rpath,{lib}','-ltorch_cpu','-ltorch','-lc10','-o',str(binary)]
        print('COMPILING:',variant,flush=True);subprocess.run(cmd,check=True,timeout=180)
        for fixture in ('trunc','terminal'):
            p=subprocess.run([str(binary),fixture],env=env,capture_output=True,text=True,timeout=15)
            text=p.stdout+p.stderr;(folder/f'{variant}_{fixture}.log').write_text(text)
            rows.append({'variant':variant,'fixture':fixture,'returncode':p.returncode,'has_asan_overflow':'heap-buffer-overflow' in text,'output_start':text[:1200]})
    (folder/'audit.json').write_text(json.dumps({'source_commit':REV,'sha256':EXPECTED,'results':rows},indent=2));print('AUDIT_RESULTS:',folder/'audit.json')
    if any(x['returncode'] for x in rows if x['variant']=='patched'):raise RuntimeError('Patched fixture failed; inspect logs')
    if not any(x['has_asan_overflow'] for x in rows if x['variant']=='original'):raise RuntimeError('Original terminal overflow was not reproduced on this runtime; do not claim it was')
    print('Original source faults reproduced; isolated patched fixtures passed. No full-learner certification.')

if __name__=='__main__':main()
