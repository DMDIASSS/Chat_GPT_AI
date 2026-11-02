import unittest
import test_game as common
APP=common.APP


def race_test(extra=''):
    return '''local Race=(function()\n'''+(APP/'src/Server/RaceSession.lua').read_text()+'''\nend)()
local alice={UserId=11,DisplayName='Alice'};local bob={UserId=22,DisplayName='Bob'};local cara={UserId=33,DisplayName='Cara'}
local messages={};local launched={};local canceled={};local active={};local release={};local time=0
local callbacks={
 clock=function()return time end,
 notify=function(player,kind,data)messages[#messages+1]={player=player,kind=kind,data=data}end,
 active=function(player)return active[player]end,
 launch=function(player,data,id)
  if player==callbacksFail then return nil,'Selected car unavailable'end
  launched[#launched+1]={player=player,data=data,id=id};active[player]={id=id};return active[player]
 end,
 cancel=function(player,id)canceled[#canceled+1]=player;active[player]=nil end,
 countdown=function(players,id)release[#release+1]={players=players,id=id}end,
}
local race=Race.new(callbacks)
'''+extra


class RaceTests(unittest.TestCase):
    run_lua=common.GameTests.run_lua
    def test_ready_barrier_shared_seed_and_finish_ranking(self):
        self.run_lua(race_test('''
assert(race:action(alice,'create',{seed=991,car='orso',settings={damage=false,assists=true,tyrePressure=.9,arbitrary='unsafe'}}))
local room=race:forPlayer(alice)
assert(#race:lobby()==1 and room.seed==991 and room.settings.damage==false and room.settings.arbitrary==nil)
assert(race:action(bob,'join',{id=room.id,car='coupe'}))
assert(not race:action(alice,'start',{}),'Unready drivers started')
assert(race:action(alice,'ready',{}));assert(race:action(bob,'ready',{}))
assert(not race:action(bob,'start',{}),'Guest started host race')
assert(race:action(alice,'start',{}));assert(#launched==2)
assert(launched[1].data.seed==991 and launched[2].data.seed==991)
assert(launched[1].data.car=='orso'and launched[2].data.car=='coupe')
assert(launched[2].data.settings.damage==false and launched[2].data.settings.tyrePressure==.9)
assert(not race:loaded(alice)and #release==0,'First loaded client released race early')
assert(race:loaded(bob)and #release==1 and #release[1].players==2,'Group did not release once all were loaded')
assert(not race:loaded(bob)and #release==1,'Duplicate ready released twice')
race:update(alice,300,5,false);time+=.2;race:update(bob,400,5,false)
assert(race:forPlayer(alice).members[1].userId==22,'Standings ignore road progress')
race:update(bob,6144,100,true);race:update(alice,6144,98,true)
local result=race:forPlayer(alice)
assert(result.status=='finished'and result.members[1].userId==11 and result.members[1].time==98,'Finishes did not rank by elapsed time')
'''))

    def test_partial_launch_failure_rolls_back_and_can_retry(self):
        self.run_lua(race_test('''
race:action(alice,'create',{seed=5});local id=race:forPlayer(alice).id
race:action(bob,'join',{id=id});race:action(alice,'ready',{});race:action(bob,'ready',{})
callbacksFail=bob
assert(not race:action(alice,'start',{}))
assert(#canceled==1 and canceled[1]==alice and not active[alice],'Failed group launch left a live partial race')
assert(race:forPlayer(alice).status=='lobby'and not race:forPlayer(alice).members[1].ready)
callbacksFail=nil;race:action(alice,'ready',{});race:action(bob,'ready',{})
assert(race:action(alice,'start',{})and active[alice]and active[bob],'Room could not retry after launch failure')
'''))

    def test_disconnect_during_loading_releases_remaining_driver(self):
        self.run_lua(race_test('''
race:action(alice,'create',{});local id=race:forPlayer(alice).id
race:action(bob,'join',{id=id});race:action(alice,'ready',{});race:action(bob,'ready',{});race:action(alice,'start',{})
race:loaded(alice);race:remove(bob)
assert(#release==1 and #release[1].players==1 and release[1].players[1]==alice,'Departed loading driver held the race forever')
local room=race:forPlayer(alice);assert(room.members[2].dnf)
race:update(alice,6144,120,true);assert(race:forPlayer(alice).status=='finished')
'''))

    def test_malformed_requests_cannot_hijack_rooms_or_bloat_settings(self):
        self.run_lua(race_test('''
assert(not race:action(alice,'join',{id={}}))
race:action(alice,'create',{seed=0/0,settings={damage='no',tyrePressure=math.huge,assists=true}})
local room=race:forPlayer(alice);assert(room.seed==room.seed and room.settings.damage==nil and room.settings.tyrePressure==nil)
assert(not race:action(bob,'start',{}))
active[bob]={};assert(not race:action(bob,'join',{id=room.id}))
active[bob]=nil;race:action(bob,'join',{id=room.id});race:remove(alice)
assert(race:forPlayer(bob).host==22,'Host departure did not transfer room')
race:remove(bob);assert(#race:lobby()==0,'Empty room leaked')
'''))

    def test_standings_network_broadcast_is_rate_bounded(self):
        self.run_lua(race_test('''
race:action(alice,'create',{});local id=race:forPlayer(alice).id
race:action(bob,'join',{id=id});race:action(alice,'ready',{});race:action(bob,'ready',{});race:action(alice,'start',{});race:loaded(alice);race:loaded(bob)
messages={}
for i=1,1000 do race:update(alice,i,1,false);race:update(bob,i+1,1,false)end
assert(#messages<=2,'Standings emitted one packet per physics step')
time=.2;race:update(bob,2000,2,false);assert(#messages==4)
'''))

    def test_retirement_during_loading_releases_ready_drivers(self):
        self.run_lua(race_test('''

race:action(alice,'create',{});local id=race:forPlayer(alice).id
race:action(bob,'join',{id=id});race:action(alice,'ready',{});race:action(bob,'ready',{});race:action(alice,'start',{})
race:loaded(alice);race:update(bob,0,0,false,'Loading cancelled')
assert(#release==1 and #release[1].players==1 and release[1].players[1]==alice)
assert(race:forPlayer(alice).status=='running')
'''))

    def test_early_finisher_can_leave_without_losing_result(self):
        self.run_lua(race_test('''

race:action(alice,'create',{});local id=race:forPlayer(alice).id
race:action(bob,'join',{id=id});race:action(alice,'ready',{});race:action(bob,'ready',{});race:action(alice,'start',{})
race:loaded(alice);race:loaded(bob);race:update(alice,6144,100,true)
assert(race:action(alice,'leave',{}))
local room=race:forPlayer(bob)
assert(room.members[1].userId==11 and room.members[1].finished and not room.members[1].dnf,'Leaving results invalidated a finish')
'''))
