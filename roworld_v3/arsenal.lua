-- Value-ranked strikes and finite, fully funded Scattershot suppression salvos.
local Arsenal={}
local Geography=require('./geography')
local Weapons=require('./shared/weapons')
local function hostile(frame,id)
    return id>0 and id~=frame.me and not frame.state:are_allies(frame.me,id)
        and not (frame.state.bot_friend_guard or {})[id] and not frame.state:has_request(frame.me,id)
end
local function duplicate(frame,t,kind)
    for _,n in pairs(frame.state.nukes) do
        if n.owner==frame.me and Geography.valid(frame.map,n.to_tile)
            and frame.map.dist2(n.to_tile,t)<(Weapons.radius(frame.map,kind)*.8)^2 then return true end
    end
    return false
end
local values={[0]=125000,[1]=175000,[2]=125000,[3]=50000,[4]=1500000,[5]=1000000}
local function value(frame,t,kind)
    local v=0;local s,m=frame.state,frame.map;local r=Weapons.radius(m,kind)
    for _,b in pairs(s.structures) do if hostile(frame,b.owner) and not s:has_fallout(b.tile) and m.dist2(t,b.tile)<=r*r then
        local weight=1
        -- Child targets are random. A structure in the outer ring is potential
        -- collateral value, not a guaranteed hit by every warhead.
        if kind=='scatter' and m.dist2(t,b.tile)>(30/(m.k_lin or 1))^2 then weight=.35 end
        v+=(values[b.kind] or 0)*(b.level or 1)*weight
    end end
    return v
end
local function scatterAction(frame,p,first)
    return {kind='scatter',intent={type='nuke',kind='scatter',tile=p.tile},cost=frame.ctx.rules:cost('scatter'),
        bias=first and p.score or 14,channel='missile',cooldown=1,gold_reserve=p.gold_reserve,
        label='Scattershot suppression '..tostring(p.sent+1)..'/'..tostring(p.total)..'; reassess SAMs before every launch',
        plan={salvo={tile=p.tile,total=p.total,sent=p.sent,remaining=p.remaining,coverage=p.coverage,
            created_tick=p.created_tick,deadline=p.deadline,gold_reserve=p.gold_reserve,
            interception_budget=p.interception_budget,score=p.score,objective_sid=p.objective_sid,objective_owner=p.objective_owner,flight_ticks=p.flight_ticks}}}
end
function Arsenal.generate(frame,o,agent)
    local s,m,me=frame.state,frame.map,frame.me;local rules=frame.ctx.rules
    local rows={};agent.missileAssessments={}
    if agent.salvoPlan then
        local p=agent.salvoPlan;local cost=rules:cost('scatter')
        local allowed,why=Weapons.canLaunch(s,me,p.tile,'scatter',p)
        local objective=p.objective_sid and s.structures[p.objective_sid]
        if p.remaining<=0 or frame.useScatter==false or s.tick>p.deadline or not hostile(frame,s:tile_owner(p.tile))
            or p.objective_sid and (not objective or objective.owner~=p.objective_owner)
            or not allowed or not rules:availability('scatter').ok or frame.info.gold<p.remaining*cost+p.gold_reserve then
            agent.lastSalvo={tile=p.tile,status=p.remaining<=0 and 'completed' or 'stopped',sent=p.sent,total=p.total,tick=s.tick,
                reason=p.remaining<=0 and 'planned launch count completed; waiting for impact' or why or 'objective, target, deadline, funding or unlock changed'}
            agent.strikeCooldowns[p.tile]=s.tick+150;agent.salvoPlan=nil
        else
            table.insert(rows,scatterAction(frame,p,false));return rows
        end
    end
    local targets={}
    for sid,b in pairs(s.structures) do if hostile(frame,b.owner) and not s:has_fallout(b.tile) then
        table.insert(targets,{tile=b.tile,kind=b.kind,owner=b.owner,sid=sid,weight=(b.level or 1)*(b.kind==4 and 9 or b.kind==5 and 7 or b.kind==3 and 1 or 4)})
    end end
    table.sort(targets,function(a,b) return a.weight==b.weight and a.tile<b.tile or a.weight>b.weight end)
    while #targets>128 do table.remove(targets) end
    -- Keep SAM suppression candidates as well as the best economic clusters.
    for _,target in ipairs(targets) do target.cluster=value(frame,target.tile,'hydrogen') end
    table.sort(targets,function(a,b)
        local x=a.cluster+(a.kind==4 and 2500000 or 0);local y=b.cluster+(b.kind==4 and 2500000 or 0)
        return x==y and a.tile<b.tile or x>y
    end)
    local gold=frame.info.gold or 0
    local reserve=math.min(gold*.15,math.max(125000,(frame.info.income or 0)*3))
    for _,kind in ipairs({'atom','hydrogen','mirv','scatter'}) do
        local available=rules:availability(kind)
        if kind=='scatter' and frame.useScatter==false or not available.ok then
            table.insert(agent.missileAssessments,{kind=kind,available=false,reason=kind=='scatter' and frame.useScatter==false
                and 'Scattershot disabled' or available.reason or 'gold, owned unlock or ready launcher unavailable'})
            continue
        end
        local choices={}
        local aims={}
        for i=1,math.min(8,#targets) do
            local target=targets[i];table.insert(aims,target)
            if kind=='scatter' and target.kind==4 then
                -- A centered single Scattershot can lose its main warhead to
                -- the SAM while all children land outside that SAM's blast
                -- radius. Offset the aim so children can actually hit it.
                local r=math.max(1,math.floor(28/(m.k_lin or 1)+.5))
                for _,d in ipairs({{1,0},{-1,0},{0,1},{0,-1}}) do
                    local x,y=target.tile%m.W+d[1]*r,target.tile//m.W+d[2]*r
                    local t=y*m.W+x
                    if x>=0 and x<m.W and y>=0 and y<m.H and s:tile_owner(t)==target.owner then
                        local aim=table.clone(target);aim.tile=t;aim.offset=true;table.insert(aims,aim)
                    end
                end
            end
        end
        local recorded=0
        for _,target in ipairs(aims) do
            if s.tick<((agent.suppressionCooldowns or {})[tostring(target.sid)] or 0) then continue end
            if s.tick<(agent.strikeCooldowns[target.tile] or 0) or duplicate(frame,target.tile,kind) then continue end
            local cost=rules:cost(kind);local v=value(frame,target.tile,kind)
            local q,why
            if kind=='scatter' then q,why=Weapons.scatterAssessment(s,me,target.tile,6) end
            local count=q and q.count or 1;local total=cost*count
            local worthwhile=v>=total*.9
            -- Taking out the observed hostile air-defense network can unlock
            -- cheaper follow-up strikes. Still require a significant SAM asset.
            if kind=='scatter' and q and target.kind==4 and q.sam_levels>0 then worthwhile=v>=total*.35 and total<=gold*.4 end
            if kind=='scatter' and q and target.kind==4 and not target.offset and q.count==1 and q.interception_budget>0 then
                worthwhile=false -- choose a ring offset or save for another salvo.
            end
            local p=q and {tile=target.tile,total=count,sent=0,remaining=count,coverage=q.coverage,
                created_tick=s.tick,deadline=s.tick+(count+2)*10,gold_reserve=reserve,
                interception_budget=q.interception_budget,objective_sid=target.kind==4 and target.sid or nil,objective_owner=target.owner,flight_ticks=q.flight_ticks} or nil
            local allowed,reason=Weapons.canLaunch(s,me,target.tile,kind,p)
            if recorded<6 then recorded+=1;table.insert(agent.missileAssessments,{kind=kind,tile=target.tile,
                estimated_value=v,launch_count=count,total_cost=total,interception=q,eligible=allowed and worthwhile and gold>=total+reserve,
                reason=why or reason or (not worthwhile and 'asset value below total salvo expense' or gold<total+reserve and 'whole salvo is not funded' or 'candidate available')}) end
            if not worthwhile or kind=='scatter' and not q or gold<total+reserve or not allowed or not rules:placement(kind,target.tile).ok then continue end
            local score=4+math.min(6,v/math.max(1,total))+(o.incomingBy[target.owner] and 3 or 0)
            if kind=='scatter' then
                p.score=score+(target.kind==4 and 2 or 0)+(target.offset and count<=2 and .5 or 0);table.insert(choices,scatterAction(frame,p,true))
            else
                table.insert(choices,{kind=kind,intent={type='nuke',kind=kind,tile=target.tile},cost=cost,
                    bias=score,channel='missile',cooldown=2,gold_reserve=reserve,
                    label='Launching '..kind..' at the best affordable exposed asset cluster'})
            end
        end
        table.sort(choices,function(a,b) return a.bias==b.bias and a.intent.tile<b.intent.tile or a.bias>b.bias end)
        for i=1,math.min(2,#choices) do table.insert(rows,choices[i]) end
    end
    return rows
end
return Arsenal
