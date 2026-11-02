"""Integration checks for view, cabin visibility, replay restoration and race UI.

These use headless Roblox doubles; they do not establish rendered image quality.
"""
import unittest
import test_game as harness


_CAPTURE = '''
local settingsObject,uiObject
local Settings=require(nodes['Client/Settings.lua']);local settingsNew=Settings.new
Settings.new=function(...)settingsObject=settingsNew(...);return settingsObject end
local UI=require(nodes['Client/UI.lua']);local uiNew=UI.new
UI.new=function(...)uiObject=uiNew(...);return uiObject end
'''
_HELPERS = '''
local function click(text)
 for _,o in ipairs(created)do if o:IsA('TextButton')and o.Parent and o.Text==text then o.Activated:Fire();return end end
 error('Missing button '..text)
end
local function key(name)
 local e={KeyCode=Enum.KeyCode[name],UserInputType=Enum.UserInputType.Keyboard}
 input.InputBegan:Fire(e,false);input.InputEnded:Fire(e);return e
end
local function visual()
 local scene=workspace:FindFirstChild('ExpeditionLocal');assert(scene,'Missing local rally scene')
 for _,o in ipairs(scene:GetChildren())do if o:IsA('Model')and o:FindFirstChild('Chassis')then return o end end
 error('Missing local car')
end
'''


class FirstPersonTests(unittest.TestCase):
    run_lua = harness.GameTests.run_lua

    def test_racing_keeps_adjusted_cockpit_view_when_camera_key_repeats(self):
        self.run_lua(harness.roblox(_HELPERS+'''
settingsObject:set('fov',90);settingsObject:set('seatHeight',.4);settingsObject:set('seatForward',.3)
settingsObject:set('shake',1);advance(.3,true)
click('TAKE THE ROAD →');advance(6,true)
local car=visual();local cabin=workspace.ExpeditionLocal:FindFirstChild('RallyCockpit')
assert(cabin,'First-person driving has no detailed cabin')
local function eye()
 local localEye=cabin:GetPivot():Inverse()*workspace.CurrentCamera.CFrame.Position
 assert(math.abs(localEye.X+1.15)<.002 and math.abs(localEye.Y-1.85)<.002 and math.abs(localEye.Z-.05)<.002,
  'View moved outside the configured driver eye')
 assert(workspace.CurrentCamera.FieldOfView==90,'FOV setting ignored')
end
eye()
for i=1,12 do key('C');advance(.12,true);eye()end
assert(car.Cabin.LocalTransparencyModifier==1 and car.Windscreen.LocalTransparencyModifier==1 and car.Roof.LocalTransparencyModifier==1,
 'Opaque fallback geometry blocks first-person road visibility')
key('H');advance(.1,true)
local lights=0;for _,p in ipairs(car:GetDescendants())do if p:IsA('SpotLight')then assert(p.Enabled);lights+=1 end end
assert(lights==2,'Headlight binding did not light the road')
key('H');advance(.1,true)
for _,p in ipairs(car:GetDescendants())do if p:IsA('SpotLight')then assert(not p.Enabled)end end
''', client=True, before_client=_CAPTURE), timeout=60)

    def test_replay_external_cameras_restore_body_after_cockpit(self):
        self.run_lua(harness.roblox(_HELPERS+'''
click('TAKE THE ROAD →');advance(6,true)
input.InputBegan:Fire({KeyCode=Enum.KeyCode.W},false);advance(1,true)
input.InputEnded:Fire({KeyCode=Enum.KeyCode.W});advance(.2,true)
click('RETIRE & SAVE');advance(3,true);click('WATCH REPLAY');advance(3,true)
local car=visual()
assert(car.Cabin.LocalTransparencyModifier==0 and car.Windscreen.LocalTransparencyModifier==0,
 'Replay CHASE inherited the hidden cockpit shell')
-- CHASE -> ORBIT -> DIRECTOR -> FREECAM -> COCKPIT
for i=1,4 do key('C');advance(.15,true)end
assert(string.find(uiObject.replayLabel.Text,'COCKPIT',1,true),'Camera cycle did not reach cockpit')
assert(car.Cabin.LocalTransparencyModifier==1 and car.Windscreen.LocalTransparencyModifier==1)
local cabin=workspace.ExpeditionLocal.RallyCockpit
assert(cabin['Padded dashboard'].Transparency==0)
key('C');advance(.15,true)
assert(string.find(uiObject.replayLabel.Text,'CHASE',1,true),'Replay camera did not return to chase')
assert(car.Cabin.LocalTransparencyModifier==0 and car.Windscreen.LocalTransparencyModifier==0 and cabin['Padded dashboard'].Transparency==1,
 'Exiting cockpit did not restore exterior and hide cabin')
click('EXIT REPLAY');advance(.4,true)
assert(not workspace:FindFirstChild('ExpeditionLocal'),'Replay world survived exit')
''', client=True, before_client=_CAPTURE), timeout=60)

    def test_pressure_deflates_only_the_affected_visual_tyre_and_lights_obey_quality(self):
        self.run_lua(harness.roblox('''
local Assets=require(nodes['Shared/Assets.lua']);local C=require(nodes['Shared/Config.lua']);local D=require(nodes['Shared/Dynamics.lua'])
local Route=require(nodes['Shared/Route.lua']);local route=Route.new(89,0,C);local car=C.Cars[1]
local visual=Assets.car(workspace,car,false,false,false);local state=D.new(route)
D.step(state,{},route,car,C.Step);Assets.pose(visual,state,route,Vector3.zero,0)
local before=visual.wheels[1].tyre.Size.Y
state.tyres[1].pressure=.1;state.tyres[1].punctured=true;Assets.pose(visual,state,route,Vector3.zero,0)
assert(visual.wheels[1].tyre.Size.Y<before*.8,'Deflation does not change tyre silhouette')
assert(visual.wheels[2].tyre.Size.Y>visual.wheels[1].tyre.Size.Y*1.2,'Unpunctured axle tyre also collapsed')
Assets.headlights(visual,true,'high')
for _,light in ipairs(visual.lights)do assert(light.Enabled and light.Shadows and light.Range>30)end
Assets.headlights(visual,true,'low');for _,light in ipairs(visual.lights)do assert(light.Enabled and not light.Shadows)end
Assets.headlights(visual,false,'medium');for _,light in ipairs(visual.lights)do assert(not light.Enabled)end
''', server=False))

    def test_race_room_buttons_can_host_ready_and_show_shared_rules(self):
        self.run_lua(harness.roblox(_HELPERS+'''
click('RACE FRIENDS');advance(.4,true)
assert(uiObject.racePanel.Visible,'Friends race panel did not open')
click('HOST RALLY');advance(.2,true)
assert(uiObject.raceData and uiObject.raceData.status=='lobby'and #uiObject.raceData.members==1,'Host button did not create room')
local guest=newPlayer(202);players.PlayerAdded:Fire(guest);advance(.2,true)
remotes.Action.OnServerEvent:Fire(guest,'raceJoin',{id=uiObject.raceData.id,car='hatch'})
advance(.2,true);click('READY');advance(.2,true)
local localMember
for _,m in ipairs(uiObject.raceData.members)do if m.userId==localPlayer.UserId then localMember=m end end
assert(localMember and localMember.ready,'Ready button did not update lobby')
remotes.Action.OnServerEvent:Fire(guest,'raceReady',{ready=true,car='hatch'});advance(.2,true)
click('START RACE');advance(.4,true)
assert(uiObject.raceData.status=='loading'and not uiObject.racePanel.Visible,'Race loading did not replace the room view')
''', client=True, before_client=_CAPTURE), timeout=60)
