"""Detailed peer cars render locally; server proxy replication remains bounded."""
import unittest
import test_game as h
from test_original_course import MAP
from test_original_assets import FIXTURE

class OriginalMultiplayerTests(unittest.TestCase):
    run_lua=h.GameTests.run_lua
    def test_peer_poses_are_compact_and_proxies_do_not_copy_detailed_assets(self):
        self.run_lua(h.roblox('''
local latest;remotes.State.OnClientEvent:Connect(function(p)latest=p end)
local guest=newPlayer(202);players.PlayerAdded:Fire(guest);advance(.3)
remotes.Action.OnServerEvent:Fire(localPlayer,'start',{mode='sprint',seed=5})
remotes.Action.OnServerEvent:Fire(guest,'start',{mode='sprint',seed=5});advance(.4)
assert(#latest.nearby==2)
local proxy=workspace.Rally_202.NativeCar
local count=0;for _,p in ipairs(proxy:GetDescendants())do if p:IsA('BasePart')then count+=1 end end
assert(count<60 and not proxy:FindFirstChild('Original exterior'),'Server replicates the detailed original car per part')
assert(latest.nearby[1].s.tyres==nil and latest.nearby[1].s.settings==nil,'Peer packet contains unnecessary simulation tables')
''',before_server=MAP+FIXTURE))
    def test_client_reuses_original_peer_car_and_removes_only_its_local_copy(self):
        self.run_lua(h.roblox('''
local function click(text)for _,o in ipairs(created)do if o:IsA('TextButton')and o.Parent and o.Text==text then o.Activated:Fire();return end end;error(text)end
click('TAKE THE ROAD →');advance(6,true)
local guest=newPlayer(202);players.PlayerAdded:Fire(guest);advance(.3,true)
remotes.Action.OnServerEvent:Fire(guest,'start',{mode='sprint',seed=5});advance(.5,true)
local peer=workspace.ExpeditionLocal:FindFirstChild('OriginalOpponent_202')
assert(peer and peer:FindFirstChild('Original exterior'),'Original peer visuals were not created')
assert(peer['Original exterior'].Interior.OriginalInstrumentFace)
assert(workspace.Rally_202.NativeCar.Chassis.LocalTransparencyModifier==1,'Portable proxy overlaps original visual')
remotes.Action.OnServerEvent:Fire(guest,'retire',{});advance(.5,true)
assert(not workspace.ExpeditionLocal:FindFirstChild('OriginalOpponent_202'))
assert(source.Parent==cars and shell.Parent==exterior,'Cleaning up a peer deleted source assets')
''',before_server=MAP+FIXTURE,client=True),timeout=60)
if __name__=='__main__':unittest.main()
