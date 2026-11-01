-- Bounded public-state telemetry. Observations are not reconstructed player inputs.
local Recorder={};Recorder.__index=Recorder
function Recorder.new(frame)
    local self=setmetatable({start_tick=frame.state.tick,me=frame.me,players={},samples={},events={},
        structures={},attacks={},nukes={},initialized=false,events_dropped=0,samples_dropped=0},Recorder)
    return self
end
function Recorder:event(row)
    table.insert(self.events,row)
    if #self.events>256 then table.remove(self.events,1);self.events_dropped+=1 end
end
function Recorder:observe(frame)
    local s=frame.state
    -- At most once per game second; no extra requests or full terrain scans.
    if self.lastTick and s.tick-self.lastTick<10 then return end
    self.lastTick=s.tick
    local counts={}
    for sid,b in pairs(s.structures) do
        counts[b.owner]=counts[b.owner] or {}
        local c=counts[b.owner];local kind=tostring(b.kind);c[kind]=(c[kind] or 0)+1
        local old=self.structures[sid]
        if self.initialized and (self.players[b.owner] or (s.owners[b.owner] or {}).kind==2 or b.owner==frame.me)
            and (not old or old.owner~=b.owner or old.level~=(b.level or 1)) then
            self:event({tick=s.tick,type=not old and 'structure_observed' or old.owner~=b.owner and 'structure_capture' or 'structure_upgrade',
                nation=b.owner,previous_owner=old and old.owner,sid=sid,kind=b.kind,tile=b.tile,level=b.level or 1})
        end
        self.structures[sid]={owner=b.owner,level=b.level or 1}
    end
    for sid,old in pairs(self.structures) do
        if not s.structures[sid] then
            if self.players[old.owner] then self:event({tick=s.tick,type='structure_removed',nation=old.owner,sid=sid}) end
            self.structures[sid]=nil
        end
    end
    for id,o in pairs(s.owners) do
        if o.kind==2 or id==frame.me then
            local p=self.players[id]
            if not p then
                p={nation=id,name=o.name,first_tick=s.tick,first_land=o.tiles or 0,peak_land=0,observed_attacks=0,observed_missiles=0}
                self.players[id]=p
            end
            p.land=o.tiles or 0;p.peak_land=math.max(p.peak_land,p.land);p.troops=o.troops or 0
            p.gold=o.gold or 0;p.income=o.income or 0;p.alive=o.alive;p.buildings=counts[id] or {}
            p.committed=0;p.incoming=0
        end
    end
    local attacks={}
    for aid,a in pairs(s.attacks) do
        attacks[aid]=true
        if not a.retreating then
            local attacker,target=self.players[a.attacker],self.players[a.target]
            if attacker then attacker.committed+=(a.troops or 0) end
            if target then target.incoming+=(a.troops or 0) end
        end
        if self.initialized and not self.attacks[aid] and not a.retreating and (self.players[a.attacker] or a.target==frame.me) then
            local p=self.players[a.attacker];if p then p.observed_attacks+=1 end
            self:event({tick=s.tick,type='attack_observed',nation=a.attacker,target=a.target,troops=a.troops,anchor=a.anchor_tile})
        end
    end
    self.attacks=attacks
    local nukes={}
    for nid,n in pairs(s.nukes) do
        nukes[nid]=true
        if self.initialized and not self.nukes[nid] then
            local p=self.players[n.owner];if p then p.observed_missiles+=1 end
            self:event({tick=s.tick,type='missile_observed',nation=n.owner,kind=n.kind,tile=n.to_tile})
        end
    end
    self.nukes=nukes
    if not self.sampleTick or s.tick-self.sampleTick>=100 then
        self.sampleTick=s.tick
        local ranked={}
        for id,p in pairs(self.players) do
            if p.alive and id~=frame.me then table.insert(ranked,p) end
        end
        table.sort(ranked,function(a,b) return a.land>b.land end)
        local rows={}
        local function add(p)
            if p then table.insert(rows,{nation=p.nation,land=p.land,troops=p.troops,gold=p.gold,income=p.income,committed=p.committed,incoming=p.incoming,buildings=table.clone(p.buildings)}) end
        end
        add(self.players[frame.me])
        for i=1,math.min(12,#ranked) do add(ranked[i]) end
        table.insert(self.samples,{tick=s.tick,players=rows})
        -- Preserve first ten minutes plus the latest twenty minutes.
        if #self.samples>180 then table.remove(self.samples,61);self.samples_dropped+=1 end
    end
    self.initialized=true
end
function Recorder:report()
    local players={};for _,p in pairs(self.players) do table.insert(players,p) end
    table.sort(players,function(a,b) return a.peak_land>b.peak_land end)
    return {scope='Public snapshots since start; observed events may miss actions between samples. Not training labels or proof of intent.',
        start_tick=self.start_tick,players=players,samples=self.samples,events=self.events,
        samples_dropped=self.samples_dropped,events_dropped=self.events_dropped,sample_interval_ticks=100,event_scan_interval_ticks=10}
end
return Recorder
