local Agent=require('../agent')
local Actions=require('../actions')
local Observe=require('../observe')
local Neural=require('../neural')
local Schema=require('../schema')
local Geography=require('../geography')
local fixture=require('./fixture')
local n=0
local function test(name,fn) fn();n+=1;print('PASS',name) end
local function world()
    local f=fixture();f.info.kind=2;f.info.team=0
    f.state.owners[2].kind=2;f.state.owners[2].team=0;f.state.owners[2].tiles=40;f.state.owners[2].max_troops=10000
    return f
end
local function prepared(f,p)
    p=p or Agent.new();p:reset(f);p.cooperation:update(f)
    return p,Observe.read(f,p)
end
local function find(rows,kind)
    for _,a in ipairs(rows) do if a.kind==kind then return a end end
end
test('new policy acts on public state without an old policy module or trained weights',function()
    local f=world();local p=Agent.new();local a=assert(p:decide(f))
    assert(a.kind=='expand' and p.weights==nil and #p.observation.context==204)
    for _,c in ipairs(p.candidates) do assert(#c.features==48) end
end)
test('observation preserves exact public relationships, banks and attack identifiers',function()
    local f=world();f.state.allied[1026]=true;f.state.requests[2049]=10
    f.state.attacks[7]={attacker=2,target=1,troops=4321,retreating=false}
    local p,o=prepared(f)
    assert(o.diplomacy[2].allied and o.diplomacy[2].incoming_request)
    assert(o.players[2].troops==1000 and o.attacks[1].id==7 and o.incoming==4321)
    assert(#Schema.globals==32 and #Schema.types+#Schema.arguments==48)
end)
test('candidate troop allocation is proportionate and retains 42 percent capacity for counters',function()
    local f=world();f.set(393,2);f.state.attacks[3]={attacker=2,target=1,troops=4000}
    local p,o=prepared(f);local a=assert(find(Actions.generate(f,o,p),'attack'))
    assert(a.plan.defensive_counter and o.home-a.plan.amount>=42000 and a.plan.amount<5000)
    assert(a.cooldown==1)
end)
test('counterattack holds if capacity floor or incoming reserve leaves insufficient troops',function()
    local f=world();f.set(393,2);f.info.max_troops=200000;f.state.attacks[3]={attacker=2,target=1,troops=4000}
    local p,o=prepared(f);assert(not find(Actions.generate(f,o,p),'attack'))
end)
test('already sufficient army receives no duplicate counter reinforcement',function()
    local f=world();f.set(393,2);f.state.attacks[3]={attacker=2,target=1,troops=4000}
    f.state.attacks[4]={attacker=1,target=2,troops=30000}
    local p,o=prepared(f);assert(not find(Actions.generate(f,o,p),'attack'))
end)
test('allied, protected friend and pending-peace targets do not receive land orders',function()
    for _,mode in ipairs({'ally','friend','peace'}) do
        local f=world();f.set(393,2);local p=Agent.new()
        if mode=='ally' then f.state.allied[1026]=true
        elseif mode=='friend' then p.cooperation:setRoster({{user_id=20,display_name='Enemy',is_friend=true}})
        else f.state.requests[1026]=10 end
        local _,o=prepared(f,p)
        for _,a in ipairs(Actions.generate(f,o,p)) do assert(a.kind~='attack') end
    end
end)
test('active own attack is recalled when the nation becomes protected',function()
    local f=world();f.state.allied[1026]=true;f.state.attacks[4]={attacker=1,target=2,troops=30000}
    local a=assert(Agent.new():decide(f));assert(a.kind=='retreat')
end)
test('arbitrary team counts and opposing-team friends remain distinct',function()
    local f=world();f.info.team=4;f.state.owners[2].team=7;f.state.team_names={'A','B','C','D','E','F','G'}
    local p=Agent.new();p.cooperation:setRoster({{user_id=20,display_name='Enemy',is_friend=true}})
    local _,o=prepared(f,p)
    assert(p.cooperation.status.team_count==7 and not p.cooperation:isFriend(2) and not o.diplomacy[2].same_team)
end)
test('a growing dominant treaty ally adjusts reserves without declaring hostility',function()
    local f=world();f.state.owners[2].troops=120000;f.state.allied[1026]=true;f.set(393,2)
    local p,o=prepared(f);assert(o.reserve>=30000)
    assert(not find(Actions.generate(f,o,p),'attack') and f.state:are_allies(1,2))
end)
test('current spawn can be scored and foreign marks affect spawn evaluation',function()
    local f=world();f.state.phase=0
    assert(Geography.spawnScore(f,f.info.spawn_tile))
    local t=1*32+12;local before=assert(Geography.spawnScore(f,t))
    f.state.owners[2].spawn_tile=t+1
    local after=assert(Geography.spawnScore(f,t));assert(after<before)
end)
test('precise owned interior required for buildings; coast exception is only water for ports',function()
    local f=world();local safe=Geography.safe(f,12*32+5,'city');assert(not safe)
    f.map.k_lin=10
    assert(Geography.safe(f,12*32+5,'city'))
    f.state.flags[12*32+5]=true;assert(not Geography.safe(f,12*32+5,'city'))
end)
test('native and fallback terrain bytes yield the same magnitude',function()
    local f=world();local b=buffer.create(f.map.N);buffer.writeu8(b,400,131)
    f.map.tile_bytes=b;assert(Geography.magnitude(f.map,400)==3)
    f.map.tile_bytes=nil;f.map.bytes=b;assert(Geography.magnitude(f.map,400)==3)
end)
test('sea landings prefer a water crossing over redundant nearby land and avoid dominant human centers',function()
    local f=world();local t=12*32+19;local anchor=f.info.spawn_tile
    function f.map:is_water(p) return self.water[p]==true end
    assert(not Geography.landing(f,t,anchor,false))
    f.map.water[12*32+12]=true;f.state.owners[2].kind=0
    assert(Geography.landing(f,t,anchor,false))
    f.state.owners[2].kind=2;f.state.owners[2].spawn_tile=t;f.state.owners[2].troops=200000
    assert(not Geography.landing(f,t,anchor,false))
end)
test('construction uses the legal upgrade destination and stops post spam',function()
    local f=world();f.map.k_lin=10;f.info.gold=1000000
    f.state.structures[7]={owner=1,kind=0,tile=389,level=2,active_tick=0}
    f.state.attacks[3]={attacker=2,target=1,troops=20000}
    for i=1,3 do f.state.structures[10+i]={owner=1,kind=3,tile=350+i,level=1,active_tick=0} end
    local p,o=prepared(f)
    assert(not find(Actions.generate(f,o,p),'defense'))
end)
test('bounded candidates always retain wait and valid finite feature vectors',function()
    local f=world();f.info.gold=1000000;f.map.k_lin=10
    local p,o=prepared(f);local rows=Actions.generate(f,o,p)
    assert(#rows<=96 and find(rows,'wait'))
    for _,a in ipairs(rows) do for _,v in ipairs(a.features) do assert(v==v and math.abs(v)<math.huge) end end
end)
test('model rejects incompatible OpenFront and malformed weights',function()
    assert(not Neural.validate({version=1,schema='openfront'}))
    assert(not Neural.validate({version=1,schema=Schema.version}))
    local p=Agent.new(nil,{version=1,schema='openfront'})
    assert(not p.weights and p.modelStatus:find('mismatch'))
end)
test('softmax respects probabilities and deterministic selection',function()
    local i,p=Neural.pick({-10,3,2});assert(i==2 and p[2]>p[3])
    local total=0;for _,v in ipairs(p) do total+=v end;assert(math.abs(total-1)<1e-10)
    assert(Neural.pick({0,0},.1)==1 and Neural.pick({0,0},.9)==2)
end)
test('cooldowns and action outcomes refer to sent orders rather than proposals',function()
    local f=world();local p=Agent.new();local a=assert(p:decide(f));p:rejected('changed bank')
    assert(p.metrics.orders==0 and p.blocked)
    p:sent(a,f.now);assert(p.metrics.orders==1 and not p.blocked)
    f.state.tick+=10;f.now+=1;p:decide(f)
    assert(p.observation.context[200]>0 and p.observation.context[201]==0)
end)
test('observation resets history on a different match instead of carrying outcomes across games',function()
    local f=world();local p=Agent.new();p:decide(f);p.lastObservation.land=999999
    p.lastSentKind=9;p.lastSentAt=f.now;p.blocked=true
    local g=world();p:decide(g);assert(p.outcome[1]==0 and p.outcome[4]==0 and p.outcome[5]==0 and p.me==g.me)
end)
test('duplicate authoritative tick cannot produce a second decision',function()
    local f=world();local p=Agent.new();p:decide(f);assert(not p:decide(f))
end)
test('live cadence matches training and reports observation age; elimination bypasses the wait',function()
    local f=world();local p=Agent.new();p:decide(f)
    f.state.tick+=1;f.now+=.1
    assert(not p:decide(f) and not p.evaluated and p:report().observation_age_ticks==1)
    f.info.alive=false
    assert(not p:decide(f) and p.evaluated and p:report().observation_age_ticks==0)
end)
test('confirmed betrayal is tracked while mere expiry is not blamed on an ally',function()
    local f=world();local p=Agent.new();p:decide(f)
    f.state.tick+=10;f.state.alliance_seq=1;f.state.alliance_events={{seq=1,a=1,b=2,breaker=2}}
    p:decide(f);assert(p.distrust[2]==f.now+180)
    f.state.tick+=10;f.state.alliance_seq=2;f.state.alliance_events[2]={seq=2,a=1,b=3,breaker=0,expired=true}
    p:decide(f);assert(p.distrust[3]==nil)
end)
test('campaign budgets and deadlines do not reset with reinforcement',function()
    local f=world();f.set(393,2);local p,o=prepared(f)
    local a=assert(find(Actions.generate(f,o,p),'attack'));p:sent(a,f.now)
    local c=p.campaigns[2];local budget,deadline=c.budget,c.deadline
    p:sent(a,f.now+4);assert(c.budget==budget and c.deadline==deadline and c.spent==a.plan.amount*2)
end)
test('new report exposes candidate ranks and exact observation scope without claiming trained strength',function()
    local f=world();local p=Agent.new();p:decide(f);local r=p:report()
    assert(r.version=='3.1.0' and r.schema==Schema.version and #r.candidates>0 and not r.competitive_strength_verified)
    assert(r.policy:find('no trained model') and #r.context==204 and r.exact_diplomacy)
end)
print('V3 AGENT SCENARIOS',n)
