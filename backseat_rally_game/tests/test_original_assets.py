"""Native objects and eye/gauge data survive optional external-asset failures."""
import unittest
import test_game as h

FIXTURE='''
local C=require(nodes['Shared/Config.lua']);local Assets=require(nodes['Shared/Assets.lua'])
local assets=Instance.new('Folder',services.ReplicatedStorage);assets.Name='Assets'
local cars=Instance.new('Folder',assets);cars.Name='Cars'
local source=Instance.new('Model',cars);source.Name=C.Cars[1].template
local body=Instance.new('Part',source);body.Name='Body';body.Transparency=1;body.CFrame=CFrame.identity
local eye=Instance.new('Attachment',body);eye.Name='DriverEye';eye.CFrame=CFrame.new(-1.35,2.55,1)
local exterior=Instance.new('Model',source);exterior.Name='Exterior'
local shell=Instance.new('MeshPart',exterior);shell.Name='OriginalShell';shell.MeshId='rbxassetid://111';shell.Transparency=0
local trim=Instance.new('Part',exterior);trim.Name='OriginalSill';trim.Transparency=0
local interior=Instance.new('Model',source);interior.Name='Interior'
local face=Instance.new('Part',interior);face.Name='OriginalInstrumentFace';face.CFrame=CFrame.new(-1,1,-1)
local hub=Instance.new('Part',interior);hub.Name='SpeedoHub';hub.CFrame=CFrame.new(-1,1,-1);hub:SetAttribute('ZeroAngle',135);hub:SetAttribute('MaxAngle',-135);hub:SetAttribute('MaxValue',200)
local needle=Instance.new('Part',interior);needle.Name='SpeedoNeedle';needle.CFrame=CFrame.new(-1,1.2,-1)
local code=Instance.new('Script',interior);code.Name='DoNotRun';code.Source='error("should never execute")'
'''
class OriginalAssetTests(unittest.TestCase):
    run_lua=h.GameTests.run_lua
    def test_native_interior_is_kept_when_external_mesh_fails(self):
        self.run_lua(h.roblox(FIXTURE+'''
content.status=Enum.AssetFetchStatus.Failure
local v=Assets.car(workspace,C.Cars[1],false,true);advance(.3)
assert(v.skin and v.skinStatus=='partial'and v.interiorReady,'One mesh failure discarded the original interior')
assert(v.interior.OriginalInstrumentFace and v.interior.OriginalInstrumentFace.Transparency==0)
assert(not v.interior:FindFirstChild('DoNotRun'),'A cloned gameplay script remained executable')
assert(v.model.Chassis.Transparency==0,'Incomplete exterior removed the complete backup body')
assert(source.Interior.DoNotRun==code and code.Parent==interior and shell.Parent==exterior,'Original source was edited')
assert(v.eyeOffsets.Driver and math.abs(v.eyeOffsets.Driver.Position.X+1.35)<.01)
local Cockpit=require(nodes['Client/Cockpit.lua']);local cabin=Cockpit.new(workspace,C.Cars[1],{visual=v})
cabin:update(CFrame.identity,{v=20,rpm=2000},.1,false)
assert(cabin:source()=='original'and cabin.model['Padded dashboard'].Transparency==1)
''',server=False))

    def test_optional_private_decor_does_not_block_geometry(self):
        self.run_lua(h.roblox(FIXTURE+'''
local decal=Instance.new('Decal',exterior);decal.Name='PrivateDecoration';decal.Texture='rbxassetid://999'
function content:PreloadAsync(ids,callback)
 self.calls[#self.calls+1]=ids
 for _,id in ipairs(ids)do assert(type(id)=='string'and id=='rbxassetid://111','Optional private texture was treated as required geometry');callback(id,Enum.AssetFetchStatus.Success)end
end
local v=Assets.car(workspace,C.Cars[1],false,true);advance(.3)
assert(v.skinStatus=='loaded'and v.model.Chassis.Transparency==1 and v.interiorReady)
assert(source.Exterior.PrivateDecoration==decal,'Optional decoration was removed from its source')
''',server=False))

    def test_original_gauge_parts_use_their_saved_angle_and_scale_attributes(self):
        self.run_lua(h.roblox(FIXTURE+'''
local v=Assets.car(workspace,C.Cars[1],false,true);advance(.3)
assert(#v.instrumentParts==1 and v.instrumentParts[1].max==200)
local Cockpit=require(nodes['Client/Cockpit.lua']);local cabin=Cockpit.new(workspace,C.Cars[1],{visual=v})
local cf=CFrame.new(20,80,-200)
cabin:update(cf,{v=0,steer=0},.1,false);local zero=v.interior.SpeedoNeedle.Position
cabin:update(cf,{v=100/(.28*3.6),steer=0},.1,false)
assert((v.interior.SpeedoNeedle.Position-zero).Magnitude>.1,'Original gauge is still a static display')
assert(v.interior.OriginalInstrumentFace.Parent==v.interior)
''',server=False))
if __name__=='__main__':unittest.main()
