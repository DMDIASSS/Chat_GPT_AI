"""Camera isolation and finite-state regressions for sky-only rally rendering.

Headless checks do not validate the Roblox renderer itself.
"""
import unittest
import test_game as h


class SceneContinuityTests(unittest.TestCase):
    run_lua = h.GameTests.run_lua

    def test_cached_legacy_camera_writes_do_not_move_expansion_view(self):
        self.run_lua(h.roblox('''
local Presence=require(nodes['Client/Presence.lua'])
local gui=Instance.new('ScreenGui',localPlayer.PlayerGui)
local original=workspace.CurrentCamera;original.Parent=workspace
original.CFrame=CFrame.new(12,8,3);original.FieldOfView=83;original.CameraType=Enum.CameraType.Custom
local originalFocus=CFrame.new(12,8,43);original.Focus=originalFocus
local view=Presence.new(gui);view:open()
local managed=workspace.CurrentCamera
assert(managed~=original,'Expansion reused the camera cached by legacy controllers')
assert(original.Parent==view.cameraStore and managed.Parent==view.cameraStore)
local target=CFrame.new(13800,11,785)*CFrame.Angles(0,math.pi,0)
view:view(target,81)
-- Representative old GarageScene/CockpitCamera controller retains original ref.
runService.RenderStepped:Connect(function()original.CFrame=CFrame.new(0,800,-30000);original.Focus=CFrame.new(0,0,0)end)
advance(.2,true)
assert(workspace.CurrentCamera==managed)
assert((managed.CFrame.Position-target.Position).Magnitude<.001,'Cached original controller took over the rally')
assert((managed.Focus.Position-(target.Position+target.LookVector*32)).Magnitude<.001,'Scriptable focus stayed in the original scene')
view:close()
assert(workspace.CurrentCamera==original and original.Parent==workspace,'Original camera instance/parent did not restore')
assert(original.CFrame.Position.X==12 and original.FieldOfView==83 and original.CameraType==Enum.CameraType.Custom)
assert(original.Focus==originalFocus and not workspace:FindFirstChild('ExpeditionCameraStore'))
''', server=False))

    def test_foreign_camera_switch_and_deleted_managed_camera_recover(self):
        self.run_lua(h.roblox('''
local Presence=require(nodes['Client/Presence.lua']);local gui=Instance.new('ScreenGui',localPlayer.PlayerGui)
local original=workspace.CurrentCamera;local view=Presence.new(gui);view:open()
local target=CFrame.new(13800,15,800);view:view(target,77)
local first=workspace.CurrentCamera;local foreign=Instance.new('Camera',workspace);foreign.CFrame=CFrame.new(900000,500,0)
workspace.CurrentCamera=foreign;advance(.05,true)
assert(workspace.CurrentCamera==first and first.CFrame.Position.X==13800,'Foreign camera selection left the rally in the sky')
first:Destroy();workspace.CurrentCamera=foreign;advance(.05,true)
assert(workspace.CurrentCamera~=first and workspace.CurrentCamera.CFrame.Position.X==13800,'Removed view was not recreated')
view:close();assert(workspace.CurrentCamera==original)
''', server=False))

    def test_invalid_or_degenerate_view_never_replaces_last_valid_frame(self):
        self.run_lua(h.roblox('''
local Presence=require(nodes['Client/Presence.lua']);local gui=Instance.new('ScreenGui',localPlayer.PlayerGui)
local view=Presence.new(gui);view:open();local target=CFrame.new(13800,13,768)
assert(view:view(target,78));advance(.05,true)
assert(not view:view(CFrame.new(0/0,0,0),90))
assert(not view:view(CFrame.lookAt(Vector3.zero,Vector3.zero),90))
advance(.05,true)
assert(workspace.CurrentCamera.CFrame.Position.X==13800 and workspace.CurrentCamera.FieldOfView==78)
assert(gui:GetAttribute('RejectedViewFrames')==2)
view:close()
''', server=False))

    def test_nonfinite_local_prediction_is_recovered_before_chunk_selection(self):
        self.run_lua(h.roblox('''
local function click(text)
 for _,o in ipairs(created)do if o:IsA('TextButton')and o.Parent and o.Text==text then o.Activated:Fire();return end end
 error('Missing button '..text)
end
click('TAKE THE ROAD →');advance(6,true)
local D=require(nodes['Shared/Dynamics.lua']);local original=D.step
local injected=false
D.step=function(state,...)
 local result=original(state,...)
 if not injected then injected=true;state.z=0/0 end
 return result
end
-- Invoke client prediction without an intervening server Heartbeat.
runService.RenderStepped:Fire(1/60)
for _,fn in pairs(runService.bound)do fn(1/60)end
assert(injected and localPlayer.PlayerGui.ExpeditionUI:GetAttribute('RecoveredInvalidState')==1)
assert(workspace.CurrentCamera.CFrame.Position.Z==workspace.CurrentCamera.CFrame.Position.Z)
D.step=original;advance(.1,true)
''', client=True), timeout=60)

    def test_network_nonfinite_pose_is_rejected_and_boundary_frames_remain_visible(self):
        self.run_lua(h.roblox('''
local function click(text)
 for _,o in ipairs(created)do if o:IsA('TextButton')and o.Parent and o.Text==text then o.Activated:Fire();return end end
 error('Missing button '..text)
end
local latest;remotes.State.OnClientEvent:Connect(function(p)latest=p end)
click('TAKE THE ROAD →');advance(6,true)
assert(latest and latest.runs[1])
local D=require(nodes['Shared/Dynamics.lua']);local C=require(nodes['Shared/Config.lua']);local Route=require(nodes['Shared/Route.lua'])
local live=latest.runs[1];local route=Route.new(live.seed,live.length,C)
local scene=workspace.ExpeditionLocal;local prior=workspace.CurrentCamera.CFrame.Position
local broken=D.copy(live);broken.s.bodyY=0/0;broken.s.z=786
remotes.State.OnClientEvent:Fire({time=workspace:GetServerTimeNow(),runs={broken}});advance(.02,true)
assert(workspace.ExpeditionLocal==scene and workspace.CurrentCamera.CFrame.Position.Y==workspace.CurrentCamera.CFrame.Position.Y)
assert((workspace.CurrentCamera.CFrame.Position-prior).Magnitude<3,'Invalid source pose reached camera')
-- Exercise the exact screenshot region and the later origin-rebase boundary.
for _,z in ipairs({750,767.9,768,786,1024,4095.9,4096,4100})do
 local valid=D.copy(live);D.reset(valid.s,route,z);valid.s.v=0;valid.s.distance=z
 valid.originZ=-math.floor(z/4096)*4096;valid.penalty=z;valid.status='countdown'
 remotes.State.OnClientEvent:Fire({time=workspace:GetServerTimeNow(),runs={valid}})
 runService.RenderStepped:Fire(1/60)
 for _,fn in pairs(runService.bound)do fn(1/60)end
 local camera=workspace.CurrentCamera
 assert(camera.CFrame.Position.Y==camera.CFrame.Position.Y and math.abs(camera.CFrame.Position.Y)<1000)
 assert((camera.Focus.Position-camera.CFrame.Position).Magnitude>20,'Rally focus was not maintained')
 assert(scene:FindFirstChild('RallyCockpit'),'Cabin disappeared across a checkpoint/rebase')
end
''', client=True), timeout=60)

    def test_recreated_camera_keeps_replay_freecam_controls(self):
        self.run_lua(h.roblox('''
local function click(text)for _,o in ipairs(created)do if o:IsA('TextButton')and o.Parent and o.Text==text then o.Activated:Fire();return end end;error(text)end
local function key(name)local e={KeyCode=Enum.KeyCode[name],UserInputType=Enum.UserInputType.Keyboard};input.InputBegan:Fire(e,false);input.InputEnded:Fire(e)end
click('TAKE THE ROAD →');advance(6,true);click('RETIRE & SAVE');advance(3,true);click('WATCH REPLAY');advance(2,true)
for i=1,3 do key('C');advance(.2,true)end
key('P');local old=workspace.CurrentCamera;old:Destroy();advance(.1,true)
local current=workspace.CurrentCamera;assert(current~=old)
local before=current.CFrame.Position;input.InputBegan:Fire({KeyCode=Enum.KeyCode.W},false);advance(.5,true);input.InputEnded:Fire({KeyCode=Enum.KeyCode.W})
assert((current.CFrame.Position-before).Magnitude>5,'Replay rig kept writing its deleted camera')
click('EXIT REPLAY');advance(.2,true)
''',client=True),timeout=60)

if __name__=='__main__':unittest.main()
