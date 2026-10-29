local Observe={}
local Schema=require('./schema')
local Geography=require('./geography')
local Weapons=require('./shared/weapons')
local function ratio(a,b) return Schema.clamp((a or 0)/math.max(1,b or 0),0,8) end
function Observe.read(frame,agent)
    local s,m,me,info=frame.state,frame.map,frame.me,frame.info
    local o={tick=s.tick,phase=s.phase,me=me,home=math.max(0,info.troops or 0),capacity=math.max(1,info.max_troops or 1),
        incoming=0,outgoing=0,incomingBy={},outgoingTo={},pressure={},committed={},assets={},counts={},levels={},
        players={},attacks={},units={},missiles={},diplomacy={},relationships={},allyPower={},alliedNear=0,humanFronts=0,foreignFronts=0,threat=0}
    o.anchor=Geography.anchor(frame,agent.anchor)
    o.groups,o.near,o.frontSites,agent.frontCursor,o.frontCoverage=Geography.fronts(frame,agent.frontCursor)
    agent.anchor=o.anchor
    for aid,a in pairs(s.attacks) do
        table.insert(o.attacks,{id=aid,attacker=a.attacker,target=a.target,troops=a.troops,retreating=a.retreating==true})
        if not a.retreating then
            local n=math.max(0,a.troops or 0)
            o.pressure[a.target]=(o.pressure[a.target] or 0)+n
            o.committed[a.attacker]=(o.committed[a.attacker] or 0)+n
            if a.attacker==me then o.outgoing+=n;o.outgoingTo[a.target]=(o.outgoingTo[a.target] or 0)+n end
            if a.target==me then o.incoming+=n;o.incomingBy[a.attacker]=(o.incomingBy[a.attacker] or 0)+n end
        end
    end
    for _,b in pairs(s.structures) do
        local value=({[0]=4,[1]=5,[2]=6,[3]=0,[4]=4,[5]=3})[b.kind] or 0
        o.assets[b.owner]=(o.assets[b.owner] or 0)+value*(b.level or 1)*((b.active_tick or 0)<=s.tick and 1 or .5)
        if b.owner==me then
            o.counts[b.kind]=(o.counts[b.kind] or 0)+1;o.levels[b.kind]=(o.levels[b.kind] or 0)+(b.level or 1)
        end
    end
    local leader=0;local alive=0
    for id,p in pairs(s.owners) do
        if p.alive then
            alive+=1;leader=math.max(leader,p.tiles or 0)
            local allied=id~=me and s:are_allies(me,id) or false
            local team=(info.team or 0)>0 and info.team==p.team
            local rel={nation=id,allied=allied,same_team=team,friend=agent.cooperation:isFriend(id),
                outgoing_request=id~=me and s:has_request(me,id) or false,incoming_request=id~=me and s:has_request(id,me) or false}
            if allied and type(s.alliance_info)=='function' then rel.expiry=s:alliance_info(me,id) end
            o.diplomacy[id]=rel
            table.insert(o.players,{id=id,name=p.name,kind=p.kind,team=p.team or 0,troops=p.troops or 0,
                capacity=p.max_troops or 0,gold=p.gold or 0,income=p.income or 0,land=p.tiles or 0,
                traitor_until=p.traitor_until or 0,assets=o.assets[id] or 0})
            if o.near[id] then
                if allied then o.alliedNear+=1
                elseif id~=me then
                    o.foreignFronts+=1;if p.kind==2 then o.humanFronts+=1 end
                    o.threat=math.max(o.threat,p.troops or 0)
                end
            end
        end
    end
    table.sort(o.players,function(a,b) return a.id<b.id end)
    local teamPower={}
    for _,p in ipairs(o.players) do if p.team>0 then teamPower[p.team]=(teamPower[p.team] or 0)+p.troops end end
    for _,p in ipairs(o.players) do o.allyPower[p.id]=p.team>0 and teamPower[p.team]-p.troops or 0 end
    for k,allied in pairs(s.alliances or {}) do
        if allied and type(k)=='number' then
            local a,b=k//1024,k%1024;local x,y=s.owners[a],s.owners[b]
            if x and y and x.alive and y.alive then
                table.insert(o.relationships,{a=a,b=b,allied=true})
                if not ((x.team or 0)>0 and x.team==y.team) then
                    o.allyPower[a]=(o.allyPower[a] or 0)+(y.troops or 0)
                    o.allyPower[b]=(o.allyPower[b] or 0)+(x.troops or 0)
                end
            end
        end
    end
    -- Exact transient rows and exact relationship flags are never reconstructed from a map latent.
    for uid,u in pairs(s.units or {}) do
        table.insert(o.units,{uid=uid,kind=u.kind,owner=u.owner,hp=u.hp,max_hp=u.max_hp,
            troops=u.troops,state=u.state,path=u.path,start_tick=u.start_tick,patrol_tile=u.patrol_tile,ticks_per_tile_x100=u.ticks_per_tile_x100})
    end
    for uid,n in pairs(s.nukes) do table.insert(o.missiles,{uid=uid,kind=n.kind,owner=n.owner,to_tile=n.to_tile,
        from_tile=n.from_tile,launch_tick=n.launch_tick,flight_ticks=n.flight_ticks,sam_sid=n.sam_sid}) end
    o.alerts=Weapons.alerts(s,me);o.nuclearThreat=Weapons.threat(s,me)
    -- This is a policy safety budget, deliberately separate from game legality.
    o.reserve=math.max(o.home*.35,o.incoming*1.5,math.min(o.home*.7,o.threat*.25))
    for id in pairs(o.near) do
        local p=s.owners[id];local rel=o.diplomacy[id]
        if p and rel and rel.allied and not rel.same_team and p.kind==2 and (p.troops or 0)>o.home*1.5 then
            o.reserve=math.max(o.reserve,o.home*((p.troops or 0)>=o.home*2 and .6 or .45))
        end
    end
    o.available=math.max(0,o.home-o.reserve)
    local ships,boats=0,0
    for _,u in ipairs(o.units) do if u.owner==me then if u.kind==2 then ships+=1 elseif u.kind==0 then boats+=1 end end end
    o.ships,o.boats=ships,boats
    local neutral=o.groups[0];local teamCount=agent.cooperation.status.team_count or 0
    local c={s.phase==0 and 1 or 0,s.phase==1 and 1 or 0,Schema.clamp((s.tick-math.max(0,s.playing_since or 0))/600,0,20),
        Schema.log(o.home),Schema.log(o.capacity),ratio(o.home,o.capacity),Schema.log(info.gold),ratio(info.tiles,m.N),
        Schema.log(info.income),ratio(o.incoming,o.home),ratio(o.outgoing,o.home),ratio(o.reserve,o.home),ratio(o.available,o.home),
        Schema.log(neutral and neutral.front or 0),o.foreignFronts/16,o.humanFronts/8,ratio(o.threat,o.home),
        (o.levels[0] or 0)/16,(o.levels[2] or 0)/16,(o.levels[1] or 0)/16,(o.counts[3] or 0)/8,
        (o.levels[4] or 0)/8,(o.levels[5] or 0)/8,ships/8,boats/10,#o.alerts/8,
        (info.team or 0)>0 and 1 or 0,teamCount/16,o.alliedNear/16,ratio(leader,info.tiles),
        (info.traitor_until or 0)>s.tick and 1 or 0,o.frontCoverage}
    local function tile(t)
        if not Geography.valid(m,t) then for _=1,4 do table.insert(c,0) end;return end
        local id=s:tile_owner(t)
        table.insert(c,id==me and 1 or 0);table.insert(c,id>0 and s:are_allies(me,id) and 1 or 0)
        table.insert(c,m:is_contestable(t) and 1 or 0);table.insert(c,s:has_fallout(t) and 1 or 0)
    end
    local ax,ay=o.anchor%m.W,o.anchor//m.W;local step=math.max(1,math.ceil(8/(m.k_lin or 1)))
    for dy=-2,2 do for dx=-2,2 do
        local x,y=ax+dx*step,ay+dy*step
        tile(x>=0 and x<m.W and y>=0 and y<m.H and y*m.W+x or -1)
    end end
    for y=0,3 do for x=0,3 do tile(math.min(m.H-1,math.floor((y+.5)*m.H/4))*m.W+math.min(m.W-1,math.floor((x+.5)*m.W/4))) end end
    local previous=agent.outcome or {}
    for i=1,8 do table.insert(c,Schema.clamp(previous[i] or 0)) end
    assert(#c==Schema.context,'Observation schema size changed')
    for i,v in ipairs(c) do c[i]=Schema.clamp(v) end
    o.context=c;o.alive=alive;o.leaderLand=leader
    return o
end
return Observe
