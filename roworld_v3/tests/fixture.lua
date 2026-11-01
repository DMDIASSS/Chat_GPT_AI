-- Synthetic observations with the same documented client API shape. No game assets.
local function fixture()
    local map = {W = 32, H = 24, N = 32 * 24, k_lin = 2, water = {}}
    function map.dist2(a,b)
        return (a % map.W - b % map.W)^2 + (a // map.W - b // map.W)^2
    end
    function map:is_land(t) return t >= 0 and t < self.N and not self.water[t] end
    function map:is_contestable(t) return self:is_land(t) end
    function map:is_coastal(t)
        return self:is_land(t) and (self.water[t-1] or self.water[t+1] or self.water[t-self.W] or self.water[t+self.W]) == true
    end
    local s = {map = map, local_owner = 1, loaded = true, tick = 1, phase = 1,
        owner = buffer.create(map.N * 4), flags = {}, owners = {}, structures = {}, attacks = {}, nukes = {},
        allied = {}, requests = {}, rules = {STRUCT_MIN_DIST = 4, MAX_BOATS_PLAYER = 3, NUKE_RADIUS = {[0] = 15}}}
    function s:tile_owner(t) return buffer.readi32(self.owner, t*4) end
    function s:has_fallout(t) return self.flags[t] == true end
    function s:are_allies(a,b) return self.allied[a*1024+b] or self.allied[b*1024+a] or false end
    function s:has_request(a,b) return self.requests[a*1024+b] ~= nil end
    function s:owner_name(id) return self.owners[id] and self.owners[id].name or "Unknown" end
    function s:borders_tile(id,t)
        local x = t % map.W
        return (x > 0 and self:tile_owner(t-1) == id) or (x < map.W-1 and self:tile_owner(t+1) == id)
            or (t >= map.W and self:tile_owner(t-map.W) == id) or (t < map.N-map.W and self:tile_owner(t+map.W) == id)
    end
    local info = {alive = true, spawned = true, troops = 50000, max_troops = 100000, gold = 0,
        tiles = 60, label_tile = 12*32+5, spawn_tile = 12*32+5, name = "Local"}
    s.owners[1] = info
    s.owners[2] = {alive = true, spawned = true, troops = 1000, name = "Enemy", spawn_tile = 12*32+16}
    local function set(t,id) buffer.writei32(s.owner,t*4,id) end
    for y = 8, 16 do for x = 2, 8 do set(y*32+x,1) end end
    local border = {}
    local function refresh()
        table.clear(border)
        for t = 0, map.N-1 do
            if s:tile_owner(t) == 1 then
                local x = t % map.W
                if (x > 0 and s:tile_owner(t-1) ~= 1) or (x < map.W-1 and s:tile_owner(t+1) ~= 1)
                    or (t >= map.W and s:tile_owner(t-map.W) ~= 1) or (t < map.N-map.W and s:tile_owner(t+map.W) ~= 1) then border[t] = true end
            end
        end
        local land, coast = {}, {}
        for t = 0, map.N-1 do
            if map:is_land(t) then table.insert(land,t) end
            if map:is_coastal(t) then table.insert(coast,t) end
        end
        for name, list in pairs({land_list = land, coast_list = coast}) do
            local b = buffer.create(#list*4)
            for i,t in ipairs(list) do buffer.writei32(b,(i-1)*4,t) end
            map[name] = b
        end
    end
    refresh()
    local session = {state = s, mode = 1, state_mode = 1, _sim = {}, sent = {}, connected = true}
    function session:send_intent(intent) table.insert(self.sent, intent) end
    function session:multiplayer_available() return self.connected end
    local ctx = {state = s, session = session, borders = {border = border}, rules = {}}
    function ctx:in_match() return self.session.mode == self.session.state_mode end
    function ctx.borders:can_reach_by_sea(t) return map:is_coastal(t) end
    function ctx.rules:transports() return self.transportCount or 0 end
    function ctx.rules:cost(kind) return kind == "atom" and 500000 or 10000 end
    function ctx.rules:availability(kind) return {ok = info.gold >= self:cost(kind), cost = self:cost(kind)} end
    function ctx.rules:placement(kind,t)
        local target = s:tile_owner(t)
        return {ok = kind == "atom" and target > 1 or target == 1, tile = t, upgrade = false}
    end
    return {state = s, map = map, me = 1, info = info, ctx = ctx, session = session, now = 10,
        set = set, refresh = refresh, main = {session = session, ui = {ctx = ctx}}}
end
return fixture
