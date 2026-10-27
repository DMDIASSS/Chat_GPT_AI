local Core=require('../core')
local Policy=require('../policy')
local Mirror=require('../mirror')
local count=0
local function test(name,fn) fn();count+=1;print('PASS',name) end
local function world()
    local w,h=256,128;local home=60*w+16;local remote=60*w+218
    local raw=buffer.create(w*h);buffer.fill(raw,0,128)
    local data={t=100,phase=1,map_w=w,map_h=h,owner=buffer.create(w*h*4),flags=buffer.create(w*h),
        owners={{1,'Us',0,2,0,true,1,50000,0,100000,0,0,home},
            {2,'Near human',0,2,0,true,1,40000,0,100000,0,0,-1},
            {3,'Remote country',0,0,0,true,1,1000,0,10000,0,0,-1}},
        structs={{1,0,1,home,1,0,{}},{2,2,1,home-2,1,0,{}},{3,1,1,remote,1,0,{}}}}
    local function set(t,id) buffer.writei32(data.owner,t*4,id) end
    for y=52,68 do for x=10,22 do set(y*w+x,1) end end
    for y=52,68 do for x=210,226 do set(y*w+x,1) end end
    local map=Mirror.map({width=w,height=h,k_lin=5},raw,data)
    local s=Mirror.snapshot(data,map,1);local session={state=s,connected=true}
    local ctx=Mirror.context(session)
    return {state=s,map=map,me=1,info=s.owners[1],ctx=ctx,now=10,home=home,remote=remote,set=set}
end
local function troops(f)
    return {home=f.info.troops,reserve=f.info.troops*.35,available=f.info.troops*.65,
        incoming=0,outgoing={},enemyActive=0,neutralActive=0,targets={}}
end

test('selects the valuable building cluster instead of an isolated remote port',function()
    local f=world();local c=Core.new();local summary=c:update(f)
    assert(f.map.dist2(summary.center_tile,f.home)<10 and summary.asset_value>=15)
    assert(c:priority(f.map,f.home)>c:priority(f.map,f.remote))
end)
test('retains original home protection when the economic center moves elsewhere',function()
    local f=world()
    for i=4,8 do f.state.structures[i]={owner=1,kind=0,tile=f.remote+i,level=3} end
    local c=Core.new();local r=c:update(f)
    assert(f.map.dist2(r.center_tile,f.remote)<100 and #r.anchors==2)
    assert(c:isSite(f.map,f.home) and c:isSite(f.map,f.remote))
end)
test('a lost home switches protection to owned assets without pursuing an empty enemy island',function()
    local f=world();local c=Core.new();c:update(f)
    for y=52,68 do for x=10,22 do f.set(y*256+x,2) end end
    f.state.structures[1].owner=2;f.state.structures[2].owner=2
    local r=c:update(f)
    assert(not r.home_owned and f.state:tile_owner(r.center_tile)==1)
    assert(f.map.dist2(r.center_tile,f.remote)<10)
end)
test('local cleanup is found even when the rotating border page contains only a remote outpost',function()
    local f,p=world(),Policy.new()
    table.clear(f.ctx.borders.border);f.ctx.borders.border[f.remote+8]=true
    local action=assert(p:decide(f))
    assert(action.intent.type=='attack' and f.state:tile_owner(action.intent.tile)==0)
    assert(p.strategy:corePriority(f,action.intent.tile)>0)
    assert(f.map.dist2(action.intent.tile,f.home)<30^2)
end)
test('pressure at the core raises reserves and recalls a distant raid first',function()
    local f,p=world(),Policy.new();local breach=f.home+6
    f.set(breach,2);f.state.attacks[20]={aid=20,attacker=2,target=1,troops=12000,anchor_tile=breach}
    f.state.attacks[21]={aid=21,attacker=1,target=3,troops=15000,anchor_tile=f.remote+12}
    local action=assert(p:decide(f));local report=p:report()
    assert(action.intent.type=='retreat' and action.intent.attack_id==21)
    assert(report.strategy.core.at_risk and report.strategy.core.critical)
    assert(report.timeline[1].reserve>=f.info.troops*.65)
end)
test('distant new wars are blocked while useful territory around home needs clearing',function()
    local f,p=world(),Policy.new();p:reset(f);p.strategy:updateCore(f)
    assert(p.strategy.core.summary.needs_buffer)
    assert(not p.strategy:canTarget(f,3,troops(f)))
    local near=f.home+7;f.set(near,2);f.state.owners[2].kind=1;f.state.owners[2].troops=1000
    p.strategy:updateCore(f)
    assert(p.strategy:canTarget(f,2,troops(f)))
end)
test('new economic construction favors the established core over detached labels',function()
    local f,p=world(),Policy.new();f.info.gold=1000000;f.info.label_tile=f.remote
    p:reset(f);p.strategy:updateCore(f)
    local action=assert(p:build(f,{f.remote,f.home},'city',{}))
    assert(f.map.dist2(action.intent.tile,f.home)<10)
end)
test('defenses cover the important area instead of a distant expansion',function()
    local f,p=world(),Policy.new();f.info.gold=1000000
    p:reset(f);p.strategy:updateCore(f)
    local homeSite=56*256+18;local remoteSite=56*256+220
    local action=assert(p:build(f,{remoteSite,homeSite},'defense',{}))
    assert(action.intent.tile==homeSite)
end)
test('sudden loss inside the stable core triggers an emergency even with no incoming army row',function()
    local f=world();local c=Core.new();c:update(f)
    for y=52,68 do for x=10,22 do if x<14 or x>18 or y<58 or y>62 then f.set(y*256+x,2) end end end
    f.now+=5;local r=c:update(f)
    assert(r.critical and r.at_risk and r.incoming==0)
end)
test('invalid attack anchors are never treated as locations inside a core',function()
    local f=world();local c=Core.new();c:update(f)
    assert(not c:isSite(f.map,-1) and not c:isSite(f.map,nil))
end)
test('core diagnostics include the original home, economic center and sampled buffer state',function()
    local f,p=world(),Policy.new();p:decide(f)
    local c=p:report().strategy.core
    assert(c.home_tile==f.home and c.home_owned and c.center_tile and c.clearable_tiles>0)
    assert(c.neutral_samples>0 and c.owned_samples>0 and c.owned_fraction<1)
end)
test('hostile transport approaches to the core trigger reserves before a land attack exists',function()
    local f,p=world(),Policy.new()
    f.state.units[9]={uid=9,kind=0,owner=2,path={f.home+8},start_tick=100,ticks_per_tile_x100=100,troops=15000}
    p:decide(f);local r=p:report()
    assert(r.strategy.core.hostile_transports==1 and r.strategy.core.naval_incoming==15000)
    assert(r.strategy.core.critical and r.timeline[1].reserve>=f.info.troops*.65)
end)
test('allied transports do not create a false core invasion warning',function()
    local f=world();f.state.alliances[1026]=true
    f.state.units[9]={kind=0,owner=2,path={f.home+8},start_tick=100,ticks_per_tile_x100=100,troops=50000}
    local c=Core.new();local r=c:update(f)
    assert(r.hostile_transports==0 and not r.at_risk)
end)
test('a port near core buildings is preferred for a new patrol over a detached port',function()
    local f,p=world(),Policy.new();p:reset(f);p.strategy:updateCore(f)
    f.state.structures[4]={kind=1,owner=1,tile=f.home+3,active_tick=0}
    function f.map:is_water(t) return t==f.home+4 or t==f.remote+1 end
    function f.ctx.rules:availability(kind) return {ok=kind=='warship'} end
    function f.ctx.rules:placement(_,t) return {ok=true,tile=t} end
    function f.ctx.rules:cost(_) return 250000 end
    f.info.gold=1000000
    local action=assert(p:fleet(f,{}))
    assert(action.intent.kind=='warship' and action.intent.tile==f.home+4)
end)
print('CORE TESTS',count)
