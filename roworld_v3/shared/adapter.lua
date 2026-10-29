-- Adapter for the supplied RoWorld place, version 111 / Airfront client.
-- Uses the existing live Main.session; never creates a second simulation.
local Adapter = {}
local Weapons = require("./weapons")
Adapter.__index = Adapter

function Adapter.new(services, requireModule, now, capabilities)
    return setmetatable({services = services, requireModule = requireModule,
        capabilities = capabilities or {}, discoveryRoute = "not connected",
        accessStats = {},
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
            local readOK, actual = pcall(caps.getidentity)
            self.accessStats.identity_after_set = readOK and tostring(actual) or "read failed"
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

function Adapter:inspectFunction(fn)
    local caps = self.capabilities
    if type(fn) ~= "function" then return nil end
    self.accessStats.functions_inspected = (self.accessStats.functions_inspected or 0) + 1
    local values
    if type(caps.getupvalues) == "function" then
        local ok, result = pcall(caps.getupvalues, fn)
        if ok and type(result) == "table" and next(result) ~= nil then values = result end
    end
    if not values and type(caps.getupvalue) == "function" then
        values = {}
        for index = 1, 80 do
            local result = table.pack(pcall(caps.getupvalue, fn, index))
            if not result[1] or result.n < 2 then break end
            local value = result.n >= 3 and result[3] or result[2]
            values[index] = value
        end
    end
    if not values then return nil end
    for _, value in pairs(values) do
        local found = liveContext(value)
        if found then return found end
    end
    return nil
end

function Adapter:findCallbacks()
    local getter = self.capabilities.getconnections
    if type(getter) ~= "function" then return nil end
    local signals = {}
    local input, run = self.services.UserInputService, self.services.RunService
    if input then
        table.insert(signals, input.InputBegan)
        table.insert(signals, input.InputEnded)
    end
    if run then table.insert(signals, run.Heartbeat) end
    for _, signal in ipairs(signals) do
        local ok, connections = pcall(getter, signal)
        if ok and type(connections) == "table" then
            for _, connection in pairs(connections) do
                -- Read callbacks only: never fire, disable, replace or hook them.
                local readable, fn = pcall(function() return connection.Function end)
                if readable then
                    local found = self:inspectFunction(fn)
                    if found then self.discoveryRoute = "existing input callback"; return found end
                end
            end
        end
    end
    return nil
end

function Adapter:findLiveClient()
    local gc = self.capabilities.getgc
    if type(gc) ~= "function" then return nil end
    local ok, values = pcall(gc, true)
    if not ok or type(values) ~= "table" then self.gcError = tostring(values); return nil end
    local functions = {}
    self.accessStats.gc_tables, self.accessStats.gc_functions = 0, 0
    for _, value in pairs(values) do
        if type(value) == "table" then self.accessStats.gc_tables += 1 end
        if type(value) == "function" then
            self.accessStats.gc_functions += 1
            table.insert(functions, value)
        end
        local found = liveContext(value)
        if found then self.discoveryRoute = "existing client tables"; return found end
    end
    for _, fn in ipairs(functions) do
        local ownGameFunction = false
        if type(self.capabilities.getfenv) == "function" and self.clientScript then
            local okEnv, environment = pcall(self.capabilities.getfenv, fn)
            if okEnv and type(environment) == "table" then
                local okScript, matches = pcall(function()
                    local script = environment.script
                    return script and (script == self.clientScript or script:IsDescendantOf(self.clientScript))
                end)
                ownGameFunction = okScript and matches == true
            end
        end
        if ownGameFunction then
            local found = self:inspectFunction(fn)
            if found then self.discoveryRoute = "existing game closure"; return found end
        end
    end
    self.gcError = "No live RoWorld context found yet"
    return nil
end

function Adapter:diagnostics()
    local caps, lines = self.capabilities, {"RoWorld Bot 3.0.0 - client access diagnostics"}
    for _, key in ipairs({"getidentity", "setidentity", "getgc", "getconnections", "getupvalues", "getupvalue", "getfenv", "getsenv", "getrenv"}) do
        table.insert(lines, key .. "=" .. type(caps[key]))
    end
    table.insert(lines, "route=" .. self.discoveryRoute)
    table.insert(lines, "module_error=" .. tostring(self.moduleError or "none"))
    table.insert(lines, "table_scan=" .. tostring(self.gcError or "not needed"))
    local keys = {}
    for key in pairs(self.accessStats) do table.insert(keys, key) end
    table.sort(keys)
    for _, key in ipairs(keys) do table.insert(lines, key .. "=" .. tostring(self.accessStats[key])) end
    if self.network then table.insert(lines,self.network:diagnostics()) end
    return table.concat(lines, "\n")
end

function Adapter:discover()
    if self.main and self.main.session and self.main.ui and self.main.ui.ctx then return self.main end
    if self.now() < self.nextDiscovery then return nil end
    self.nextDiscovery = self.now() + 8
    self.accessStats.functions_inspected = 0
    local player = self.services.Players.LocalPlayer
    local scripts = player and player:FindFirstChild("PlayerScripts")
    local client = scripts and scripts:FindFirstChild("AirfrontClient")
    self.clientScript = client
    local module = client and client:FindFirstChild("Main")
    if not module or not module:IsA("ModuleScript") then return nil end
    local ok, main = self:call(self.requireModule, module)
    if ok and type(main) == "table" and main.session and main.ui and main.ui.ctx then
        self.main, self.discoveryError, self.discoveryRoute = main, nil, "cached Main module"
        return main
    end
    self.moduleError = ok and "Main module has no running session in this context" or tostring(main)
    -- Some executors replace require. Try the original client environment too.
    for _, getter in ipairs({"getsenv", "getrenv"}) do
        if type(self.capabilities[getter]) == "function" then
            local envOK, environment
            if getter == "getsenv" then envOK, environment = pcall(self.capabilities[getter], client)
            else envOK, environment = pcall(self.capabilities[getter]) end
            if envOK and type(environment) == "table" then
                local readOK, nativeRequire = pcall(function() return environment.require end)
                if readOK and type(nativeRequire) == "function" and nativeRequire ~= self.requireModule then
                    local loaded, nativeMain = self:call(nativeRequire, module)
                    if loaded and liveContext(nativeMain) then
                        self.main, self.discoveryError, self.discoveryRoute = nativeMain, nil, "client environment require"
                        return nativeMain
                    end
                end
            end
        end
    end
    local found = self:findCallbacks() or self:findLiveClient()
    if found then self.main, self.discoveryError = found, nil; return found end
    if self.network then
        self.networkActive=true
        local main=self.network:poll()
        if main then self.main,self.discoveryRoute,self.discoveryError=main,"multiplayer observer",nil;return main end
        self.discoveryError=self.network.status
        return nil
    end
    self.discoveryError = "Client access blocked or not ready; see diagnostics in JJSploit workspace / F9"
    return nil
end

function Adapter:frame()
    if self.networkActive then
        local main=self.network:poll()
        if main then self.main,self.discoveryRoute,self.discoveryError=main,"multiplayer observer",nil end
        if not main or not main.session.state.loaded then
            self.discoveryError=self.network.status
            return nil,self.network.status
        end
    end
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
    if live.now - self.lastSent < .2 then return false, "Waiting for the next order slot" end
    local s, me, rules = live.state, live.me, live.ctx.rules
    local intent = table.clone(action.intent)
    local kind = intent.type
    if not live.info.alive or s.phase == 2 then return false, "Match finished or nation eliminated" end
    if kind == "spawn" then
        if live.info.spawned and s.phase~=0 or not tileValid(live, intent.tile) or not live.map:is_contestable(intent.tile)
            or s:tile_owner(intent.tile) ~= 0 or s:has_fallout(intent.tile) then return false, "Spawn point changed" end
    else
        if not live.info.spawned or s.phase ~= 1 then return false, "Waiting for the playing phase" end
        if kind == "attack" or kind == "boat" then
            if not tileValid(live, intent.tile) or not live.map:is_contestable(intent.tile) or s:has_fallout(intent.tile) then
                return false, "Target is no longer claimable"
            end
            local target = s:tile_owner(intent.tile)
            if target == me or (target > 0 and (s:are_allies(me, target) or (s.bot_friend_guard or {})[target])) then return false, "Target is now friendly" end
            if target>0 and s:has_request(me,target) then return false,"Waiting for our alliance proposal before attacking" end
            if kind == "attack" and not s:borders_tile(me, intent.tile) then return false, "Target no longer borders your land" end
            if kind == "boat" and (not live.map:is_coastal(intent.tile) or not live.ctx.borders:can_reach_by_sea(intent.tile)
                or rules:transports() >= (s.rules.MAX_BOATS_PLAYER or 3)) then return false, "Sea route unavailable" end
            local troops = math.max(0, live.info.troops or 0)
            local incoming = 0
            for _, attack in pairs(s.attacks) do
                if attack.target == me and not attack.retreating then incoming += attack.troops or 0 end
            end
            local reserve = math.max(action.reserve or 0, troops * .35, incoming * 1.5)
            if (action.plan or {}).defensive_counter then
                local active=false
                for _,a in pairs(s.attacks) do if a.attacker==target and a.target==me and not a.retreating then active=true end end
                if not active then return false,'Attacker stopped; reassessing counterattack' end
                reserve=math.max(reserve,math.ceil((live.info.max_troops or 0)*.42))
            end
            if action.survival then
                if kind~='boat' or target~=0 or incoming<=troops*1.25 or rules:transports()>0 then
                    return false,'Survival expedition conditions changed'
                end
                reserve=troops*.9
            end
            intent.ratio = math.min(tonumber(intent.ratio) or 0, 1, math.max(0, troops-reserve) / math.max(1, troops))
            if intent.ratio ~= intent.ratio or intent.ratio <= 0 or troops * intent.ratio < 100 then return false, "Holding troop reserves" end
            if intent.ratio<.01 then return false,"Order below the game's 1% minimum; holding reserves" end
            if action.plan and action.plan.amount and troops*intent.ratio<action.plan.amount*.9 then
                return false,"Troop budget changed; recalculating the attack"
            end
        elseif kind == "build" or kind == "nuke" then
            if not tileValid(live, intent.tile) or not rules:availability(intent.kind).ok then return false, "Building or weapon is not ready" end
            if not rules:placement(intent.kind, intent.tile).ok then return false, "Placement changed" end
            if kind=="build" and action.safety then
                if Weapons.hazard(s,intent.tile,action.safety.margin) then return false,"Incoming strike threatens the construction site" end
                local map=live.map;local x,y=intent.tile%map.W,intent.tile//map.W
                local radius=math.ceil(action.safety.margin/(map.k_lin or 1))
                for yy=math.max(0,y-radius),math.min(map.H-1,y+radius) do
                    for xx=math.max(0,x-radius),math.min(map.W-1,x+radius) do
                        if (xx-x)^2+(yy-y)^2<=radius*radius then
                            local t=yy*map.W+xx
                            if s:has_fallout(t) or s:tile_owner(t)~=me and (map:is_contestable(t) or not action.safety.coastal) then
                                return false,"Border moved too close to the construction site"
                            end
                        end
                    end
                end
            end
            if kind == "nuke" then
                local allowed,reason=Weapons.canLaunch(s,me,intent.tile,intent.kind)
                if not allowed then return false,reason end
            end
        elseif kind=='donate' then
            local owner=s.owners[intent.target]
            if not owner or not owner.alive or intent.target==me or not s:are_allies(me,intent.target) then return false,'Support partner is no longer allied' end
            local incoming=0
            for _,a in pairs(s.attacks) do if a.target==me and not a.retreating then incoming+=a.troops or 0 end end
            local home=math.max(0,live.info.troops or 0)
            local reserve=math.max(action.reserve or 0,home*.65,incoming*1.5)
            if incoming>0 or type(intent.troops)~='number' or intent.troops~=intent.troops or intent.troops==math.huge then return false,'Holding support during an invasion or invalid budget' end
            intent.troops=math.floor(math.min(intent.troops,home*.08,math.max(0,home-reserve),math.max(0,(owner.max_troops or 0)-(owner.troops or 0))))
            if intent.troops<100 then return false,'No safe troop support budget' end
        elseif kind == "retreat" then
            local attack = s.attacks[intent.attack_id]
            if not attack or attack.attacker ~= me or attack.retreating then return false, "Attack already ended" end
        elseif kind=='ally_extend' then
            local info=type(s.alliance_info)=='function' and s:alliance_info(me,intent.target)
            if not info or not info.can_extend then return false,'Alliance renewal window changed or already requested' end
            if not Weapons.allianceSafe(s,me,intent.target) then return false,'Our strike endangers this alliance' end
            if (s.owners[intent.target].traitor_until or 0)>s.tick then return false,'Alliance partner is marked traitor' end
        elseif kind == "ally_reply" then
            if not s:has_request(intent.target, me) then return false, "Alliance request expired" end
            if intent.accept and not Weapons.allianceSafe(s,me,intent.target) then return false,"Our in-flight strike endangers this alliance" end
            local owner=s.owners[intent.target]
            if intent.accept and (not owner or not owner.alive or (owner.traitor_until or 0)>s.tick) then
                return false,"Alliance partner is no longer reliable"
            end
        elseif kind=="ally_request" or kind=="ally_break" then
            local owner=s.owners[intent.target]
            if not owner or not owner.alive or intent.target==me then return false,"Diplomacy target changed" end
            if kind=="ally_request" and (s:are_allies(me,intent.target) or s:has_request(me,intent.target)
                or (owner.traitor_until or 0)>s.tick) then return false,"Alliance request is no longer needed" end
            if kind=="ally_request" and not Weapons.allianceSafe(s,me,intent.target) then return false,"Our in-flight strike endangers this alliance" end
            if kind=="ally_break" then
                if not s:are_allies(me,intent.target) or (owner.traitor_until or 0)<=s.tick
                    or (live.info.team or 0)>0 and live.info.team==owner.team then return false,"Alliance cannot be safely ended" end
                local exposure=owner.troops or 0
                for id,o in pairs(s.owners) do
                    if id~=me and id~=intent.target and o.alive and not s:are_allies(me,id) then exposure+=o.troops or 0 end
                end
                if (live.info.troops or 0)<=math.max(50000,exposure*4) then return false,"Betrayal would leave too little defensive margin" end
                for _,a in pairs(s.attacks) do
                    if not a.retreating and (a.target==me or a.attacker==me and a.target>0) then return false,"Cannot betray during an active war" end
                end
            end
        elseif kind=="move_warship" then
            local u=(s.units or {})[intent.uid]
            if not u or u.owner~=me or u.kind~=2 or u.state~=0 or not tileValid(live,intent.tile)
                or type(live.map.is_water)~="function" or not live.map:is_water(intent.tile) then return false,"Warship order is no longer valid" end
            if u.max_hp>0 and u.hp<u.max_hp*.8 then return false,"Letting the warship retreat and repair" end
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
