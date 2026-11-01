local Weapons=require('../weapons')
local Mirror=require('../mirror')
local Policy=require('../policy')
local Adapter=require('../adapter')
local Wire=require('../wire')
local count=0
local function test(name,fn) fn();count+=1;print('PASS',name) end
local function world()
    local map={W=320,H=200,N=64000,k_lin=10}
    function map.dist2(a,b) return (a%320-b%320)^2+(a//320-b//320)^2 end
    function map:is_contestable(t) return t>=0 and t<self.N end
    function map:is_coastal(_) return false end
    local a,b=100*320+10,100*320+250
    local data={t=100,phase=1,owner=buffer.create(map.N*4),flags=buffer.create(map.N),
        owners={{1,'Us',0,2,0,true,1,100000,100000000,200000,0,0,a},
            {2,'Enemy',0,2,0,true,1,100000,100000000,200000,0,0,b}},
        structs={{1,5,1,a,1,0,{}},{2,5,2,b,1,0,{}}}}
    buffer.writei32(data.owner,a*4,1);buffer.writei32(data.owner,b*4,2)
    local s=Mirror.snapshot(data,map,1)
    local session={state=s,connected=true,sent={},mode=2,state_mode=2}
    function session:multiplayer_available() return true end
    function session:send_intent(intent) table.insert(self.sent,intent) end
    local ctx=Mirror.context(session)
    return {state=s,map=map,me=1,info=s.owners[1],ctx=ctx,now=10,session=session,
        main={session=session,ui={ctx=ctx}},a=a,b=b}
end
local function adapter(f)
    local a=Adapter.new({},function() error('Must reuse session') end,function() return f.now end)
    a.main=f.main;return a
end
test('all three weapons require gold and a reloaded active silo',function()
    local f=world();local s=f.state
    for _,kind in ipairs({'atom','hydrogen','mirv'}) do
        assert(f.ctx.rules:availability(kind).ok and Weapons.canLaunch(s,1,f.b,kind))
    end
    s.structures[1].shots={100}
    assert(not f.ctx.rules:availability('atom').ok)
    s.tick=190;assert(f.ctx.rules:availability('atom').ok)
    s.structures[1].active_tick=200;assert(not f.ctx.rules:availability('atom').ok)
end)
test('snapshot and deltas preserve nuclear launches, reload stamps and global MIRV price',function()
    local f=world();local s=f.state
    Mirror.delta(s,{t=101,ev={{12,9,2,2,f.b,f.a,101,90},{32,1,{101}}}})
    assert(s.nukes[9].kind==2 and s.nukes[9].flight_ticks==90 and s.mirvs_launched==1)
    assert(f.ctx.rules:cost('mirv')==40000000 and not f.ctx.rules:availability('atom').ok)
    Mirror.delta(s,{t=102,ev={{29,3,9,102,110,true}}});assert(s.nukes[9].sam_sid==3)
    Mirror.delta(s,{t=103,ev={{13,9,2,f.a,0,2}}});assert(not s.nukes[9])
end)
test('hydrogen safety covers its larger blast rather than the atom radius',function()
    local f=world();buffer.writei32(f.state.owner,(f.b+8)*4,1)
    assert(Weapons.blastSafe(f.state,1,f.b,'atom'))
    assert(not Weapons.blastSafe(f.state,1,f.b,'hydrogen'))
end)
test('MIRV safety includes the spread and warhead radius and excludes allied collateral',function()
    local f=world();local t=f.b-150
    f.state.owners[3]={alive=true,team=0,spawn_tile=t};f.state.alliances[1027]=true
    buffer.writei32(f.state.owner,t*4,3)
    assert(not Weapons.blastSafe(f.state,1,f.b,'mirv'))
    assert(Weapons.blastSafe(f.state,1,f.b,'hydrogen'))
end)
test('hostile SAM coverage blocks atom and hydrogen while the MIRV carrier bypasses it',function()
    local f=world();f.state.structures[4]={owner=2,kind=4,tile=f.b,level=1,active_tick=0,shots={}}
    assert(not Weapons.canLaunch(f.state,1,f.b,'atom'))
    assert(not Weapons.canLaunch(f.state,1,f.b,'hydrogen'))
    assert(Weapons.canLaunch(f.state,1,f.b,'mirv'))
    f.state.alliances[1026]=true;assert(not Weapons.canLaunch(f.state,1,f.b,'mirv'))
end)
test('SAMs belonging to third parties and near the launch site also count',function()
    local f=world();f.state.owners[3]={alive=true,team=0,spawn_tile=-1}
    f.state.structures[4]={owner=3,kind=4,tile=f.a+2,level=1,active_tick=0,shots={100}}
    assert(Weapons.blocked(f.state,1,f.a,f.b,'atom'))
    f.state.alliances[1027]=true
    assert(not Weapons.blocked(f.state,1,f.a,f.b,'atom'))
end)
test('a fresh SAM or ally change cancels a planned launch at send time',function()
    for _,change in ipairs({'sam','ally','cooldown'}) do
        local f=world();local a=adapter(f);local view=assert(a:frame())
        assert(Weapons.canLaunch(f.state,1,f.b,'hydrogen'))
        if change=='sam' then f.state.structures[9]={owner=2,kind=4,tile=f.b,level=1,active_tick=0,shots={}}
        elseif change=='ally' then f.state.alliances[1026]=true
        else f.state.structures[1].shots={100} end
        assert(not a:send({intent={type='nuke',kind='hydrogen',tile=f.b}},view))
        assert(#f.session.sent==0)
    end
end)
test('launch policy uses atom for a valuable isolated target and hydrogen for a larger cluster',function()
    local f=world();f.state.structures[2].kind=4
    -- Target SAMs are interception risks, not an isolated easy kill.
    assert(not Policy.new():strike(f))
    f.state.structures[2].kind=5
    assert(Policy.new():strike(f).intent.kind=='atom')
    for i,delta in ipairs({8,-8,8*320,-8*320,6+6*320,6-6*320,-6+6*320,-6-6*320}) do
        local t=f.b+delta
        f.state.structures[i+2]={owner=2,kind=5,tile=t,level=1,active_tick=0,shots={}}
        buffer.writei32(f.state.owner,t*4,2)
    end
    assert(Policy.new():strike(f).intent.kind=='hydrogen')
end)
test('MIRV is selectable for a large defended country and respects its escalating cost',function()
    local f=world();local n=3
    for y=30,170,20 do for x=110,290,20 do
        local t=y*320+x;f.state.structures[n]={owner=2,kind=5,tile=t,level=1,active_tick=0,shots={}}
        buffer.writei32(f.state.owner,t*4,2);n+=1
    end end
    f.state.structures[1000]={owner=2,kind=4,tile=f.b,level=30,active_tick=0,shots={}}
    local a=assert(Policy.new():strike(f));assert(a.intent.kind=='mirv')
    f.state.mirvs_launched=10;assert(not f.ctx.rules:availability('mirv').ok)
end)
test('the policy does not fire another missile at an existing strike or waste gold on cheap targets',function()
    local f=world();f.state.nukes[9]={owner=1,kind=0,from_tile=f.a,to_tile=f.b,launch_tick=100,flight_ticks=100}
    assert(not Policy.new():strike(f))
    f.state.nukes={};f.state.structures[2].kind=0
    assert(not Policy.new():strike(f))
end)
test('proactive SAM construction covers infrastructure and obeys the inland setback',function()
    local f=world()
    for t=0,f.map.N-1 do buffer.writei32(f.state.owner,t*4,1) end
    f.state.structures[2].owner=1;f.state.structures[2].kind=0
    f.state.structures[3]={owner=1,kind=2,tile=f.b+10,level=1,active_tick=0,shots={}}
    f.state.structures[4]={owner=2,kind=5,tile=f.b+100,level=1,active_tick=0,shots={}}
    local p=Policy.new();local action=assert(p:economy(f,{f.b-3,f.b+20},{incoming=0,home=100000}))
    assert(action.intent.kind=='sam' and p:siteSafe(f,action.intent.tile,'sam'))
end)
test('a running strike prevents accepting an alliance with the endangered nation',function()
    local f=world();f.state.nukes[9]={owner=1,kind=1,to_tile=f.b}
    assert(not Weapons.allianceSafe(f.state,1,2))
    local a=adapter(f);local view=assert(a:frame());f.state.requests[2049]=100
    assert(not a:send({intent={type='ally_reply',target=2,accept=true}},view))
end)
test('enemy silo construction and readiness are distinguished in threat reports',function()
    local f=world();f.state.structures[2].active_tick=200
    local t=Weapons.threat(f.state,1)
    assert(t.hostile_silos==1 and t.building_silos==1 and t.ready_silos==0)
    f.state.tick=200;assert(Weapons.threat(f.state,1).ready_silos==1)
    f.state.structures[2].shots={200};assert(Weapons.threat(f.state,1).ready_silos==0)
    local p=Policy.new();p:reset(f);assert(p:report().nuclear_threat.hostile_silos==1)
end)
test('fallout updates count zones and prevent wasting a missile on a ruined target',function()
    local f=world();assert(f.state.fallout_count==0)
    Mirror.delta(f.state,{t=101,flags={f.b*256+1}})
    assert(f.state.fallout_count==1 and not Weapons.canLaunch(f.state,1,f.b,'atom'))
    Mirror.delta(f.state,{t=102,flags={f.b*256+1}});assert(f.state.fallout_count==1)
    Mirror.delta(f.state,{t=103,flags={f.b*256}});assert(f.state.fallout_count==0)
end)
test('new construction moves outside the blast footprint of an incoming missile',function()
    local f=world();for t=0,f.map.N-1 do buffer.writei32(f.state.owner,t*4,1) end
    f.state.nukes[9]={owner=2,kind=1,to_tile=f.b,launch_tick=100,flight_ticks=100}
    local action=assert(Policy.new():build(f,{f.b,f.b+25},'city',{}))
    assert(action.intent.tile==f.b+25)
    local a=adapter(f);local view=assert(a:frame())
    assert(not a:send({intent={type='build',kind='city',tile=f.b},safety={margin=18}},view))
end)
test('imminent strike hazards differ from distant warnings and clear after detonation',function()
    local f=world();f.state.nukes[9]={owner=2,kind=0,to_tile=f.b,launch_tick=100,flight_ticks=100}
    assert(Weapons.hazard(f.state,f.b,0) and not Weapons.hazard(f.state,f.b,0,3))
    f.state.tick=175;assert(Weapons.hazard(f.state,f.b,0,3))
    Mirror.delta(f.state,{t=176,ev={{13,9,0,f.b,1,2}}})
    assert(not Weapons.hazard(f.state,f.b,0))
end)
print('WEAPON TESTS',count)
