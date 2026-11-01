-- Continuous investment, with a defended economic core and marginal coverage.
local Infrastructure={}
local Geography=require('./geography')
local Weapons=require('./shared/weapons')
local ids={city=0,port=1,factory=2,defense=3,sam=4,silo=5}
local weights={[0]=2,[1]=3,[2]=2,[3]=.2,[4]=1,[5]=4}
local function coverage(frame,t)
    local s,m=frame.state,frame.map;local n=0
    for _,b in pairs(s.structures) do
        if b.kind==4 and (b.owner==frame.me or s:are_allies(frame.me,b.owner)) then
            local r=(150-480/(math.max(1,b.level or 1)+5))/(m.k_lin or 1)
            if m.dist2(t,b.tile)<=r*r then n+=b.level or 1 end
        end
    end
    return n
end
function Infrastructure.reserve(frame,o,agent)
    local gold=math.max(0,frame.info.gold or 0)
    local reserve=math.min(gold*.15,math.max(125000,(frame.info.income or 0)*3))
    if agent.salvoPlan then reserve=math.max(reserve,agent.salvoPlan.remaining*frame.ctx.rules:cost('scatter')) end
    return reserve
end
function Infrastructure.generate(frame,o,agent,sites)
    local s,m,me=frame.state,frame.map,frame.me;local rules=frame.ctx.rules
    local rows,diagnostics={},{};local gold=frame.info.gold or 0
    local reserve=Infrastructure.reserve(frame,o,agent)
    local city,port,factory=o.levels[0] or 0,o.levels[1] or 0,o.levels[2] or 0
    local coast=port>0
    for _,t in ipairs(sites) do if m:is_coastal(t) then coast=true;break end end
    if not coast then for t in pairs(frame.ctx.borders.border) do if m:is_coastal(t) then coast=true;break end end end
    local early=s.tick-math.max(0,s.playing_since or 0)<1200
    local threat=(o.nuclearThreat.hostile_silos or 0)>0 or #o.alerts>0
    local desiredDefense=threat and 7 or 2 -- extra slots help withstand Scattershot.
    local recent=0;for _,at in ipairs(agent.postPurchases) do if frame.now-at<60 then recent+=1 end end
    local missileCost=rules:cost('scatter')
    if missileCost==math.huge then missileCost=3750000 end
    local siloGoal=math.clamp(math.floor(math.max(0,gold-reserve)/math.max(750000,missileCost)),1,6)
    agent.economyPlan={coast_access=coast,early_factory_window=early,gold_reserve=reserve,
        sam_slots_per_asset=desiredDefense,desired_silo_levels=siloGoal,
        scope='Continuous marginal investment; safety, available sites and current prices bound purchases'}
    local own={};for _,b in pairs(s.structures) do if b.owner==me then table.insert(own,b) end end
    local covered={};for _,b in ipairs(own) do covered[b.tile]=coverage(frame,b.tile) end
    for _,kind in ipairs({'city','port','factory','sam','silo','defense'}) do
        local available=rules:availability(kind);local cost=available.cost or rules:cost(kind)
        local d={kind=kind,available=available.ok==true,cost=cost,checked_sites=#sites,legal_sites=0,safe_sites=0,gold_reserve=reserve}
        table.insert(diagnostics,d)
        if not available.ok then d.reason=tostring(available.reason or 'current game availability');continue end
        if gold-cost<reserve and not (kind=='sam' and #o.alerts>0 and not agent.salvoPlan) then
            d.reason='preserving economic or committed salvo funding';continue
        end
        if kind=='factory' and coast and (not early or factory>=2 or factory>=math.max(1,city)) then
            d.reason='coastal economy uses ports after a small early factory investment';continue
        end
        if kind=='factory' and city==0 then d.reason='establish the first city before factory support';continue end
        if kind=='defense' and ((o.counts[3] or 0)>=3 or recent>=3 or o.incoming==0) then
            d.reason='post cap, rolling purchase cap or no land invasion';continue
        end
        if kind=='silo' and ((o.levels[5] or 0)>=siloGoal or city<2 or gold-cost-reserve<750000 or o.incoming>o.home*.8) then
            d.reason='launcher capacity, economy or invasion funding target already met';continue
        end
        local base
        if kind=='city' then base=6.2+math.clamp(o.home/o.capacity,0,1.2)*1.8+math.clamp(port/2-city,-2,4)*.45
        elseif kind=='port' then base=6.8+math.clamp(city*1.5-port,-2,4)*.4
        elseif kind=='factory' then base=coast and 7.2-factory*1.2 or 6.7+math.clamp(city-factory,-2,4)*.35
        elseif kind=='sam' then base=4.4+(threat and 2 or 0)+math.min(3,#o.alerts)
        elseif kind=='silo' then base=5.5+(siloGoal-(o.levels[5] or 0))*.45
        else base=4+math.min(4,o.incoming/math.max(1,o.home)*5) end
        local proposals,used={},{}
        for _,requested in ipairs(sites) do
            local p=rules:placement(kind,requested)
            if p.ok and Geography.valid(m,p.tile) and not used[p.tile] then
                used[p.tile]=true;d.legal_sites+=1
                local safe,margin=Geography.safe(frame,p.tile,kind)
                if not safe then continue end
                d.safe_sites+=1
                local previous,concentration=nil,0
                for _,b in ipairs(own) do
                    if b.tile==p.tile and b.kind==ids[kind] then previous=b end
                    if m.dist2(b.tile,p.tile)*(m.k_lin or 1)^2<60^2 then concentration+=b.level or 1 end
                end
                -- Native UIRules returns upgrade_sid, the observer returns upgrade.
                local upgrade=p.upgrade==true or (p.upgrade_sid or 0)>0
                local level=previous and previous.level or 0
                local bias=base-concentration*.025-(upgrade and level*.04 or 0)
                local gain=0
                if kind=='sam' then
                    local radius=(150-480/(math.max(1,level+1)+5))/(m.k_lin or 1)
                    for _,b in ipairs(own) do
                        local count=covered[b.tile] or 0
                        if count<desiredDefense and m.dist2(p.tile,b.tile)<=radius^2 then
                            local extra=upgrade and 1 or math.min(desiredDefense-count,1)
                            gain+=(weights[b.kind] or 0)*extra/desiredDefense
                        end
                    end
                    if gain==0 then continue end
                    bias+=math.min(7,gain*1.4)
                elseif kind~='defense' then
                    local slots=coverage(frame,p.tile)
                    bias+=math.min(.5,slots*.1)
                    if kind=='silo' and slots==0 and threat then bias-=2 end
                end
                -- Keep the economic core useful without stacking everything in a
                -- single blast circle. Upgrade protected existing sites as well.
                local distance=math.sqrt(m.dist2(o.anchor,p.tile))*(m.k_lin or 1)
                bias-=math.min(.5,distance/1500)
                table.insert(proposals,{kind=kind,intent={type='build',kind=kind,tile=p.tile},cost=cost,
                    bias=bias,upgrade=upgrade,level=level,payback=gain,channel='construction',cooldown=1,
                    gold_reserve=reserve,safety={margin=margin,coastal=kind=='port'},
                    label=(upgrade and 'Upgrading ' or 'Building ')..kind..(kind=='sam' and ' for overlapping core protection' or ' at a protected site')})
            end
        end
        table.sort(proposals,function(a,b) return a.bias==b.bias and a.intent.tile<b.intent.tile or a.bias>b.bias end)
        d.candidates=math.min(3,#proposals);d.best_score=proposals[1] and proposals[1].bias
        d.reason=#proposals==0 and 'no legal safe site adds the required coverage or investment' or 'continuous investment candidate'
        for i=1,math.min(3,#proposals) do table.insert(rows,proposals[i]) end
    end
    return rows,diagnostics
end
return Infrastructure
