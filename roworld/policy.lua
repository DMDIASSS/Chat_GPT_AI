-- RoWorld strategy adapted from Solo AggroBot's reserve / expansion approach.
-- This module reads client observations and returns one ordinary game order.
local Policy = {}
local Weapons = require("./weapons")
local Strategy = require("./strategy")
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
    if self.strategy then self.strategy:sent(action,self.state,self.me,now) end
    self.history=self.history or {}
    local target=action.intent.target or (action.intent.tile and self.state and self.state:tile_owner(action.intent.tile))
    table.insert(self.history,{tick=self.state and self.state.tick or 0,kind=kind,label=action.label,
        target=target,target_kind=target and self.state and (self.state.owners[target] or {}).kind,
        tile=action.intent.tile,ratio=action.intent.ratio,
        troops=self.state and self.state.owners[self.me].troops or 0})
    if #self.history>64 then table.remove(self.history,1) end
end

function Policy:reset(frame)
    self.state, self.me = frame.state, frame.me
    self.cursor, self.border = nil, nil
    self.cooldowns = {}
    self.opponents,self.attacksSeen,self.frontsSeen={},{},{}
    self.lastTick=nil;self.lastPlan=nil;self.history={};self.siteCache={}
    self.spawnPlan=nil
    self.strategy=Strategy.new(frame)
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
    if self.strategy and not self.strategy:canTarget(frame,g.id,a) then return nil end
    local pressure,third,outgoing=self:opportunity(frame,g.id)
    local wanted=math.max(250,(enemy.troops or 0)*1.4-(a.targets[g.id] or 0)*.5)
    local ceiling,reserve=self:attackAmount(frame,a,wanted,false)
    if not ceiling then return nil end
    if enemy.kind==2 then ceiling=math.min(ceiling,math.floor(a.home*.15)) end
    local coalition=self:coalitionPressure(frame,g.id,groups)
    local best
    for _,fraction in ipairs({.65,.85,1}) do
        local amount=math.floor(ceiling*fraction)
        if amount>=math.max(100,math.ceil(a.home*.01)) then
            local plan=self:forecast(frame,g,a,amount)
            plan.coalition_pressure=coalition;plan.third_party_incoming=third;plan.enemy_committed=outgoing
            if enemy.kind==0 then
                plan.country_counter=Strategy.countryCounter(amount,enemy.troops or 0)
                plan.risk+=math.max(0,plan.country_counter+a.incoming+coalition-(a.home-amount))
            end
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
    if self.strategy then self.strategy:observe(frame) end
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
    local score,water,land,nearest,players=0,0,0,math.huge,0
    local sectors={}
    local radius=math.max(4,math.ceil(24/(map.k_lin or 1)))
    local step=math.max(1,math.floor(radius/3))
    local x,y=tile%map.W,tile//map.W
    local function isWater(t)
        return type(map.is_water)=="function" and map:is_water(t) or map.water and map.water[t]==true
    end
    for dy=-radius,radius,step do for dx=-radius,radius,step do
        local xx,yy=x+dx,y+dy
        if xx>=0 and yy>=0 and xx<map.W and yy<map.H then
            local t=yy*map.W+xx
            if map:is_contestable(t) then
                local id=s:tile_owner(t);local o=s.owners[id]
                if id==0 and not s:has_fallout(t) then
                    land+=1;local kind=terrain(map,t);score+=kind==2 and 2 or kind==3 and .8 or -.5
                elseif o and o.kind==1 then land+=1;score+=.3 else score-=3 end
            elseif isWater(t) then water+=1 end
        end
    end end
    for id,o in pairs(s.owners) do
        if id~=frame.me and o.alive and o.spawned and valid(map,o.spawn_tile) then
            local distance=math.sqrt(map.dist2(tile,o.spawn_tile))*(map.k_lin or 1)
            if o.kind==1 then
                if distance<100 and (o.troops or 0)<25000 then score+=math.max(0,1-distance/100)*2 end
            elseif o.kind==2 and not friendly(s,frame.me,id) then
                nearest=math.min(nearest,distance)
                if distance<180 then
                    players+=1;score-=20*(1-distance/180)
                    local dx,dy=o.spawn_tile%map.W-x,o.spawn_tile//map.W-y
                    local sector=math.floor((math.atan2(dy,dx)+math.pi)*4/math.pi)%8
                    sectors[sector]=true
                end
                if distance<55 then score-=(55-distance)*2+25 end
            elseif o.kind==0 and not friendly(s,frame.me,id) and distance<80 and (o.troops or 0)>50000 then
                score-=8*(1-distance/80)
            end
        end
    end
    local protected,open,blocked=0,0,0
    local rayStep=math.max(2,math.ceil(20/(map.k_lin or 1)))
    for _,d in ipairs({{1,0},{1,1},{0,1},{-1,1},{-1,0},{-1,-1},{0,-1},{1,-1}}) do
        local clean=true
        for n=1,3 do
            local xx,yy=x+d[1]*rayStep*n,y+d[2]*rayStep*n
            if xx<0 or yy<0 or xx>=map.W or yy>=map.H then clean=false;break end
            local t=yy*map.W+xx;local id=s:tile_owner(t)
            if isWater(t) then protected+=1;clean=false;break end
            if not map:is_contestable(t) or s:has_fallout(t) or id>0 and not friendly(s,frame.me,id) then
                blocked+=1;clean=false;break
            end
        end
        if clean then open+=1 end
    end
    local opposed=0;for sector=0,3 do if sectors[sector] and sectors[sector+4] then opposed+=1 end end
    -- Backing onto a coast is useful only if there is still room to expand.
    score+=math.min(6,water*.7)+math.min(100,nearest)*.08
    if land>=15 then score+=math.min(3,protected)*4+math.min(4,open)*2
    else score-=35 end
    score-=opposed*18+math.max(0,blocked-3)*5
    return score,{nearby_players=players,water_sides=protected,open_directions=open,
        blocked_directions=blocked,opposing_player_sectors=opposed,local_land_samples=land}
end

function Policy:spawn(frame)
    if not self:ready("spawn", frame.now) then return nil, "Waiting for spawn confirmation" end
    local s, map, best, bestScore = frame.state, frame.map, nil, -math.huge
    for _ = 1, 160 do
        local tile = self:landSample(map, "land_list")
        if valid(map, tile) and map:is_contestable(tile) and s:tile_owner(tile) == 0 and not s:has_fallout(tile) then
            local score,detail = self:spawnScore(frame,tile)
            if score > bestScore then best, bestScore = tile, score;self.spawnPlan=detail end
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
                if not friendly(s, me, id) and map:is_contestable(t) and not s:has_fallout(t)
                    and not Weapons.hazard(s,t,0,3) then
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
    if Weapons.hazard(frame.state,tile,margin) then return false,margin end
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
            local accept=not hostile and (o.traitor_until or 0)<=s.tick and Weapons.allianceSafe(s,frame.me,id)
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
                and (o.troops or 0)>=a.home*.6
                and not s:has_request(frame.me,id) and (o.traitor_until or 0)<=s.tick
                and Weapons.allianceSafe(s,frame.me,id)
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
                if kind=="sam" then
                    local level,oldRadius=1,0
                    if place.upgrade then for _,b in pairs(frame.state.structures) do
                        if b.owner==frame.me and b.kind==4 and b.tile==place.tile then
                            level=(b.level or 1)+1
                            oldRadius=(150-480/((b.level or 1)+5))/(frame.map.k_lin or 1)
                        end
                    end end
                    local radius=(150-480/(level+5))/(frame.map.k_lin or 1)
                    local protected=0
                    for _,b in pairs(frame.state.structures) do
                        if b.owner==frame.me and b.kind~=4 and frame.map.dist2(place.tile,b.tile)<=radius^2
                            and (not place.upgrade or frame.map.dist2(place.tile,b.tile)>oldRadius^2)
                            and not Weapons.covered(frame.state,frame.me,b.tile,self.desiredSAMCoverage) then protected+=b.kind==5 and 8 or 3 end
                    end
                    if protected==0 then score=-math.huge else score+=protected*30 end
                end
            end
            if bestScore == nil or score > bestScore then best, bestScore = place, score end
        end
    end
    if best and bestScore>-math.huge then
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
    local exposed=false;local enemySilo=false
    local nuclearThreat=Weapons.threat(frame.state,frame.me)
    self.desiredSAMCoverage=nuclearThreat.ready_silos>=2 and 2 or 1
    for _,b in pairs(frame.state.structures) do
        if b.owner==frame.me and b.kind~=4 and not Weapons.covered(frame.state,frame.me,b.tile,self.desiredSAMCoverage) then exposed=true end
        if b.kind==5 and not friendly(frame.state,frame.me,b.owner) then enemySilo=true end
    end
    if exposed and (counts[4] or 0)<6 and (incomingNuke or enemySilo or city+factory>=3) then table.insert(wanted,"sam") end
    -- Protect the first city budget instead of spending every 50K on posts.
    if city==0 then table.insert(wanted,"city") end
    if armies.incoming > armies.home * (city==0 and .6 or .2) and (counts[3] or 0) < 3 then table.insert(wanted, "defense") end
    if city > 0 and factory == 0 then table.insert(wanted, "factory") end
    if city > 0 and port == 0 then table.insert(wanted, "port") end
    if armies.home >= (frame.info.max_troops or math.huge) * .75 and city < 6 then table.insert(wanted, "city") end
    if factory < math.max(1, math.ceil(city / 2)) then table.insert(wanted, "factory") end
    if city >= 1 and factory > 0 and (frame.info.gold or 0)>=1750000 then
        if (counts[5] or 0) == 0 then table.insert(wanted,"silo") end
    end
    if city < 6 and (frame.info.gold or 0) > frame.ctx.rules:cost("city") * 2 then table.insert(wanted, "city") end
    for _, kind in ipairs(wanted) do
        local action = self:build(frame, sites, kind, counts)
        if action then return action end
    end
    return nil
end

function Policy:blastSafe(frame,tile,kind)
    return Weapons.blastSafe(frame.state,frame.me,tile,kind or "atom")
end

function Policy:strike(frame)
    if not self:ready("nuke",frame.now) or not self:ready("weapon_scan",frame.now) then return nil end
    self.cooldowns.weapon_scan=frame.now+4
    local targets,best,bestScore={},nil,0
    for _, b in pairs(frame.state.structures) do
        if b.owner > 0 and not friendly(frame.state, frame.me, b.owner) then table.insert(targets, b) end
    end
    local weights={[0]=250000,[1]=250000,[2]=250000,[3]=150000,[4]=1500000,[5]=1000000}
    table.sort(targets,function(a,b) return (weights[a.kind] or 100000)*(a.level or 1)>(weights[b.kind] or 100000)*(b.level or 1) end)
    for _,kind in ipairs({"atom","hydrogen","mirv"}) do
        local rules=frame.ctx.rules;local cost=rules:cost(kind)
        if rules:availability(kind).ok and (frame.info.gold or 0)>=cost+math.max(250000,cost*.15) then
            for i=1,math.min(12,#targets) do
                local target=targets[i];local duplicate=false
                for _,n in pairs(frame.state.nukes) do
                    local existingKind=({[0]="atom",[1]="hydrogen",[2]="mirv",[3]="atom"})[n.kind] or "atom"
                    if n.owner==frame.me and (n.kind==2 and frame.state:tile_owner(n.to_tile)==target.owner
                        or frame.map.dist2(target.tile,n.to_tile)<math.max(Weapons.radius(frame.map,kind),Weapons.radius(frame.map,existingKind))^2) then duplicate=true;break end
                end
                local diplomatic=not self.strategy or self.strategy:nuclearTarget(frame,target.owner)
                if diplomatic and not duplicate and rules:placement(kind,target.tile).ok then
                    local radius=Weapons.radius(frame.map,kind);local value=0
                    for _,b in pairs(frame.state.structures) do
                        if b.owner>0 and not friendly(frame.state,frame.me,b.owner) and (kind~="mirv" or b.owner==target.owner)
                            and frame.map.dist2(b.tile,target.tile)<=radius^2 then
                            value+=(weights[b.kind] or 100000)*(b.level or 1)
                        end
                    end
                    if kind=="mirv" then
                        -- Warheads may be intercepted and land stochastically.
                        -- Discount broad-area damage rather than promise immunity.
                        value=value*.5
                    end
                    local score=value/cost
                    if score>math.max(.8,bestScore) and Weapons.canLaunch(frame.state,frame.me,target.tile,kind) then
                        bestScore=score
                        best={intent={type="nuke",kind=kind,tile=target.tile},channel="nuke",cooldown=3,
                            plan={weapon=kind,cost=cost,estimated_structure_value=value},
                            label="Launching "..kind.." at "..frame.state:owner_name(target.owner)}
                    end
                end
            end
        end
    end
    return best
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
    if self.strategy and (self.strategy.board.mode~="develop" or (armies.enemyActive or 0)>0) then return nil end
    if armies.incoming > 0 or not self:ready("boat", frame.now) or armies.available < armies.home * .12 then return nil end
    if frame.ctx.rules:transports() >= (frame.state.rules.MAX_BOATS_PLAYER or 3) then return nil end
    local chosen, score
    for _ = 1, 120 do
        local tile = self:landSample(frame.map, "coast_list")
        if valid(frame.map, tile) and frame.map:is_coastal(tile) and not frame.state:has_fallout(tile) then
            local target = frame.state:tile_owner(tile)
            local owner = frame.state.owners[target]
            local weak = target == 0 or (owner and owner.alive and (owner.troops or 0) < armies.available * .2)
            if target>0 and self.strategy and not self.strategy:canTarget(frame,target,armies) then weak=false end
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
    local board=self.strategy:updateBoard(frame,groups,a,self.frontsSeen,self.adjacentAllies)
    if self:ready("retreat",frame.now) then
        local reassess=self.strategy:review(frame,a)
        if reassess then return reassess end
    end
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
    local strike=self:strike(frame)
    if strike then return strike end
    local best, score,currentBest,currentScore
    if self:ready("attack", frame.now) and a.enemyActive < 2 then
        for id, g in pairs(groups) do
            local enemy = frame.state.owners[id]
            if id > 0 and enemy and enemy.alive then
                local pressure=self:opportunity(frame,id)
                local required=enemy.kind==2 and (pressure>.5 and 1.5 or 1.8) or enemy.kind==0 and 1.5 or (pressure>.3 and 1.1 or 1.35)
                local asset,tile,sid=self.strategy:assetOpportunity(frame,g)
                local proposal=table.clone(g);proposal.tile=tile
                if a.home > (enemy.troops or 0) * required then
                    local plan=self:enemyPlan(frame,proposal,a,groups)
                    if plan then
                    plan.objective_sid=sid;plan.asset_opportunity=asset
                    local value=self.strategy:utility(frame,proposal,plan,a)
                    table.insert(board.candidates,{nation=id,kind=enemy.kind,score=value,amount=plan.amount,asset_opportunity=asset})
                    if (enemy.traitor_until or 0)>frame.state.tick then value+=.5 end
                    if score == nil or value > score then
                        best, score = {intent = {type = "attack", tile = tile, ratio = plan.amount / a.home},
                            reserve = plan.reserve, plan=plan, channel = "attack", cooldown = 2.5,
                            label = "Attacking " .. enemy.name}, value
                    end
                    if a.targets[id] and (not currentScore or value>currentScore) then
                        currentBest,currentScore={intent={type="attack",tile=tile,ratio=plan.amount/a.home},
                            reserve=plan.reserve,plan=plan,channel="attack",cooldown=2.5,label="Reinforcing a profitable front against "..enemy.name},value
                    end
                    end
                end
            end
        end
    end
    if best and a.enemyActive>0 and not a.targets[frame.state:tile_owner(best.intent.tile)] then
        local recall
        for _,attack in ipairs(a.outgoing) do
            local campaign=self.strategy.campaigns[attack.target]
            if attack.target>0 and campaign and frame.now-campaign.started>8 and frame.now-campaign.lastProgress>6
                and score>(currentScore or 4)+4 and (not recall or attack.troops>recall.troops) then recall=attack end
        end
        if recall and self:ready("retreat",frame.now) then
            return {intent={type="retreat",attack_id=recall.aid},channel="retreat",cooldown=3,
                label="A better opportunity is available; ending the stalled front first"}
        end
        best,score=currentBest,currentScore
    end
    local neutral = groups[0]
    local neutralScore=neutral and 5+math.min(2,math.log(1+neutral.front)) or -math.huge
    if best and (not neutral or a.neutralActive>0 or score>neutralScore) then return best end
    if board.recover or a.incoming > a.home*.25 then return nil,"Defending - holding reserves and reassessing the whole board" end
    if neutral and self:ready("attack", frame.now) and a.available > 200 and a.enemyActive == 0 then
        local surplus=math.max(0,a.home-self:growthTarget(frame.info))
        if a.neutralActive == 0 or surplus>a.home*.08 and (a.targets[0] or 0)<surplus*.5 then
            local amount,reserve=self:attackAmount(frame,a,0,true)
            if amount then return {intent = {type = "attack", tile = neutral.tile, ratio = amount / a.home},
                reserve = reserve,plan={amount=amount,growth_target=self:growthTarget(frame.info)},
                channel = "attack", cooldown = 2.5, label = "Expanding with a recruitment-aware troop budget"} end
        end
    end
    if best then return best end
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
    return {version="1.5.0",scope="Since the current observer snapshot; intent estimates are heuristic",
        strategy=self.strategy and self.strategy.board or {},timeline=self.strategy and self.strategy.timeline or {},
        recruitment_target=info and self:growthTarget(info) or 0,spawn_plan=self.spawnPlan,
        tick=self.state and self.state.tick or 0,alive=info and info.alive or false,
        land=info and info.tiles or 0,troops=info and info.troops or 0,metrics=self.metrics,
        gold=info and info.gold or 0,allies=allies,traitors=traitors,navy=navy,recent_orders=self.history or {},
        nuclear_threat=self.state and Weapons.threat(self.state,self.me) or {},fallout_tiles=self.state and self.state.fallout_count or 0,
        last_action=self.lastAction,last_plan=self.lastPlan,recent_threats=threats}
end

return Policy
