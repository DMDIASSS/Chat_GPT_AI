-- RoWorld Bot 1.0.1 | paste this entire file into JJSploit.
-- No downloads, localhost bridge, or external service at runtime.

local Policy = (function()

-- RoWorld strategy adapted from Solo AggroBot's reserve / expansion approach.
-- This module reads client observations and returns one ordinary game order.
local Policy = {}
Policy.__index = Policy

local function neighbours(map, tile, visit)
    local x, w = tile % map.W, map.W
    if x > 0 then visit(tile - 1) end
    if x < w - 1 then visit(tile + 1) end
    if tile >= w then visit(tile - w) end
    if tile < map.N - w then visit(tile + w) end
end

local function valid(map, tile)
    return type(tile) == "number" and tile >= 0 and tile < map.N
end

local function friendly(s, me, other)
    return other == me or (other > 0 and s:are_allies(me, other))
end

function Policy.new()
    return setmetatable({state = nil, me = nil, cooldowns = {}, seed = 739391,
        cursor = nil, border = nil, lastAction = "Idle"}, Policy)
end

function Policy:random(n)
    self.seed = (self.seed * 48271) % 2147483647
    return self.seed % math.max(1, n)
end

function Policy:ready(key, now)
    return now >= (self.cooldowns[key] or -math.huge)
end

function Policy:sent(action, now)
    self.cooldowns[action.channel] = now + action.cooldown
    self.lastAction = action.label
end

function Policy:reset(frame)
    self.state, self.me = frame.state, frame.me
    self.cursor, self.border = nil, nil
    self.cooldowns = {}
end

function Policy:landSample(map, list)
    local bytes = map[list]
    if typeof(bytes) == "buffer" and buffer.len(bytes) >= 4 then
        return buffer.readi32(bytes, self:random(buffer.len(bytes) // 4) * 4)
    end
    return self:random(map.N)
end

function Policy:spawn(frame)
    if not self:ready("spawn", frame.now) then return nil, "Waiting for spawn confirmation" end
    local s, map, best, bestScore = frame.state, frame.map, nil, -math.huge
    for _ = 1, 160 do
        local tile = self:landSample(map, "land_list")
        if valid(map, tile) and map:is_contestable(tile) and s:tile_owner(tile) == 0 and not s:has_fallout(tile) then
            local score = 0
            local x, y = tile % map.W, tile // map.W
            -- Count a small surrounding land patch, rather than choosing water
            -- or deliberately spawning beside a large established army.
            for dx = -8, 8, 4 do
                for dy = -8, 8, 4 do
                    local xx, yy = x + dx, y + dy
                    if xx >= 0 and xx < map.W and yy >= 0 and yy < map.H then
                        local t = yy * map.W + xx
                        if map:is_contestable(t) then score += s:tile_owner(t) == 0 and 2 or -4 end
                    end
                end
            end
            for id, owner in pairs(s.owners) do
                if id ~= frame.me and owner.alive and owner.spawned and valid(map, owner.spawn_tile) then
                    score += math.min(35, math.sqrt(map.dist2(tile, owner.spawn_tile))) * .12
                    if map.dist2(tile, owner.spawn_tile) < 400 then score -= 80 end
                end
            end
            if score > bestScore then best, bestScore = tile, score end
        end
    end
    if best then return {intent = {type = "spawn", tile = best}, channel = "spawn", cooldown = 4,
        label = "Choosing a starting territory"} end
    return nil, "Searching for unclaimed spawn land"
end

function Policy:fronts(frame)
    local s, map, me = frame.state, frame.map, frame.me
    local border = frame.ctx.borders.border
    if self.border ~= border then self.border, self.cursor = border, nil end
    if self.cursor ~= nil and border[self.cursor] == nil then self.cursor = nil end
    local groups, sites, seen = {}, {}, {}
    local function site(tile)
        if valid(map, tile) and s:tile_owner(tile) == me and not seen[tile] then
            seen[tile] = true
            if #sites < 320 then table.insert(sites, tile) end
        end
    end
    site(frame.info.label_tile); site(frame.info.spawn_tile)
    for _, b in pairs(s.structures) do if b.owner == me then site(b.tile) end end
    local first
    -- Rotate through the maintained border cache. No two-million-tile scan on
    -- every decision, and no first-page-only blind spot on long borders.
    for _ = 1, 2400 do
        local tile = next(border, self.cursor)
        if tile == nil then self.cursor = nil; tile = next(border) end
        if tile == nil or tile == first then break end
        first = first or tile; self.cursor = tile
        if s:tile_owner(tile) == me then
            site(tile)
            neighbours(map, tile, function(t)
                local id = s:tile_owner(t)
                if not friendly(s, me, id) and map:is_contestable(t) and not s:has_fallout(t) then
                    local g = groups[id]
                    if not g then g = {id = id, tile = t, front = 0}; groups[id] = g end
                    g.front += 1
                end
            end)
        end
    end
    -- Probe inland sites near the capital and existing structures for economy.
    local bases = table.clone(sites)
    local spacing = math.ceil((s.rules.STRUCT_MIN_DIST or 8) * 1.3)
    for i = 1, math.min(16, #bases) do
        local b = bases[i]
        for _, delta in ipairs({spacing, -spacing, spacing * map.W, -spacing * map.W}) do
            local t = b + delta
            if valid(map, t) and map.dist2(b, t) <= spacing * spacing then site(t) end
        end
    end
    return groups, sites
end

function Policy:armies(frame, groups)
    local incoming, outgoing, enemyActive, neutralActive, targets = 0, {}, 0, 0, {}
    for _, a in pairs(frame.state.attacks) do
        if not a.retreating then
            if a.target == frame.me then incoming += math.max(0, a.troops or 0) end
            if a.attacker == frame.me then
                table.insert(outgoing, a)
                targets[a.target] = (targets[a.target] or 0) + (a.troops or 0)
                if a.target == 0 then neutralActive += 1 else enemyActive += 1 end
            end
        end
    end
    local strongest = 0
    for id in pairs(groups) do
        local enemy = frame.state.owners[id]
        if id > 0 and enemy and enemy.alive then strongest = math.max(strongest, enemy.troops or 0) end
    end
    local home = math.max(0, frame.info.troops or 0)
    local reserve = math.min(home, math.max(home * .35, incoming * 1.35, math.min(home * .70, strongest * .35)))
    return {home = home, reserve = reserve, available = math.max(0, home - reserve),
        incoming = incoming, outgoing = outgoing, enemyActive = enemyActive, neutralActive = neutralActive, targets = targets}
end

function Policy:build(frame, sites, kind, counts)
    if not self:ready("build", frame.now) then return nil end
    local rules = frame.ctx.rules
    local availability = rules:availability(kind)
    if not availability.ok then return nil end
    local best, bestScore
    for i = 1, math.min(90, #sites) do
        local place = rules:placement(kind, sites[i])
        if place.ok and valid(frame.map, place.tile) then
            local score = place.upgrade and -10 or 10
            local center = frame.info.label_tile
            if valid(frame.map, center) then score -= math.sqrt(frame.map.dist2(center, place.tile)) * .02 end
            if kind == "defense" or kind == "sam" then
                score = frame.ctx.borders.border[place.tile] and 30 or score
            end
            if bestScore == nil or score > bestScore then best, bestScore = place, score end
        end
    end
    if best then
        return {intent = {type = "build", kind = kind, tile = best.tile}, channel = "build", cooldown = 6,
            label = (best.upgrade and "Upgrading " or "Building ") .. kind}
    end
    return nil
end

function Policy:economy(frame, sites, armies)
    local counts = {}
    for _, b in pairs(frame.state.structures) do
        if b.owner == frame.me then counts[b.kind] = (counts[b.kind] or 0) + 1 end
    end
    local city, factory, port = counts[0] or 0, counts[2] or 0, counts[1] or 0
    local incomingNuke = false
    for _, n in pairs(frame.state.nukes) do
        if valid(frame.map, n.to_tile) and frame.state:tile_owner(n.to_tile) == frame.me then incomingNuke = true end
    end
    local wanted = {}
    if incomingNuke and (counts[4] or 0) < 2 then table.insert(wanted, "sam") end
    if armies.incoming > armies.home * .2 and (counts[3] or 0) < 3 then table.insert(wanted, "defense") end
    if city == 0 then table.insert(wanted, "city") end
    if city > 0 and factory == 0 then table.insert(wanted, "factory") end
    if city > 0 and port == 0 then table.insert(wanted, "port") end
    if armies.home >= (frame.info.max_troops or math.huge) * .75 and city < 6 then table.insert(wanted, "city") end
    if factory < math.max(1, math.ceil(city / 2)) then table.insert(wanted, "factory") end
    if city >= 2 and factory > 0 and (frame.info.tiles or 0) > 500 then
        if (counts[5] or 0) == 0 then table.insert(wanted, "silo") end
        if (counts[4] or 0) == 0 then table.insert(wanted, "sam") end
    end
    if city < 6 and (frame.info.gold or 0) > frame.ctx.rules:cost("city") * 2 then table.insert(wanted, "city") end
    for _, kind in ipairs(wanted) do
        local action = self:build(frame, sites, kind, counts)
        if action then return action end
    end
    return nil
end

function Policy:blastSafe(frame, tile)
    local map, s = frame.map, frame.state
    -- Include the alliance-break radius, which is larger than atom damage.
    local r = math.ceil(math.max((s.rules.NUKE_RADIUS or {})[0] or 0, (s.rules.NUKE_ALLIANCE_BREAK_FULL or 100) / (map.k_lin or 1)))
    local x, y = tile % map.W, tile // map.W
    for yy = math.max(0, y-r), math.min(map.H-1, y+r) do
        for xx = math.max(0, x-r), math.min(map.W-1, x+r) do
            if (xx-x)^2 + (yy-y)^2 <= r*r and friendly(s, frame.me, s:tile_owner(yy*map.W+xx)) then return false end
        end
    end
    return true
end

function Policy:strike(frame)
    if not self:ready("nuke", frame.now) or not frame.ctx.rules:availability("atom").ok then return nil end
    local cost = frame.ctx.rules:cost("atom")
    if (frame.info.gold or 0) < cost * 1.5 then return nil end
    local targets = {}
    for _, b in pairs(frame.state.structures) do
        if b.owner > 0 and not friendly(frame.state, frame.me, b.owner) then table.insert(targets, b) end
    end
    table.sort(targets, function(a,b) return (a.level or 1) > (b.level or 1) end)
    for i = 1, math.min(6, #targets) do
        local target = targets[i]
        if self:blastSafe(frame, target.tile) and frame.ctx.rules:placement("atom", target.tile).ok then
            return {intent = {type = "nuke", kind = "atom", tile = target.tile}, channel = "nuke", cooldown = 15,
                label = "Launching atom at " .. frame.state:owner_name(target.owner)}
        end
    end
    return nil
end

function Policy:naval(frame, armies)
    if armies.incoming > 0 or not self:ready("boat", frame.now) or armies.available < armies.home * .12 then return nil end
    if frame.ctx.rules:transports() >= (frame.state.rules.MAX_BOATS_PLAYER or 3) then return nil end
    local chosen, score
    for _ = 1, 120 do
        local tile = self:landSample(frame.map, "coast_list")
        if valid(frame.map, tile) and frame.map:is_coastal(tile) and not frame.state:has_fallout(tile) then
            local target = frame.state:tile_owner(tile)
            local owner = frame.state.owners[target]
            local weak = target == 0 or (owner and owner.alive and (owner.troops or 0) < armies.available * .45)
            if weak and not friendly(frame.state, frame.me, target) and frame.ctx.borders:can_reach_by_sea(tile) then
                local value = target == 0 and 10 or 20
                if valid(frame.map, frame.info.label_tile) then value -= math.sqrt(frame.map.dist2(tile, frame.info.label_tile)) * .02 end
                if score == nil or value > score then chosen, score = tile, value end
            end
        end
    end
    if chosen then return {intent = {type = "boat", tile = chosen, ratio = math.min(.25, armies.available / armies.home)},
        reserve = armies.reserve, channel = "boat", cooldown = 12, label = "Sending a coastal landing"} end
    return nil
end

function Policy:decide(frame)
    if self.state ~= frame.state or self.me ~= frame.me then self:reset(frame) end
    if not frame.info.alive then return nil, "Eliminated - waiting for the next match" end
    if not frame.info.spawned then return self:spawn(frame) end
    if frame.state.phase == 0 then return nil, "Spawned - waiting for the round" end
    if frame.state.phase ~= 1 then return nil, "Match finished" end
    local groups, sites = self:fronts(frame)
    local a = self:armies(frame, groups)
    if a.incoming > a.home * .75 and self:ready("retreat", frame.now) then
        for _, attack in ipairs(a.outgoing) do
            return {intent = {type = "retreat", attack_id = attack.aid}, channel = "retreat", cooldown = 3,
                label = "Recalling troops to defend"}
        end
    end
    -- Economy / defensive construction has its own cooldown and never drains
    -- the troop reserve. Observed structures (including construction) are used.
    local build = self:economy(frame, sites, a)
    if build then return build end
    if self:ready("diplomacy", frame.now) then
        for id, owner in pairs(frame.state.owners) do
            if id ~= frame.me and owner.alive and frame.state:has_request(id, frame.me) and not a.targets[id] then
                return {intent = {type = "ally_reply", target = id, accept = true}, channel = "diplomacy", cooldown = 8,
                    label = "Accepting alliance with " .. owner.name}
            end
        end
    end
    if a.incoming > a.home * .25 then return nil, "Defending - holding troop reserves" end
    local best, score
    if self:ready("attack", frame.now) and a.enemyActive < 2 then
        for id, g in pairs(groups) do
            local enemy = frame.state.owners[id]
            if id > 0 and enemy and enemy.alive then
                local need = math.max(250, (enemy.troops or 0) * 1.4 - (a.targets[id] or 0) * .5)
                if need <= a.available and a.home > (enemy.troops or 0) * 1.35 then
                    local value = math.log(1 + g.front) + a.home / math.max(100, enemy.troops or 0)
                    if score == nil or value > score then
                        best, score = {intent = {type = "attack", tile = g.tile, ratio = math.min(.55, need / a.home)},
                            reserve = a.reserve, channel = "attack", cooldown = 2.5,
                            label = "Attacking " .. enemy.name}, value
                    end
                end
            end
        end
    end
    if best then return best end
    local neutral = groups[0]
    if neutral and self:ready("attack", frame.now) and a.available > 200 and a.enemyActive == 0 then
        local high = a.home > (frame.info.max_troops or math.huge) * .8
        if a.neutralActive == 0 or (high and (a.targets[0] or 0) < a.home * .25) then
            local amount = math.min(a.available * .5, a.home * (high and .22 or .10))
            if amount >= 100 then return {intent = {type = "attack", tile = neutral.tile, ratio = amount / a.home},
                reserve = a.reserve, channel = "attack", cooldown = 2.5, label = "Expanding into unclaimed land"} end
        end
    end
    local strike = self:strike(frame)
    if strike then return strike end
    local boat = self:naval(frame, a)
    if boat then return boat end
    if a.enemyActive > 0 or a.neutralActive > 0 then return nil, "Watching the current attack; rebuilding troops" end
    return nil, "Recruiting troops and saving for the next move"
end

return Policy


end)()

local Adapter = (function()

-- Adapter for the supplied RoWorld place, version 111 / Airfront client.
-- Uses the existing live Main.session; never creates a second simulation.
local Adapter = {}
Adapter.__index = Adapter

function Adapter.new(services, requireModule, now, capabilities)
    return setmetatable({services = services, requireModule = requireModule,
        capabilities = capabilities or {}, discoveryRoute = "not connected",
        now = now or os.clock, main = nil, nextDiscovery = 0, lastSent = -math.huge,
        tickState = nil, lastTick = nil, tickChangedAt = 0}, Adapter)
end

function Adapter:call(fn, ...)
    local caps = self.capabilities
    local original, changed
    if type(caps.getidentity) == "function" and type(caps.setidentity) == "function" then
        local ok, identity = pcall(caps.getidentity)
        if ok and type(identity) == "number" then
            original = identity
            changed = pcall(caps.setidentity, 2)
        end
    end
    local result = table.pack(pcall(fn, ...))
    if changed then
        local restored, err = pcall(caps.setidentity, original)
        if not restored then return false, "Cannot restore executor thread identity: " .. tostring(err) end
    end
    return table.unpack(result, 1, result.n)
end

local function liveContext(candidate)
    if type(candidate) ~= "table" then return nil end
    local session = rawget(candidate, "session")
    local ui = rawget(candidate, "ui")
    local ctx = type(ui) == "table" and rawget(ui, "ctx") or rawget(candidate, "ctx")
    if type(ctx) ~= "table" and type(rawget(candidate, "rules")) == "table" then ctx = candidate end
    if type(ctx) ~= "table" then return nil end
    session = session or rawget(ctx, "session")
    if type(session) ~= "table" or rawget(ctx, "session") ~= session then return nil end
    local state = rawget(session, "state")
    if type(state) ~= "table" or rawget(ctx, "state") ~= state or type(rawget(state, "owners")) ~= "table"
        or type(rawget(state, "map")) ~= "table" or type(rawget(ctx, "borders")) ~= "table"
        or type(rawget(ctx, "rules")) ~= "table" then return nil end
    if type(session.send_intent) ~= "function" or type(ctx.in_match) ~= "function" then return nil end
    return {session = session, ui = {ctx = ctx}}
end

function Adapter:findLiveClient()
    local gc = self.capabilities.getgc
    if type(gc) ~= "function" then return nil end
    local ok, values = pcall(gc, true)
    if not ok or type(values) ~= "table" then self.gcError = tostring(values); return nil end
    for _, value in pairs(values) do
        local found = liveContext(value)
        if found then self.discoveryRoute = "existing client tables"; return found end
    end
    self.gcError = "No live RoWorld context found yet"
    return nil
end

function Adapter:diagnostics()
    local caps, lines = self.capabilities, {"RoWorld Bot 1.0.1 - client access diagnostics"}
    for _, key in ipairs({"getidentity", "setidentity", "getgc"}) do
        table.insert(lines, key .. "=" .. type(caps[key]))
    end
    table.insert(lines, "route=" .. self.discoveryRoute)
    table.insert(lines, "module_error=" .. tostring(self.moduleError or "none"))
    table.insert(lines, "table_scan=" .. tostring(self.gcError or "not needed"))
    return table.concat(lines, "\n")
end

function Adapter:discover()
    if self.main and self.main.session and self.main.ui and self.main.ui.ctx then return self.main end
    if self.now() < self.nextDiscovery then return nil end
    self.nextDiscovery = self.now() + 8
    local player = self.services.Players.LocalPlayer
    local scripts = player and player:FindFirstChild("PlayerScripts")
    local client = scripts and scripts:FindFirstChild("AirfrontClient")
    local module = client and client:FindFirstChild("Main")
    if not module or not module:IsA("ModuleScript") then return nil end
    local ok, main = self:call(self.requireModule, module)
    if ok and type(main) == "table" and main.session and main.ui and main.ui.ctx then
        self.main, self.discoveryError, self.discoveryRoute = main, nil, "cached Main module"
        return main
    end
    self.moduleError = ok and "Main module has no running session in this context" or tostring(main)
    local found = self:findLiveClient()
    if found then self.main, self.discoveryError = found, nil; return found end
    self.discoveryError = "Client access blocked or not ready; see diagnostics in JJSploit workspace / F9"
    return nil
end

function Adapter:frame()
    local main = self:discover()
    if not main then return nil, self.discoveryError or "Waiting for the RoWorld client to load" end
    local session, ui = main.session, main.ui
    local ctx = ui and ui.ctx
    local s = session and session.state
    if not session or not ctx or not s or not s.map or s.loaded ~= true then return nil, "Join a RoWorld match first" end
    if session.paused then return nil, "Game paused" end
    if session.mode ~= 1 and session.mode ~= 2 then return nil, "Join a solo or multiplayer match" end
    if ctx.session ~= session or ctx.state ~= s or not ctx:in_match() then return nil, "Waiting for the current match state" end
    if session.mode == 2 and (session._sim ~= nil or not session:multiplayer_available()) then
        return nil, "Waiting for the multiplayer connection"
    end
    if session.mode == 1 and session._sim == nil then return nil, "Waiting for the solo simulation" end
    local me = s.local_owner
    local info = s.owners and s.owners[me]
    if not me or me == 0 or not info then return nil, "Waiting for your nation; spectators cannot issue orders" end
    if type(session.send_intent) ~= "function" or not ctx.rules or not ctx.borders or type(ctx.borders.border) ~= "table"
        or type(s.tile_owner) ~= "function" or type(s.map.is_contestable) ~= "function" then
        return nil, "RoWorld API changed; this client version is unsupported"
    end
    local now = self.now()
    if self.tickState ~= s or self.lastTick ~= s.tick then
        self.tickState, self.lastTick, self.tickChangedAt = s, s.tick, now
    elseif s.phase == 1 and now - self.tickChangedAt > 6 then
        return nil, "Waiting for fresh game updates"
    end
    return {session = session, ctx = ctx, state = s, map = s.map, info = info, me = me, now = now}
end

local function tileValid(frame, tile)
    return type(tile) == "number" and tile % 1 == 0 and tile >= 0 and tile < frame.map.N
end

function Adapter:send(action, frame)
    local live, reason = self:frame()
    if not live then return false, reason end
    if live.session ~= frame.session or live.state ~= frame.state or live.me ~= frame.me then
        return false, "Match changed; recalculating"
    end
    if live.now - self.lastSent < .5 then return false, "Waiting for the next order slot" end
    local s, me, rules = live.state, live.me, live.ctx.rules
    local intent = table.clone(action.intent)
    local kind = intent.type
    if not live.info.alive or s.phase == 2 then return false, "Match finished or nation eliminated" end
    if kind == "spawn" then
        if live.info.spawned or not tileValid(live, intent.tile) or not live.map:is_contestable(intent.tile)
            or s:tile_owner(intent.tile) ~= 0 or s:has_fallout(intent.tile) then return false, "Spawn point changed" end
    else
        if not live.info.spawned or s.phase ~= 1 then return false, "Waiting for the playing phase" end
        if kind == "attack" or kind == "boat" then
            if not tileValid(live, intent.tile) or not live.map:is_contestable(intent.tile) or s:has_fallout(intent.tile) then
                return false, "Target is no longer claimable"
            end
            local target = s:tile_owner(intent.tile)
            if target == me or (target > 0 and s:are_allies(me, target)) then return false, "Target is now friendly" end
            if kind == "attack" and not s:borders_tile(me, intent.tile) then return false, "Target no longer borders your land" end
            if kind == "boat" and (not live.map:is_coastal(intent.tile) or not live.ctx.borders:can_reach_by_sea(intent.tile)
                or rules:transports() >= (s.rules.MAX_BOATS_PLAYER or 3)) then return false, "Sea route unavailable" end
            local troops = math.max(0, live.info.troops or 0)
            local incoming = 0
            for _, attack in pairs(s.attacks) do
                if attack.target == me and not attack.retreating then incoming += attack.troops or 0 end
            end
            local reserve = math.max(action.reserve or 0, troops * .35, incoming * 1.35)
            intent.ratio = math.min(tonumber(intent.ratio) or 0, .55, math.max(0, troops-reserve) / math.max(1, troops))
            if intent.ratio ~= intent.ratio or intent.ratio <= 0 or troops * intent.ratio < 100 then return false, "Holding troop reserves" end
        elseif kind == "build" or kind == "nuke" then
            if not tileValid(live, intent.tile) or not rules:availability(intent.kind).ok then return false, "Building or weapon is not ready" end
            if not rules:placement(intent.kind, intent.tile).ok then return false, "Placement changed" end
            if kind == "nuke" then
                local target = s:tile_owner(intent.tile)
                if target == 0 or target == me or s:are_allies(me, target) then return false, "Strike target changed" end
                local radius = math.ceil(math.max((s.rules.NUKE_RADIUS or {})[0] or 0,
                    (s.rules.NUKE_ALLIANCE_BREAK_FULL or 100) / (live.map.k_lin or 1)))
                local x, y = intent.tile % live.map.W, intent.tile // live.map.W
                for yy = math.max(0,y-radius), math.min(live.map.H-1,y+radius) do
                    for xx = math.max(0,x-radius), math.min(live.map.W-1,x+radius) do
                        if (xx-x)^2+(yy-y)^2 <= radius*radius then
                            local owner = s:tile_owner(yy*live.map.W+xx)
                            if owner == me or (owner > 0 and s:are_allies(me,owner)) then
                                return false, "Friendly land entered the strike area"
                            end
                        end
                    end
                end
            end
        elseif kind == "retreat" then
            local attack = s.attacks[intent.attack_id]
            if not attack or attack.attacker ~= me or attack.retreating then return false, "Attack already ended" end
        elseif kind == "ally_reply" then
            if not s:has_request(intent.target, me) then return false, "Alliance request expired" end
        else
            return false, "Unsupported order type: " .. tostring(kind)
        end
    end
    -- send_intent is the same route the game's controls use. In multiplayer,
    -- the server validates and applies it; a sent order is not a confirmation.
    live.session:send_intent(intent)
    self.lastSent = live.now
    return true
end

return Adapter


end)()

-- Policy and Adapter are embedded by build.py in the standalone script.
local Services = {
    Players = game:GetService("Players"),
    CoreGui = game:GetService("CoreGui"),
    UserInputService = game:GetService("UserInputService"),
}
local env = (type(getgenv) == "function" and getgenv()) or _G
local previous = env.__RoWorldBot
if type(previous) == "table" and type(previous.destroy) == "function" then pcall(previous.destroy) end
local api = {enabled = false, alive = true, connections = {}}
env.__RoWorldBot = api

local gui = Instance.new("ScreenGui")
gui.Name = "RoWorldBot"
gui.ResetOnSpawn = false
gui.ZIndexBehavior = Enum.ZIndexBehavior.Sibling
gui.DisplayOrder = 10000
local parent = type(gethui) == "function" and gethui() or Services.CoreGui
local attached = pcall(function() gui.Parent = parent end)
if not attached then gui.Parent = Services.Players.LocalPlayer:WaitForChild("PlayerGui") end
local panel = Instance.new("Frame")
panel.Size = UDim2.fromOffset(330, 116)
panel.Position = UDim2.new(1, -346, 0, 60)
panel.BackgroundColor3 = Color3.fromRGB(20, 29, 42)
panel.BorderSizePixel = 0
panel.Parent = gui
local corner = Instance.new("UICorner")
corner.CornerRadius = UDim.new(0, 10)
corner.Parent = panel
local button = Instance.new("TextButton")
button.Name = "Toggle"
button.Size = UDim2.new(1, -24, 0, 40)
button.Position = UDim2.fromOffset(12, 10)
button.Font = Enum.Font.GothamBold
button.TextSize = 17
button.TextColor3 = Color3.fromRGB(255, 255, 255)
button.BorderSizePixel = 0
button.Parent = panel
local buttonCorner = corner:Clone()
buttonCorner.Parent = button
local status = Instance.new("TextLabel")
status.Name = "Status"
status.Size = UDim2.new(1, -24, 0, 51)
status.Position = UDim2.fromOffset(12, 56)
status.BackgroundTransparency = 1
status.Font = Enum.Font.Gotham
status.TextSize = 13
status.TextColor3 = Color3.fromRGB(221, 231, 242)
status.TextWrapped = true
status.TextXAlignment = Enum.TextXAlignment.Left
status.Parent = panel

local function repaint(message)
    if not api.alive then return end
    button.Text = api.enabled and "Stop bot" or "Start bot"
    button.BackgroundColor3 = api.enabled and Color3.fromRGB(166, 58, 65) or Color3.fromRGB(33, 133, 99)
    status.Text = message or "Stopped - press Start bot (F6 also toggles)"
end

local adapter = Adapter.new(Services, require, nil, {
    getidentity = getthreadidentity or getidentity,
    setidentity = setthreadidentity or setidentity,
    getgc = getgc,
})
local reported
function api.diagnostics() return adapter:diagnostics() end
local function reportAccessFailure()
    if not adapter.discoveryError then return end
    local report = adapter:diagnostics()
    if report == reported then return end
    reported = report
    if type(writefile) == "function" then pcall(writefile, "RoWorld_Diagnostics.txt", report) end
    warn(report)
end
local policy = Policy.new()
local lastCommand, lastCommandAt = "", -math.huge
local function toggle()
    api.enabled = not api.enabled
    if api.enabled then
        policy = Policy.new()
        repaint("Connecting to your RoWorld match...")
    else
        repaint("Stopped - no new orders; existing game attacks continue")
    end
end
table.insert(api.connections, button.Activated:Connect(toggle))
table.insert(api.connections, Services.UserInputService.InputBegan:Connect(function(input, consumed)
    if not consumed and input.KeyCode == Enum.KeyCode.F6 then toggle() end
end))
function api.destroy()
    api.alive, api.enabled = false, false
    for _, connection in ipairs(api.connections) do connection:Disconnect() end
    gui:Destroy()
    if env.__RoWorldBot == api then env.__RoWorldBot = nil end
end
table.insert(api.connections, gui.AncestryChanged:Connect(function(_, newParent)
    if newParent == nil then api.alive, api.enabled = false, false end
end))
repaint()
task.spawn(function()
    while api.alive do
        if api.enabled then
            local ok, message = adapter:call(function()
                local frame, reason = adapter:frame()
                if not api.enabled or not api.alive then return end
                if not frame then return reason end
                -- The normal client sends a rate-limited activity heartbeat
                -- from user input. Keep that same heartbeat while autoplay is on.
                if type(frame.session.note_activity) == "function" then frame.session:note_activity() end
                local action, waiting = policy:decide(frame)
                if not api.enabled or not api.alive then return end
                if action then
                    local sent, blocked = adapter:send(action, frame)
                    if sent then
                        policy:sent(action, frame.now)
                        lastCommand, lastCommandAt = action.label, os.clock()
                        return "Order sent: " .. action.label
                    else
                        return blocked
                    end
                else
                    local suffix = os.clock() - lastCommandAt < 5 and ("\nLast: " .. lastCommand) or ""
                    return (waiting or "Watching the match") .. suffix
                end
            end)
            -- UI and executor file operations run after the identity is restored.
            if ok then
                reportAccessFailure()
                repaint(message)
            else
                api.enabled = false
                repaint("Stopped after an error: " .. tostring(message))
                warn("[RoWorldBot] " .. tostring(message))
            end
        end
        task.wait(.55)
    end
end)
