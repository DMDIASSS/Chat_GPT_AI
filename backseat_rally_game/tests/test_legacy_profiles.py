"""Export compatibility must speak the real client's Replica protocol."""
import os
from pathlib import Path
import sys
import unittest

import test_game as harness

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
from tools.rbxl_addon import Place, instance_paths, property_rows


def isolated(extra, save_source=None, replica_source=None):
    text = (APP/'tests/roblox_mock.luau').read_text()
    text += "\nlocal bridgeModule=Instance.new('ModuleScript')\nmodules[bridgeModule]=function(script)\n"
    text += (APP/'src/Server/LegacyProfiles.lua').read_text() + '\nend\n'
    if save_source:
        text += '''
local exported=Instance.new('Folder',services.ReplicatedStorage);exported.Name='Shared'
local save=Instance.new('ModuleScript',exported);save.Name='SaveStructure'
local util=Instance.new('Folder',exported);util.Name='RBXUtil'
local net=Instance.new('ModuleScript',util);net.Name='Net'
modules[save]=function(script)
''' + save_source + '\nend\n'
    if replica_source:
        text += '''
game.ReplicatedStorage=services.ReplicatedStorage
local collection=Instance.new('CollectionService');services.CollectionService=collection
function collection:GetTagged()return {}end
function collection:GetInstanceAddedSignal()return event()end
function collection:GetInstanceRemovedSignal()return event()end
local replicaShared=Instance.new('Folder',services.ReplicatedStorage);replicaShared.Name='ReplicaShared'
for _,name in ipairs({'Remote','Signal','Maid'})do local m=Instance.new('ModuleScript',replicaShared);m.Name=name end
modules[replicaShared.Signal]=function()return {New=event}end
modules[replicaShared.Maid]=function()return {New=function()return {Add=function()end,IsActive=function()return true end}end}end
modules[replicaShared.Remote]=function()return {New=function(name)
 local result=services.ReplicatedStorage.RemoteEvents:FindFirstChild(name)
 assert(result,'Bridge omitted protocol remote '..name);return result
end}end
local replicaModule=Instance.new('ModuleScript');replicaModule.Name='ReplicaClient'
modules[replicaModule]=function(script)
''' + replica_source + '\nend\n'
    return text + extra


class LegacyProfileTests(unittest.TestCase):
    run_lua = harness.GameTests.run_lua

    def test_standalone_does_not_create_legacy_backend_or_settings(self):
        self.run_lua(isolated('''
local bridge=require(bridgeModule)
assert(bridge.start()==nil)
assert(not services.ReplicatedStorage:FindFirstChild('RemoteEvents'))
assert(not localPlayer:FindFirstChild('Settings'))
'''))


class ActualExportProfileTests(unittest.TestCase):
    run_lua = harness.GameTests.run_lua

    @classmethod
    def setUpClass(cls):
        path=os.environ.get('BACKSEAT_BASE_RBXL')
        if not path:
            raise unittest.SkipTest('Set BACKSEAT_BASE_RBXL for the uploaded client protocol and schema')
        place=Place(Path(path).read_bytes());paths=instance_paths(place);sources=property_rows(place,'Source')
        cls.save=next(sources[ref]for ref,path in paths.items()if path=='ReplicatedStorage.Shared.SaveStructure')
        cls.replica=next(sources[ref]for ref,path in paths.items()if path=='StarterPlayer.StarterPlayerScripts.Client.Init.Data.ReplicaClient')

    def test_real_replica_client_receives_fresh_defaults_and_settings_updates(self):
        self.run_lua(isolated('''
local defaults=require(save).NotIncludingData
local bridge=require(bridgeModule).start()
for key,value in pairs(defaults.Settings)do
 local item=localPlayer.Settings:FindFirstChild(key)
 assert(item and item.Value==value,'Missing schema setting '..key)
end
assert(localPlayer.Settings:GetAttribute('SessionOnlyCompatibility')==true)
local client=require(replicaModule);local received=0;local profile
client.OnNew('PlayerProfile',function(value)received+=1;profile=value end)
client.RequestData();advance(.1)
assert(client.IsReady and received==1 and profile and profile.Tags.Player==localPlayer)
assert(profile.Tags.SessionOnly==true and profile.Parent==nil and profile.Token=='PlayerProfile')
assert(profile.Data.Progress.Level==1 and next(profile.Data.Gamepasses)==nil,'Session bridge invented progress or entitlements')
assert(profile.Data~=defaults and profile.Data.Settings~=defaults.Settings,'Shared default schema was mutated')
local changed=0
profile:OnSet({'Settings','MusicVolume'},function(value)assert(value==.35);changed+=1 end)
local option=net:FindFirstChild('RE/SetOptionRE');option.OnServerEvent:Fire(localPlayer,'MusicVolume',.35)
assert(changed==1 and profile.Data.Settings.MusicVolume==.35 and localPlayer.Settings.MusicVolume.Value==.35)
advance(.6);bridge.events.ReplicaRequestData:FireServer();advance(.1)
assert(received==1 and client.IsReady,'Repeated data requests duplicated the profile')
assert(defaults.Settings.MusicVolume==1,'Original defaults were overwritten')
''', self.save, self.replica))

    def test_invalid_options_are_rejected_and_new_players_have_independent_profiles(self):
        self.run_lua(isolated('''
local bridge=require(bridgeModule).start();local option=net:FindFirstChild('RE/SetOptionRE')
local before=localPlayer.Settings.MusicVolume.Value
for _,payload in ipairs({{'MusicVolume','bad'},{'MusicVolume',0/0},{'MusicVolume',math.huge},{'UnknownSetting',3},{'GraphicsQuality',false}})do
 option.OnServerEvent:Fire(localPlayer,table.unpack(payload))
end
assert(localPlayer.Settings.MusicVolume.Value==before and not localPlayer.Settings:FindFirstChild('UnknownSetting'))
option.OnServerEvent:Fire(localPlayer,'GraphicsQuality',9);assert(localPlayer.Settings.GraphicsQuality.Value==4)
option.OnServerEvent:Fire(localPlayer,'MusicVolume',-2);assert(localPlayer.Settings.MusicVolume.Value==0)
local friend=newPlayer(202);players.PlayerAdded:Fire(friend)
assert(friend.Settings.MusicVolume.Value==1 and bridge.get(friend).Settings~=bridge.get(localPlayer).Settings)
bridge.get(friend).Progress.Level=2;assert(bridge.get(localPlayer).Progress.Level==1)
players.PlayerRemoving:Fire(friend);assert(bridge.get(friend)==nil,'Removed session profile was retained')
''', self.save))


if __name__=='__main__':
    unittest.main()
