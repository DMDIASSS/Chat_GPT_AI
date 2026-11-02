import unittest
import test_game as common


class RaceServerIntegrationTests(unittest.TestCase):
    run_lua = common.GameTests.run_lua

    def test_two_driver_shared_start_barrier_standings_and_retirement(self):
        self.run_lua(common.roblox('''
local guest=newPlayer(202);players.PlayerAdded:Fire(guest);advance(.3)
local function action(player,kind,data)
 remotes.Action.OnServerEvent:Fire(player,kind,data or {});advance(.15)
end
local function lastAction(player,kind)
 local sent=remotes.Action.p.sent or {}
 for i=#sent,1,-1 do if sent[i][1]==player and sent[i][2]==kind then return sent[i][3]end end
end
local function lastState(player)
 local sent=remotes.State.p.sent or {}
 for i=#sent,1,-1 do if sent[i][1]==player then return sent[i][2].runs[1]end end
end
action(localPlayer,'raceCreate',{seed=1357,car='hatch',settings={damage=false,assists=true,tyrePressure=.9}})
local room=lastAction(localPlayer,'race');assert(room and room.status=='lobby')
action(guest,'raceJoin',{id=room.id,car='hatch'})
action(localPlayer,'raceReady',{ready=true});action(guest,'raceReady',{ready=true})
action(localPlayer,'raceStart')
local hostStart=lastAction(localPlayer,'start');local guestStart=lastAction(guest,'start')
assert(hostStart and guestStart and hostStart.race==room.id and guestStart.race==room.id,'Race did not launch ordinary runs')
assert(hostStart.seed==1357 and guestStart.seed==1357 and hostStart.length==guestStart.length,'Drivers received different roads')
assert(hostStart.slot~=guestStart.slot,'Separate rally lanes overlapped')
assert(hostStart.settings.damage==false and guestStart.settings.damage==false and math.abs(guestStart.settings.tyrePressure-.9)<.001,'Host rules were not enforced')
action(localPlayer,'ready');advance(4)
assert(lastState(localPlayer).status=='loading'and lastState(guest).status=='loading','One driver started while the other road was loading')
assert(not lastAction(localPlayer,'countdown'),'Countdown ran before all drivers were loaded')
action(guest,'ready');advance(.1)
assert(lastState(localPlayer).status=='countdown'and lastState(guest).status=='countdown','Countdown was not shared')
advance(3.1)
assert(lastState(localPlayer).status=='running'and lastState(guest).status=='running')
assert(math.abs(lastState(localPlayer).clock-lastState(guest).clock)<.02,'Race clocks started on different ticks')
action(localPlayer,'start',{mode='sprint',seed=8})
local intact=lastAction(guest,'race')
for _,member in ipairs(intact.members)do if member.userId==localPlayer.UserId then assert(not member.dnf,'Repeated start removed the active racer from its group')end end
for seq=1,50 do
 remotes.Input.OnServerEvent:Fire(localPlayer,{seq=seq,throttle=1})
 remotes.Input.OnServerEvent:Fire(guest,{seq=seq,brake=1})
 advance(.05)
end
local standing=lastAction(localPlayer,'race')
assert(standing.status=='running'and standing.members[1].userId==localPlayer.UserId and standing.members[1].z>standing.members[2].z,'Standings did not track real progress')
action(guest,'retire');local result=lastAction(guest,'result');assert(result and result.reason=='retired')
standing=lastAction(localPlayer,'race');assert(standing.members[2].dnf,'Retired driver remained live in standings')
action(localPlayer,'retire');assert(lastAction(localPlayer,'race').status=='finished','Race did not close after all drivers retired')
'''))

    def test_service_requires_stop_and_bay_then_repairs_with_penalty(self):
        self.run_lua(common.roblox('''
local function action(kind,data)remotes.Action.OnServerEvent:Fire(localPlayer,kind,data or {});advance(.16)end
local function state()
 local sent=remotes.State.p.sent or {};return sent[#sent][2].runs[1]
end
local function notice()
 local sent=remotes.Action.p.sent or {};for i=#sent,1,-1 do if sent[i][2]=='notice'then return sent[i][3]end end
end
action('start',{mode='sprint',seed=55,settings={damage=true,assists=true,tyrePressure=1}});action('ready');advance(3.3)
assert(state().s.tyres[2].punctured and state().s.damage>0,'Damaged test fixture was not applied')
for seq=1,120 do remotes.Input.OnServerEvent:Fire(localPlayer,{seq=seq,throttle=1});advance(.05)end
assert(math.abs(state().s.v)>1.5)
action('service',{pressure=1.1});assert(state().penalty==0 and string.find(notice(),'Stop the car',1,true),'Service allowed a moving car')
for seq=121,280 do remotes.Input.OnServerEvent:Fire(localPlayer,{seq=seq,brake=1});advance(.05)end
assert(math.abs(state().s.v)<1.5)
assert(state().s.z>85 and state().s.z<680,'Fixture did not stop between service bays')
action('service',{pressure=1.1});assert(state().penalty==0 and string.find(notice(),'checkpoint bays',1,true),'Service allowed repairs away from a bay')
action('recover');advance(.2)
assert(state().penalty==5 and state().s.z<80)
action('service',{pressure=1.15})
local serviced=state()
assert(serviced.penalty==20 and serviced.s.damage==0 and serviced.s.health.engine==1 and not serviced.s.terminal,'Service did not repair mechanics or apply 15 seconds')
for _,tyre in ipairs(serviced.s.tyres)do
 assert(not tyre.punctured and tyre.wear<.001 and math.abs(tyre.targetPressure-1.15)<.001,'Tyres were not replaced at selected pressure')
end
action('service',{pressure=.8});assert(state().penalty==20,'Immediate repeated service was not rate limited')
''',before_server='''
local testDynamics=require(nodes['Shared/Dynamics.lua']);local originalNew=testDynamics.new
local testConfig=require(nodes['Shared/Config.lua'])
testDynamics.new=function(route)
 local state=originalNew(route);testDynamics.impact(state,60,1,testConfig.Cars[1]);testDynamics.puncture(state,2,testConfig.Cars[1]);return state
end
'''))
