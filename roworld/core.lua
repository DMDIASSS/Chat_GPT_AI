-- Local territory objectives. Troops remain a global bank in RoWorld; these
-- anchors guide expansion and coverage rather than inventing regional garrisons.
local Core={};Core.__index=Core
local VALUES={[0]=8,[1]=7,[2]=8,[3]=2,[4]=3,[5]=6,[6]=4,[7]=5,[8]=5}
local function valid(map,t) return type(t)=='number' and t>=0 and t<map.N end
local function friendly(s,me,id) return id==me or id>0 and s:are_allies(me,id) end
local function neighbours(map,t,fn)
    local x=t%map.W
    if x>0 then fn(t-1) end;if x<map.W-1 then fn(t+1) end
    if t>=map.W then fn(t-map.W) end;if t<map.N-map.W then fn(t+map.W) end
end
function Core.new() return setmetatable({anchors={},fronts={},summary={}},Core) end
function Core:priority(map,tile)
    if not valid(map,tile) then return 0 end
    local best=0
    for _,a in ipairs(self.anchors) do
        local distance=math.sqrt(map.dist2(tile,a.tile))*(map.k_lin or 1)
        best=math.max(best,math.max(0,1-distance/a.radius)*(a.kind=='economic' and 9 or 7))
    end
    return best
end
function Core:isSite(map,tile) return self:priority(map,tile)>0 end
function Core:update(frame)
    local s,map,me=frame.state,frame.map,frame.me
    local function owned(t) return valid(map,t) and s:tile_owner(t)==me and not s:has_fallout(t) end
    local assets,candidates={},{}
    local spawn=frame.info.spawn_tile
    if owned(spawn) then table.insert(candidates,spawn) end
    if owned(frame.info.label_tile) then table.insert(candidates,frame.info.label_tile) end
    for _,b in pairs(s.structures) do
        if b.owner==me and owned(b.tile) then
            table.insert(assets,{tile=b.tile,kind=b.kind,level=b.level or 1,sid=b.sid,
                value=(VALUES[b.kind] or 1)*(b.level or 1)})
            if #candidates<64 then table.insert(candidates,b.tile) end
        end
    end
    if #candidates==0 then
        -- A lost spawn must not keep the bot defending an empty enemy island.
        for t in pairs(frame.ctx.borders.border) do if owned(t) then table.insert(candidates,t);break end end
    end
    local function value(tile)
        local total=0
        for _,b in ipairs(assets) do
            local d=math.sqrt(map.dist2(tile,b.tile))*(map.k_lin or 1)
            if d<=120 then total+=b.value*(1-d/240) end
        end
        return total
    end
    local best,weight=nil,-1
    for _,t in ipairs(candidates) do local v=value(t);if v>weight then best,weight=t,v end end
    -- Keep the center stable through small changes in levels and ownership.
    if owned(self.primary) and best and value(self.primary)*1.25+3>=weight then best=self.primary;weight=value(best) end
    local changed=best~=self.primary
    self.primary=best;self.anchors={};self.fronts={}
    if best then table.insert(self.anchors,{tile=best,radius=100,kind='economic'}) end
    if owned(spawn) and spawn~=best then table.insert(self.anchors,{tile=spawn,radius=70,kind='home'}) end
    if self.relocation and frame.now<self.relocation.untilTime and valid(map,self.relocation.tile) then
        table.insert(self.anchors,{tile=self.relocation.tile,radius=70,kind='relocation'})
    end
    local summary={center_tile=best,home_tile=spawn,home_owned=owned(spawn),asset_value=math.max(0,weight),
        anchors=self.anchors,owned_samples=0,neutral_samples=0,hostile_samples=0,allied_samples=0,
        incoming=0,clearable_tiles=0,closest_hostile_distance=nil,threat_pressure=0,at_risk=false,critical=false}
    summary.buildings={};summary.protected_building_count=0
    for _,b in ipairs(assets) do
        if self:isSite(map,b.tile) then
            summary.protected_building_count+=1
            if #summary.buildings<32 then table.insert(summary.buildings,{tile=b.tile,kind=b.kind,level=b.level,sid=b.sid}) end
        end
    end
    summary.naval_incoming=0;summary.hostile_transports=0;summary.hostile_warships=0
    local seen,hostiles,frontSeen={},{},{}
    local function frontier(t)
        local id=s:tile_owner(t)
        if friendly(s,me,id) or not map:is_contestable(t) or s:has_fallout(t) or frontSeen[t] then return end
        if not s:borders_tile(me,t) then return end
        frontSeen[t]=true;summary.clearable_tiles+=1
        local g=self.fronts[id]
        if not g then g={id=id,tile=t,front=0,tiles={}};self.fronts[id]=g end
        g.front+=1
        if self:priority(map,t)>self:priority(map,g.tile) then g.tile=t end
        if #g.tiles<12 then table.insert(g.tiles,t) end
    end
    local function sample(t)
        if seen[t] or not map:is_contestable(t) or s:has_fallout(t) then return end
        seen[t]=true;local id=s:tile_owner(t)
        if id==me then summary.owned_samples+=1;neighbours(map,t,frontier)
        elseif id==0 then summary.neutral_samples+=1;frontier(t)
        elseif friendly(s,me,id) then summary.allied_samples+=1
        else
            summary.hostile_samples+=1;frontier(t)
            local distance=math.huge
            for _,a in ipairs(self.anchors) do distance=math.min(distance,math.sqrt(map.dist2(t,a.tile))*(map.k_lin or 1)) end
            hostiles[id]=math.min(hostiles[id] or math.huge,distance)
            summary.closest_hostile_distance=math.min(summary.closest_hostile_distance or math.huge,distance)
        end
    end
    for _,a in ipairs(self.anchors) do
        local radius=math.ceil(a.radius/(map.k_lin or 1));local stride=math.max(1,math.ceil(radius/32))
        local x,y=a.tile%map.W,a.tile//map.W
        for yy=math.max(0,y-radius),math.min(map.H-1,y+radius),stride do
            for xx=math.max(0,x-radius),math.min(map.W-1,x+radius),stride do
                if (xx-x)^2+(yy-y)^2<=radius^2 then sample(yy*map.W+xx) end
            end
        end
        -- Exact radial probes supplement a coarse grid on high-resolution maps,
        -- keeping narrow nearby frontiers visible without a whole-map scan.
        for _,d in ipairs({{1,0},{1,1},{0,1},{-1,1},{-1,0},{-1,-1},{0,-1},{1,-1}}) do
            for n=0,radius do
                local xx,yy=x+d[1]*n,y+d[2]*n
                if xx<0 or yy<0 or xx>=map.W or yy>=map.H then break end
                if (xx-x)^2+(yy-y)^2<=radius^2 then sample(yy*map.W+xx) end
            end
        end
    end
    local pressures={}
    for id,distance in pairs(hostiles) do
        local o=s.owners[id]
        if o and o.alive then
            local pressure=(o.troops or 0)*(o.kind==2 and .4 or o.kind==0 and .22 or .08)
            table.insert(pressures,pressure)
            if o.kind==2 and distance<=40 and (o.troops or 0)>(frame.info.troops or 0)*.5 then summary.at_risk=true end
        end
    end
    table.sort(pressures,function(a,b) return a>b end)
    summary.threat_pressure=(pressures[1] or 0)+(pressures[2] or 0)*.5
    for _,attack in pairs(s.attacks) do
        if attack.target==me and not attack.retreating then
            if valid(map,attack.anchor_tile) and self:isSite(map,attack.anchor_tile)
                or not valid(map,attack.anchor_tile) and hostiles[attack.attacker] then summary.incoming+=attack.troops or 0 end
        end
    end
    for _,u in pairs(s.units or {}) do
        if not friendly(s,me,u.owner) and (u.kind==0 or u.kind==2) then
            local path=u.path or {};local tile=u.patrol_tile
            if #path>0 then
                local index=math.clamp(math.floor(math.max(0,s.tick-(u.start_tick or s.tick))*100/math.max(1,u.ticks_per_tile_x100 or 100))+1,1,#path)
                tile=path[index]
            end
            if valid(map,tile) and self:isSite(map,tile) then
                if u.kind==0 then
                    summary.hostile_transports+=1;summary.naval_incoming+=math.max(0,u.troops or 0)
                else summary.hostile_warships+=1 end
            end
        end
    end
    summary.land_incoming=summary.incoming
    summary.incoming+=summary.naval_incoming
    local home=math.max(1,frame.info.troops or 0)
    summary.at_risk=summary.at_risk or summary.incoming>home*.08
        or summary.hostile_samples>0 and summary.threat_pressure>home*.4 or summary.hostile_warships>0
    summary.critical=summary.incoming>home*.2
    local total=summary.owned_samples+summary.neutral_samples+summary.hostile_samples+summary.allied_samples
    summary.owned_fraction=summary.owned_samples/math.max(1,total)
    summary.friendly_fraction=(summary.owned_samples+summary.allied_samples)/math.max(1,total)
    summary.secured=summary.hostile_samples==0 and summary.friendly_fraction>=.7
    summary.needs_buffer=summary.clearable_tiles>0 and summary.friendly_fraction<.55
    if changed then self.samples={} end
    self.samples=self.samples or {}
    for _,row in ipairs(self.samples) do
        if frame.now-row.at<15 and row.share-summary.owned_fraction>.15 then summary.critical=true;summary.at_risk=true end
    end
    if not self.lastSample or changed or frame.now-self.lastSample>=5 then
        self.lastSample=frame.now;table.insert(self.samples,{at=frame.now,share=summary.owned_fraction})
        if #self.samples>6 then table.remove(self.samples,1) end
    end
    self.summary=summary;return summary
end
function Core:buildScore(frame,tile,kind)
    local map=frame.map;local priority=self:priority(map,tile)
    if kind=='defense' or kind=='sam' then
        local radius=(kind=='defense' and 30 or 70)/(map.k_lin or 1);local score=0
        for _,a in ipairs(self.anchors) do
            if map.dist2(tile,a.tile)<=radius^2 then score+=a.kind=='economic' and 14 or 9 end
        end
        return score
    end
    if kind=='port' then return priority end
    return priority*2-(priority==0 and 12 or 0)
end
return Core
