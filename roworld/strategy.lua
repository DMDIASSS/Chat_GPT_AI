-- Strategic memory for the observed board; no hidden player inputs are assumed.
local Strategy={};Strategy.__index=Strategy
local Core = require("./core")
function Strategy.new(frame)
    local owners={};for sid,b in pairs(frame.state.structures) do owners[sid]=b.owner end
    local allies={};for id in pairs(frame.state.owners) do if frame.state:are_allies(frame.me,id) then allies[id]=true end end
    return setmetatable({campaigns={},peace={},structures=owners,timeline={},recoverUntil=0,board={},core=Core.new(),
        allies=allies,relationships={},distrust={},asked={},allianceSeq=frame.state.alliance_seq or 0},Strategy)
end
function Strategy:trustworthy(frame,id) return frame.now>=(self.distrust[id] or 0) end
function Strategy:canAsk(frame,id) return self:trustworthy(frame,id) and frame.now>=(self.asked[id] or 0) end
function Strategy:allianceEnded(frame,id,confirmed,reason)
    table.insert(self.relationships,{nation=id,tick=frame.state.tick,confirmed_betrayal=confirmed,reason=reason})
    if #self.relationships>32 then table.remove(self.relationships,1) end
    if confirmed then
        self.distrust[id]=frame.now+180;self.peace[id]=nil
        if self.core.fronts[id] or (self.adjacentAllies or {})[id] then self.recoverUntil=frame.now+12 end
    end
end
function Strategy:updateCore(frame) return self.core:update(frame) end
function Strategy:corePriority(frame,tile) return self.core:priority(frame.map,tile) end
local function friendly(s,me,id) return id==me or id>0 and s:are_allies(me,id) end
function Strategy:sent(action,s,me,now)
    local kind=action.intent.type
    if kind=='ally_request' then self.peace[action.intent.target]=now+45;self.asked[action.intent.target]=now+120 end
    local target=action.intent.tile and s:tile_owner(action.intent.tile) or 0
    if (kind=='attack' or kind=='boat') and target>0 then
        local c=self.campaigns[target]
        if not c or now-(c.lastSent or now)>60 then
            c={started=now,lastProgress=now,sends=0,spent=0,captures=0,lastTiles=(s.owners[target] or {}).tiles}
            self.campaigns[target]=c
        end
        c.lastSent=now;c.sends+=1;c.spent+=(s.owners[me].troops or 0)*(action.intent.ratio or 0)
    elseif kind=='retreat' then
        local attack=s.attacks[action.intent.attack_id]
        if attack and attack.target>0 then
            local c=self.campaigns[attack.target]
            if c then c.pauseUntil=now+25 end
        end
    end
end
function Strategy:observe(frame)
    local s=frame.state
    local recorded={}
    for _,event in ipairs(s.alliance_events or {}) do
        if event.seq>self.allianceSeq and (event.a==frame.me or event.b==frame.me) then
            local other=event.a==frame.me and event.b or event.a;recorded[other]=true
            self:allianceEnded(frame,other,event.breaker==other and not event.expired,
                event.expired and 'expired' or event.breaker==other and 'partner broke alliance' or 'alliance ended')
        end
        self.allianceSeq=math.max(self.allianceSeq,event.seq)
    end
    for id,o in pairs(s.owners) do
        local allied=s:are_allies(frame.me,id)
        if self.allies[id] and not allied and not recorded[id] then
            self:allianceEnded(frame,id,false,'ended; cause unavailable on this route')
            if (o.traitor_until or 0)>s.tick then self.distrust[id]=frame.now+90 end
        end
        self.allies[id]=allied or nil
    end
    for sid,b in pairs(s.structures) do
        local previous=self.structures[sid]
        if previous and previous~=frame.me and b.owner==frame.me then
            local c=self.campaigns[previous]
            if c then c.captures+=1;c.lastProgress=frame.now end
        end
        self.structures[sid]=b.owner
    end
    for sid in pairs(self.structures) do if not s.structures[sid] then self.structures[sid]=nil end end
    for id,c in pairs(self.campaigns) do
        local enemy=s.owners[id]
        if not enemy or not enemy.alive then self.campaigns[id]=nil
        else
            if c.lastTiles and enemy.tiles and enemy.tiles<c.lastTiles then c.lastProgress=frame.now end
            c.lastTiles=enemy.tiles
        end
    end
end
-- Exact conditional amount from the inspected country AI's defensive routine.
-- It still needs a valid shared border and a recent incoming attack to apply.
function Strategy.countryCounter(amount,bank)
    if bank<amount*1.1 or amount<bank*.02 then return 0 end
    return bank*math.clamp(amount*1.25/math.max(bank,1),.05,.4)
end
function Strategy:updateBoard(frame,groups,a,fronts,allies)
    self.adjacentAllies=allies or {}
    local s,home=frame.state,a.home
    local near={};for id in pairs(groups) do near[id]=true end
    for id,m in pairs(fronts or {}) do if frame.now-m.at<=8 then near[id]=true end end
    local b={human_neighbours=0,country_neighbours=0,largest_human=0,pressure=0,
        incoming=a.incoming,committed=0,leaders={},candidates={},mode='develop',unreliable_ally_pressure=0}
    local core=self.core.summary
    b.core=core
    local pressures={}
    b.naval_pressure=0
    for id,o in pairs(s.owners) do
        if id~=frame.me and o.alive then
            if o.kind==2 then table.insert(b.leaders,{nation=id,troops=o.troops or 0,land=o.tiles or 0,neighbour=near[id]==true}) end
            if near[id] and not friendly(s,frame.me,id) then
                local bank=o.troops or 0
                if o.kind==2 then
                    b.human_neighbours+=1;b.largest_human=math.max(b.largest_human,bank)
                elseif o.kind==0 then b.country_neighbours+=1 end
                table.insert(pressures,bank*(o.kind==2 and .5 or o.kind==0 and .28 or .1))
            elseif (allies or {})[id] and o.kind==0 and (o.troops or 0)>home*3 then
                -- Country alliances can be broken when their partner becomes
                -- much weaker; an alliance is not a permanent defensive wall.
                b.unreliable_ally_pressure+=(o.troops or 0)*.12
            end
        end
    end
    table.sort(pressures,function(x,y) return x>y end)
    b.pressure=(pressures[1] or 0)+(pressures[2] or 0)*.6+(pressures[3] or 0)*.3
    local borders=frame.ctx.borders
    if type(borders.has_coast)=='function' and borders:has_coast() then
        for _,port in pairs(s.structures) do
            local o=s.owners[port.owner]
            if port.kind==1 and o and o.kind==2 and not near[port.owner] and not friendly(s,frame.me,port.owner)
                and borders:can_reach_by_sea(port.tile) then
                b.naval_pressure=math.max(b.naval_pressure,math.min(home*.2,(o.troops or 0)*.05))
            end
        end
    end
    local retained=math.min(home*.9,b.pressure+b.unreliable_ally_pressure+b.naval_pressure)
    a.reserve=math.min(home,math.max(a.reserve,retained,a.incoming*1.5))
    if core.at_risk then
        a.reserve=math.min(home,math.max(a.reserve,home*.65,core.incoming*1.8,
            math.min(home*.9,core.threat_pressure)))
    end
    a.available=math.max(0,home-a.reserve)
    for _,attack in ipairs(a.outgoing) do b.committed+=attack.troops or 0 end
    -- Land losses are stronger evidence than a bank drop caused by our own order.
    local peak=frame.info.tiles or 0
    for _,row in ipairs(self.timeline) do if frame.now-row.at<20 then peak=math.max(peak,row.land) end end
    if peak>=50 and (frame.info.tiles or 0)<peak*.88 then self.recoverUntil=frame.now+15 end
    b.recover=frame.now<self.recoverUntil or a.incoming>home*.35 or core.critical==true
    local stranded=core.center_tile and (core.clearable_tiles or 0)==0 and (core.friendly_fraction or 1)<.15
        and a.incoming==0 and (core.naval_incoming or 0)==0 and b.committed==0
    if stranded then self.strandedSince=self.strandedSince or frame.now else self.strandedSince=nil end
    b.escape=self.strandedSince~=nil and frame.now-self.strandedSince>=20
    b.overextended=b.human_neighbours>0 and b.largest_human>home*1.4
    if b.recover then b.mode='recover' elseif core.at_risk or b.overextended or a.incoming>home*.15 then b.mode='guard' end
    if b.escape then b.mode='relocate';a.reserve=math.max(a.reserve,home*.75);a.available=math.max(0,home-a.reserve) end
    table.sort(b.leaders,function(x,y) return x.land>y.land end)
    while #b.leaders>5 do table.remove(b.leaders) end
    self.board=b
    if not self.lastSample or frame.now-self.lastSample>=5 then
        self.lastSample=frame.now
        table.insert(self.timeline,{at=frame.now,tick=s.tick,land=frame.info.tiles or 0,troops=home,
            capacity=frame.info.max_troops or 0,gold=frame.info.gold or 0,incoming=a.incoming,
            committed=b.committed,reserve=a.reserve,mode=b.mode,human_neighbours=b.human_neighbours,
            core_tile=core.center_tile,core_at_risk=core.at_risk,core_owned_fraction=core.owned_fraction})
        if #self.timeline>120 then table.remove(self.timeline,1) end
    end
    return b
end
function Strategy:canTarget(frame,id,a)
    local s=frame.state;local o=s.owners[id];local b=self.board
    if not o or friendly(s,frame.me,id) then return false end
    if frame.now<(self.peace[id] or 0) or s:has_request(frame.me,id) then return false end
    if a.incoming>a.home*.2 then return false end
    if (self.core.summary.at_risk or self.core.summary.needs_buffer) and not self.core.fronts[id] then return false end
    if b.recover or b.overextended and o.kind~=1 then return false end
    local c=self.campaigns[id]
    if c and frame.now-(c.lastSent or c.started)>45 and not (a.targets or {})[id] then
        self.campaigns[id]=nil;c=nil
    end
    if c then
        if frame.now<(c.pauseUntil or 0) then return false end
        if frame.now-(c.lastSent or -math.huge)<(o.kind==2 and 7 or o.kind==0 and 4.5 or 3) then return false end
        if c.sends>=3 and frame.now-c.lastProgress>8 then return false end
        if o.kind==2 and c.spent>a.home*.35 then return false end
    end
    if o.kind==2 and a.incoming>a.home*.1 then return false end
    return true
end
function Strategy:nuclearTarget(frame,id)
    if frame.now<(self.peace[id] or 0) or frame.state:has_request(frame.me,id) then return false end
    local o=frame.state.owners[id]
    if self.core.summary.at_risk and not self.core.fronts[id] then
        local direct=false
        for _,a in pairs(frame.state.attacks) do
            if a.attacker==id and a.target==frame.me and not a.retreating then direct=true end
        end
        if not direct then return false end
    end
    if o and o.kind==2 and self.board.mode~='develop' then
        for _,a in pairs(frame.state.attacks) do
            if a.attacker==id and a.target==frame.me and not a.retreating then return true end
        end
        return false
    end
    return true
end
function Strategy:assetOpportunity(frame,g)
    local map=frame.map;local best,tile,sid=0,g.tile,nil
    local bestScore=self:corePriority(frame,g.tile)
    for _,b in pairs(frame.state.structures) do
        if b.owner==g.id and b.kind~=3 then
            local weight=({[0]=4,[1]=5,[2]=5,[4]=2,[5]=3})[b.kind] or 1
            for _,t in ipairs(g.tiles or {g.tile}) do
                local d=math.sqrt(map.dist2(t,b.tile))*(map.k_lin or 1)
                local value=weight*math.max(0,1-d/40)
                local score=value+self:corePriority(frame,t)
                if score>bestScore then bestScore=score;best,tile,sid=value,t,b.sid end
            end
        end
    end
    return best,tile,sid
end
function Strategy:utility(frame,g,plan,a)
    local o=frame.state.owners[g.id];local asset=self:assetOpportunity(frame,g)
    local c=self.campaigns[g.id]
    local value=math.min(4,math.log(1+a.home/math.max(100,o.troops or 0)))*3
        +math.min(3,math.log(1+g.front))*.5+(plan.pressure or 0)*3+asset
        -plan.amount/math.max(1,a.home)*8+(o.kind==2 and -7 or o.kind==0 and -1.5 or 0)
        -math.min(4,(c and c.sends or 0)*.6)-math.max(0,(self.board.human_neighbours or 0)-1)*1.5
    value+=math.clamp(plan.score/200,-1,1)
    value+=self:corePriority(frame,g.tile)
    return value
end
function Strategy:review(frame,a)
    local best,priority,reason
    for _,attack in ipairs(a.outgoing) do
        local known=type(attack.anchor_tile)=='number' and attack.anchor_tile>=0 and attack.anchor_tile<frame.map.N
        local away=known and not self.core:isSite(frame.map,attack.anchor_tile) or not known and self.core.summary.at_risk
        if attack.target>0 then
            local o=frame.state.owners[attack.target] or {};local c=self.campaigns[attack.target]
            local why
            local core=self.core.summary
            if (core.at_risk or core.needs_buffer) and away then
                why='Recalling a distant raid to protect the home and economic center'
            elseif friendly(frame.state,frame.me,attack.target) then why='Recalling troops after an alliance changed'
            elseif self.board.recover or a.incoming>a.home*.5 then why='Recalling the largest raid to defend the whole territory'
            elseif c and c.captures>0 and o.kind==0 and ((self.board.human_neighbours or 0)>0
                or self.board.mode=='guard' or c.sends>=3 or frame.now-c.lastProgress>6) then
                why='Secured a country building; banking the gain and reassessing'
            elseif c and c.sends>=3 and frame.now-c.lastProgress>10 then why='Ending a stalled campaign; reassessing other fronts'
            elseif c and o.kind==2 and c.spent>a.home*.35 and frame.now-c.started>7 then why='Limiting exposure against a human player'
            end
            if why and (not priority or (attack.troops or 0)>priority) then best,priority,reason=attack,attack.troops or 0,why end
        elseif (self.board.recover or (self.core.summary.at_risk or self.core.summary.needs_buffer) and away)
            and (not priority or (attack.troops or 0)>priority) then
            best,priority,reason=attack,attack.troops or 0,'Recalling distant expansion to secure home and core buildings'
        end
    end
    if best then return {intent={type='retreat',attack_id=best.aid},channel='retreat',
        cooldown=(self.core.summary.critical or a.incoming>a.home*.5) and .6 or 3,label=reason} end
end
return Strategy
