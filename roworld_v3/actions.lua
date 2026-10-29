-- RoWorld candidate decoder: engine-feasible proposals plus explicit, separate risk filters.
local Actions={}
local Schema=require('./schema')
local Geography=require('./geography')
local Weapons=require('./shared/weapons')
local function clamp(v) return Schema.clamp(v,0,8) end
local function ratio(a,b) return clamp((a or 0)/math.max(1,b or 0)) end
local function recruit(p,seconds)
    local home,cap=math.max(0,p.troops or 0),math.max(1,p.max_troops or 1)
    return math.max(0,(home^.73/4+10)*(1-home/cap)*10*seconds)
end
local function protected(frame,agent,id)
    return id==frame.me or id>0 and (frame.state:are_allies(frame.me,id) or agent.cooperation:isFriend(id)
        or frame.state:has_request(frame.me,id))
end
function Actions.features(frame,o,a)
    local s,m=frame.state,frame.map;local intent=a.intent or {};local t=intent.tile
    local target=intent.target or (Geography.valid(m,t) and s:tile_owner(t) or 0)
    local p=s.owners[target] or {};local rel=o.diplomacy[target] or {}
    local f=table.create(#Schema.types,0);f[assert(Schema.ids[a.kind])]=1
    local args={intent.ratio or ratio(intent.troops,o.home),ratio(a.cost,frame.info.gold),ratio(p.troops,o.home),
        ratio(p.tiles,frame.info.tiles),Schema.log(p.gold),p.kind==2 and 1 or 0,p.kind==0 and 1 or 0,p.kind==1 and 1 or 0,
        rel.allied and 1 or 0,rel.friend and 1 or 0,ratio(o.incomingBy[target],o.home),ratio(o.pressure[target],p.troops),
        ratio(o.outgoingTo[target],p.troops),(o.assets[target] or 0)/32,ratio(o.allyPower[target],o.home),
        Geography.valid(m,t) and math.sqrt(m.dist2(t,o.anchor))*(m.k_lin or 1)/1000 or 0,
        Geography.valid(m,t) and 1-Geography.magnitude(m,t)/31 or 0,
        Geography.valid(m,t) and m:is_coastal(t) and 1 or 0,
        Geography.valid(m,t) and s:has_fallout(t) and 1 or 0,a.upgrade and 1 or 0,(a.level or 0)/16,
        ratio(a.need,o.home),ratio(o.incoming+o.threat*.15,o.home),a.payback or 0,(a.bias or 0)/16}
    for _,v in ipairs(args) do table.insert(f,Schema.clamp(v)) end
    assert(#f==Schema.action,'Action schema size changed');return f
end
local function acceptScore(frame,agent,o,id)
    local s=frame.state;local p=s.owners[id]
    if not p or not p.alive or (p.traitor_until or 0)>s.tick or (agent.distrust[id] or 0)>frame.now
        or (o.outgoingTo[id] or 0)>0 or not Weapons.allianceSafe(s,frame.me,id) then return -20 end
    local memory=agent.profiles:assessment(frame,id)
    local score=(p.kind==2 and 3 or p.kind==0 and 0 or -4)-(memory.betrayal_penalty or 0)
    if agent.cooperation:isFriend(id) then score+=10 end
    if o.near[id] then score+=2 end
    local strength=(p.troops or 0)/math.max(1,o.home)
    score+=math.min(2,strength)
    if p.kind==0 and o.near[id] and strength<.65 then score-=5 end
    if p.kind==0 and strength>3 and o.incoming<o.home*.8 then score-=8 end
    if (o.incomingBy[id] or 0)>o.home*.7 then score+=6 end
    for _,a in pairs(s.attacks) do
        if a.attacker==id and (o.incomingBy[a.target] or 0)>0 and not a.retreating then score+=3;break end
    end
    return score
end
function Actions.generate(frame,o,agent)
    local s,m,me=frame.state,frame.map,frame.me
    local rows={};local filtered={};local now=frame.now
    local function add(a)
        if now<(agent.cooldowns[a.channel or a.kind] or -math.huge) then return end
        a.channel=a.channel or a.kind;a.cooldown=a.cooldown or 2
        a.label=a.label or a.kind;a.features=Actions.features(frame,o,a)
        table.insert(rows,a)
    end
    add({kind='wait',bias=0,label='Holding reserves and watching public state',cooldown=0})
    if s.phase==2 or not frame.info.alive then return rows,filtered end
    if s.phase==0 then
        if now<(agent.cooldowns.spawn or -math.huge) then return rows,filtered end
        local options={};local spawn=frame.info.spawn_tile
        local old=Geography.valid(m,spawn) and Geography.spawnScore(frame,spawn) or nil
        for i=1,192 do
            local t=Geography.sample(m,'land_list',agent:random(10000000))
            if t then
                local score,notes=Geography.spawnScore(frame,t)
                if score and (not frame.info.spawned or not old or score>old+4) then table.insert(options,{tile=t,score=score,notes=notes}) end
            end
        end
        table.sort(options,function(a,b) return a.score==b.score and a.tile<b.tile or a.score>b.score end)
        for i=1,math.min(8,#options) do local p=options[i]
            add({kind='spawn',intent={type='spawn',tile=p.tile},bias=2+p.score*.1,channel='spawn',cooldown=2,
                label='Choosing open, flat territory with coast access',spawn=p.notes})
        end
        return rows,filtered
    end
    if not frame.info.spawned then return rows,filtered end
    local ids={};for id in pairs(o.groups) do table.insert(ids,id) end;table.sort(ids)
    local minimum=math.max(100,math.ceil(o.home*.01))
    -- Recalls are candidates with emergency priority, not an unconditional first rule.
    for aid,a in pairs(s.attacks) do
        if a.attacker==me and not a.retreating then
            local campaign=agent.campaigns[a.target]
            local bad=protected(frame,agent,a.target) or o.incoming>o.home*.65
                or campaign and (now>=campaign.deadline or now-campaign.progress_at>20)
            if bad then add({kind='retreat',intent={type='retreat',attack_id=aid},bias=15+ratio(o.incoming,o.home),
                channel='retreat:'..aid,cooldown=3,label='Recalling an unsafe or stalled campaign'}) end
        end
    end
    for _,id in ipairs(ids) do
        local g=o.groups[id];local p=s.owners[id]
        if protected(frame,agent,id) then filtered.friendly=(filtered.friendly or 0)+1;continue end
        if id>0 and (not p or not p.alive or (agent.distrust[id] or 0)>now and o.incomingBy[id]==nil) then continue end
        local active=o.outgoingTo[id] or 0;local ceiling=o.available
        local counter=id>0 and (o.incomingBy[id] or 0)>1.5*math.max(1,p.troops or 0)
        local reserve=o.reserve
        if counter then reserve=math.max(reserve,math.ceil(o.capacity*.42));ceiling=math.max(0,o.home-reserve) end
        local campaign=agent.campaigns[id]
        if campaign then
            if now<campaign.pause_until or now>=campaign.deadline then continue end
            ceiling=math.min(ceiling,math.max(0,campaign.budget-campaign.spent))
        end
        local need,bias
        if id==0 then
            need=math.max(o.home-o.capacity*.42,math.min(o.home*.12,recruit(frame.info,5)*.7))-active
            bias=3.5+math.min(1,g.front/100)
        else
            local home=p.troops or 0
            need=math.ceil(math.max(0,home*1.5+recruit(p,3)-active))
            bias=2+math.min(2,(o.assets[id] or 0)/10)+math.min(2,Schema.log(p.gold)*2)
            if p.kind==1 then bias+=1 elseif p.kind==2 then bias-=2 end
            bias+=math.min(3,(o.pressure[id] or 0)/math.max(1,home))-math.min(4,(o.allyPower[id] or 0)/math.max(1,o.home))
            if counter then bias+=6 end
            -- A pressure estimate is not a promise that a human will defend this way.
            local otherThreat=math.max(0,o.threat-home)
            if not counter and (home>o.home*.55 or o.incoming>o.home*.15 or otherThreat>o.home*2) then
                -- A learner may test a small raid on an already pressured peer. This is
                -- a separate low-prior candidate, not a claim to afford full elimination.
                local raid=math.floor(math.min(o.home*.1,ceiling))
                if p.kind==2 and home<=o.home*1.1 and o.incoming==0 and (o.pressure[id] or 0)>home*.5
                    and raid>=minimum and not Weapons.hazard(s,g.tile,0,3) then
                    add({kind='attack',intent={type='attack',tile=g.tile,ratio=raid/math.max(1,o.home)},reserve=reserve,
                        bias=-2,channel='attack:'..id,cooldown=5,need=raid,plan={amount=raid},
                        label='Limited raid against a visibly distracted peer'})
                end
                filtered.risk=(filtered.risk or 0)+1;continue
            end
            if active>=home*1.5+recruit(p,3) then continue end
        end
        if need<minimum then continue end
        if id>0 and need>ceiling then filtered.budget=(filtered.budget or 0)+1;continue end
        local amounts={math.min(need,ceiling)}
        if id==0 then amounts={math.min(need,ceiling),math.min(need*.6,ceiling)} end
        for j,n in ipairs(amounts) do
            n=math.floor(n)
            if n>=minimum and not Weapons.hazard(s,g.tile,0,3) then
                local amountBias=bias-(j-1)*.2
                add({kind=id==0 and 'expand' or 'attack',intent={type='attack',tile=g.tile,ratio=n/math.max(1,o.home)},
                    reserve=reserve,bias=amountBias,channel=counter and 'counterattack' or ('attack:'..id),cooldown=counter and 1 or 3,
                    label=counter and 'Proportional counterattack; retain at least 42% capacity' or id==0 and 'Expanding into neutral land' or 'Taking a viable frontier and valuable assets',
                    need=need,plan={amount=n,defensive_counter=counter,capacity_floor=counter and .42 or nil}})
            end
        end
    end
    -- Formal relationships and own pending proposals remain exact facts.
    local playerIds={};for id in pairs(o.diplomacy) do if id~=me then table.insert(playerIds,id) end end;table.sort(playerIds)
    for _,id in ipairs(playerIds) do
        local rel=o.diplomacy[id];local p=s.owners[id];local score=acceptScore(frame,agent,o,id)
        if rel.incoming_request then
            local yes=score>=4
            add({kind=yes and 'ally_accept' or 'ally_reject',intent={type='ally_reply',target=id,accept=yes},bias=yes and 7 or 1,
                channel='reply:'..id,cooldown=5,label=yes and 'Accepting a useful alliance' or 'Declining a risky alliance'})
        elseif rel.allied and rel.expiry and rel.expiry.can_extend and score>=3 then
            add({kind='ally_extend',intent={type='ally_extend',target=id},bias=6,channel='renew:'..id,cooldown=30,label='Renewing a useful alliance'})
        elseif not rel.allied and not rel.outgoing_request and score>=6 and (o.near[id] or rel.friend) then
            add({kind='ally_request',intent={type='ally_request',target=id},bias=4+math.min(3,score/5),
                channel='peace:'..id,cooldown=120,label='Offering a useful partnership'})
        end
        if rel.allied and not rel.same_team and not rel.friend and (p.traitor_until or 0)>s.tick and o.incoming==0 and o.outgoing==0 then
            local exposure=0
            for other,q in pairs(s.owners) do if other~=me and q.alive and (other==id or not s:are_allies(me,other)) then exposure+=q.troops or 0 end end
            if o.home>math.max(50000,exposure*4) then
                add({kind='ally_break',intent={type='ally_break',target=id},bias=2,channel='break:'..id,cooldown=120,
                    label='Ending a marked traitor partnership with a large defensive margin'})
            end
        end
    end
    local aid=agent.cooperation:aid(frame,{home=o.home,incoming=o.incoming,available=o.available,reserve=o.reserve},true)
    if aid then aid.kind='donate';aid.bias=5;add(aid) end
    local sites=Geography.sites(frame,o.anchor,o.frontSites)
    local rules=frame.ctx.rules
    local kinds={'city','factory','port','defense','sam','silo'}
    local hasHostileSilo=false
    for _,b in pairs(s.structures) do
        if b.kind==5 and b.owner~=me and not s:are_allies(me,b.owner) then hasHostileSilo=true;break end
    end
    local posts=(o.counts[3] or 0);local recent=0
    for _,stamp in ipairs(agent.postPurchases) do if now-stamp<60 then recent+=1 end end
    local safeCache={}
    for _,kind in ipairs(kinds) do
        local available=rules:availability(kind)
        if not available.ok then continue end
        local bias
        if kind=='city' then bias=4.5+(o.home/o.capacity)*2-(o.levels[0] or 0)*.35
        elseif kind=='factory' then bias=(o.levels[0] or 0)>0 and 5.2-(o.levels[2] or 0)*.7 or -3
        elseif kind=='port' then bias=4.3-(o.levels[1] or 0)*.7
        elseif kind=='defense' then
            if posts>=3 or recent>=3 or o.incoming==0 then continue end
            bias=4+math.min(4,o.incoming/math.max(1,o.home)*5)
        elseif kind=='sam' then
            if not hasHostileSilo and #o.alerts==0 then continue end
            bias=6+math.min(2,#o.alerts)-(o.levels[4] or 0)
        else
            if o.home<o.incoming*2 or (o.levels[0] or 0)<2 or (frame.info.gold or 0)<available.cost+750000 then continue end
            bias=3-(o.levels[5] or 0)
        end
        local proposals={};local used={}
        for _,t in ipairs(sites) do
            local placement=rules:placement(kind,t)
            if placement.ok and not used[placement.tile] then
                used[placement.tile]=true
                local margin=(kind=='defense' or kind=='sam') and 8 or 18
                local key=tostring(placement.tile)..':'..margin..':'..tostring(kind=='port')
                local safe=safeCache[key]
                if safe==nil then safe=Geography.safe(frame,placement.tile,kind);safeCache[key]=safe end
                if safe then
                    local level=0
                    for _,b in pairs(s.structures) do if b.tile==placement.tile then level=b.level or 1 end end
                    local concentration=0
                    for _,b in pairs(s.structures) do
                        if b.owner==me and m.dist2(b.tile,placement.tile)*(m.k_lin or 1)^2<80^2 then concentration+=b.level or 1 end
                    end
                    local payback=kind=='city' and recruit({troops=o.home,max_troops=o.capacity+250000},30)-recruit(frame.info,30) or 0
                    table.insert(proposals,{kind=kind,intent={type='build',kind=kind,tile=placement.tile},cost=available.cost,
                        bias=bias-(placement.upgrade and .15+level*.12 or 0)-concentration*.015,
                        upgrade=placement.upgrade,level=level,payback=payback/100000,channel='construction',cooldown=3,
                        safety={margin=margin,coastal=kind=='port'},label=(placement.upgrade and 'Upgrading ' or 'Building ')..kind..' at a protected site'})
                end
            end
        end
        table.sort(proposals,function(a,b) return a.bias==b.bias and a.intent.tile<b.intent.tile or a.bias>b.bias end)
        for i=1,math.min(2,#proposals) do add(proposals[i]) end
    end
    -- Naval routes, missile availability and blast protection use RoWorld's actual checks.
    local coasts={};local seenCoasts={}
    for i=1,64 do
        local t=Geography.sample(m,'coast_list',agent:random(10000000))
        if t and not seenCoasts[t] and m:is_contestable(t) and not s:has_fallout(t)
            and not protected(frame,agent,s:tile_owner(t)) and frame.ctx.borders:can_reach_by_sea(t) then
            seenCoasts[t]=true;table.insert(coasts,t)
        end
    end
    table.sort(coasts)
    if o.boats==0 then
        local naval={}
        for _,t in ipairs(coasts) do
            local id=s:tile_owner(t);local p=s.owners[id]
            local neutral=id==0
            local escape=neutral and o.incoming>o.home*1.25 and rules:transports()==0
            local amount=math.floor(escape and o.home*.1 or math.min(o.home*.1,o.available))
            local safeHuman=p and p.kind==2 and (o.assets[id] or 0)>0 and (o.pressure[id] or 0)>(p.troops or 0)
            local landing=Geography.landing(frame,t,o.anchor,escape)
            if landing and amount>=minimum and (neutral or p and (p.troops or 0)*1.8<amount and (p.kind~=2 or safeHuman)) then
                local bias=escape and 13 or 4.4+landing+(neutral and 0 or 1)
                table.insert(naval,{kind='boat',intent={type='boat',tile=t,ratio=amount/math.max(1,o.home)},bias=bias,
                    reserve=escape and o.home*.9 or o.reserve,survival=escape,channel='boat',cooldown=20,plan={amount=amount},
                    label=escape and 'Sending a 10% neutral survival expedition; retain 90% home bank' or 'Opening a limited, reachable sea frontier'})
            end
        end
        table.sort(naval,function(a,b) return a.bias==b.bias and a.intent.tile<b.intent.tile or a.bias>b.bias end)
        for i=1,math.min(4,#naval) do add(naval[i]) end
    end
    local waterTargets={}
    for _,b in pairs(s.structures) do if b.owner==me and b.kind==1 and b.active_tick<=s.tick then
        Geography.neighbors(m,b.tile,function(t) if type(m.is_water)=='function' and m:is_water(t) then table.insert(waterTargets,t) end end)
    end end
    local threats={}
    for _,u in pairs(s.units or {}) do
        local path=u.path or {};local index=math.clamp(math.floor(math.max(0,s.tick-(u.start_tick or s.tick))*100/math.max(1,u.ticks_per_tile_x100 or 100))+1,1,math.max(1,#path))
        local t=path[index] or u.patrol_tile
        if u.owner~=me and not s:are_allies(me,u.owner) and (u.kind==0 or u.kind==2)
            and Geography.valid(m,t) and type(m.is_water)=='function' and m:is_water(t)
            and m.dist2(o.anchor,t)*(m.k_lin or 1)^2<200^2 then table.insert(threats,t) end
    end
    table.sort(waterTargets);table.sort(threats)
    local patrol=threats[1] or waterTargets[1]
    if patrol and #waterTargets>0 then
        if o.ships<(#threats>0 and 3 or 1) and rules:availability('warship').ok then
            local t=waterTargets[1]
            if rules:placement('warship',t).ok then add({kind='warship',intent={type='build',kind='warship',tile=t},
                cost=rules:cost('warship'),bias=#threats>0 and 7 or 3.5,channel='fleet',cooldown=10,label='Building a coastal warship'}) end
        end
        for uid,u in pairs(s.units or {}) do
            if #threats>0 and u.owner==me and u.kind==2 and u.state==0 and (u.max_hp or 0)>0 and u.hp>=u.max_hp*.8 then
                local path=u.path or {};local pos=path[1] or u.patrol_tile;local body=m.water_body_of or m.body_of
                if Geography.valid(m,pos) and body and body(m,pos)==body(m,patrol)
                    and (not Geography.valid(m,u.patrol_tile) or m.dist2(u.patrol_tile,patrol)>25) then
                    add({kind='move_warship',intent={type='move_warship',uid=uid,tile=patrol},bias=8,
                        channel='ship:'..uid,cooldown=6,label='Intercepting a visible coastal threat'})
                end
            end
        end
    end
    local strikeTargets={}
    for _,b in pairs(s.structures) do
        if b.owner>0 and not protected(frame,agent,b.owner) then table.insert(strikeTargets,{tile=b.tile,value=(b.level or 1)*(b.kind==3 and 1 or 4),owner=b.owner}) end
    end
    table.sort(strikeTargets,function(a,b) return a.value==b.value and a.tile<b.tile or a.value>b.value end)
    -- Keep a bounded strategic shortlist, then favor real clusters rather than the
    -- first arbitrary building in a large empire (large blasts need real value).
    while #strikeTargets>128 do table.remove(strikeTargets) end
    local clusterRadius=Weapons.radius(m,'hydrogen')^2
    for _,target in ipairs(strikeTargets) do
        target.cluster=0
        for _,other in ipairs(strikeTargets) do
            if m.dist2(target.tile,other.tile)<=clusterRadius then target.cluster+=other.value end
        end
    end
    table.sort(strikeTargets,function(a,b)
        if a.cluster~=b.cluster then return a.cluster>b.cluster end
        return a.value==b.value and a.tile<b.tile or a.value>b.value
    end)
    for _,kind in ipairs({'atom','hydrogen','mirv'}) do
        if not rules:availability(kind).ok then continue end
        for i=1,math.min(4,#strikeTargets) do
            local target=strikeTargets[i]
            local duplicate=false
            for _,n in pairs(s.nukes) do
                if n.owner==me and Geography.valid(m,n.to_tile) and m.dist2(n.to_tile,target.tile)<(Weapons.radius(m,kind)*.8)^2 then duplicate=true;break end
            end
            local value=0;local radius=Weapons.radius(m,kind)
            for _,b in pairs(s.structures) do
                if b.owner>0 and not protected(frame,agent,b.owner) and m.dist2(b.tile,target.tile)<=radius^2 then
                    value+=(({[0]=125000,[1]=125000,[2]=125000,[3]=50000,[4]=1500000,[5]=1000000})[b.kind] or 0)*(b.level or 1)
                end
            end
            local cost=rules:cost(kind)
            if not duplicate and value>=cost*.9 and rules:placement(kind,target.tile).ok
                and Weapons.canLaunch(s,me,target.tile,kind) then
                add({kind=kind,intent={type='nuke',kind=kind,tile=target.tile},cost=rules:cost(kind),
                    bias=3+math.min(5,value/math.max(1,cost))+(o.incomingBy[target.owner] and 4 or 0),channel='missile',cooldown=10,
                    label='Launching '..kind..' at a valuable exposed target'})
                break
            end
        end
    end
    -- Fair family budget: a large diplomacy roster cannot evict every combat/build proposal.
    table.sort(rows,function(a,b)
        if a.bias~=b.bias then return a.bias>b.bias end
        if a.kind~=b.kind then return a.kind<b.kind end
        local x,y=a.intent or {},b.intent or {}
        if (x.target or -1)~=(y.target or -1) then return (x.target or -1)<(y.target or -1) end
        return (x.tile or x.attack_id or x.uid or -1)<(y.tile or y.attack_id or y.uid or -1)
    end)
    local selected={};local counts={}
    for _,a in ipairs(rows) do
        local n=counts[a.kind] or 0
        if n<8 and #selected<Schema.max_candidates then table.insert(selected,a);counts[a.kind]=n+1 end
    end
    local hasWait=false;for _,a in ipairs(selected) do if a.kind=='wait' then hasWait=true end end
    if not hasWait then if #selected==Schema.max_candidates then table.remove(selected) end
        local a={kind='wait',bias=0,cooldown=0,label='Holding reserves and watching public state'};a.features=Actions.features(frame,o,a);table.insert(selected,a)
    end
    return selected,filtered
end
return Actions
