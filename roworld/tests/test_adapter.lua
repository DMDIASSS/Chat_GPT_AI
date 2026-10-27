local Adapter = require("../adapter")
local fixture = require("./fixture")
local tests = 0
local function test(name, run) run(); tests += 1; print("PASS",name) end
local function adapter(f)
    local a = Adapter.new({},function() error("Must reuse the live session") end,function() return f.now end)
    a.main = f.main
    return a
end
local function attack(tile)
    return {intent = {type = "attack", tile = tile, ratio = .2}, reserve = 17500}
end

local function moduleServices()
    local module = {IsA = function(_, name) return name == "ModuleScript" end}
    local client = {FindFirstChild = function(_, name) return name == "Main" and module or nil end}
    local scripts = {FindFirstChild = function(_, name) return name == "AirfrontClient" and client or nil end}
    return {Players = {LocalPlayer = {FindFirstChild = function(_, name) return name == "PlayerScripts" and scripts or nil end}}}
end

test("uses ordinary client identity for require and restores executor identity", function()
    local f, identity = fixture(), 8
    local a = Adapter.new(moduleServices(),function()
        assert(identity == 2, "Cannot require a non-RobloxScript module from a RobloxScript")
        return f.main
    end,function() return f.now end,{
        getidentity = function() return identity end,
        setidentity = function(value) identity = value end,
    })
    assert(a:frame().session == f.session and identity == 8)
    local ok = a:call(function() assert(identity == 2); error("test failure") end)
    assert(not ok and identity == 8)
end)

test("finds the existing live client when direct require is blocked", function()
    for _, variant in ipairs({"main", "ui", "context"}) do
        local f = fixture()
        local candidate = variant == "main" and f.main or variant == "ui" and f.main.ui or f.ctx
        local a = Adapter.new(moduleServices(),function()
            error("Cannot require a non-RobloxScript module from a RobloxScript")
        end,function() return f.now end,{getgc = function(tables)
            assert(tables); return {function() end, {}, {session={}}, candidate}
        end})
        assert(a:frame().session == f.session and a.discoveryRoute == "existing client tables")
        assert(#f.session.sent == 0)
    end
end)

test("reports missing executor capabilities without inventing a session", function()
    local a = Adapter.new(moduleServices(),function() error("Cannot require a non-RobloxScript module") end,function() return 10 end)
    local view, reason = a:frame()
    assert(not view and reason:find("diagnostics"))
    local report = a:diagnostics()
    assert(report:find("getgc=nil") and report:find("non%-RobloxScript"))
end)

test("discovers the original cached Main module without starting another client", function()
    local f = fixture()
    local module = {IsA = function(_, name) return name == "ModuleScript" end}
    local client = {FindFirstChild = function(_, name) return name == "Main" and module or nil end}
    local scripts = {FindFirstChild = function(_, name) return name == "AirfrontClient" and client or nil end}
    local player = {FindFirstChild = function(_, name) return name == "PlayerScripts" and scripts or nil end}
    local calls = 0
    local a = Adapter.new({Players = {LocalPlayer = player}},function(mod)
        assert(mod == module); calls += 1; return f.main
    end,function() return f.now end)
    assert(a:frame().session == f.session and calls == 1)
    assert(a:frame().session == f.session and calls == 1)
end)

test("routes solo and joined multiplayer commands through existing send_intent", function()
    for _, mode in ipairs({1,2}) do
        local f = fixture(); f.session.mode = mode; f.session.state_mode = mode
        if mode == 2 then f.session._sim = nil end
        local a = adapter(f); local view = assert(a:frame())
        assert(a:send(attack(12*32+9),view)); assert(#f.session.sent == 1)
        assert(f.session.sent[1].type == "attack")
    end
end)
test("alliance and ownership changes cancel a previously planned attack", function()
    for _, target in ipairs({1,2}) do
        local f = fixture(); local a = adapter(f); local view = assert(a:frame())
        f.set(12*32+9,target); f.state.allied[1026] = true
        assert(not a:send(attack(12*32+9),view)); assert(#f.session.sent == 0)
    end
end)
test("fresh incoming attacks reduce or cancel spending", function()
    local f = fixture(); local a = adapter(f); local view = assert(a:frame())
    f.state.attacks[9] = {attacker = 2,target = 1,troops = 45000}
    assert(not a:send(attack(12*32+9),view)); assert(#f.session.sent == 0)
end)
test("spectating, menu, loading, pause and stale telemetry issue no commands", function()
    for _, scenario in ipairs({"spectate","menu","loading","pause","stale","disconnected","old-context"}) do
        local f = fixture(); local a = adapter(f); assert(a:frame())
        if scenario == "spectate" then f.state.local_owner = 0
        elseif scenario == "menu" then f.session.mode = 0
        elseif scenario == "loading" then f.state.loaded = false
        elseif scenario == "pause" then f.session.paused = true
        elseif scenario == "stale" then f.now += 7
        elseif scenario == "disconnected" then f.session.mode = 2; f.session.state_mode = 2; f.session._sim = nil; f.session.connected = false
        elseif scenario == "old-context" then f.ctx.state = {} end
        local view = a:frame(); assert(view == nil,scenario); assert(#f.session.sent == 0)
    end
end)
test("a changed tick recovers from stale state", function()
    local f = fixture(); local a = adapter(f); assert(a:frame())
    f.now += 7; assert(a:frame() == nil)
    f.state.tick += 1; assert(a:frame())
end)
test("switching matches invalidates a queued order", function()
    local f = fixture(); local a = adapter(f); local view = assert(a:frame())
    local second = fixture(); a.main = second.main
    assert(not a:send(attack(12*32+9),view)); assert(#second.session.sent == 0)
end)
test("rate limit and finite troop ratios", function()
    local f = fixture(); local a = adapter(f); local view = assert(a:frame())
    local invalid = attack(12*32+9); invalid.intent.ratio = 0/0
    assert(not a:send(invalid,view))
    assert(a:send(attack(12*32+9),view))
    assert(not a:send(attack(12*32+9),view)); assert(#f.session.sent == 1)
end)
test("build readiness and retreat ownership are checked at send time", function()
    local f = fixture(); local a = adapter(f); local view = assert(a:frame())
    assert(not a:send({intent = {type = "build",kind = "city",tile = f.info.label_tile}},view))
    f.state.attacks[9] = {aid = 9,attacker = 2,target = 1,troops = 100}
    assert(not a:send({intent = {type = "retreat",attack_id = 9}},view))
    assert(#f.session.sent == 0)
end)
test("atom order is cancelled if friendly territory entered its area", function()
    local f = fixture(); f.info.gold = 1000000
    local a = adapter(f); local view = assert(a:frame())
    f.set(12*32+9,2)
    local order = {intent = {type = "nuke",kind = "atom",tile = 12*32+9}}
    assert(not a:send(order,view)); assert(#f.session.sent == 0)
end)
print("ADAPTER TESTS",tests)
