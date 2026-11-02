"""Studio collector preserves sources and records only observable state."""
import unittest, xml.etree.ElementTree as ET
from pathlib import Path
import test_game as h
APP=Path(__file__).resolve().parents[1]
SOURCE=APP/'collector/Collector.lua'
SETUP='''
function methods:GetAttributes()return table.clone(self.p.attrs)end
function methods:IsDescendantOf(root)local p=self.Parent;while p do if p==root then return true end;p=p.Parent end;return false end
function methods:GetMass()return 125 end
function cfMT:GetComponents()return self.Position.X,self.Position.Y,self.Position.Z,table.unpack(self.r)end
local encoded={};function http:JSONEncode(value)encoded[#encoded+1]=value;return 'fixture-json'end
local Collector=(function()
'''+SOURCE.read_text()+'''\nend)()
'''
class CollectorTests(unittest.TestCase):
    run_lua=h.GameTests.run_lua
    def test_capture_retains_native_geometry_values_sources_and_original_script_state(self):
        self.run_lua(h.roblox(SETUP+'''
local originals=Instance.new('Folder',workspace);originals.Name='OriginalCars'
local body=Instance.new('Part',originals);body.Name='Body';body:SetAttribute('Power',75);body.AssemblyMass=830
local scriptSource=Instance.new('Script',originals);scriptSource.Name='Spawner';scriptSource.Source='error("must not execute")';scriptSource.Disabled=false
local output,manifest
task.spawn(function()output,manifest=Collector.capture({roots={originals}})end);advance(1)
assert(output and #manifest.items==3 and manifest.scriptSummary.readable==1)
assert(body.Parent==originals and body:GetAttribute('Power')==75 and not scriptSource.Disabled)
local copied=output.CopiedObjects.OriginalCars.Spawner
assert(copied.Disabled and copied:GetAttribute('DM_OriginalDisabled')==false and copied.Source==scriptSource.Source)
assert(output.Manifest['00001'].Value=='fixture-json')
assert(string.find(manifest.limitation,'no missing server code',1,true))
''',server=False))
    def test_runtime_recording_is_bounded_and_does_not_change_the_car(self):
        self.run_lua(h.roblox(SETUP+'''
local car=Instance.new('Model',workspace);car.Name='WorkingCar'
local body=Instance.new('Part',car);body.Name='Body';car.PrimaryPart=body;body.AssemblyMass=830
local before=body.CFrame
Collector.start(car,{maxSamples=2});advance(1)
assert(Collector.stop()==nil,'Recording did not stop at sample limit')
local report=encoded[#encoded];assert(#report.samples==2 and report.initial.properties.AssemblyMass==830)
assert(body.Parent==car and body.CFrame==before,'Collector modified car state')
''',server=False))
    def test_importable_module_matches_reviewable_source(self):
        root=ET.parse(APP.parent/'downloads/DM_Collector.rbxmx')
        self.assertEqual(root.find('.//ProtectedString').text,SOURCE.read_text())
if __name__=='__main__':unittest.main()
