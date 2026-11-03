"""Measure preparation CPU and scheduler waits; excludes HTTP and live Roblox FPS."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

import torch
import build_chronos
import chronos
import export_standalone as export

BASELINE='2dd06519ec2cafab436d4a0fb22ae2cc60057330'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--assets',type=Path,default=chronos.APP/'models/chronos')
    parser.add_argument('--luau',default=os.environ.get('LUAU_BIN')or shutil.which('luau'))
    parser.add_argument('--output',type=Path,default=Path('work/chronos-startup.json'))
    args=parser.parse_args()
    if not args.luau:parser.error('Set LUAU_BIN or pass --luau')
    torch.set_num_threads(1)
    root=chronos.APP.parent
    old=subprocess.check_output(['git','show',BASELINE+':downloads/TurboBall_Chronos.lua'],cwd=root,text=True)
    old_policy=old.split('local Keyboard=(function()',1)[0]
    old_tensors=old.split('local function loadTensors()\n',1)[1].split('\nend\ntask.spawn(function()',1)[0]
    current=build_chronos.source(args.assets).split('local Keyboard=(function()',1)[0]
    tensors,cases=chronos.prepare_model(chronos.Chronos(args.assets))
    _,layout,count=build_chronos.model_data(tensors)
    source=current+'\nlocal OldPolicy=(function()\n'+old_policy+'\nreturn Policy\nend)()\n'
    for name,file in [('Startup','local_startup.lua'),('Worker','local_cooperative.lua')]:
        source+='local '+name+'=(function()\n'+(chronos.APP/'templates'/file).read_text()+'\nend)()\n'
    source+='local cases='+export.literal(cases)+'\nlocal layout='+export.literal(layout)+'\nlocal count='+str(count)+'\n'
    source+='''
local baselineWaits,forcedWaits=0,0
local sliceAt=os.clock()
local function loadingYield(force)
 if force or os.clock()-sliceAt>=.002 then
  baselineWaits+=1;if force then forcedWaits+=1 end
  sliceAt=os.clock()
 end
end
local loadOld
do
 local Policy=OldPolicy
 loadOld=function()
'''+old_tensors+'''
 end
end
local began=os.clock()
local oldTensors=loadOld()
local decodeCpu=os.clock()-began;local decodeWaits=baselineWaits
local raw=buffer.tostring(oldTensors['shared.0.weight'].data)
began=os.clock()
local oldPredict=OldPolicy.new(oldTensors,{yieldWork=loadingYield})
local packCpu=os.clock()-began;local packWaits=baselineWaits-decodeWaits
local function check(predict,loader,old)
 local worker=Worker.new(predict)
 for _,case in ipairs(cases)do
  worker:start(case.query,case.entities,{})
  local result
  repeat
   result=worker:step(old and .0015 or .0025)
   if not result then loader(old or nil)end
  until result
  assert(result.index==case.action,'Startup action mismatch')
  for i,v in ipairs(result.logits)do
   assert(math.abs(v-case.logits[i])<.0003+math.abs(case.logits[i])*.0001,'Startup logit mismatch')
  end
 end
end
began=os.clock();check(oldPredict,loadingYield,true)
local testCpu=os.clock()-began
local baselineCpu=decodeCpu+packCpu+testCpu
local fastWaits,simulatedWait=0,0
local startup=Startup.new({clock=function()return os.clock()+simulatedWait end,
 wait=function()fastWaits+=1;simulatedWait+=.1 end,spawn=function()error('HTTP is excluded')end})
began=os.clock()
local views=Policy.loadBuffer(buffer.fromstring(raw),layout,count)
local fastPredict=Policy.new(views,{yieldWork=function()startup:checkpoint()end})
check(fastPredict,function()startup:checkpoint()end,false)
local fastCpu=os.clock()-began
print(('STARTUP_JSON {"baseline":{"cpu_seconds":%.6f,"decode_cpu_seconds":%.6f,"pack_cpu_seconds":%.6f,"test_cpu_seconds":%.6f,"decode_waits":%d,"pack_waits":%d,"test_waits":%d,"waits":%d},"fast":{"cpu_seconds":%.6f,"waits":%d},"parity_states":%d}')
 :format(baselineCpu,decodeCpu,packCpu,testCpu,decodeWaits,packWaits,forcedWaits,baselineWaits,fastCpu,fastWaits,#cases))
'''
    with tempfile.TemporaryDirectory()as directory:
        path=Path(directory)/'startup.luau';path.write_text(source)
        result=subprocess.run([args.luau,str(path)],capture_output=True,text=True,timeout=60)
    if result.returncode:raise RuntimeError(result.stdout+result.stderr)
    line=next(line.removeprefix('STARTUP_JSON ')for line in result.stdout.splitlines()if line.startswith('STARTUP_JSON '))
    report=json.loads(line)
    report.update(baseline_revision=BASELINE,adapter_version='6.10',
                  mode='Luau CLI VM; waits counted without sleeping; model already present in memory',
                  http_download_included=False,live_roblox_startup_measured=False,
                  assumed_scheduler_fps=10,raw_model_bytes=build_chronos.RUNTIME_MODEL['bytes'])
    for key in ('baseline','fast'):
        report[key]['estimated_seconds_at_10fps']=report[key]['cpu_seconds']+report[key]['waits']/10
    report['startup_wait_reduction_factor']=report['baseline']['waits']/max(1,report['fast']['waits'])
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':main()
