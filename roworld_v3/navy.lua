-- Connected-water coastal defense; healthy ships spread out rather than pile up.
local Navy={}
local Geography=require('./geography')
function Navy.position(s,u)
    local path=u.path or {};local i=math.clamp(math.floor(math.max(0,s.tick-(u.start_tick or s.tick))*100/math.max(1,u.ticks_per_tile_x100 or 100))+1,1,math.max(1,#path))
    return path[i] or u.patrol_tile
end
local function body(m,t)
    if not Geography.valid(m,t) then return 0 end
    local fn=m.water_body_of or m.body_of
    return fn and fn(m,t) or 0
end
function Navy.generate(frame,o,agent)
    local s,m,me=frame.state,frame.map,frame.me;local k=m.k_lin or 1;local rules=frame.ctx.rules
    local zones,seen={},{};local ships={};local readyPorts=0
    local function add(t,weight,source)
        if not Geography.valid(m,t) or type(m.is_water)~='function' or not m:is_water(t) then return end
        if not seen[t] then seen[t]={tile=t,weight=weight,source=source,body=body(m,t)};table.insert(zones,seen[t])
        else seen[t].weight=math.max(seen[t].weight,weight) end
    end
    for _,b in pairs(s.structures) do if b.owner==me and b.kind==1 and (b.active_tick or 0)<=s.tick then
        readyPorts+=1;Geography.neighbors(m,b.tile,function(t) add(t,2+(b.level or 1)*.2,'port') end)
    end end
    -- Border probes are spread over the entire frontier, not only the home port.
    local coast={};for t in pairs(frame.ctx.borders.border) do if s:tile_owner(t)==me and m:is_coastal(t) then table.insert(coast,t) end end
    table.sort(coast)
    local stride=math.max(1,math.ceil(#coast/48))
    for i=1,#coast,stride do local t=coast[i]
        local weight=1+math.max(0,1-math.sqrt(m.dist2(t,o.anchor))*k/220)*2
        Geography.neighbors(m,t,function(n) add(n,weight,'coast') end)
    end
    local threats={}
    for uid,u in pairs(s.units or {}) do
        if u.owner==me and u.kind==2 then table.insert(ships,{uid=uid,u=u,tile=Navy.position(s,u)})
        elseif u.owner~=me and not s:are_allies(me,u.owner) and not (s.bot_friend_guard or {})[u.owner]
            and (u.kind==0 or u.kind==2) then
            local t=Navy.position(s,u)
            if Geography.valid(m,t) then
                local near=m.dist2(t,o.anchor)*k*k<240^2
                if not near then for _,z in ipairs(zones) do if m.dist2(t,z.tile)*k*k<180^2 then near=true;break end end end
                if near then table.insert(threats,{tile=t,kind=u.kind,owner=u.owner,weight=u.kind==0 and 5 or 6}) end
            end
        end
    end
    table.sort(ships,function(a,b) return a.uid<b.uid end)
    for _,t in ipairs(threats) do add(t.tile,t.weight,'threat') end
    local eligible={}
    for _,z in ipairs(zones) do
        if not rules:placement('warship',z.tile).ok then
            -- Placement includes gold; movement must remain possible when broke.
            local connected=false
            for _,b in pairs(s.structures) do if b.owner==me and b.kind==1 and (b.active_tick or 0)<=s.tick then
                Geography.neighbors(m,b.tile,function(t) if body(m,t)>0 and body(m,t)==z.body then connected=true end end)
            end end
            if not connected then continue end
        end
        local cover=0
        for _,ship in ipairs(ships) do
            local t=Geography.valid(m,ship.u.patrol_tile) and ship.u.patrol_tile or ship.tile
            if Geography.valid(m,t) and body(m,t)==z.body and m.dist2(t,z.tile)*k*k<100^2 then
                local ready=ship.u.state==0 and (ship.u.hp or 0)>=math.max(1,ship.u.max_hp or 0)*.8
                cover+=ready and 1 or .25
            end
        end
        z.cover=cover;z.score=z.weight-cover*2.7
        table.insert(eligible,z)
    end
    table.sort(eligible,function(a,b) return a.score==b.score and a.tile<b.tile or a.score>b.score end)
    local rows={};local best=eligible[1]
    -- Dynamic force size grows with protected coastline, ports and hostile fleets.
    local desired=math.min(32,math.max(2,readyPorts*2,math.ceil(#coast*k/120),#threats*2+1))
    local gold=frame.info.gold or 0;local reserve=(agent.economyPlan or {}).gold_reserve or 0
    if best and readyPorts>0 and #ships<desired and rules:availability('warship').ok
        and gold-rules:cost('warship')>=reserve and (best.cover<2 or #threats>0) then
        table.insert(rows,{kind='warship',intent={type='build',kind='warship',tile=best.tile},cost=rules:cost('warship'),
            bias=(#threats>0 and 10 or 7.6)-best.cover*.6,channel='fleet',cooldown=1,gold_reserve=reserve,
            label='Expanding the connected coastal defense fleet',plan={desired_fleet=desired,zone=best.source}})
    end
    local assigned={}
    for _,ship in ipairs(ships) do
        local u=ship.u
        if u.state~=0 or (u.max_hp or 0)<=0 or u.hp<u.max_hp*.8 then continue end
        for _,z in ipairs(eligible) do
            if assigned[z.tile] or body(m,ship.tile)~=z.body then continue end
            if z.source~='threat' and (z.cover>0 or #ships<2) then continue end
            if Geography.valid(m,u.patrol_tile) and m.dist2(u.patrol_tile,z.tile)*k*k<(z.source=='threat' and 10 or 40)^2 then continue end
            local currentCovered=0
            for _,other in ipairs(ships) do if other.uid~=ship.uid and Geography.valid(m,other.tile)
                and m.dist2(other.tile,ship.tile)*k*k<80^2 then currentCovered+=1 end end
            if z.source~='threat' and currentCovered==0 then continue end
            assigned[z.tile]=true
            table.insert(rows,{kind='move_warship',intent={type='move_warship',uid=ship.uid,tile=z.tile},
                bias=z.source=='threat' and 11 or 8.2,channel='ship:'..ship.uid,cooldown=8,
                label=z.source=='threat' and 'Intercepting a visible coastal threat' or 'Spreading healthy warships around the economic coast'})
            break
        end
    end
    agent.navalPlan={desired_fleet=desired,own_ships=#ships,ready_ports=readyPorts,coastal_probes=#coast,
        defensive_zones=#eligible,hostile_coastal_units=#threats,best_zone=best}
    return rows
end
return Navy
