"""Cadence under non-divisible frame rates and retained active-run timings."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

LUAU=os.environ.get('LUAU_BIN')or shutil.which('luau')
ROOT=Path(__file__).resolve().parents[1]

@unittest.skipUnless(LUAU,'Set LUAU_BIN to exercise deadline scheduling')
class TimingTests(unittest.TestCase):
    def run_lua(self,body):
        source='local Timing=(function()\n'+(ROOT/'templates/local_timing.lua').read_text()+'\nend)()\n'+body
        with tempfile.TemporaryDirectory()as directory:
            path=Path(directory)/'timing.luau';path.write_text(source)
            result=subprocess.run([LUAU,str(path)],text=True,capture_output=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_non_divisible_frame_rates_preserve_fifteen_hz_without_bursts(self):
        self.run_lua('''
for _,hz in ipairs({50,60,75,120,144})do
 local sampleAt,decisionAt=nil,nil;local count=0
 for frame=1,hz*10 do
  local now=frame/hz
  local due,nextAt=Timing.due(now,sampleAt,1/30)
  if due then
   sampleAt=nextAt
   local decision,nextDecision=Timing.due(now,decisionAt,1/15)
   if decision then count+=1;decisionAt=nextDecision end
  end
 end
 assert(count>=149 and count<=151,'Frame rounding reduced decision rate: '..hz..' Hz -> '..count/10)
end
local due,nextAt,late=Timing.due(10,.1,1/15)
assert(due and nextAt>10 and late>9)
assert(not Timing.due(10,nextAt,1/15),'Replayed missed decisions in a burst')
''')

    def test_rate_excludes_pauses_and_timing_history_is_bounded(self):
        self.run_lua('''
local t=Timing.new(15)
for i=1,300 do t:record({time=i/15,model_ran=i%2==0,model_ms=10,entities=7})end
local r=t:report()
assert(r.samples==120 and math.abs(r.decision_hz-15)<.01)
assert(r.model_calls==60 and r.fields.model_ms.mean==10)
t:record({time=1000,model_ms=10,model_ran=true})
assert(t.rate==0,'Counted paused time as slow inference')
for i=1,20 do t:record({time=1000+i/15,model_ms=10,model_ran=true})end
assert(math.abs(t.rate-15)<.01,'Pause contaminated resumed decision rate')
''')
