-- Adapter for the supplied RoWorld place, version 111 / Airfront client.
-- Uses the existing live Main.session; never creates a second simulation.
local Adapter = {}
Adapter.__index = Adapter

function Adapter.new(services, requireModule, now)
    return setmetatable({services = services, requireModule = requireModule,
        now = now or os.clock, main = nil, nextDiscovery = 0, lastSent = -math.huge,
        tickState = nil, lastTick = nil, tickChangedAt = 0}, Adapter)
end

function Adapter:discover()
    if self.main and self.main.session and self.main.ui and self.main.ui.ctx then return self.main end
    if self.now() < self.nextDiscovery then return nil end
    self.nextDiscovery = self.now() + 2
    local player = self.services.Players.LocalPlayer
    local scripts = player and player:FindFirstChild("PlayerScripts")
    local client = scripts and scripts:FindFirstChild("AirfrontClient")
    local module = client and client:FindFirstChild("Main")
    if not module or not module:IsA("ModuleScript") then return nil end
    local ok, main = pcall(self.requireModule, module)
    if not ok then self.discoveryError = "Cannot read RoWorld client: " .. tostring(main); return nil end
    if type(main) ~= "table" then self.discoveryError = "RoWorld Main API changed"; return nil end
    self.main = main
    return main
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
