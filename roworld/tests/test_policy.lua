local Policy = require("../policy")
local fixture = require("./fixture")
local tests = 0
local function test(name, run)
    run(); tests += 1; print("PASS", name)
end

test("expands with bounded troop commitment and cooldown", function()
    local f, p = fixture(), Policy.new()
    local a = assert(p:decide(f))
    assert(a.intent.type == "attack" and f.state:tile_owner(a.intent.tile) == 0)
    assert(a.intent.ratio > 0 and f.info.troops * (1-a.intent.ratio) >= a.reserve)
    p:sent(a,f.now)
    local nextOrder = p:decide(f)
    assert(nextOrder == nil)
    f.now += 3
    assert(p:decide(f))
end)
test("attacks an affordable bordering enemy when neutral growth is blocked, never an ally", function()
    local f, p = fixture(), Policy.new()
    f.set(12*32+9,2); f.refresh()
    for t=0,f.map.N-1 do if f.state:tile_owner(t)==0 then f.state.flags[t]=true end end
    local a = assert(p:decide(f))
    assert(f.state:tile_owner(a.intent.tile) == 2)
    f.state.allied[1026] = true
    local other = p:decide(f)
    assert(not other or not other.intent.tile or f.state:tile_owner(other.intent.tile) ~= 2)
end)
test("recalls outgoing troops under a large incoming attack", function()
    local f, p = fixture(), Policy.new()
    f.state.attacks[11] = {aid = 11, attacker = 1, target = 2, troops = 20000}
    f.state.attacks[12] = {aid = 12, attacker = 2, target = 1, troops = 45000}
    local a = assert(p:decide(f))
    assert(a.intent.type == "retreat" and a.intent.attack_id == 11)
    f.state.attacks[11] = nil
    local idle, text = p:decide(f)
    assert(idle == nil and text:find("Defending"))
end)
test("builds a city then a factory using observed construction", function()
    local f, p = fixture(), Policy.new()
    for y=1,22 do for x=1,24 do f.set(y*32+x,1) end end
    f.refresh()
    f.info.gold = 50000
    local a = assert(p:decide(f)); assert(a.intent.type == "build" and a.intent.kind == "city")
    p:sent(a,f.now)
    f.state.structures[1] = {owner = 1, kind = 0, tile = a.intent.tile, level = 1, active_tick = 100}
    f.now += 7
    local b = assert(p:decide(f)); assert(b.intent.type == "build" and b.intent.kind == "factory")
end)
test("economic buildings wait for an interior and ports keep a land setback",function()
    local f,p=fixture(),Policy.new();f.info.gold=1000000
    assert(not p:build(f,{8*32+2},"city",{}))
    for y=1,22 do for x=1,24 do f.set(y*32+x,1) end end
    local center=12*32+12
    assert(p:build(f,{center},"city",{}))
    f.set(center+1,2);p.siteCache={}
    assert(not p:build(f,{center},"city",{}))
    f.set(center+1,0);f.map.water[center+1]=true;p.siteCache={}
    assert(not p:siteSafe(f,center,"city"))
    assert(p:siteSafe(f,center,"port"))
end)
test("threat memory counts distinct attacks rather than guessing from spending",function()
    local f,p=fixture(),Policy.new();p:reset(f);p:observe(f)
    f.state.tick+=1;f.state.owners[2].troops=100;p:observe(f)
    assert(p.opponents[2].heat==0)
    f.state.attacks[9]={attacker=2,target=1,troops=50};f.state.tick+=1;p:observe(f)
    assert(p.opponents[2].heat==1)
    f.state.tick+=1;p:observe(f);assert(p.opponents[2].heat<=1)
    local r=p:report();assert(r.recent_threats[1].nation==2 and r.metrics.orders==0)
end)
test("forecast charges more for a defended front",function()
    local f,p=fixture(),Policy.new();p:reset(f);p:observe(f)
    local g={id=2,tile=12*32+9,front=1}
    local mag=p:frontCost(f,g)
    f.state.structures[3]={owner=2,kind=3,tile=g.tile,active_tick=0}
    assert(p:frontCost(f,g)>mag)
end)
test("a target's nearby allies count as counterattack risk",function()
    local f,p=fixture(),Policy.new();p:reset(f)
    f.state.owners[3]={alive=true,troops=200000,name="Coalition"};f.state.allied[2*1024+3]=true
    assert(p:coalitionPressure(f,2,{[3]={}})==70000)
    f.state.allied[1*1024+3]=true
    assert(p:coalitionPressure(f,2,{[3]={}})==0)
end)
test("does not start a second enemy war while an attack is running",function()
    local f,p=fixture(),Policy.new();f.set(12*32+9,2);f.refresh()
    f.state.owners[3]={alive=true,troops=100,name="Other"}
    f.state.attacks[5]={aid=5,attacker=1,target=3,troops=2000}
    local a=p:decide(f)
    assert(not a or a.intent.type~="attack" or f.state:tile_owner(a.intent.tile)~=2)
end)
test("traitor requests are declined and betrayal never breaks team alliances",function()
    local f,p=fixture(),Policy.new();p:reset(f)
    f.state.requests[2*1024+1]=f.state.tick;f.state.owners[2].traitor_until=100
    local a=p:diplomacy(f,{},p:armies(f,{}));assert(a.intent.type=="ally_reply" and not a.intent.accept)
    f.state.requests={};f.state.allied[1026]=true;f.info.team=1;f.state.owners[2].team=1
    f.info.troops=1000000;p.adjacentAllies={[2]=true}
    assert(not p:diplomacy(f,{},p:armies(f,{})))
    f.state.owners[2].team=0
    assert(p:diplomacy(f,{},p:armies(f,{})).intent.type=="ally_break")
end)
test("spawn scoring prefers flat open land away from human starts",function()
    local f,p=fixture(),Policy.new();f.state.owners[2].kind=2
    for t=0,f.map.N-1 do f.set(t,0) end
    local near=12*32+16;local far=12*32+3
    assert(p:spawnScore(f,far)>p:spawnScore(f,near))
    local before=p:spawnScore(f,far);f.map.terrain=buffer.create(f.map.N);buffer.fill(f.map.terrain,0,4)
    assert(p:spawnScore(f,far)<before)
end)
test("chooses an unclaimed spawn without treating an eliminated owner as respawnable", function()
    local f, p = fixture(), Policy.new()
    f.info.spawned = false; f.state.phase = 0
    local a = assert(p:decide(f)); assert(a.intent.type == "spawn")
    assert(f.map:is_contestable(a.intent.tile) and f.state:tile_owner(a.intent.tile) == 0)
    f.info.alive = false
    local b, text = p:decide(f); assert(not b and text:find("Eliminated"))
end)
test("accepts a real incoming alliance request", function()
    local f, p = fixture(), Policy.new()
    f.set(393,2);f.refresh()
    f.state.requests[2*1024+1] = f.state.tick
    local a = assert(p:decide(f))
    assert(a.intent.type == "ally_reply" and a.intent.target == 2 and a.intent.accept)
end)
test("skips fallout and does not resend a running neutral attack without surplus", function()
    local f, p = fixture(), Policy.new()
    f.state.attacks[7] = {aid = 7, attacker = 1, target = 0, troops = 10000}
    local a = p:decide(f); assert(a == nil)
    f.state.attacks = {}
    for t = 0, f.map.N-1 do if f.state:tile_owner(t) == 0 then f.state.flags[t] = true end end
    local b = p:decide(f); assert(b == nil)
end)
test("new local owner resets cooldowns and old front cursor", function()
    local f, p = fixture(), Policy.new()
    local a = assert(p:decide(f)); p:sent(a,f.now)
    local second = fixture()
    assert(p:decide(second))
end)
test("a coastal landing uses only a reachable nonfriendly coast", function()
    local f, p = fixture(), Policy.new()
    for y = 0, f.map.H-1 do f.map.water[y*32+20] = true end
    f.refresh()
    local a = assert(p:naval(f,{incoming = 0, home = 50000, available = 30000, reserve = 20000}))
    assert(a.intent.type == "boat" and f.map:is_coastal(a.intent.tile))
    assert(a.intent.ratio <= .25)
end)
test("blast scan rejects allied and own land in the full exclusion radius", function()
    local f, p = fixture(), Policy.new()
    assert(not p:blastSafe(f,12*32+9))
    for t = 0, f.map.N-1 do f.set(t,2) end
    assert(p:blastSafe(f,12*32+9))
    f.set(12*32+10,3); f.state.allied[1027] = true
    assert(not p:blastSafe(f,12*32+9))
end)
test("recruitment optimum follows capacity and maximizes the actual shaped curve",function()
    local p=Policy.new()
    for _,cap in ipairs({1000,10000,100000,1000000}) do
        local target=p:growthTarget({max_troops=cap})
        local function rate(h) return (h^.73/4+10)*(1-h/cap) end
        for i=0,1000 do assert(rate(target)+1e-6>=rate(cap*i/1000)) end
        assert(target>cap*.3 and target<cap*.423)
    end
end)
test("neutral spending varies continuously and preserves growth under low and high banks",function()
    local f,p=fixture(),Policy.new()
    local ratios={}
    for _,home in ipairs({10000,60000,95000}) do
        f.info.troops=home
        local a={home=home,reserve=home*.35}
        local amount,reserve=p:attackAmount(f,a,0,true)
        assert(amount and home-amount>=reserve and amount>=home*.01)
        table.insert(ratios,amount/home)
    end
    assert(ratios[3]>.55 and ratios[3]>ratios[1] and ratios[1]~=ratios[2])
end)
test("growth preference never authorizes an attack that violates defensive reserves",function()
    local f,p=fixture(),Policy.new();f.info.troops=90000
    local amount=p:attackAmount(f,{home=90000,reserve=89900},50000,false)
    assert(not amount)
    local early=p:attackAmount(f,{home=90000,reserve=40000},100,true)
    assert(early and early<=50000)
end)
test("opportunity distinguishes other attackers from our own and a target's allies",function()
    local f,p=fixture(),Policy.new()
    f.state.owners[3]={alive=true,troops=5000}
    f.state.attacks[1]={attacker=1,target=2,troops=900}
    assert(p:opportunity(f,2)==0)
    f.state.attacks[2]={attacker=3,target=2,troops=700}
    assert(p:opportunity(f,2)==.7)
    f.state.allied[2*1024+3]=true;assert(p:opportunity(f,2)==0)
    f.state.allied={};f.state.attacks[2].retreating=true;assert(p:opportunity(f,2)==0)
end)
test("under attack alone never justifies invading an overwhelming enemy",function()
    local f,p=fixture(),Policy.new();p:reset(f);p:observe(f)
    f.state.owners[2].troops=500000;f.state.attacks[20]={attacker=3,target=2,troops=1000000}
    local plan=p:enemyPlan(f,{id=2,tile=393,front=1},p:armies(f,{}),{})
    assert(not plan)
end)
test("decision prefers an equally weak enemy facing a real third-party attack",function()
    local f,p=fixture(),Policy.new()
    f.set(12*32+9,2);f.set(13*32+9,3);f.refresh()
    f.state.owners[3]={alive=true,troops=1000,name="Pressed enemy"}
    f.state.attacks[40]={attacker=4,target=3,troops=800}
    for t=0,f.map.N-1 do if f.state:tile_owner(t)==0 then f.state.flags[t]=true end end
    local a=assert(p:decide(f))
    assert(a.intent.type=="attack" and f.state:tile_owner(a.intent.tile)==3)
    assert(a.plan.third_party_incoming==800)
end)
print("POLICY TESTS",tests)
