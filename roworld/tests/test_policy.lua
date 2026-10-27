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
test("attacks a weaker bordering enemy, never an ally", function()
    local f, p = fixture(), Policy.new()
    f.set(12*32+9,2); f.refresh()
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
    f.info.gold = 50000
    local a = assert(p:decide(f)); assert(a.intent.type == "build" and a.intent.kind == "city")
    p:sent(a,f.now)
    f.state.structures[1] = {owner = 1, kind = 0, tile = a.intent.tile, level = 1, active_tick = 100}
    f.now += 7
    local b = assert(p:decide(f)); assert(b.intent.type == "build" and b.intent.kind == "factory")
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
print("POLICY TESTS",tests)
