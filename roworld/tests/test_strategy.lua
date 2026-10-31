local Strategy=require('../strategy')
local Policy=require('../policy')
local Adapter=require('../adapter')
local fixture=require('./fixture')
local n=0
local function test(name,fn) fn();n+=1;print('PASS',name) end
local function armies(home)
    return {home=home,reserve=home*.35,available=home*.65,incoming=0,outgoing={},enemyActive=0,neutralActive=0,targets={}}
end
local function front(f,id,tile) f.set(tile,id);f.refresh();return {id=id,tile=tile,front=1,tiles={tile}} end
local function blockNeutral(f) for t=0,f.map.N-1 do if f.state:tile_owner(t)==0 then f.state.flags[t]=true end end end
local function adapter(f) local a=Adapter.new({},function() error('reuse session') end,function() return f.now end);a.main=f.main;return a end

test('alliance requests prevent the report regression of requesting then attacking',function()
    local f,p=fixture(),Policy.new();f.state.owners[2].kind=2;p:reset(f)
    p:sent({intent={type='ally_request',target=2},channel='diplomacy',cooldown=35,label='Ask'},f.now)
    f.now+=3.3
    assert(not p.strategy:canTarget(f,2,armies(50000)))
    f.state.requests[1026]=1
    local a=adapter(f);local view=assert(a:frame());f.set(393,2)
    assert(not a:send({intent={type='attack',tile=393,ratio=.1}},view))
    f.now+=50;assert(not p.strategy:canTarget(f,2,armies(50000)))
    f.state.requests={};assert(p.strategy:canTarget(f,2,armies(50000)))
end)
test('the same army is more cautious against a human than a country',function()
    local f,p=fixture(),Policy.new();f.state.owners[2].troops=20000;f.state.owners[2].kind=2;f.info.max_troops=50000
    front(f,2,393);blockNeutral(f)
    local action=p:decide(f);assert(not action or action.intent.type~='attack')
    f.state.owners[2].kind=0
    assert(p:decide(f).intent.type=='attack')
end)
test('several nearby humans raise reserves and appear in the board view',function()
    local f=fixture();f.state.owners[2].kind=2;f.state.owners[2].troops=60000
    f.state.owners[3]={kind=2,troops=50000,alive=true,tiles=100}
    local s=Strategy.new(f);local a=armies(100000)
    local b=s:updateBoard(f,{[2]={},[3]={}},a)
    assert(b.human_neighbours==2 and b.largest_human==60000 and a.reserve>=45000)
    assert(#b.leaders==2)
end)
test('losing land triggers recovery and recall without mistaking our own send for damage',function()
    local f=fixture();local s=Strategy.new(f);local a=armies(50000)
    f.info.tiles=100;s:updateBoard(f,{},a)
    f.now+=6;f.info.troops=30000;s:updateBoard(f,{},armies(30000));assert(not s.board.recover)
    f.now+=1;f.info.tiles=75
    a=armies(30000);a.outgoing={{aid=10,target=2,troops=15000}}
    s:updateBoard(f,{},a);assert(s.board.recover and not s:canTarget(f,2,a))
    assert(s:review(f,a).intent.attack_id==10)
end)
test('human reinforcements are paced and stop when a campaign stalls',function()
    local f=fixture();f.state.owners[2].kind=2;f.set(393,2)
    local s=Strategy.new(f);local a=armies(50000)
    local action={intent={type='attack',tile=393,ratio=.03}}
    s:sent(action,f.state,1,f.now);f.now+=3
    assert(not s:canTarget(f,2,a))
    f.now+=5;assert(s:canTarget(f,2,a))
    s:sent(action,f.state,1,f.now);f.now+=8;s:sent(action,f.state,1,f.now)
    f.now+=12;assert(not s:canTarget(f,2,a))
    a.outgoing={{aid=10,target=2,troops=10000}}
    assert(s:review(f,a).intent.type=='retreat')
    f.now+=60;assert(s:canTarget(f,2,armies(50000)))
end)
test('a captured country building is a bankable raid gain with a cooldown',function()
    local f=fixture();f.state.owners[2].kind=0;f.set(393,2)
    f.state.structures[8]={sid=8,kind=1,owner=2,tile=393,level=1}
    local s=Strategy.new(f);s:sent({intent={type='attack',tile=393,ratio=.1}},f.state,1,f.now)
    f.state.structures[8].owner=1;f.now+=10;s:observe(f)
    s.board.human_neighbours=1
    local a=armies(50000);a.outgoing={{aid=10,target=2,troops=10000}}
    local action=assert(s:review(f,a));assert(action.intent.type=='retreat')
    f.state.attacks[10]=a.outgoing[1];s:sent(action,f.state,1,f.now)
    assert(not s:canTarget(f,2,a))
end)
test('country defensive counter amount follows its thresholds and clamps',function()
    assert(Strategy.countryCounter(100,10000)==0)
    assert(Strategy.countryCounter(200,10000)==500)
    assert(Strategy.countryCounter(1000,10000)==1250)
    assert(Strategy.countryCounter(5000,10000)==4000)
    assert(Strategy.countryCounter(9500,10000)==0)
end)
test('nearby visible country assets improve the raid objective without inventing buildings',function()
    local f=fixture();local s=Strategy.new(f)
    local g={id=2,tile=393,front=2,tiles={393,425}}
    assert(s:assetOpportunity(f,g)==0)
    f.state.structures[3]={sid=3,kind=1,owner=2,tile=426,level=1}
    local value,tile,sid=s:assetOpportunity(f,g)
    assert(value>0 and tile==425 and sid==3)
end)
test('country alliances with a dominant neighbour still require a defensive margin',function()
    local f=fixture();f.state.owners[2].kind=0;f.state.owners[2].troops=400000;f.state.allied[1026]=true
    local s=Strategy.new(f);local a=armies(100000);local b=s:updateBoard(f,{},a,{}, {[2]=true})
    assert(b.unreliable_ally_pressure==48000 and a.reserve>=48000)
end)
test('first-city savings survive moderate pressure, with emergency defense still permitted',function()
    local f,p=fixture(),Policy.new()
    for t=0,f.map.N-1 do f.set(t,1) end
    function f.ctx.rules:cost(kind) return kind=='defense' and 50000 or 125000 end
    f.info.gold=100000
    assert(not p:economy(f,{f.info.label_tile},{incoming=25000,home=100000}))
    f.info.gold=125000
    assert(p:economy(f,{f.info.label_tile},{incoming=25000,home=100000}).intent.kind=='city')
    f.info.gold=100000
    assert(p:economy(f,{f.info.label_tile},{incoming=70000,home=100000}).intent.kind=='defense')
end)
test('spawn density counts human players rather than AI countries',function()
    local f,p=fixture(),Policy.new();for t=0,f.map.N-1 do f.set(t,0) end
    local tile=12*32+10;local country=f.state.owners[2];country.spawn_tile=12*32+20;country.kind=0
    local score,detail=p:spawnScore(f,tile);assert(detail.nearby_players==0)
    country.kind=2
    local human,humanDetail=p:spawnScore(f,tile)
    assert(human<score and humanDetail.nearby_players==1)
end)
test('players on opposite sides are worse than an otherwise similar single-sided start',function()
    local f,p=fixture(),Policy.new();for t=0,f.map.N-1 do f.set(t,0) end
    f.state.owners[2].kind=2;f.state.owners[2].spawn_tile=12*32+23
    f.state.owners[3]={kind=2,alive=true,spawned=true,spawn_tile=12*32+1,troops=1000}
    local surrounded,d=p:spawnScore(f,12*32+12);assert(d.opposing_player_sectors>0)
    f.state.owners[3].alive=false
    assert(p:spawnScore(f,12*32+12)>surrounded)
end)
test('board history is bounded and the match report includes strategy and owner kinds',function()
    local f,p=fixture(),Policy.new();p:decide(f)
    for i=1,130 do f.now+=5;p.strategy:updateBoard(f,{},armies(50000)) end
    local r=p:report();assert(#r.timeline==120 and r.strategy.mode=='develop')
    f.state.owners[2].kind=0;f.set(393,2)
    p:sent({intent={type='attack',tile=393,ratio=.1},channel='attack',cooldown=2,label='Raid'},f.now)
    assert(p:report().recent_orders[1].target==2 and p:report().recent_orders[1].target_kind==0)
end)
test('a clearly better opportunity ends an old stalled front before opening the next',function()
    local f,p=fixture(),Policy.new();f.info.max_troops=50000
    f.state.owners[2].kind=0
    f.state.owners[3]={kind=0,alive=true,troops=1000,name='Port country'}
    front(f,2,393);front(f,3,425);blockNeutral(f)
    f.state.structures[3]={sid=3,owner=3,kind=1,tile=425,level=1,active_tick=0}
    p:reset(f)
    p.strategy:sent({intent={type='attack',tile=393,ratio=.04}},f.state,1,f.now)
    f.state.attacks[10]={aid=10,attacker=1,target=2,troops=2000}
    f.now+=9
    local action=assert(p:decide(f))
    assert(action.intent.type=='retreat' and action.intent.attack_id==10)
    assert(#p:report().strategy.candidates>0)
end)
test('reachable remote human ports contribute to the larger strategic picture',function()
    local f=fixture();f.state.owners[2].kind=2;f.state.owners[2].troops=500000
    f.state.structures[2]={kind=1,owner=2,tile=393}
    function f.ctx.borders:has_coast() return true end
    function f.ctx.borders:can_reach_by_sea(_) return true end
    local s=Strategy.new(f);local b=s:updateBoard(f,{},armies(50000))
    assert(b.naval_pressure==10000 and b.leaders[1].nation==2)
end)
print('STRATEGY TESTS',n)
