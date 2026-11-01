"""Spawn must survive unpublished places, denied saves and processed input."""
import unittest
import test_game as harness

CLICK = '''
local function click(text)
 for _,o in ipairs(created)do if o:IsA('TextButton')and o.Parent and o.Text==text then o.Activated:Fire();return end end
 error('Missing button '..text)
end
'''


class OfflineSpawnTests(unittest.TestCase):
    run_lua = harness.GameTests.run_lua

    def test_unpublished_place_spawns_visible_server_car_without_any_store_api(self):
        self.run_lua(harness.roblox(CLICK+'''
assert(replicated:GetAttribute('ServerReady'),'Server startup stopped')
click('TAKE THE ROAD →');advance(6,true)
local car=workspace:FindFirstChild('Rally_'..localPlayer.UserId)
assert(car and car:FindFirstChild('NativeCar'),'No visible server car spawned')
local visible=0
for _,p in ipairs(car.NativeCar:GetDescendants())do
 if p:IsA('BasePart')and p.Transparency<1 then visible+=1 end
 assert(not p:IsA('MeshPart')and not p:IsA('SpecialMesh')and not p:IsA('Sound'),'Car depends on an external asset')
end
assert(visible>20 and car.Driver.Occupant,'Car is incomplete or driver was not seated')
assert(not replicated:FindFirstChild('ImportedAudio'),'Offline startup imported external audio')
''',client=True,before_server="game.GameId=0;function datastore:GetDataStore()error('Store API must not be called for an unpublished place')end"))

    def test_throwing_getdatastore_does_not_abort_server_or_spawn(self):
        self.run_lua(harness.roblox(CLICK+'''
assert(replicated:GetAttribute('ServerReady'))
click('TAKE THE ROAD →');advance(6,true)
assert(workspace:FindFirstChild('Rally_'..localPlayer.UserId),'GetDataStore failure prevented spawning')
local library=remotes.Request.OnServerInvoke(localPlayer,'library')
assert(string.find(library.status,'Session only',1,true),'Offline mode was not reported')
''',client=True,before_server="function datastore:GetDataStore()error('You must publish this place to the web to access DataStore')end"))

    def test_session_only_run_can_drive_bank_and_watch_replay(self):
        self.run_lua(harness.roblox(CLICK+'''
local ui=localPlayer.PlayerGui.ExpeditionUI
for _,obj in ipairs(created)do if obj:IsA('TextButton')and obj.Parent and obj.Text==''then
 for _,label in ipairs(obj:GetChildren())do if label.Text=='Endless Journey'then obj.Activated:Fire()end end
end end
click('TAKE THE ROAD →');advance(6,true)
local car=workspace:FindFirstChild('Rally_'..localPlayer.UserId);assert(car)
local before=car:GetPivot().Position
-- ContextActionService can mark an event processed; driving must still receive it.
input.InputBegan:Fire({KeyCode=Enum.KeyCode.W},true)
context.bound.ExpeditionControls('ExpeditionControls',Enum.UserInputState.Begin,{KeyCode=Enum.KeyCode.W})
advance(3,true)
context.bound.ExpeditionControls('ExpeditionControls',Enum.UserInputState.End,{KeyCode=Enum.KeyCode.W})
assert((car:GetPivot().Position-before).Magnitude>20,'Processed input prevented the car from moving')
click('BANK RUN & SAVE');advance(.5,true)
assert(not workspace:FindFirstChild('Rally_'..localPlayer.UserId),'Banking left a duplicate car')
click('WATCH REPLAY');advance(1,true)
assert(ui.ResponsiveCanvas.ReplayControls.Visible,'A session-only run cannot be replayed')
''',client=True,before_server='game.GameId=0'))

    def test_loading_cloud_profile_does_not_block_the_starter_car(self):
        self.run_lua(harness.roblox(CLICK+'''
click('TAKE THE ROAD →');advance(6,true)
assert(workspace:FindFirstChild('Rally_'..localPlayer.UserId),'A slow cloud profile blocked spawning')
''',client=True,before_server="local store=datastore:GetDataStore('BRExpeditionProfiles_v1');function store:GetAsync()task.wait(30);return nil end"))

    def test_missing_server_shows_start_failure_and_releases_button(self):
        self.run_lua(harness.roblox(CLICK+'''
click('TAKE THE ROAD →');advance(9,true)
local ui=localPlayer.PlayerGui.ExpeditionUI
local notice=false;local ready=false
for _,obj in ipairs(ui:GetDescendants())do
 if obj.Text and string.find(obj.Text,'Unable to start',1,true)then notice=true end
 if obj.Text=='TAKE THE ROAD →'then ready=true end
end
assert(notice and ready and ui.ResponsiveCanvas.GarageMenu.Visible,'A failed spawn was silent or left the start button stuck')
''',client=True,server=False))
