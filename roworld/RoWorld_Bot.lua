-- RoWorld Bot 1.3.0 | paste this entire file into JJSploit.
-- No external script downloads or localhost bridge.

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
        cursor = nil, border = nil, lastAction = "Idle", opponents = {}, attacksSeen = {},
        metrics = {orders=0,attack=0,build=0,retreat=0,spawn=0}, frontsSeen={}}, Policy)
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
    self.metrics.orders+=1
    local kind=action.intent.type;self.metrics[kind]=(self.metrics[kind] or 0)+1
    self.lastPlan=action.plan
    self.history=self.history or {}
    table.insert(self.history,{tick=self.state and self.state.tick or 0,kind=kind,label=action.label,
        target=action.intent.target,tile=action.intent.tile,ratio=action.intent.ratio,
        troops=self.state and self.state.owners[self.me].troops or 0})
    if #self.history>64 then table.remove(self.history,1) end
end

function Policy:reset(frame)
    self.state, self.me = frame.state, frame.me
    self.cursor, self.border = nil, nil
    self.cooldowns = {}
    self.opponents,self.attacksSeen,self.frontsSeen={},{},{}
    self.lastTick=nil;self.lastPlan=nil;self.history={};self.siteCache={}
    self.metrics={orders=0,attack=0,build=0,retreat=0,spawn=0,peakLand=frame.info.tiles or 0,initialLand=frame.info.tiles or 0}
end

local function recruitment(info,seconds)
    local home,cap=math.max(0,info.troops or 0),math.max(1,info.max_troops or 1)
    return math.max(0,(home^.73/4+10)*(1-home/cap)*10*seconds)
end

function Policy:growthTarget(info)
    local cap=math.max(1,info.max_troops or 1)
    if self.growthCap~=cap then
        -- Derivative of (h^.73/4+10)*(1-h/cap), solved without a fixed 42%.
        local lo,hi=0,cap*.73/1.73
        for _=1,28 do
            local h=(lo+hi)/2
            if 1.73*h+40*h^.27<.73*cap then lo=h else hi=h end
        end
        self.growthCap,self.growthBank=cap,(lo+hi)/2
    end
    return self.growthBank
end

function Policy:attackAmount(frame,a,wanted,neutral)
    local target=self:growthTarget(frame.info)
    local reserve=math.max(a.reserve,math.min(target*.92,a.home*.5))
    local budget=math.max(0,a.home-reserve)
    local recovery=recruitment(frame.info,5)*.7
    if neutral then
        -- Early expansion remains possible below the optimum. Once above it,
        -- invest surplus in actual land rather than deliberately wasting troops.
        wanted=math.max(math.max(0,a.home-target),math.min(a.home*.10,recovery))
    end
    local amount=math.floor(math.min(wanted,budget))
    if amount<math.max(100,math.ceil(a.home*.01)) then return nil,reserve end
    return amount,reserve
end

function Policy:opportunity(frame,target)
    local incoming,outgoing=0,0
    for _,a in pairs(frame.state.attacks) do
        if not a.retreating then
            if a.target==target and a.attacker~=frame.me and a.attacker>0
                and not frame.state:are_allies(a.attacker,target) then incoming+=math.max(0,a.troops or 0) end
            if a.attacker==target then outgoing+=math.max(0,a.troops or 0) end
        end
    end
    local bank=math.max(1,(frame.state.owners[target] or {}).troops or 0)
    return math.min(1,incoming/bank),incoming,outgoing
end

function Policy:enemyPlan(frame,g,a,groups)
    local enemy=frame.state.owners[g.id]
    local pressure,third,outgoing=self:opportunity(frame,g.id)
    local wanted=math.max(250,(enemy.troops or 0)*1.4-(a.targets[g.id] or 0)*.5)
    local ceiling,reserve=self:attackAmount(frame,a,wanted,false)
    if not ceiling then return nil end
    local coalition=self:coalitionPressure(frame,g.id,groups)
    local best
    for _,fraction in ipairs({.65,.85,1}) do
        local amount=math.floor(ceiling*fraction)
        if amount>=math.max(100,math.ceil(a.home*.01)) then
            local plan=self:forecast(frame,g,a,amount)
            plan.coalition_pressure=coalition;plan.third_party_incoming=third;plan.enemy_committed=outgoing
            plan.risk+=math.max(0,coalition+a.incoming-(a.home-amount))
            local viable=(amount>=wanted or plan.score>0 and plan.land>=3) and plan.risk<a.home*.05
            if viable then
                -- Preference is bounded: being attacked is an opportunity,
                -- not evidence that an enemy's remaining army has disappeared.
                plan.selection_score=plan.score+pressure*12
                if not best or plan.selection_score>best.selection_score then best=plan end
            end
        end
    end
    if best then best.reserve=reserve;best.pressure=pressure end
    return best
end

function Policy:observe(frame)
    local tick=frame.state.tick or math.floor(frame.now*10)
    if self.lastTick and tick<=self.lastTick then return end
    local dt=self.lastTick and math.min(10,(tick-self.lastTick)/10) or 0
    self.lastTick=tick
    self.globalOutgoing,self.globalIncoming={},{}
    for id,info in pairs(frame.state.owners) do
        if info.alive then
            local m=self.opponents[id] or {heat=0,spending=0}
            m.heat*=math.exp(-dt/30)
            if m.home and dt>0 then
                -- Spending is an observation, not proof of a future attack.
                m.spending=m.spending*.75+math.max(0,m.home-(info.troops or 0))*.25
                m.trend=((info.troops or 0)-m.home)/dt
            end
            m.home,m.tiles=info.troops or 0,info.tiles or 0
            self.opponents[id]=m
        else self.opponents[id]=nil end
    end
    local live={}
    for aid,attack in pairs(frame.state.attacks) do
        live[aid]=true
        if not attack.retreating then
            self.globalOutgoing[attack.attacker]=(self.globalOutgoing[attack.attacker] or 0)+(attack.troops or 0)
            self.globalIncoming[attack.target]=(self.globalIncoming[attack.target] or 0)+(attack.troops or 0)
            if attack.target==frame.me then
                local m=self.opponents[attack.attacker]
                if m and not self.attacksSeen[aid] then m.heat=math.min(3,m.heat+1) end
            end
        end
    end
    self.attacksSeen=live
    self.metrics.peakLand=math.max(self.metrics.peakLand or 0,frame.info.tiles or 0)
end

local function terrain(map,tile)
    if typeof(map.terrain)=="buffer" then return buffer.readu8(map.terrain,tile) end
    if typeof(map.bytes)=="buffer" then
        local v=buffer.readu8(map.bytes,tile)%32
        return v<10 and 2 or v<20 and 3 or 4
    end
    return 2
end

function Policy:frontCost(frame,g)
    local mag,cost=0,0
    local samples=g.tiles or {g.tile}
    for _,tile in ipairs(samples) do
        local t=terrain(frame.map,tile)
        local m=t==4 and 120 or (t==3 or t==5) and 100 or 80
        local c=t==4 and 25 or (t==3 or t==5) and 20 or 16.5
        for _,b in pairs(frame.state.structures) do
            if b.owner==g.id and b.kind==3 and (b.active_tick or 0)<=frame.state.tick
                and frame.map.dist2(tile,b.tile)<=(30/(frame.map.k_lin or 1))^2 then
                m*=5;c*=3;break
            end
        end
        mag+=m;cost+=c
    end
    return mag/#samples,cost/#samples
end

function Policy:forecast(frame,g,armies,amount)
    local enemy=g.id>0 and frame.state.owners[g.id] or nil
    local enemyHome=enemy and (enemy.troops or 0) or 0
    local area=(frame.map.k_lin or 1)^2
    local enemyArea=enemy and math.max(area,(enemy.tiles or 20)*area) or math.huge
    local mag,tileCost=self:frontCost(frame,g)
    local front=math.max(1,math.min(g.front or 1,80)*(frame.map.k_lin or 1))
    local growth=enemy and recruitment(enemy,4) or 0
    local losses,gains,risks=0,0,0
    local m=self.opponents[g.id] or {}
    -- Three bounded responses, not a claim to know a person's hidden inputs.
    for _,reply in ipairs({0,.15,.35}) do
        local bank=enemyHome*(1-reply)+growth*.5
        local power=math.clamp(bank/math.max(amount,1),.6,2)
        local tribe=enemy and enemy.kind==1 and .7 or 1
        local perTile=enemy and mag*tribe*power*(.463+.0039*bank/enemyArea) or mag*.2
        local speed=enemy and math.clamp(bank/math.max(amount,1),.82,7.5)*tileCost/(8.55*front)
            or math.clamp(2000*tileCost/math.max(amount,1),5,100)/(front*2)
        local captured=math.min(enemyArea,40/math.max(.001,speed),amount*.8/math.max(1,perTile))
        local lost=captured*perTile
        local counter=enemyHome*reply
        local third=math.max(0,armies.reserve-armies.incoming*1.35)
        local shortage=math.max(0,armies.incoming+counter+third-(armies.home-amount+recruitment(frame.info,4)*.6))
        losses+=lost/3;gains+=captured/3;risks+=shortage/3
    end
    local after={troops=math.max(0,armies.home-amount),max_troops=frame.info.max_troops}
    local recruitmentLost=math.max(0,recruitment(frame.info,8)-recruitment(after,8))
    local score=gains-losses*.018-risks*.12-amount*.0006-recruitmentLost*.004
    if enemy then
        -- Efficient neutral growth usually wins over a new war. A nearly
        -- finished target, counterattack or observed exposed army can change it.
        score-=8
        if gains>=enemyArea*.75 then score+=math.min(90,enemyArea*.8)+(enemy.gold or 0)*.000015 end
        if (self.globalIncoming[g.id] or 0)>0 then score+=math.min(18,(self.globalIncoming[g.id] or 0)/math.max(enemyHome,1)*8) end
        if m.heat and m.heat>0 then score+=math.min(12,m.heat*6) end
        if armies.targets[g.id] then score+=6 end
    end
    return {score=score,land=gains/area,loss=losses,risk=risks,amount=amount,
        target=g.id,responses="hold / 15% counter / 35% counter; heuristic, not hidden intent"}
end

function Policy:landSample(map, list)
    local bytes = map[list]
    if typeof(bytes) == "buffer" and buffer.len(bytes) >= 4 then
        return buffer.readi32(bytes, self:random(buffer.len(bytes) // 4) * 4)
    end
    return self:random(map.N)
end

function Policy:spawnScore(frame,tile)
    local s,map=frame.state,frame.map
    local score,water,nearest=0,0,math.huge
    local radius=math.max(4,math.ceil(24/(map.k_lin or 1)))
    local step=math.max(1,math.floor(radius/3))
    local x,y=tile%map.W,tile//map.W
    for dy=-radius,radius,step do for dx=-radius,radius,step do
        local xx,yy=x+dx,y+dy
        if xx>=0 and yy>=0 and xx<map.W and yy<map.H then
            local t=yy*map.W+xx
            if map:is_contestable(t) then
                local id=s:tile_owner(t);local o=s.owners[id]
                if id==0 and not s:has_fallout(t) then
                    local kind=terrain(map,t);score+=kind==2 and 2 or kind==3 and .8 or -.5
                elseif o and o.kind==1 then score+=.3 else score-=3 end
            elseif type(map.is_water)=="function" and map:is_water(t) then water+=1 end
        end
    end end
    for id,o in pairs(s.owners) do
        if id~=frame.me and o.alive and o.spawned and valid(map,o.spawn_tile) then
            local distance=math.sqrt(map.dist2(tile,o.spawn_tile))*(map.k_lin or 1)
            if o.kind==1 then
                if distance<100 and (o.troops or 0)<25000 then score+=math.max(0,1-distance/100)*2 end
            elseif not friendly(s,frame.me,id) then
                nearest=math.min(nearest,distance)
                if distance<55 then score-=(55-distance)*2+25 end
            end
        end
    end
    -- Access to a coast is useful; an isolated sliver with little land is not.
    score+=math.min(6,water*.7)+math.min(100,nearest)*.08
    return score
end

function Policy:spawn(frame)
    if not self:ready("spawn", frame.now) then return nil, "Waiting for spawn confirmation" end
    local s, map, best, bestScore = frame.state, frame.map, nil, -math.huge
    for _ = 1, 160 do
        local tile = self:landSample(map, "land_list")
        if valid(map, tile) and map:is_contestable(tile) and s:tile_owner(tile) == 0 and not s:has_fallout(tile) then
            local score = self:spawnScore(frame,tile)
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
    self.siteCache={};self.adjacentAllies={}
    local function site(tile,interior)
        if valid(map, tile) and s:tile_owner(tile) == me and not seen[tile] then
            seen[tile] = true
            if #sites < (interior and 320 or 224) then table.insert(sites, tile) end
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
                if id>0 and id~=me and friendly(s,me,id) then self.adjacentAllies[id]=true end
                if not friendly(s, me, id) and map:is_contestable(t) and not s:has_fallout(t) then
                    local g = groups[id]
                    if not g then g = {id = id, tile = t, front = 0, tiles={},seen={}}; groups[id] = g end
                    if not g.seen[t] then
                        g.seen[t]=true;g.front+=1
                        if #g.tiles<12 then table.insert(g.tiles,t) end
                    end
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
    -- A border-only candidate list missed safe interior construction sites.
    for _=1,96 do site(self:landSample(map,"land_list"),true) end
    for id,g in pairs(groups) do self.frontsSeen[id]={at=frame.now,tile=g.tile} end
    return groups, sites
end

function Policy:siteSafe(frame,tile,kind)
    local margin=(kind=="defense" or kind=="sam") and 8 or 18
    local coastal=kind=="port"
    local key=tostring(tile)..":"..margin..":"..tostring(coastal)
    self.siteCache=self.siteCache or {}
    if self.siteCache[key]~=nil then return self.siteCache[key],margin end
    local map,s=frame.map,frame.state
    local r=math.ceil(margin/(map.k_lin or 1));local x,y=tile%map.W,tile//map.W
    for yy=math.max(0,y-r),math.min(map.H-1,y+r) do
        for xx=math.max(0,x-r),math.min(map.W-1,x+r) do
            if (xx-x)^2+(yy-y)^2<=r*r then
                local t=yy*map.W+xx
                if s:has_fallout(t) or s:tile_owner(t)~=frame.me and (map:is_contestable(t) or not coastal) then
                    self.siteCache[key]=false;return false,margin
                end
            end
        end
    end
    self.siteCache[key]=true;return true,margin
end

function Policy:coalitionPressure(frame,target,groups)
    local pressure=0
    for id,o in pairs(frame.state.owners) do
        if id~=target and id~=frame.me and o.alive and not friendly(frame.state,frame.me,id)
            and frame.state:are_allies(target,id) and (groups[id] or self.frontsSeen[id]) then
            pressure+=(o.troops or 0)*.35
        end
    end
    return pressure
end

function Policy:diplomacy(frame,groups,a)
    if not self:ready("diplomacy",frame.now) then return nil end
    local s=frame.state
    for id,o in pairs(s.owners) do
        if id~=frame.me and o.alive and s:has_request(id,frame.me) and not a.targets[id] then
            local hostile=((self.opponents[id] or {}).heat or 0)>.5
            local accept=not hostile and (o.traitor_until or 0)<=s.tick
            return {intent={type="ally_reply",target=id,accept=accept},channel="diplomacy",cooldown=5,
                label=(accept and "Accepting alliance with " or "Declining unreliable ally ")..o.name}
        end
    end
    for id,o in pairs(s.owners) do
        local sameTeam=(frame.info.team or 0)>0 and frame.info.team==o.team
        if id~=frame.me and o.alive and friendly(s,frame.me,id) and not sameTeam and (o.traitor_until or 0)>s.tick
            and a.enemyActive==0 and a.incoming==0 and (self.adjacentAllies or {})[id] then
            -- Breaking even an unreliable alliance marks US for 30 seconds.
            -- Only permit it with a very large bank covering all nearby enemies.
            local exposure=(o.troops or 0)+self:coalitionPressure(frame,id,groups)
            for other in pairs(groups) do if other>0 then exposure+=(s.owners[other] or {}).troops or 0 end end
            if a.home>math.max(50000,exposure*4) and a.home>(frame.info.max_troops or math.huge)*.85 then
                return {intent={type="ally_break",target=id},channel="diplomacy",cooldown=35,
                    label="Ending a marked traitor's alliance with a defensive margin"}
            end
        end
    end
    -- Ask a strong neighbouring nontraitor for cover, rather than starting
    -- simultaneous wars. Existing requests and allies are not spammed.
    if a.incoming>0 or a.enemyActive>0 or a.strongest>a.home*.8 then
        local best,power
        for id in pairs(groups) do
            local o=s.owners[id]
            if id>0 and o and o.kind~=1 and not a.targets[id] and not friendly(s,frame.me,id)
                and not s:has_request(frame.me,id) and (o.traitor_until or 0)<=s.tick
                and ((self.opponents[id] or {}).heat or 0)<.2 then
                if not power or (o.troops or 0)>power then best,power=id,o.troops or 0 end
            end
        end
        if best then return {intent={type="ally_request",target=best},channel="diplomacy",cooldown=35,
            label="Seeking a safer frontier with "..s:owner_name(best)} end
    end
    return nil
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
    local strongest,pressure = 0,{}
    for id,memory in pairs(self.frontsSeen) do
        local enemy = frame.state.owners[id]
        if frame.now-memory.at>8 or not enemy or not enemy.alive or friendly(frame.state,frame.me,id) then
            self.frontsSeen[id]=nil
        elseif id>0 then
            local bank=enemy.troops or 0
            strongest=math.max(strongest,bank)
            local heat=(self.opponents[id] or {}).heat or 0
            table.insert(pressure,bank*(enemy.kind==2 and .22 or .13)*(1+heat*.35))
        end
    end
    -- Direct calls from tools/tests may provide a frontier before observing it.
    if next(self.frontsSeen)==nil then
        for id in pairs(groups) do
            local enemy=frame.state.owners[id]
            if id>0 and enemy and enemy.alive and not friendly(frame.state,frame.me,id) then
                strongest=math.max(strongest,enemy.troops or 0)
            end
        end
    end
    table.sort(pressure,function(a,b) return a>b end)
    local home = math.max(0, frame.info.troops or 0)
    local predicted=(pressure[1] or 0)+(pressure[2] or 0)*.45
    local reserve=math.min(home,math.max(home*.35,incoming*1.35,math.min(home*.78,math.max(predicted,strongest*.35))))
    return {home = home, reserve = reserve, available = math.max(0, home - reserve),
        incoming = incoming, outgoing = outgoing, enemyActive = enemyActive, neutralActive = neutralActive, targets = targets,
        predictedPressure=predicted,strongest=strongest}
end

function Policy:build(frame, sites, kind, counts)
    if not self:ready("build", frame.now) then return nil end
    local rules = frame.ctx.rules
    local availability = rules:availability(kind)
    if not availability.ok then return nil end
    local best, bestScore
    for i = 1, math.min(320, #sites) do
        local place = rules:placement(kind, sites[i])
        if place.ok and valid(frame.map, place.tile) and self:siteSafe(frame,place.tile,kind) then
            local score = place.upgrade and -10 or 10
            local center = frame.info.label_tile
            if valid(frame.map, center) then score -= math.sqrt(frame.map.dist2(center, place.tile)) * .02 end
            if kind == "defense" or kind == "sam" then
                for _,attack in pairs(frame.state.attacks) do
                    if attack.target==frame.me and valid(frame.map,attack.anchor_tile) then
                        score+=math.max(0,35-math.sqrt(frame.map.dist2(place.tile,attack.anchor_tile)))
                    end
                end
            end
            if bestScore == nil or score > bestScore then best, bestScore = place, score end
        end
    end
    if best then
        return {intent = {type = "build", kind = kind, tile = best.tile}, channel = "build", cooldown = 6,
            safety={margin=(kind=="defense" or kind=="sam") and 8 or 18,coastal=kind=="port"},
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

local function unitTile(s,u)
    local path=u.path or {}
    if #path==0 then return u.patrol_tile end
    local index=math.clamp(math.floor(math.max(0,s.tick-(u.start_tick or s.tick))*100/math.max(1,u.ticks_per_tile_x100 or 100))+1,1,#path)
    return path[index]
end

function Policy:fleet(frame,armies)
    if not self:ready("fleet",frame.now) or type(frame.map.is_water)~="function" then return nil end
    local s,map=frame.state,frame.map
    local ports,ships={},{}
    for _,b in pairs(s.structures) do
        if b.owner==frame.me and b.kind==1 and (b.active_tick or 0)<=s.tick then table.insert(ports,b) end
    end
    if #ports==0 then return nil end
    for _,u in pairs(s.units or {}) do if u.owner==frame.me and u.kind==2 then table.insert(ships,u) end end
    local threat,threatScore,patrol
    for _,port in ipairs(ports) do
        neighbours(map,port.tile,function(t) if map:is_water(t) then patrol=patrol or t end end)
        for _,u in pairs(s.units or {}) do
            local t=unitTile(s,u)
            if u.owner>0 and not friendly(s,frame.me,u.owner) and (u.kind==0 or u.kind==2)
                and valid(map,t) and map:is_water(t) then
                local distance=math.sqrt(map.dist2(t,port.tile))*(map.k_lin or 1)
                local value=(u.kind==0 and 180 or 130)-distance
                if value>0 and (not threatScore or value>threatScore) then threat,threatScore=t,value end
            end
        end
    end
    local target=threat or patrol
    if not target then return nil end
    local wanted=threat and math.min(3,#ports+1) or 1
    if #ships<wanted and frame.ctx.rules:availability("warship").ok
        and (frame.info.gold or 0)>=frame.ctx.rules:cost("warship")*(threat and 1 or 1.7)
        and frame.ctx.rules:placement("warship",target).ok then
        return {intent={type="build",kind="warship",tile=target},channel="fleet",cooldown=10,
            label=threat and "Building a warship against a coastal threat" or "Building a coastal patrol warship"}
    end
    for _,u in ipairs(ships) do
        local t=unitTile(s,u)
        -- Let the game's automatic retreat/heal logic handle damaged ships.
        if u.state==0 and valid(map,t) and (u.max_hp or 0)>0 and u.hp>=u.max_hp*.8 then
            local bodyOf=map.water_body_of or map.body_of
            local sameSea=type(bodyOf)=="function" and bodyOf(map,t)==bodyOf(map,target)
            if sameSea and threat and (not valid(map,u.patrol_tile) or map.dist2(u.patrol_tile,target)> (20/(map.k_lin or 1))^2) then
                return {intent={type="move_warship",uid=u.uid,tile=target},channel="fleet",cooldown=6,
                    label="Moving a warship to intercept a coastal threat"}
            end
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
            local weak = target == 0 or (owner and owner.alive and (owner.troops or 0) < armies.available * .2)
            if target>0 and (armies.enemyActive or 0)>0 and not (armies.targets or {})[target] then weak=false end
            if weak and not friendly(frame.state, frame.me, target) and frame.ctx.borders:can_reach_by_sea(tile) then
                local value = target == 0 and 10 or 20
                local safe=true
                for _,u in pairs(frame.state.units or {}) do
                    local t=unitTile(frame.state,u)
                    if u.kind==2 and not friendly(frame.state,frame.me,u.owner) and valid(frame.map,t)
                        and frame.map.dist2(t,tile)<(150/(frame.map.k_lin or 1))^2 then safe=false;break end
                end
                if valid(frame.map, frame.info.label_tile) then value -= math.sqrt(frame.map.dist2(tile, frame.info.label_tile)) * .02 end
                if safe and (score == nil or value > score) then chosen, score = tile, value end
            end
        end
    end
    if chosen then
        local owner=frame.state.owners[frame.state:tile_owner(chosen)]
        local wanted=owner and math.max(250,(owner.troops or 0)*1.6) or math.max(100,armies.home-self:growthTarget(frame.info))
        local amount,reserve=self:attackAmount(frame,armies,wanted,owner==nil)
        if amount then return {intent = {type = "boat", tile = chosen, ratio = amount/armies.home},
            reserve = reserve, plan={amount=amount},channel = "boat", cooldown = 12, label = "Sending a coastal landing"} end
    end
    return nil
end

function Policy:decide(frame)
    if self.state ~= frame.state or self.me ~= frame.me then self:reset(frame) end
    self:observe(frame)
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
    local diplomatic=self:diplomacy(frame,groups,a)
    if diplomatic then return diplomatic end
    local fleet=self:fleet(frame,a)
    if fleet then return fleet end
    local best, score
    if self:ready("attack", frame.now) and a.enemyActive < 2 then
        for id, g in pairs(groups) do
            local enemy = frame.state.owners[id]
            local anotherWar=a.enemyActive>0 and not a.targets[id]
            if id > 0 and enemy and enemy.alive and not anotherWar then
                local pressure=self:opportunity(frame,id)
                if a.home > (enemy.troops or 0) * (pressure>.3 and 1.1 or 1.35) then
                    local plan=self:enemyPlan(frame,g,a,groups)
                    if plan then
                    local value = math.log(1 + g.front) + a.home / math.max(100, enemy.troops or 0)
                    -- A bounded tie-break: keep the established growth and army
                    -- budgets while preferring lower-cost, less exposed fronts.
                    value+=math.clamp(plan.score/200,-1.5,1.5)+pressure*1.5
                    if (enemy.traitor_until or 0)>frame.state.tick then value+=.5 end
                    if score == nil or value > score then
                        best, score = {intent = {type = "attack", tile = g.tile, ratio = plan.amount / a.home},
                            reserve = plan.reserve, plan=plan, channel = "attack", cooldown = 2.5,
                            label = "Attacking " .. enemy.name}, value
                    end
                    end
                end
            end
        end
    end
    if best then return best end
    if a.incoming > a.home*.25 then return nil,"Defending - holding reserves against observed attacks" end
    local neutral = groups[0]
    if neutral and self:ready("attack", frame.now) and a.available > 200 and a.enemyActive == 0 then
        local surplus=math.max(0,a.home-self:growthTarget(frame.info))
        if a.neutralActive == 0 or surplus>a.home*.08 and (a.targets[0] or 0)<surplus*.5 then
            local amount,reserve=self:attackAmount(frame,a,0,true)
            if amount then return {intent = {type = "attack", tile = neutral.tile, ratio = amount / a.home},
                reserve = reserve,plan={amount=amount,growth_target=self:growthTarget(frame.info)},
                channel = "attack", cooldown = 2.5, label = "Expanding with a recruitment-aware troop budget"} end
        end
    end
    local strike = self:strike(frame)
    if strike then return strike end
    local boat = self:naval(frame, a)
    if boat then return boat end
    if a.enemyActive > 0 or a.neutralActive > 0 then return nil, "Watching the current attack; rebuilding troops" end
    return nil, "Recruiting troops and saving for the next move"
end

function Policy:report()
    local info=self.state and self.state.owners[self.me]
    local threats={}
    for id,m in pairs(self.opponents) do
        if id~=self.me and (m.heat or 0)>0 then
            table.insert(threats,{nation=id,recent_hostility=m.heat,observed_spending=m.spending or 0})
        end
    end
    table.sort(threats,function(a,b) return a.recent_hostility>b.recent_hostility end)
    local allies,traitors,navy={},{},{transports=0,warships=0}
    if self.state then
        for id,o in pairs(self.state.owners) do
            if id~=self.me and self.state:are_allies(self.me,id) then table.insert(allies,id) end
            if (o.traitor_until or 0)>self.state.tick then table.insert(traitors,id) end
        end
        for _,u in pairs(self.state.units or {}) do
            if u.owner==self.me and u.kind==0 then navy.transports+=1 end
            if u.owner==self.me and u.kind==2 then navy.warships+=1 end
        end
    end
    return {version="1.3.0",scope="Since the current observer snapshot; intent estimates are heuristic",
        recruitment_target=info and self:growthTarget(info) or 0,
        tick=self.state and self.state.tick or 0,alive=info and info.alive or false,
        land=info and info.tiles or 0,troops=info and info.troops or 0,metrics=self.metrics,
        gold=info and info.gold or 0,allies=allies,traitors=traitors,navy=navy,recent_orders=self.history or {},
        last_action=self.lastAction,last_plan=self.lastPlan,recent_threats=threats}
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
    local caps, lines = self.capabilities, {"RoWorld Bot 1.3.0 - client access diagnostics"}
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
            local owner=s.owners[intent.target]
            if intent.accept and (not owner or not owner.alive or (owner.traitor_until or 0)>s.tick) then
                return false,"Alliance partner is no longer reliable"
            end
        elseif kind=="ally_request" or kind=="ally_break" then
            local owner=s.owners[intent.target]
            if not owner or not owner.alive or intent.target==me then return false,"Diplomacy target changed" end
            if kind=="ally_request" and (s:are_allies(me,intent.target) or s:has_request(me,intent.target)
                or (owner.traitor_until or 0)>s.tick) then return false,"Alliance request is no longer needed" end
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


end)()

local Wire = (function()

-- Independent reader for the observed RoWorld v2 client wire format.
-- No ModuleScript require, memory inspection, or simulation is used here.
local Wire = {}
local MAX = 16777216
local function reader(bytes, offset)
    return {b=bytes, n=offset or 0, size=buffer.len(bytes)}
end
local function take(r,n)
    assert(n >= 0 and r.n+n <= r.size,"Truncated RoWorld packet")
    local offset=r.n; r.n+=n; return offset
end
local function byte(r) return buffer.readu8(r.b,take(r,1)) end
local function var(r)
    local value, scale=0,1
    for _=1,8 do
        local v=byte(r);value+=(v%128)*scale
        if v<128 then return value end
        scale*=128
    end
    error("Invalid RoWorld varint")
end
local function signed(n) return n%2==0 and n/2 or -(n+1)/2 end
local function count(r, maximum)
    local n=var(r);assert(n <= (maximum or MAX),"RoWorld collection too large");return n
end
local function text(r)
    local n=count(r,r.size);return buffer.readstring(r.b,take(r,n),n)
end
local function opened(packet,decompress)
    local r=reader(packet)
    local envelope=byte(r)
    if envelope==0 then return r end
    assert(envelope==1,"Unknown RoWorld envelope")
    local expected=count(r,128*1024*1024)
    assert(type(decompress)=="function","Zstd decompression is unavailable")
    local compressed=buffer.create(r.size-r.n);buffer.copy(compressed,0,r.b,r.n)
    local result=decompress(compressed)
    assert(buffer.len(result)==expected,"RoWorld decompressed length mismatch")
    return reader(result)
end
local value
value=function(r,depth)
    assert(depth<=32,"RoWorld packet nesting too deep")
    local tag=byte(r)
    if tag>=16 then return tag-16 end
    if tag==0 then return nil end
    if tag==1 then return false end
    if tag==2 then return true end
    if tag==3 then return var(r) end
    if tag==4 then return -var(r)-1 end
    if tag==5 then return buffer.readf64(r.b,take(r,8)) end
    if tag==6 then return text(r) end
    if tag==12 then return {} end
    if tag==10 then
        local result={}
        for _=1,count(r,r.size) do local key=text(r);result[key]=value(r,depth+1) end
        return result
    end
    if tag==7 then
        local result={};for i=1,count(r,r.size) do result[i]=value(r,depth+1) end;return result
    end
    if tag==8 then
        local result,total={},0
        for i=1,count(r,r.size) do total+=signed(var(r));result[i]=total end
        return result
    end
    if tag==11 then
        local n=count(r,r.size);local out=buffer.create(n);buffer.copy(out,0,r.b,take(r,n),n);return out
    end
    if tag==13 or tag==14 then
        local width=tag==13 and byte(r) or nil
        assert(width==nil or width==1 or width==2 or width==4,"Invalid RoWorld grid width")
        local n=count(r);local out=width and buffer.create(n*width) or {};local written=0
        while written<n do
            local entry=var(r);if not width then entry=signed(entry) end
            local run=count(r,n-written);assert(run>0,"Empty RoWorld run")
            if width and entry==0 then -- newly allocated grid is already zeroed
            elseif width==1 then buffer.fill(out,written,entry,run)
            else
                for i=written,written+run-1 do
                    if width==2 then buffer.writeu16(out,i*2,entry)
                    elseif width==4 then buffer.writeu32(out,i*4,entry)
                    else out[i+1]=entry end
                end
            end
            written+=run
        end
        return out
    end
    if tag==9 then
        -- Decode the compressed paths used by the naval observer.
        local n,width=count(r),var(r);assert(width>0 and n>0,"Invalid RoWorld path")
        local out={var(r)};local codes=take(r,math.ceil((n-1)/2))
        for i=1,n-1 do
            local b=buffer.readu8(r.b,codes+(i-1)//2)
            local code=i%2==1 and b%16 or b//16
            if code==15 then out[i+1]=out[i]+signed(var(r))
            else out[i+1]=out[i]+(code//3-1)*width+(code%3-1) end
        end
        return out
    end
    error("Unsupported RoWorld value tag "..tostring(tag))
end
local function tileList(r,base)
    byte(r) -- wire storage hint; return a regular array for either representation
    local n=count(r);local result,previous={},0
    while #result<n do
        local entry,run=var(r),count(r,n-#result);assert(run>0,"Empty RoWorld tile run")
        for _=1,run do previous+=signed(var(r));table.insert(result,previous*base+entry) end
    end
    return result
end
function Wire.snapshot(packet,decompress)
    local r=opened(packet,decompress);assert(byte(r)==2,"Expected RoWorld snapshot")
    local result=value(r,0);assert(type(result)=="table" and r.n==r.size,"Invalid RoWorld snapshot")
    return result
end
function Wire.delta(packet,tail,decompress)
    local r=opened(packet,decompress);assert(byte(r)==1,"Expected RoWorld delta")
    local flags,result=byte(r),{}
    if bit32.band(flags,32)~=0 then result.t=var(r) end
    if bit32.band(flags,1)~=0 then result.tiles=tileList(r,1024) end
    if bit32.band(flags,2)~=0 then result.flags=tileList(r,256) end
    if bit32.band(flags,4)~=0 then
        byte(r);result.stats={};for i=1,count(r,r.size*2) do result.stats[i]=signed(var(r)) end
    end
    if bit32.band(flags,8)~=0 then
        result.ev={};for i=1,count(r,r.size) do result.ev[i]=value(r,1) end
    end
    if bit32.band(flags,16)~=0 then for k,v in pairs(value(r,1)) do result[k]=v end end
    assert(r.n==r.size,"Trailing RoWorld delta data")
    if tail then
        local tr=opened(tail,decompress);assert(byte(tr)==3,"Expected RoWorld event tail")
        result.ev=result.ev or {}
        for _=1,count(tr,tr.size) do
            local index=var(tr);local event=value(tr,1)
            table.insert(result.ev,math.clamp(index,1,#result.ev+1),event)
        end
        assert(tr.n==tr.size,"Trailing RoWorld tail data")
    end
    return result
end
function Wire.intent(intent)
    local types={spawn=1,attack=2,boat=3,build=4,nuke=5,retreat=6,move_warship=7,ally_request=8,ally_reply=9,ally_break=10}
    local fields={"tile","target","attack_id","troops","uid"}
    local out=buffer.create(128);local at=3
    buffer.writeu8(out,1,4);buffer.writeu8(out,2,assert(types[intent.type],"Unsupported order"))
    local function write(n)
        repeat local b=n%128;n=math.floor(n/128);buffer.writeu8(out,at,b+(n>0 and 128 or 0));at+=1 until n==0
    end
    local mask=0
    for i,key in ipairs(fields) do if intent[key]~=nil then mask+=2^(i-1) end end
    if intent.ratio~=nil then mask+=32 end
    if intent.kind~=nil then mask+=64 end
    if intent.accept~=nil then mask+=128 end
    buffer.writeu8(out,at,mask);at+=1
    for _,key in ipairs(fields) do
        local n=intent[key];if n~=nil then assert(n%1==0 and math.abs(n)<2147483647);write(n>=0 and n*2 or -n*2-1) end
    end
    if intent.ratio~=nil then assert(intent.ratio==intent.ratio);buffer.writef64(out,at,intent.ratio);at+=8 end
    if intent.kind~=nil then assert(#intent.kind<=16);write(#intent.kind);buffer.writestring(out,at,intent.kind);at+=#intent.kind end
    if intent.accept~=nil then buffer.writeu8(out,at,intent.accept and 1 or 0);at+=1 end
    local result=buffer.create(at);buffer.copy(result,0,out,0,at);return result
end
return Wire


end)()

local Mirror = (function()

-- Read-only multiplayer observations. This does not run or modify game physics.
local Mirror={}
local State={};State.__index=State
local KINDS={city=0,port=1,factory=2,defense=3,sam=4,silo=5}
local function adjacent(map,t,fn)
    local x=t%map.W
    if x>0 then fn(t-1) end;if x<map.W-1 then fn(t+1) end
    if t>=map.W then fn(t-map.W) end;if t<map.N-map.W then fn(t+map.W) end
end
local function key(a,b) return math.min(a,b)*1024+math.max(a,b) end
function State:tile_owner(t) assert(t>=0 and t<self.map.N);return buffer.readi32(self.owner,t*4) end
function State:has_fallout(t) return bit32.band(buffer.readu8(self.flags,t),1)~=0 end
function State:owner_name(id) return self.owners[id] and self.owners[id].name or "Unknown" end
function State:are_allies(a,b)
    if a==0 or b==0 or a==b then return false end
    local x,y=self.owners[a],self.owners[b]
    return self.alliances[key(a,b)]==true or (x and y and x.team>0 and x.team==y.team) or false
end
function State:has_request(a,b) return self.requests[a*1024+b]~=nil end
function State:borders_tile(id,t)
    local found=false;adjacent(self.map,t,function(n) if self:tile_owner(n)==id then found=true end end);return found
end
function State:recheck(t)
    if self:tile_owner(t)~=self.local_owner then self.border[t]=nil;return end
    local border=false;adjacent(self.map,t,function(n) if self:tile_owner(n)~=self.local_owner then border=true end end)
    self.border[t]=border or nil
end
local function owner(row)
    return {id=row[1],name=tostring(row[2]),kind=row[4] or 0,team=row[5] or 0,alive=row[6]==true,
        troops=row[8] or 0,gold=row[9] or 0,max_troops=row[10] or 0,income=row[11] or 0,
        traitor_until=row[12] or 0,spawn_tile=row[13] or -1,spawned=(row[13] or -1)>=0,label_tile=row[13] or -1,tiles=0}
end
local function unit(s,row,offset)
    offset=offset or 0
    local u={uid=row[offset+1],kind=row[offset+2],owner=row[offset+3],path=row[offset+4] or {},
        start_tick=row[offset+5] or 0,ticks_per_tile_x100=row[offset+6] or 100,troops=row[offset+7] or 0,
        hp=row[offset+8] or 0,max_hp=row[offset+9] or 0,veterancy=row[offset+10] or 0,
        state=row[offset+11] or 0,patrol_tile=row[offset+12] or -1}
    s.units[u.uid]=u;return u
end
local function structure(s,row,offset)
    offset=offset or 0
    local b={sid=row[offset+1],kind=row[offset+2],owner=row[offset+3],tile=row[offset+4],
        level=row[offset+5] or 1,active_tick=row[offset+6] or 0}
    s.structures[b.sid]=b;return b
end
local function attack(s,row,offset)
    offset=offset or 0
    s.attacks[row[offset+1]]={aid=row[offset+1],attacker=row[offset+2],target=row[offset+3],
        troops=row[offset+4],anchor_tile=row[offset+5],retreating=row[offset+6]==true}
end
function Mirror.map(meta,raw,snapshot,yield)
    yield=yield or function() end
    local w,h=snapshot.map_w or meta.width,snapshot.map_h or meta.height
    assert(type(w)=="number" and type(h)=="number" and w>0 and h>0 and w*h<=16777216,"Invalid snapshot dimensions")
    assert(buffer.len(raw)==meta.width*meta.height,"Invalid terrain length")
    local map={W=w,H=h,N=w*h,k_lin=(meta.k_lin or 1)*(meta.width/w)}
    map.bytes=buffer.create(map.N)
    local land,coast=buffer.create(map.N*4),buffer.create(map.N*4)
    local lands,coasts=0,0
    function map.dist2(a,b) return (a%w-b%w)^2+(a//w-b//w)^2 end
    function map:is_contestable(t) return t>=0 and t<self.N and buffer.readu8(self.bytes,t)>=128 and buffer.readu8(self.bytes,t)~=159 end
    function map:is_water(t) return t>=0 and t<self.N and buffer.readu8(self.bytes,t)<128 end
    function map:is_coastal(t)
        if not self:is_contestable(t) then return false end
        local water=false;adjacent(self,t,function(n) if self:is_water(n) then water=true end end);return water
    end
    for t=0,map.N-1 do
        local x,y=t%w,t//w
        local source=math.min(meta.height-1,math.floor((y+.5)*meta.height/h))*meta.width+math.min(meta.width-1,math.floor((x+.5)*meta.width/w))
        buffer.writeu8(map.bytes,t,buffer.readu8(raw,source))
        if t%32768==0 then yield() end
    end
    for t=0,map.N-1 do
        if map:is_contestable(t) then
            buffer.writei32(land,lands*4,t);lands+=1
            if map:is_coastal(t) then buffer.writei32(coast,coasts*4,t);coasts+=1 end
        end
        if t%32768==0 then yield() end
    end
    map.land_list,map.coast_list=buffer.create(lands*4),buffer.create(coasts*4)
    buffer.copy(map.land_list,0,land,0,lands*4);buffer.copy(map.coast_list,0,coast,0,coasts*4)
    -- Four-neighbour water components, computed once per terrain download.
    -- Match the game's left/right/up/down coastal-body convention.
    map.water_body=buffer.create(map.N*4)
    local queue=buffer.create(map.N*4);local body,work=0,0
    for t=0,map.N-1 do
        if map:is_water(t) and buffer.readu32(map.water_body,t*4)==0 then
            body+=1;local head,tail=0,1
            buffer.writeu32(queue,0,t);buffer.writeu32(map.water_body,t*4,body)
            while head<tail do
                local p=buffer.readu32(queue,head*4);head+=1
                adjacent(map,p,function(n)
                    if map:is_water(n) and buffer.readu32(map.water_body,n*4)==0 then
                        buffer.writeu32(map.water_body,n*4,body);buffer.writeu32(queue,tail*4,n);tail+=1
                    end
                end)
                work+=1;if work%32768==0 then yield() end
            end
        end
        if t%32768==0 then yield() end
    end
    function map:water_body_of(t)
        return t>=0 and t<self.N and buffer.readu32(self.water_body,t*4) or 0
    end
    function map:coast_body_of(t)
        local found=0
        adjacent(self,t,function(n) if found==0 then found=self:water_body_of(n) end end)
        return found
    end
    return map
end
function Mirror.snapshot(data,map,me,yield)
    assert(typeof(data.owner)=="buffer" and buffer.len(data.owner)==map.N*4,"Incomplete ownership snapshot")
    assert(typeof(data.flags)=="buffer" and buffer.len(data.flags)==map.N,"Incomplete fallout snapshot")
    local s=setmetatable({map=map,owner=data.owner,flags=data.flags,owners={},structures={},attacks={},nukes={},units={},
        alliances={},requests={},built={},border={},local_owner=me,tick=data.t or 0,phase=data.phase or 0,loaded=false,
        rules={STRUCT_MIN_DIST=15/map.k_lin,MAX_BOATS_PLAYER=10}},State)
    for _,row in ipairs(data.owners or {}) do s.owners[row[1]]=owner(row) end
    for _,row in ipairs(data.structs or {}) do structure(s,row) end
    for _,row in ipairs(data.attacks or {}) do attack(s,row) end
    for _,row in ipairs(data.units or {}) do unit(s,row) end
    for _,row in ipairs(data.allies or {}) do s.alliances[key(row[1],row[2])]=true end
    for _,row in ipairs(data.requests or {}) do s.requests[row[1]*1024+row[2]]=row[3] or s.tick end
    for _,row in ipairs(data.built or {}) do
        s.built[row[1]]={};for i=0,15 do s.built[row[1]][i]=row[i+2] or 0 end
    end
    for t=0,map.N-1 do
        local id=s:tile_owner(t);local info=s.owners[id]
        if info then info.tiles+=1;if info.label_tile<0 then info.label_tile=t end end
        if id==me then s:recheck(t) end
        if yield and t%32768==0 then yield() end
    end
    assert(s.owners[me]~=nil,"Snapshot has no local nation")
    s.loaded=true;return s
end
local function built(s,id,kind)
    s.built[id]=s.built[id] or {};s.built[id][kind]=(s.built[id][kind] or 0)+1
end
function Mirror.delta(s,d)
    if d.t and d.t<=s.tick then return end
    assert(type(d.t)=="number","Delta has no authoritative tick")
    -- Reliable ordered RemoteEvents may coalesce multiple simulation ticks.
    -- A larger tick increment is not evidence of missing ownership updates.
    s.tick=d.t
    for _,entry in ipairs(d.tiles or {}) do
        local tile,id=entry//1024,entry%1024;assert(tile>=0 and tile<s.map.N,"Invalid ownership update")
        local old=s:tile_owner(tile)
        if old~=id then
            if s.owners[old] then s.owners[old].tiles-=1 end
            if s.owners[id] then s.owners[id].tiles+=1 end
            buffer.writei32(s.owner,tile*4,id);s:recheck(tile);adjacent(s.map,tile,function(n) s:recheck(n) end)
        end
    end
    for _,entry in ipairs(d.flags or {}) do
        local tile=entry//256;assert(tile>=0 and tile<s.map.N);buffer.writeu8(s.flags,tile,entry%256)
    end
    for i=1,#(d.stats or {}),6 do
        local row=d.stats;local info=s.owners[row[i]]
        if info then info.troops=row[i+2];info.gold=row[i+3];info.max_troops=row[i+4];info.income=row[i+5] end
    end
    for _,e in ipairs(d.ev or {}) do
        local kind,id=e[1],e[2]
        if kind==0 then s.owners[id]={id=id,name=tostring(e[3]),kind=e[5],team=e[6] or 0,alive=true,spawned=false,spawn_tile=-1,label_tile=-1,tiles=0,troops=0,gold=0,max_troops=0}
        elseif kind==1 and s.owners[id] then s.owners[id].alive=false
        elseif kind==2 then s.phase=id
        elseif kind==3 and s.owners[id] then local info=s.owners[id];info.spawned=true;info.spawn_tile=e[3];info.label_tile=e[3]
        elseif kind==4 then local b=structure(s,e,1);built(s,b.owner,b.kind)
        elseif kind==5 and s.structures[id] then s.structures[id].owner=e[3]
        elseif kind==6 then s.structures[id]=nil
        elseif kind==9 then local u=unit(s,e,1);if u.kind==2 then built(s,u.owner,15) end
        elseif kind==10 and s.units[id] then s.units[id].path={e[3]};s.units[id].start_tick=s.tick
        elseif kind==11 then s.units[id]=nil
        elseif kind==14 then attack(s,e,1)
        elseif kind==15 then s.attacks[id]=nil
        elseif kind==16 then s.requests[id*1024+e[3]]=e[4] or s.tick
        elseif kind==17 then s.alliances[key(id,e[3])]=true;s.requests[id*1024+e[3]]=nil;s.requests[e[3]*1024+id]=nil
        elseif kind==18 then s.alliances[key(id,e[3])]=nil
        elseif kind==20 then s.phase=2
        elseif kind==21 then s.requests[id*1024+e[3]]=nil
        elseif kind==22 and s.owners[id] then s.owners[id].traitor_until=e[3]
        elseif kind==23 and s.structures[id] then
            local b=s.structures[id];local added=e[3]-b.level
            for _=1,math.max(0,added) do built(s,b.owner,b.kind) end
            b.level,b.active_tick=e[3],e[4]
        elseif kind==25 and s.units[id] then s.units[id].hp=e[3];s.units[id].max_hp=e[4]
        elseif kind==26 and s.units[id] then s.units[id].veterancy=e[3]
        elseif kind==27 and s.units[id] then s.units[id].state=e[3];s.units[id].patrol_tile=e[4]
        elseif kind==28 and s.units[id] then
            local u=s.units[id];u.path=e[3];u.start_tick=e[4];u.ticks_per_tile_x100=e[5]
        end
    end
end
function Mirror.context(session)
    local ctx={session=session,state=session.state}
    function ctx:in_match() return self.session.connected and self.state.loaded end
    local borders={border=session.state.border}
    function borders:has_coast()
        for tile in pairs(self.border) do if ctx.state.map:is_coastal(tile) then return true end end
        return false
    end
    function borders:can_reach_by_sea(tile)
        local map=ctx.state.map
        if not map:is_coastal(tile) then return false end
        local body=map:coast_body_of(tile)
        if self.bodyTick~=ctx.state.tick then
            self.bodyTick=ctx.state.tick;self.bodies={}
            for t in pairs(self.border) do
                if map:is_coastal(t) then self.bodies[map:coast_body_of(t)]=true end
            end
        end
        return body>0 and self.bodies[body]==true
    end
    ctx.borders=borders
    local rules={}
    function rules:transports()
        local count=0;for _,u in pairs(ctx.state.units) do if u.owner==ctx.state.local_owner and u.kind==0 then count+=1 end end
        return count
    end
    function rules:cost(kind)
        local s,id=ctx.state,ctx.state.local_owner;local k=KINDS[kind]
        if kind=="warship" then
            local count=0;for _,u in pairs(s.units) do if u.owner==id and u.kind==2 then count+=1 end end
            return math.min(1000000,(math.min(count,(s.built[id] or {})[15] or 0)+1)*250000)
        end
        if k==nil then return math.huge end
        local kinds=(kind=="port" or kind=="factory") and {1,2} or {k};local n=0
        for _,wanted in ipairs(kinds) do
            local levels=0;for _,b in pairs(s.structures) do if b.owner==id and b.kind==wanted then levels+=b.level end end
            n+=math.min(levels,(s.built[id] or {})[wanted] or 0)
        end
        if k<=2 then return math.min(1000000,125000*2^math.min(n,4)) end
        if k==3 then return math.min(250000,(n+1)*50000) end
        if k==4 then return math.min(3000000,(n+1)*1500000) end
        return 1000000
    end
    function rules:availability(kind)
        -- SAM and silo are deferred because this fallback only reads land/economy.
        local supported=kind=="city" or kind=="factory" or kind=="port" or kind=="defense" or kind=="warship"
        local info=ctx.state.owners[ctx.state.local_owner]
        local port=kind~="warship"
        if not port then for _,b in pairs(ctx.state.structures) do
            if b.owner==ctx.state.local_owner and b.kind==1 and b.active_tick<=ctx.state.tick then port=true;break end
        end end
        return {ok=supported and info.alive and info.spawned and ctx.state.phase==1 and info.gold>=self:cost(kind)
            and port and (kind~="port" or borders:has_coast()),cost=self:cost(kind)}
    end
    function rules:placement(kind,tile)
        local s,id,map=ctx.state,ctx.state.local_owner,ctx.state.map
        local result={ok=false,tile=tile}
        if kind=="warship" then
            if not self:availability(kind).ok or not map:is_water(tile) then return result end
            for _,b in pairs(s.structures) do
                if b.owner==id and b.kind==1 and b.active_tick<=s.tick
                    and map:coast_body_of(b.tile)==map:water_body_of(tile) then result.ok=true;return result end
            end
            return result
        end
        if not self:availability(kind).ok or s:tile_owner(tile)~=id or not map:is_contestable(tile) then return result end
        if kind=="port" and not map:is_coastal(tile) then return result end
        for _,b in pairs(s.structures) do
            if map.dist2(tile,b.tile)<s.rules.STRUCT_MIN_DIST^2 then
                if b.owner==id and b.kind==KINDS[kind] and b.kind~=3 and b.active_tick<=s.tick then
                    return {ok=true,tile=b.tile,upgrade=true}
                end
                return result
            end
        end
        result.ok=true;return result
    end
    ctx.rules=rules;return ctx
end
return Mirror


end)()

local Network = (function()

-- Independent observer of the player's existing multiplayer connection.
local Network={};Network.__index=Network
function Network.new(services,wire,mirror,now,spawn,cooperate,decompress)
    return setmetatable({services=services,wire=wire,mirror=mirror,now=now,spawn=spawn,cooperate=cooperate,
        decompress=decompress,queue={},generation=0,packets=0,lastRequest=-math.huge,lastPacket=0,
        status="Join multiplayer; waiting for a server snapshot",destroyed=false,maps={}},Network)
end
function Network:invalidate(reason)
    self.status=reason;self.error=reason
    if self.session and self.session.state then self.session.state.loaded=false end
    self.needsSnapshot=true
end
function Network:fetchMap(data)
    local id=assert(data.map_id,"Snapshot has no map ID")
    local base=id:match("^(.-)@%d+$") or id
    local cache=self.maps[base]
    if cache then return self.mirror.map(cache.meta,cache.raw,data,self.cooperate) end
    local remote=self.root:FindFirstChild("GetMap")
    assert(remote and remote:IsA("RemoteFunction"),"RoWorld map service unavailable")
    local meta=remote:InvokeServer(base,0)
    assert(type(meta)=="table" and typeof(meta.chunk)=="buffer","RoWorld map request returned no terrain")
    assert(type(meta.zsize)=="number" and meta.zsize>0 and meta.zsize<=32*1024*1024,"Invalid map download size")
    assert(type(meta.chunks)=="number" and meta.chunks>=1 and meta.chunks<=50,"Invalid map chunk count")
    local zipped=buffer.create(meta.zsize);local offset=buffer.len(meta.chunk)
    assert(offset<=meta.zsize);buffer.copy(zipped,0,meta.chunk)
    for index=1,meta.chunks-1 do
        assert(not self.destroyed,"Observer stopped")
        local part=remote:InvokeServer(base,index)
        assert(type(part)=="table" and typeof(part.chunk)=="buffer","Interrupted RoWorld map download")
        local size=buffer.len(part.chunk);assert(offset+size<=meta.zsize,"Oversized map chunk")
        buffer.copy(zipped,offset,part.chunk);offset+=size
    end
    assert(offset==meta.zsize,"Incomplete map download")
    local raw=self.decompress(zipped)
    self.maps[base]={meta=meta,raw=raw}
    return self.mirror.map(meta,raw,data,self.cooperate)
end
function Network:process(row)
    if row.op==21 then
        self.status="Reading multiplayer snapshot and terrain..."
        local data=self.wire.snapshot(row.body,self.decompress)
        local map=self:fetchMap(data)
        local state=self.mirror.snapshot(data,map,row.me,self.cooperate)
        if self.destroyed or row.generation~=self.generation then return end
        local observer=self
        local session={mode=2,_sim=nil,state=state,connected=true}
        function session:multiplayer_available() return self.connected and not observer.destroyed end
        function session:send_intent(intent)
            assert(self.state.loaded and self.connected and not observer.destroyed,"Observer is not synchronized")
            observer.toServer:FireServer(4,observer.wire.intent(intent))
        end
        function session:note_activity()
            if observer.now()-(observer.lastActivity or -math.huge)>=30 then
                observer.lastActivity=observer.now();observer.toServer:FireServer(7)
            end
        end
        self.session=session;self.main={session=session,ui={ctx=self.mirror.context(session)}}
        self.needsSnapshot=false;self.closed=false;self.error=nil;self.status="Multiplayer snapshot synchronized"
        self.lastUpdate=self.now()
    elseif row.op==22 and self.session and self.session.state.loaded then
        local delta=self.wire.delta(row.body,row.tail,self.decompress)
        self.mirror.delta(self.session.state,delta)
        self.lastUpdate=self.now()
    end
end
function Network:receive(op,...)
    if self.destroyed then return end
    self.packets+=1;self.lastPacket=self.now()
    if op==24 then
        self.generation+=1;table.clear(self.queue)
        self.closed=true;self:invalidate("Match closed; join a multiplayer match");return
    end
    if op==31 then
        self.generation+=1;table.clear(self.queue)
        self:invalidate("Your nation changed; waiting for a fresh snapshot");return
    end
    local row
    if op==21 then
        local me,packet=...
        if type(me)~="number" or typeof(packet)~="buffer" then return end
        self.generation+=1;table.clear(self.queue)
        if self.session then self.session.state.loaded=false end
        if me==0 then
            self.needsSnapshot=false;self.status="Spectating; select your nation before starting autoplay";return
        end
        row={op=op,me=me,body=packet,generation=self.generation}
    elseif op==22 then
        local packet,tail=...
        if typeof(packet)~="buffer" or (tail~=nil and typeof(tail)~="buffer") then return end
        row={op=op,body=packet,tail=tail,generation=self.generation}
    else return end
    if #self.queue>=256 then
        self.generation+=1;table.clear(self.queue);self:invalidate("Observer update queue overflow; resynchronizing");return
    end
    table.insert(self.queue,row)
    if self.working then return end
    self.working=true
    self.spawn(function()
        while not self.destroyed and #self.queue>0 do
            local item=table.remove(self.queue,1)
            if item.generation==self.generation then
                local ok,err=pcall(function() self:process(item) end)
                if not ok and item.generation==self.generation then
                    self.generation+=1;table.clear(self.queue);self:invalidate("Network observer: "..tostring(err))
                end
            end
        end
        self.working=false
    end)
end
function Network:poll()
    if self.destroyed then return nil end
    if not self.connection then
        local replicated=self.services.ReplicatedStorage
        local root=replicated and replicated:FindFirstChild("AirfrontNet")
        local input=root and root:FindFirstChild("ToClient")
        local output=root and root:FindFirstChild("ToServer")
        if not input or not output then self.status="Waiting for RoWorld multiplayer remotes";return nil end
        self.root,self.toServer=root,output
        self.connection=input.OnClientEvent:Connect(function(...) self:receive(...) end)
        self.needsSnapshot=true
    end
    if self.session and self.session.state.loaded and (self.now()-self.lastPacket>6 or
        self.session.state.phase==1 and self.now()-(self.lastUpdate or self.lastPacket)>6) then
        self:invalidate("Multiplayer updates stopped; resynchronizing")
    end
    if not self.closed and self.needsSnapshot and not self.working and self.now()-self.lastRequest>=10 then
        self.lastRequest=self.now()
        -- The game's normal resync operation for this client's existing match.
        -- Never HELLO/JOIN/LEAVE, never switch queues or impersonate an owner.
        local ok,err=pcall(function() self.toServer:FireServer(6) end)
        if not ok then self:invalidate("Multiplayer resync request failed: "..tostring(err)) end
    end
    return self.main
end
function Network:diagnostics()
    return "network_packets="..self.packets.."\nnetwork_status="..self.status.."\nnetwork_error="..tostring(self.error or "none")
end
function Network:destroy()
    self.destroyed=true;self.generation+=1;table.clear(self.queue)
    if self.connection then self.connection:Disconnect() end
    if self.session then self.session.connected=false;self.session.state.loaded=false end
end
return Network


end)()

-- Policy and Adapter are embedded by build.py in the standalone script.
local Services = {
    Players = game:GetService("Players"),
    CoreGui = game:GetService("CoreGui"),
    UserInputService = game:GetService("UserInputService"),
    RunService = game:GetService("RunService"),
    ReplicatedStorage = game:GetService("ReplicatedStorage"),
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
    getconnections = getconnections,
    getupvalues = getupvalues or (debug and debug.getupvalues),
    getupvalue = getupvalue or (debug and debug.getupvalue),
    getfenv = getfenv,
    getsenv = getsenv,
    getrenv = getrenv,
})
adapter.network = Network.new(Services,Wire,Mirror,os.clock,task.spawn,function() task.wait() end,function(bytes)
    return game:GetService("EncodingService"):DecompressBuffer(bytes,Enum.CompressionAlgorithm.Zstd)
end)
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
local lastReport=-math.huge
local endReported=false
local reportState
function api.report() return policy:report() end
local function saveMatchReport(force,reason)
    if type(writefile)~="function" or not policy.state then return end
    if not force and os.clock()-lastReport<30 then return end
    lastReport=os.clock()
    local ok,encoded=pcall(function()
        local report=policy:report();report.saved_reason=reason
        return game:GetService("HttpService"):JSONEncode(report)
    end)
    if ok then pcall(writefile,"RoWorld_Match_Report.json",encoded) end
end
local lastCommand, lastCommandAt = "", -math.huge
local function toggle()
    api.enabled = not api.enabled
    if api.enabled then
        policy = Policy.new()
        endReported=false
        repaint("Connecting to your RoWorld match...")
    else
        saveMatchReport(true,"stopped by user")
        repaint("Stopped - no new orders; existing game attacks continue")
    end
end
table.insert(api.connections, button.Activated:Connect(toggle))
table.insert(api.connections, Services.UserInputService.InputBegan:Connect(function(input, consumed)
    if not consumed and input.KeyCode == Enum.KeyCode.F6 then toggle() end
end))
function api.destroy()
    api.alive, api.enabled = false, false
    adapter.network:destroy()
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
                if policy.state~=reportState then
                    reportState=policy.state;endReported=false;lastReport=-math.huge
                end
                local info=policy.state and policy.state.owners[policy.me]
                local ended=info and (not info.alive or policy.state.phase==2 or adapter.network.closed)
                saveMatchReport(ended and not endReported,ended and "match ended" or "periodic")
                if ended then endReported=true end
            else
                api.enabled = false
                repaint("Stopped after an error: " .. tostring(message))
                warn("[RoWorldBot] " .. tostring(message))
            end
        end
        task.wait(.55)
    end
end)
