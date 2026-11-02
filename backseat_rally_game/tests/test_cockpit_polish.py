"""Original cabins own their appearance; portable controls stay clear of the road."""
import unittest
import test_game as h

class CockpitPolishTests(unittest.TestCase):
    run_lua=h.GameTests.run_lua

    def test_original_interior_never_gets_a_native_dashboard_overlay(self):
        self.run_lua(h.roblox('''
local Cockpit=require(nodes['Client/Cockpit.lua'])
local original=Instance.new('Model',workspace);original.Name='OriginalInterior'
local dash=Instance.new('MeshPart',original);dash.Name='Dashboard';dash.Transparency=0
local visual={interiorReady=true,interior=original,skinStatus='loaded'}
local cabin=Cockpit.new(workspace,{shiftRpm=6000},{visual=visual})
assert(cabin:source()=='original')
for _,entry in ipairs(cabin.parts)do assert(entry.part.Transparency==1,'Native geometry covers the original cabin')end
local count=#created
for i=1,600 do cabin:update(CFrame.new(0,10,i),{v=20,steer=.4},1/60,false)end
assert(#created==count and dash.Transparency==0 and dash.Parent==original)
cabin:setVisible(false);cabin:setVisible(true)
for _,entry in ipairs(cabin.parts)do assert(entry.part.Transparency==1)end
cabin:destroy();assert(original.Parent==workspace and dash.Transparency==0,'Destroying controller deleted original geometry')
''',server=False))

    def test_pending_assets_hide_native_then_fallback_is_explicit_and_smaller(self):
        self.run_lua(h.roblox('''
local Cockpit=require(nodes['Client/Cockpit.lua']);local visual={skinStatus='loading'}
local cabin=Cockpit.new(workspace,{}, {visual=visual})
assert(cabin:source()=='loading')
for _,entry in ipairs(cabin.parts)do assert(entry.part.Transparency==1)end
visual.skinStatus='unavailable';cabin:update(CFrame.identity,{v=0},.1,false)
assert(cabin:source()=='fallback'and cabin.model['Padded dashboard'].Transparency==0)
assert(cabin.hub.Position.Y<.6 and cabin.hub.Position.Z< -1,'Fallback steering is too close to the eye')
for _,entry in ipairs(cabin.wheel)do
 assert(entry.part.Size.X<=.17 and entry.part.Size.Y<=.26,'Fallback wheel rim/spokes obscure the road')
end
local original=Instance.new('Model',workspace);visual.interior=original;visual.interiorReady=true;visual.skinStatus='loaded'
cabin:update(CFrame.identity,{v=20},.1,false)
assert(cabin:source()=='original')
for _,entry in ipairs(cabin.parts)do assert(entry.part.Transparency==1,'Late original did not hide native cabin')end
''',server=False))

    def test_original_steering_entries_animate_without_touching_other_meshes(self):
        self.run_lua(h.roblox('''
local Cockpit=require(nodes['Client/Cockpit.lua']);local model=Instance.new('Model',workspace)
local wheel=Instance.new('MeshPart',model);local dash=Instance.new('MeshPart',model)
local visual={interiorReady=true,interior=model,skinStatus='loaded',steeringParts={{part=wheel,hub=CFrame.new(-1,.5,-1),localFrame=CFrame.new(.2,0,0)}}}
local cabin=Cockpit.new(workspace,{}, {visual=visual});local dashBefore=dash.CFrame
cabin:update(CFrame.new(10,5,20),{steer=.7},.1,false);local before=wheel.Position
cabin:update(CFrame.new(10,5,20),{steer=-.7},.1,false)
assert((wheel.Position-before).Magnitude>.1,'Original rim did not respond to steering')
assert(dash.CFrame==dashBefore,'Original dashboard was moved by steering animation')
''',server=False))

    def test_hud_is_inset_tools_collapse_and_visual_source_is_honest(self):
        self.run_lua(h.roblox('''
local UI=require(nodes['Client/UI.lua']);local C=require(nodes['Shared/Config.lua']);local Route=require(nodes['Shared/Route.lua']);local D=require(nodes['Shared/Dynamics.lua'])
local callbacks={};for _,name in ipairs({'open','close','settings','lobby','quality','stop','recover','bookmark','camera','service','leave','call','library','watch','seek','skip','pause','rate','exitReplay','race'})do callbacks[name]=function()end end
local ui=UI.new(callbacks);ui:show('drive')
assert(ui.hud['Run strip'].Position.Y.Offset>=60,'HUD overlaps Roblox core controls')
local route=Route.new(5,6144,C);local state=D.new(route);state.v=25
local run={mode='sprint',seed=5,length=6144,passenger=0}
ui.ghost.Text='Every finished run saves a replay. Beat your time to update its ghost.'
ui:runInfo(run,state,route,22)
assert(not ui.drivingTools.Visible and not ui.ghost.Visible,'Moving view is cluttered with utility controls')
ui.toolToggle.Activated:Fire();assert(ui.drivingTools.Visible)
ui.toolToggle.Activated:Fire();assert(not ui.drivingTools.Visible)
ui:visualStatus({skinStatus='loading'});assert(string.find(ui.assetStatus.Text,'LOADING',1,true))
ui:visualStatus({skinStatus='unavailable'});assert(string.find(ui.assetStatus.Text,'PORTABLE',1,true))
ui:visualStatus({interiorReady=true});assert(ui.assetStatus.Text=='')
ui:show('replay');assert(not ui.drivingTools.Visible and not ui.toolToggle.Visible)
''',server=False))

if __name__=='__main__':unittest.main()
