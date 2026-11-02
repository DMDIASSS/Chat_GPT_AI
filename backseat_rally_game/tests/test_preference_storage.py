"""User settings remain bounded, independent, and durable alongside replay profiles."""
import unittest
import test_game as h

class PreferenceStorageTests(unittest.TestCase):
    run_lua=h.GameTests.run_lua

    def test_burst_settings_are_coalesced_and_keep_existing_rewards(self):
        self.run_lua(h.roblox('''
local P=require(nodes['Server/Persistence.lua']);local C=require(nodes['Shared/Config.lua'])
local Pref=require(nodes['Shared/Preferences.lua']);local store=P.new(C)
local profile=store:load(501);advance(.3)
local cloud=datastore:GetDataStore('BRExpeditionProfiles_v1')
cloud.values['u:501']={version=1,xp=900,records={},bests={},applied={'old'}}
local before=cloud.writes
for i=1,100 do local s=Pref.defaults();s.values.fov=i%2==0 and 95 or 60;store:setPreferences(501,s)end
advance(2.5)
assert(cloud.writes==before+1,'A slider burst issued unbounded cloud writes')
local data=cloud.values['u:501'];assert(data.preferences.values.fov==95 and data.xp==900 and data.applied[1]=='old')
local fresh=P.new(C);fresh:load(501);advance(.3)
assert(fresh.users[501].preferences.values.fov==95,'Saved view settings did not survive a new session')
'''))

    def test_offline_settings_and_cloud_failure_keep_session_values(self):
        self.run_lua(h.roblox('''
local P=require(nodes['Server/Persistence.lua']);local C=require(nodes['Shared/Config.lua']);local Pref=require(nodes['Shared/Preferences.lua'])
game.GameId=0;local offline=P.new(C);local s=Pref.defaults();s.values.damage=false
s.bindings.throttle='Z';offline:setPreferences(2,s);advance(2.5)
assert(offline.users[2].preferences.bindings.throttle=='Z'and not offline.users[2].preferences.values.damage)
assert(offline:flushPreferences(2))
game.GameId=123;local fail=P.new(C);fail:load(3);advance(.2);datastore.fail=true
fail:setPreferences(3,s);advance(2.5)
assert(not fail:flushPreferences(3)and fail.users[3].preferences.bindings.throttle=='Z')
assert(string.find(fail.status[3],'Session only',1,true))
'''))

    def test_server_accepts_only_known_bounded_settings(self):
        self.run_lua(h.roblox('''
remotes.Action.OnServerEvent:Fire(localPlayer,'preferences',{values={fov=999,damage=false,quality='exploit',unknown=42},bindings={throttle='Z',brake='bogus'}})
advance(2.5)
local response=remotes.Request.OnServerInvoke(localPlayer,'preferences')
assert(response.snapshot.values.fov==100 and response.snapshot.values.damage==false)
assert(response.snapshot.values.quality=='medium'and response.snapshot.values.unknown==nil)
assert(response.snapshot.bindings.throttle=='Z'and response.snapshot.bindings.brake=='S')
'''))

if __name__=='__main__':unittest.main()
