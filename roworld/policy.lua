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
