import unittest
import test_game as game


class ClientSettingsIntegrationTests(unittest.TestCase):
    run_lua = game.GameTests.run_lua

    def test_context_and_raw_input_dispatch_once_and_rebinding_controls_car(self):
        self.run_lua(game.roblox('''
local function click(value)
 for _,o in ipairs(created)do if o:IsA('TextButton')and o.Parent and o.Text==value then o.Activated:Fire();return o end end
 error('Missing button '..value)
end
click('TAKE THE ROAD →');advance(5,true)
local lastInput;local bookmarks=0
remotes.Input.OnServerEvent:Connect(function(_,data)lastInput=data end)
remotes.Action.OnServerEvent:Connect(function(_,kind)if kind=='bookmark'then bookmarks+=1 end end)
local function key(name,processed)
 local e={KeyCode=Enum.KeyCode[name],UserInputType=Enum.UserInputType.Keyboard,Position=Vector3.zero}
 if context.bound.ExpeditionControls then context.bound.ExpeditionControls('ExpeditionControls',Enum.UserInputState.Begin,e)end
 input.InputBegan:Fire(e,processed==true);return e
end
local function release(e)
 if context.bound.ExpeditionControls then context.bound.ExpeditionControls('ExpeditionControls',Enum.UserInputState.End,e)end
 input.InputEnded:Fire(e)
end
local b=key('B',false);release(b);assert(bookmarks==1,'CAS and UIS dispatched bookmark twice')
local w=key('W',false);advance(.2,true);assert(lastInput.throttle==1);release(w)
local f4=key('F4',false);release(f4)
local overlay=localPlayer.PlayerGui.ExpeditionUI.RallySettingsOverlay;assert(overlay.Visible,'Settings did not open')
local closedW=key('W',false);advance(.2,true);assert(lastInput.throttle==0 and lastInput.brake>.4,'Settings permitted driving');release(closedW)
click('CONTROLS')
-- The first binding button belongs to throttle; choose a previously unused key.
local binding
for _,o in ipairs(overlay:GetDescendants())do if o:IsA('TextButton')and o.Text=='W'then binding=o;break end end
assert(binding);binding.Activated:Fire()
local newKey=key('Z',false);release(newKey)
local f4close=key('F4',false);release(f4close);assert(not overlay.Visible,'Bound settings key failed to close')
local old=key('W',false);advance(.2,true);assert(lastInput.throttle==0,'Old key still drives after rebind');release(old)
local new=key('Z',true);advance(.2,true);assert(lastInput.throttle==1,'Rebound CAS key did not drive');release(new)
advance(.2,true);assert(lastInput.throttle==0,'Rebound release was lost')
''',client=True),timeout=60)

    def test_saved_bindings_and_quality_are_loaded_into_active_controls(self):
        self.run_lua(game.roblox('''
local function click(value)
 for _,o in ipairs(created)do if o:IsA('TextButton')and o.Parent and o.Text==value then o.Activated:Fire();return end end
 error('Missing button '..value)
end
local quality
for _,o in ipairs(created)do if o:IsA('TextButton')and o.Parent and o.Text=='QUALITY: LOW'then quality=o end end
assert(quality,'Saved quality was not synchronized')
click('TAKE THE ROAD →');advance(5,true)
local lastInput;remotes.Input.OnServerEvent:Connect(function(_,data)lastInput=data end)
local function send(name)
 local e={KeyCode=Enum.KeyCode[name],UserInputType=Enum.UserInputType.Keyboard,Position=Vector3.zero}
 context.bound.ExpeditionControls('ExpeditionControls',Enum.UserInputState.Begin,e);input.InputBegan:Fire(e,true);advance(.2,true)
 context.bound.ExpeditionControls('ExpeditionControls',Enum.UserInputState.End,e);input.InputEnded:Fire(e)
 return lastInput.throttle
end
assert(send('Z')==1,'Saved key was not bound')
assert(send('W')==0,'Default key stayed active after preferences load')
''',client=True,before_client='''
local oldInvoke=remotes.Request.OnServerInvoke
remotes.Request.OnServerInvoke=function(player,kind,data)
 if kind=='preferences'then return {snapshot={values={quality='low',fov=95},bindings={throttle='Z'}}}end
 return oldInvoke(player,kind,data)
end
'''),timeout=60)

    def test_replay_camera_and_settings_bindings_survive_processed_context_input(self):
        self.run_lua(game.roblox('''
local function click(value)
 for _,o in ipairs(created)do if o:IsA('TextButton')and o.Parent and o.Text==value then o.Activated:Fire();return end end
 error('Missing button '..value)
end
click('TAKE THE ROAD →');advance(5,true);click('RETIRE & SAVE');advance(4,true);click('WATCH REPLAY');advance(2,true)
local function press(name,processed)
 local e={KeyCode=Enum.KeyCode[name],UserInputType=Enum.UserInputType.Keyboard,Position=Vector3.zero}
 context.bound.ExpeditionControls('ExpeditionControls',Enum.UserInputState.Begin,e);input.InputBegan:Fire(e,processed)
 context.bound.ExpeditionControls('ExpeditionControls',Enum.UserInputState.End,e);input.InputEnded:Fire(e);advance(.2,true)
end
local function cameraLabel(fragment)
 for _,o in ipairs(created)do if o:IsA('TextLabel')and o.Parent and string.find(o.Text,fragment,1,true)then return true end end
end
assert(cameraLabel('CHASE CAMERA'))
press('C',false);assert(cameraLabel('ORBIT CAMERA'),'Replay C double-fired or was swallowed by CAS')
press('F4',true);local overlay=localPlayer.PlayerGui.ExpeditionUI.RallySettingsOverlay;assert(overlay.Visible,'Replay settings binding was swallowed')
press('F4',false);assert(not overlay.Visible,'Replay settings key failed to close')
press('C',true);assert(cameraLabel('DIRECTOR CAMERA'),'Processed replay camera bind did not fire')
''',client=True),timeout=60)
