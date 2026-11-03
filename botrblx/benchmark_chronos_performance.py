"""Compare the original and optimized actor in one Luau CLI process. No Roblox FPS measurement."""
from pathlib import Path
import argparse,json,os,shutil,subprocess,tempfile
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--assets',type=Path,default=Path(__file__).resolve().parent/'models/chronos')
parser.add_argument('--luau',default=os.environ.get('LUAU_BIN')or shutil.which('luau'))
parser.add_argument('--output',type=Path,default=Path('work/chronos-performance.json'))
args=parser.parse_args()
if not args.luau:parser.error('Set LUAU_BIN or pass --luau')
root=Path(__file__).resolve().parent.parent
import torch,chronos,export_standalone as export,build_chronos
torch.set_num_threads(1)
asset=args.assets
m=chronos.Chronos(asset);t,c=chronos.prepare_model(m)
common=(root/'botrblx/templates/local_policy.lua').read_text()
old=subprocess.check_output(['git','show','b2d5dc006b505fe87d33e61f9687a0b76177feb2:botrblx/templates/local_chronos.lua'],cwd=root,text=True)
old=old.replace('-- COMMON_ADAPTER_HERE','local Policy={}\n'+common[common.index('function Policy.decode'):common.index('local function dense')]+common[common.index('function Policy.actions()'):common.rindex('return Policy')])
old=old.replace('-- CHRONOS_PADS_HERE',export.literal(chronos.PADS.tolist())).replace('-- CHRONOS_MIRROR_PADS_HERE',export.literal([i+1 for i in chronos.MIRROR_PADS]))
s=build_chronos.source(asset).split('local Keyboard=(function()',1)[0]
s+='\nlocal Old=(function()\n'+old+'\nend)()\n'
s+='local Worker=(function()\n'+(root/'botrblx/templates/local_cooperative.lua').read_text()+'\nend)()\n'
s+='local tensors=(function()\n'+export.tensor_source(t)+'\nend)()\nlocal old=Old.new(tensors)\nlocal fast,backend=Policy.new(tensors)\ntensors=nil\nlocal cases='+export.literal(c)
s+='''
local oldTimes,fastTimes,sliceTimes={},{},{}
local maxError=0
for round=1,4 do
 for _,c in ipairs(cases)do
  local at=os.clock();local a,l=old(c.query,c.entities);local ms=(os.clock()-at)*1000
  if round>1 then oldTimes[#oldTimes+1]=ms end
  at=os.clock();local b,m=fast(c.query,c.entities);ms=(os.clock()-at)*1000
  if round>1 then fastTimes[#fastTimes+1]=ms end
  assert(a==c.action and b==c.action)
  for i,v in ipairs(m)do
   maxError=math.max(maxError,math.abs(v-c.logits[i]))
   assert(math.abs(v-c.logits[i])<.0003+math.abs(c.logits[i])*.0001)
  end
 end
end
local worker=Worker.new(fast)
local totalCpu=0
for _,c in ipairs(cases)do
 worker:start(c.query,c.entities,{})
 local result
 repeat
  local at=os.clock();result=worker:step(.0015);sliceTimes[#sliceTimes+1]=(os.clock()-at)*1000
 until result
 totalCpu+=result.cpu*1000
 assert(result.index==c.action)
end
local function stats(a)
 local total=0;for _,v in ipairs(a)do total+=v end
 table.sort(a)
 return ('{"mean":%.6f,"p95":%.6f,"max":%.6f,"samples":%d}'):format(total/#a,a[math.ceil(#a*.95)],a[#a],#a)
end
print('PERF_JSON '..('{"baseline_cpu_ms":%s,"optimized_cpu_ms":%s,"slices_ms":%s,"slice_budget_ms":1.5,"sliced_mean_cpu_ms":%.6f,"max_logit_error":%.9f,"states":%d}')
 :format(stats(oldTimes),stats(fastTimes),stats(sliceTimes),totalCpu/#cases,maxError,#cases))
'''
with tempfile.TemporaryDirectory()as directory:
 p=Path(directory)/'benchmark.luau';p.write_text(s)
 r=subprocess.run([args.luau,str(p)],capture_output=True,text=True,timeout=60)
print(r.stdout,r.stderr)
if r.returncode:raise SystemExit(r.returncode)
line=next(l.removeprefix('PERF_JSON ')for l in r.stdout.splitlines()if l.startswith('PERF_JSON '))
d=json.loads(line)
d.update(baseline_revision='b2d5dc006b505fe87d33e61f9687a0b76177feb2',backend='native vector float32, exact-zero activation skipping',
 model_revision=chronos.MANIFEST['revision'],mode='Luau CLI VM, no native code generation, same process and eight reference states',
 live_roblox_fps_measured=False,frame_budget_is_cooperative_not_a_hard_realtime_guarantee=True)
d['cpu_speedup']=d['baseline_cpu_ms']['mean']/d['optimized_cpu_ms']['mean']
args.output.parent.mkdir(parents=True,exist_ok=True)
args.output.write_text(json.dumps(d,indent=2)+'\n')
print(json.dumps(d,indent=2))
