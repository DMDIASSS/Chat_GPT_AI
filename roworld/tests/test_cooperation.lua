local C=require('../cooperation')
local Policy=require('../policy')
local Adapter=require('../adapter')
local Mirror=require('../mirror')
local Wire=require('../wire')
local fixture=require('./fixture')
local vectors=require('./wire_vectors')
local n=0;local function test(name,fn) fn();n+=1;print('PASS',name) end
local function roster() return {{user_id=222,display_name='Enemy',is_friend=true}} end
local function army() return {home=50000,reserve=35000,available=15000,incoming=0,targets={},enemyActive=0} end
test('team detection supports arbitrary counts and sparse IDs, including metadata for unseen teams',function()
 local f=fixture();local c=C.new();f.info.team=5
 for i=1,7 do f.state.owners[10+i]={kind=2,team=i*5,alive=true,name='T'..i} end
 c:update(f);assert(c.status.mode=='teams' and c.status.team_count==7 and c.status.own_team==5)
 f.state.team_names={'A','B','C','D','E','F','G','H'};c:update(f);assert(c.status.team_count==8)
end)
test('unassigned free-for-all is not mistaken for a shared team zero',function()
 local f=fixture();local c=C.new();c:update(f);assert(c.status.mode=='free_for_all' and c.status.team_count==0)
end)
test('friends require a verified Roblox friendship and unique live name binding',function()
 local f=fixture();f.state.owners[2].kind=2;local c=C.new();c:setRoster(roster());c:update(f)
 assert(c:isFriend(2) and c.status.friends[1].user_id==222)
 c:setRoster({{user_id=222,display_name='Enemy',is_friend=false}});c:update(f);assert(not c:isFriend(2))
 c:setRoster({roster()[1],{user_id=333,display_name='Enemy',is_friend=false},{user_id=444,display_name='Enemy',is_friend=true}})
 c:update(f);assert(not c:isFriend(2))
end)
test('duplicate nation display names prevent friend binding and disabling clears protection',function()
 local f=fixture();f.state.owners[2].kind=2;local c=C.new();c:setRoster(roster());c:update(f);assert(f.state.bot_friend_guard[2])
 c.enabled=false;c:update(f);assert(not c:isFriend(2) and not f.state.bot_friend_guard[2])
 c.enabled=true;f.state.owners[3]={kind=2,alive=true,name='Enemy'};c:update(f);assert(not c:isFriend(2))
end)
test('opposing-team friendship never authorizes support or cross-team priority',function()
 local f=fixture();f.info.team=1;f.state.owners[2].kind=2;f.state.owners[2].team=2
 local c=C.new();c:setRoster(roster());c:update(f);assert(not c:isFriend(2) and c.status.friends[1].opposing_team)
end)
test('friends receive alliance priority and are excluded from new attacks',function()
 local f,p=fixture(),Policy.new();f.state.owners[2].kind=2;p:reset(f)
 p.cooperation:setRoster(roster());p.cooperation:update(f)
 local a=assert(p:diplomacy(f,{},army()));assert(a.intent.type=='ally_request' and a.intent.target==2)
 assert(not p.strategy:canTarget(f,2,army()))
end)
test('a new friend match recalls an existing enemy campaign',function()
 local f,p=fixture(),Policy.new();f.state.owners[2].kind=2;p:reset(f)
 p.cooperation:setRoster(roster());p.cooperation:update(f)
 local a=army();a.outgoing={{aid=4,target=2,troops=1000,anchor_tile=f.info.label_tile}}
 assert(p.strategy:review(f,a).label:find('Roblox friend'))
end)
test('support requires actual alliance and preserves a bounded home bank',function()
 local f=fixture();f.state.owners[2].kind=2;f.state.owners[2].max_troops=100000;local c=C.new();c:setRoster(roster());c:update(f)
 f.state.attacks[8]={attacker=3,target=2,troops=20000}
 assert(not c:aid(f,army(),true));f.state.allied[1026]=true
 local order=assert(c:aid(f,army(),true));assert(order.intent.troops<=4000)
 local a=army();a.incoming=1;assert(not c:aid(f,a,true));assert(not c:aid(f,army(),false))
end)
test('teammates receive limited aid even when friend assistance is off',function()
 local f=fixture();f.info.team=3;f.state.owners[2].team=3;f.state.allied[1026]=true
 f.state.owners[2].max_troops=100000;local c=C.new();c.enabled=false;c:update(f)
 f.state.attacks[8]={attacker=3,target=2,troops=20000};assert(c:aid(f,army(),true))
end)
test('send-time support validation cancels broken alliances and new invasions',function()
 local f=fixture();f.state.allied[1026]=true;f.state.owners[2].max_troops=100000
 local a=Adapter.new({},function() error('reuse') end,function() return f.now end);a.main=f.main
 local order={intent={type='donate',target=2,troops=4000},reserve=35000}
 assert(a:send(order,assert(a:frame())));f.now+=1;f.state.allied={};assert(not a:send(order,assert(a:frame())))
 f.state.allied[1026]=true;f.state.attacks[8]={attacker=3,target=1,troops=100};assert(not a:send(order,assert(a:frame())))
end)
test('snapshot team names survive independent multiplayer decoding',function()
 local hex=vectors.snapshot;local bytes=buffer.create(#hex/2)
 for i=1,#hex,2 do buffer.writeu8(bytes,(i-1)/2,tonumber(hex:sub(i,i+1),16)) end
 local data=Wire.snapshot(bytes);data.teams={'Red','Blue','Green','Gold'}
 local raw=buffer.create(768);buffer.fill(raw,0,128);local map=Mirror.map({width=32,height=24,k_lin=2},raw,data)
 local s=Mirror.snapshot(data,map,1);assert(#s.team_names==4)
 s.owners[1].team=2;s.owners[2].team=2;assert(s:are_allies(1,2))
end)
test('unallied friends receive blast protection without pretending their SAMs are allied',function()
 local f=fixture();local Weapons=require('../weapons');local tile=21*32+28
 f.set(tile,2);f.state.bot_friend_guard={[2]=true}
 f.state.structures[9]={owner=2,kind=4,tile=tile,level=1,shots={},active_tick=0}
 assert(not Weapons.blastSafe(f.state,1,tile,'atom'))
 assert(Weapons.threat(f.state,1).hostile_sams==1)
end)
print('COOPERATION TESTS',n)
