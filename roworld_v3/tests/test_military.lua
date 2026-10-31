local Agent=require('../agent')
local Infrastructure=require('../infrastructure')
local Arsenal=require('../arsenal')
local Navy=require('../navy')
local Weapons=require('../shared/weapons')
local Mirror=require('../shared/mirror')
local Adapter=require('../shared/adapter')
local fixture=require('./fixture')
local n=0
local function test(name,fn) fn();n+=1;print('PASS',name) end
local function find(rows,kind) for _,a in ipairs(rows) do if a.kind==kind then return a end end end
local function economy()
    local f=fixture();f.map.k_lin=10;f.state.tick=4000;f.state.playing_since=0
    f.info.gold=50000000;f.info.income=100000
    f.map.water[12*32+1]=true;f.refresh()
    local p=Agent.new();local o=p:prepare(f)
    return f,p,o
end
local function weaponWorld(level)
    local m={W=320,H=200,N=64000,k_lin=10}
    function m.dist2(a,b) return (a%320-b%320)^2+(a//320-b//320)^2 end
    function m:is_contestable(t) return t>=0 and t<self.N end
    function m:is_coastal() return false end
    local a,b=100*320+10,100*320+250
    local data={t=100,phase=1,owner=buffer.create(m.N*4),flags=buffer.create(m.N),
        owners={{1,'Us',0,2,0,true,1,100000,100000000,200000,10000,0,a},
            {2,'Enemy',0,2,0,true,1,100000,100000000,200000,10000,0,b}},
        structs={{1,5,1,a,6,0,{}},{2,4,2,b,level or 10,0,{}}}}
    buffer.writei32(data.owner,a*4,1)
    for y=85,115 do for x=230,275 do buffer.writei32(data.owner,(y*320+x)*4,2) end end
    local s=Mirror.snapshot(data,m,1)
    local session={state=s,connected=true,sent={},mode=2,state_mode=2,ownsScatter=true}
    function session:has_unlock(key) return key=='scatter' and self.ownsScatter end
    function session:multiplayer_available() return true end
    function session:send_intent(intent) table.insert(self.sent,intent) end
    local ctx=Mirror.context(session)
    return {state=s,map=m,me=1,info=s.owners[1],ctx=ctx,session=session,now=10,a=a,b=b,
        main={session=session,ui={ctx=ctx}}}
end
local function adapter(f)
    local a=Adapter.new({},nil,function() return f.now end);a.main=f.main;return a
end
test('wealthy mature coastal economy continues cities and ports beyond old level caps',function()
    local f,p,o=economy();o.levels[0]=30;o.levels[1]=45
    local rows=Infrastructure.generate(f,o,p,{389,390})
    assert(find(rows,'city').bias>0 and find(rows,'port').bias>0)
end)
test('factories are early coastal support or an inland fallback, not a permanent coastal gold sink',function()
    local f,p,o=economy();o.levels[0]=4;o.levels[2]=0
    assert(not find(Infrastructure.generate(f,o,p,{389}),'factory'))
    f.state.tick=100
    assert(find(Infrastructure.generate(f,o,p,{389}),'factory'))
    f.state.tick=4000;f.map.water={};f.refresh()
    assert(find(Infrastructure.generate(f,o,p,{389}),'factory'))
end)
test('interior SAM protection is proactive and overlapping batteries stop only after covering assets',function()
    local f,p,o=economy();f.state.structures[1]={kind=0,owner=1,tile=389,level=3,active_tick=0}
    assert(find(Infrastructure.generate(f,o,p,{389}),'sam'))
    f.state.structures[2]={kind=4,owner=1,tile=390,level=7,active_tick=0}
    assert(not find(Infrastructure.generate(f,o,p,{389}),'sam'))
end)
test('construction honors native upgrade_sid and preserves the complete outstanding salvo budget',function()
    local f,p,o=economy();f.state.structures[1]={kind=0,owner=1,tile=389,level=2,active_tick=0}
    function f.ctx.rules:placement(_,t) return {ok=true,tile=t,upgrade_sid=1} end
    local a=assert(find(Infrastructure.generate(f,o,p,{389}),'city'));assert(a.upgrade and a.level==2)
    p.salvoPlan={remaining=3};f.info.gold=20000
    assert(not find(Infrastructure.generate(f,o,p,{389}),'city'))
end)
test('funded economies create several silo slots rather than stopping at one launcher',function()
    local f,p,o=economy();o.levels[0]=3;o.levels[5]=2
    assert(find(Infrastructure.generate(f,o,p,{389}),'silo'))
    o.levels[5]=6;assert(not find(Infrastructure.generate(f,o,p,{389}),'silo'))
end)
test('Scattershot price is fixed while global MIRV escalation remains independent',function()
    local f=weaponWorld();assert(Weapons.cost(f.state,'scatter')==3750000)
    f.state.mirvs_launched=9
    assert(Weapons.cost(f.state,'scatter')==3750000 and Weapons.cost(f.state,'mirv')==160000000)
end)
test('Scattershot requires the owned unlock and an active reloaded silo',function()
    local f=weaponWorld();assert(f.ctx.rules:availability('scatter').ok)
    f.session.ownsScatter=false;assert(not f.ctx.rules:availability('scatter').ok)
    f.session.ownsScatter=true;f.state.structures[1].shots={100,100,100,100,100,100}
    assert(not f.ctx.rules:availability('scatter').ok)
end)
test('overlapping high-level SAMs increase the funded volley; insufficient silo slots block it',function()
    local f=weaponWorld(10);local first=assert(Weapons.scatterAssessment(f.state,1,f.b,6))
    assert(first.count==3 and first.interception_budget>=10)
    f.state.structures[3]={kind=4,owner=2,tile=f.b+2,level=4,active_tick=0,shots={}}
    local next=assert(Weapons.scatterAssessment(f.state,1,f.b,6));assert(next.count>first.count)
    f.state.structures[1].level=1;assert(not Weapons.scatterAssessment(f.state,1,f.b,6))
end)
test('observed SAM cooldown changes the interception budget without treating the SAM as absent',function()
    local f=weaponWorld(10);f.state.structures[1].tile=f.b-10
    local fresh=assert(Weapons.scatterAssessment(f.state,1,f.b,6))
    f.state.structures[2].shots={100,100,100,100,100,100,100,100,100,100}
    local busy=assert(Weapons.scatterAssessment(f.state,1,f.b,6))
    assert(busy.count<fresh.count and busy.sam_levels==10)
end)
test('Scattershot collateral covers the entire child spread, including protected Roblox friends',function()
    local f=weaponWorld();local t=f.b+6;f.state.owners[3]={alive=true,team=0,spawn_tile=t}
    buffer.writei32(f.state.owner,t*4,3);f.state.bot_friend_guard={[3]=true}
    assert(Weapons.blastSafe(f.state,1,f.b,'atom') and not Weapons.blastSafe(f.state,1,f.b,'scatter'))
end)
test('single-SAM suppression offsets aim so the children can actually hit the SAM',function()
    local f=weaponWorld(1);local p=Agent.new();local o=p:prepare(f)
    local a=assert(find(Arsenal.generate(f,o,p),'scatter'))
    assert(a.intent.tile~=f.b and a.plan.salvo.objective_sid==2 and a.plan.salvo.total==1)
end)
test('a whole Scattershot salvo is budgeted before its first launch',function()
    local f=weaponWorld();f.info.gold=8000000;local p=Agent.new();local o=p:prepare(f)
    assert(not find(Arsenal.generate(f,o,p),'scatter'))
end)
test('planned salvos continue through their own flights and finish after a bounded number of launches',function()
    local f=weaponWorld();local p=Agent.new();local o=p:prepare(f)
    local a=assert(find(Arsenal.generate(f,o,p),'scatter'));local total=a.plan.salvo.total
    assert(total==3)
    for i=1,total do
        assert(adapter(f):send(a,f));p:sent(a,f.now)
        f.info.gold-=a.cost;table.insert(f.state.structures[1].shots,f.state.tick)
        f.state.nukes[i]={owner=1,kind=5,from_tile=f.a,to_tile=a.intent.tile,launch_tick=f.state.tick,flight_ticks=200}
        f.now+=1;f.state.tick+=10;o=p:prepare(f)
        if i<total then a=assert(find(Arsenal.generate(f,o,p),'scatter'));assert(a.plan.salvo.sent==i) end
    end
    assert(not p.salvoPlan and not find(Arsenal.generate(f,o,p),'scatter'))
end)
test('a new SAM, alliance, missing objective, depleted treasury or price increase cancels a prepared salvo before sending',function()
    for _,change in ipairs({'sam','ally','objective','funds','price'}) do
        local f=weaponWorld();local p=Agent.new();local o=p:prepare(f)
        local a=assert(find(Arsenal.generate(f,o,p),'scatter'))
        if change=='sam' then f.state.structures[3]={kind=4,owner=2,tile=f.b+1,level=5,active_tick=0,shots={}}
        elseif change=='ally' then f.state.alliances[1026]=true
        elseif change=='objective' then f.state.structures[2]=nil
        elseif change=='funds' then f.info.gold=1000000
        else local original=f.ctx.rules.cost;function f.ctx.rules:cost(kind) return original(self,kind)+(kind=='scatter' and 100000 or 0) end end
        assert(not adapter(f):send(a,f) and #f.session.sent==0)
    end
end)
test('confirmed destruction or capture of the suppression SAM ends the remaining salvo',function()
    local f=weaponWorld();local p=Agent.new();local o=p:prepare(f)
    local a=assert(find(Arsenal.generate(f,o,p),'scatter'));p:sent(a,f.now)
    f.state.structures[2]=nil;f.now+=1;f.state.tick+=10;p:prepare(f)
    assert(not p.salvoPlan and p.lastSalvo)
end)
test('coastal fleet grows beyond the old three-ship cap without overriding repairs',function()
    local f,p,o=economy();f.map.water={}
    for y=0,23 do f.map.water[y*32+1]=true end
    function f.map:is_water(t) return self.water[t]==true end
    function f.map:water_body_of(t) return self:is_water(t) and 1 or 0 end
    f.state.structures[1]={kind=1,owner=1,tile=386,level=1,active_tick=0}
    f.state.structures[2]={kind=1,owner=1,tile=258,level=1,active_tick=0};f.refresh()
    f.state.units={}
    for i=1,3 do f.state.units[i]={owner=1,kind=2,path={385},patrol_tile=385,state=1,hp=500,max_hp=1000} end
    local rows=Navy.generate(f,o,p)
    assert(find(rows,'warship') and p.navalPlan.desired_fleet>=4 and not find(rows,'move_warship'))
end)
print('V3 MILITARY SCENARIOS',n)
