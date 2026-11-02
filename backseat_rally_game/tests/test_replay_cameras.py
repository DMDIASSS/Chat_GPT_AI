"""Headless camera-controller checks; these do not validate Roblox rendering."""
import unittest
import test_game as game
roblox = game.roblox


class ReplayCameraTests(unittest.TestCase):
    run_lua = game.GameTests.run_lua

    def test_director_holds_roadside_shot_and_cuts_after_six_seconds(self):
        self.run_lua(roblox('''
local Rig=require(nodes['Client/ReplayCamera.lua'])
local camera=workspace.CurrentCamera;local rig=Rig.new(camera,input)
assert(rig:name()=='CHASE');assert(rig:cycle()=='ORBIT');assert(rig:cycle()=='DIRECTOR')
local car=CFrame.lookAt(Vector3.new(0,4,0),Vector3.new(0,4,10))
rig:update(car,{v=35},1/60,0);local anchor=camera.CFrame.Position;local look=camera.CFrame.LookVector
rig:update(car+Vector3.new(0,0,15),{v=35},1/60,.4)
assert((camera.CFrame.Position-anchor).Magnitude<.001,'Director followed car instead of holding a roadside camera')
assert((camera.CFrame.LookVector-look).Magnitude>.001,'Roadside camera did not follow the subject')
rig:update(car+Vector3.new(0,0,70),{v=35},1/60,6.1)
assert((camera.CFrame.Position-anchor).Magnitude>20,'Director did not cut to a new shot')
rig:destroy()
''', server=False))

    def test_freecam_moves_paused_and_restores_mouse_and_camera_on_exit(self):
        self.run_lua(roblox('''
local Rig=require(nodes['Client/ReplayCamera.lua']);local camera=workspace.CurrentCamera
camera.CameraType=Enum.CameraType.Custom;camera.CFrame=CFrame.new(5,6,7);camera.FieldOfView=61
input.MouseBehavior=Enum.MouseBehavior.Default;input.MouseIconEnabled=true
local original=camera.CFrame;local rig=Rig.new(camera,input);rig:setMode('FREECAM')
local function key(name,kind)return {KeyCode=Enum.KeyCode[name],UserInputType=kind or Enum.UserInputType.Keyboard}end
-- The owning CAS binding may consume WASD; it forwards those inputs.
rig:controlInput(key('W'),Enum.UserInputState.Begin);input.InputBegan:Fire(key('E'),false)
rig:update(CFrame.new(),{},.1,0);local moved=camera.CFrame.Position
assert((moved-original.Position).Magnitude>3 and moved.Y>original.Position.Y,'Freecam cannot move when playback is paused')
input.InputEnded:Fire(key('W'));input.InputEnded:Fire(key('E'))
input.InputBegan:Fire(key('Unknown',Enum.UserInputType.MouseButton2),false)
function input:GetMouseDelta()return Vector2.new(30,12)end
rig:update(CFrame.new(),{},.1,0)
assert(input.MouseBehavior==Enum.MouseBehavior.LockCurrentPosition and not input.MouseIconEnabled)
input.WindowFocusReleased:Fire()
assert(input.MouseBehavior==Enum.MouseBehavior.Default and input.MouseIconEnabled,'Focus loss left mouse captured')
local connections=table.clone(rig.connections)
rig:destroy();assert(camera.CFrame==original and camera.FieldOfView==61 and camera.CameraType==Enum.CameraType.Custom)
for _,connection in ipairs(connections)do assert(not connection.active)end
input.InputBegan:Fire(key('W'),false);assert(not rig.held.W,'Exited replay still consumes input')
rig:destroy()
''', server=False))

    def test_freecam_origin_rebase_is_continuous_and_zoom_is_clamped(self):
        self.run_lua(roblox('''
local Rig=require(nodes['Client/ReplayCamera.lua']);local camera=workspace.CurrentCamera
camera.CFrame=CFrame.new(1,2,3);local rig=Rig.new(camera,input);rig:setMode('FREECAM')
local car=CFrame.new(0,4,4000);rig:update(car,{},1/60,1)
local before=camera.CFrame.Position;local delta=Vector3.new(0,0,-4096)
rig:shift(delta);rig:update(car+delta,{},1/60,1.1)
assert((camera.CFrame.Position-before-delta).Magnitude<.001,'Origin rebase stranded freecam')
input.InputChanged:Fire({UserInputType=Enum.UserInputType.MouseWheel,Position=Vector3.new(0,0,1000)})
rig:update(car+delta,{},1/60,1.1);assert(camera.FieldOfView==25)
rig:setMode('ORBIT')
input.InputChanged:Fire({UserInputType=Enum.UserInputType.MouseWheel,Position=Vector3.new(0,0,-1000)})
assert(rig.distance==85);rig:update(car+delta,{},1/60,90)
assert(camera.CFrame.Position.X==camera.CFrame.Position.X,'Seeking produced an invalid camera pose')
rig:destroy()
''', server=False))

    def test_settings_overlay_suspends_input_and_clears_held_freecam_controls(self):
        self.run_lua(roblox('''
local Rig=require(nodes['Client/ReplayCamera.lua']);local camera=workspace.CurrentCamera
input.MouseBehavior=Enum.MouseBehavior.Default;input.MouseIconEnabled=true
local allow=true;local rig=Rig.new(camera,input,{canInput=function()return allow end});rig:setMode('FREECAM')
local w={KeyCode=Enum.KeyCode.W,UserInputType=Enum.UserInputType.Keyboard}
local mouse={KeyCode=Enum.KeyCode.Unknown,UserInputType=Enum.UserInputType.MouseButton2}
rig:controlInput(w,Enum.UserInputState.Begin);input.InputBegan:Fire(mouse,false)
rig:update(CFrame.new(),{},.1,0);local before=camera.CFrame.Position
assert(rig.held.W and input.MouseBehavior==Enum.MouseBehavior.LockCurrentPosition)
allow=false
rig:update(CFrame.new(),{},.1,0)
assert((camera.CFrame.Position-before).Magnitude<.001,'Freecam moved behind settings overlay')
assert(next(rig.held)==nil and not rig.mouseHeld and input.MouseIconEnabled,'Settings overlay did not release held controls')
assert(input.MouseBehavior==Enum.MouseBehavior.Default)
local fov=rig.fov
input.InputChanged:Fire({UserInputType=Enum.UserInputType.MouseWheel,Position=Vector3.new(0,0,2)})
rig:controlInput(w,Enum.UserInputState.Begin)
assert(rig.fov==fov and not rig.held.W,'Settings overlay consumed replay movement or zoom')
allow=true;rig:update(CFrame.new(),{},.1,0)
assert((camera.CFrame.Position-before).Magnitude<.001,'Closing settings resumed a stale movement key')
rig:destroy()
''', server=False))

    def test_replay_scrubbing_bounds_fetch_queue_and_rejects_empty_pages(self):
        self.run_lua(roblox('''
local Player=require(nodes['Client/ReplayPlayer.lua']);local frames={}
local metadata={id='test',duration=2000,pages={}}
for i=1,100 do metadata.pages[i]={from=(i-1)*20}end
local remote={InvokeServer=function()return {text=''}end}
local replay=Player.new(remote,metadata)
for i=0,99 do replay:sample(i*20)end
assert(#replay.queue<=3,'Scrubbing built an unbounded fetch queue')
advance(11);local state,reason=replay:sample(1980)
assert(not state and reason=='Invalid replay data','Empty page crashed or masqueraded as valid frames')
replay:destroy();assert(next(replay.pending)==nil and #replay.queue==0)
assert(select(2,replay:sample(0))=='Replay closed')
local empty=Player.new(remote,{id='empty',pages={}})
assert(select(2,empty:sample(0))=='Replay has no recorded frames')
assert(select(2,empty:sample(0/0))=='Invalid replay time');empty:destroy()
''', server=False))


if __name__ == '__main__':
    unittest.main()
