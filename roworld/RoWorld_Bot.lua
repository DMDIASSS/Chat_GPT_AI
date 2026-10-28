-- RoWorld Bot 2.1.0 | paste this entire file into JJSploit.
-- No external script downloads or localhost bridge.

local Weapons = (function()

-- RoWorld weapon observations and conservative launch checks shared by both routes.
local Weapons={}
Weapons.kinds={atom=0,hydrogen=1,mirv=2}
Weapons.costs={atom=750000,hydrogen=5000000,mirv=25000000}
local function valid(s,t) return type(t)=="number" and t>=0 and t<s.map.N end
local function friendly(s,me,id) return id==me or id>0 and s:are_allies(me,id) end
local function protected(s,me,id) return friendly(s,me,id) or (s.bot_friend_guard or {})[id]==true end
function Weapons.cost(s,kind)
    local base=Weapons.costs[kind]
    return base and base+(kind=="mirv" and 15000000*(s.mirvs_launched or 0) or 0) or math.huge
end
function Weapons.ready(s,b,cooldown)
    if (b.active_tick or 0)>s.tick or type(b.shots)~="table" then return false end
    local busy=0
    for _,stamp in ipairs(b.shots) do if stamp+cooldown>s.tick then busy+=1 end end
    return busy<(b.level or 1)
end
function Weapons.launchers(s,me,tile)
    local selected,distance={},nil
    for _,b in pairs(s.structures) do
        if b.owner==me and b.kind==5 and Weapons.ready(s,b,90) then
            local d=math.abs(b.tile%s.map.W-tile%s.map.W)+math.abs(b.tile//s.map.W-tile//s.map.W)
            if not distance or d<distance then selected={b};distance=d
            elseif d==distance then table.insert(selected,b) end
        end
    end
    return selected
end
function Weapons.radius(map,kind)
    return (kind=="hydrogen" and 100 or kind=="mirv" and 1518 or 30)/(map.k_lin or 1)
end
function Weapons.blastSafe(s,me,tile,kind)
    if not valid(s,tile) or not Weapons.kinds[kind] then return false end
    local map=s.map;local radius=Weapons.radius(map,kind)
    -- MIRV's future warhead locations are random. Require the full spread plus
    -- warhead blast to be clear of friendlies, not only its center point.
    local x,y=tile%map.W,tile//map.W;local r=math.ceil(radius)
    for id,o in pairs(s.owners) do
        if protected(s,me,id) and valid(s,o.spawn_tile) and s:tile_owner(o.spawn_tile)==id
            and map.dist2(tile,o.spawn_tile)<=radius*radius then return false end
    end
    for yy=math.max(0,y-r),math.min(map.H-1,y+r) do
        for xx=math.max(0,x-r),math.min(map.W-1,x+r) do
            if (xx-x)^2+(yy-y)^2<=radius*radius and protected(s,me,s:tile_owner(yy*map.W+xx)) then return false end
        end
    end
    return true
end
-- The game uses a curved 96-segment trajectory. This constructs the same shape
-- for conservative coverage screening; it does not predict future player builds.
function Weapons.arc(map,from,to)
    local x,y=from%map.W+.5,from//map.W+.5
    local dx,dy=to%map.W+.5-x,to//map.W+.5-y
    local height=math.max(math.sqrt(dx*dx+dy*dy)/3,50/(map.k_lin or 1))
    local y1,y2=math.clamp(y+dy/4-height,0,map.H-1),math.clamp(y+dy*3/4-height,0,map.H-1)
    local points={}
    for i=0,96 do
        local t=i/96;local u=1-t
        local px=u^3*x+3*u*u*t*(x+dx/4)+3*u*t*t*(x+dx*3/4)+t^3*(x+dx)
        local py=u^3*y+3*u*u*t*y1+3*u*t*t*y2+t^3*(y+dy)
        table.insert(points,{x=px,y=py})
    end
    return points
end
function Weapons.blocked(s,me,from,to,kind)
    if kind=="mirv" then return false end -- carrier only; warheads remain interceptable
    local map=s.map;local k=map.k_lin or 1;local arc
    for _,b in pairs(s.structures) do
        if b.kind==4 and not friendly(s,me,b.owner) then
            -- Include construction and cooldown: it can finish/reload in flight.
            local reach=(150-480/(math.max(1,b.level or 1)+5))/k
            local near=300/k
            if map.dist2(b.tile,from)<=near*near or map.dist2(b.tile,to)<=near*near then
                arc=arc or Weapons.arc(map,from,to)
                -- Expand by a segment length: no gap between sampled points.
                for i,p in ipairs(arc) do
                    local q=arc[math.min(i+1,#arc)]
                    local padding=math.sqrt((q.x-p.x)^2+(q.y-p.y)^2)+2
                    local t=math.clamp(math.floor(p.y),0,map.H-1)*map.W+math.clamp(math.floor(p.x),0,map.W-1)
                    if (map.dist2(t,from)<=(150/k+padding)^2 or map.dist2(t,to)<=(150/k+padding)^2)
                        and map.dist2(b.tile,t)<=(reach+padding)^2 then return true end
                end
            end
        end
    end
    return false
end
function Weapons.canLaunch(s,me,tile,kind)
    if Weapons.kinds[kind]==nil or not valid(s,tile) then return false,"Unsupported weapon or target" end
    local id=s:tile_owner(tile)
    if id==0 or friendly(s,me,id) then return false,"Target is no longer hostile" end
    if s:has_request(me,id) then return false,"Our alliance proposal is still pending" end
    if s:has_fallout(tile) then return false,"Target is already a fallout zone" end
    if not Weapons.blastSafe(s,me,tile,kind) then return false,"Friendly territory is inside the possible strike area" end
    local launchers=Weapons.launchers(s,me,tile)
    if #launchers==0 then return false,"No missile silo is ready" end
    for _,b in ipairs(launchers) do
        if Weapons.blocked(s,me,b.tile,tile,kind) then return false,"Observed SAM coverage threatens the launch route" end
    end
    return true
end
function Weapons.covered(s,me,tile,minimum)
    local count=0
    for _,b in pairs(s.structures) do
        if b.kind==4 and friendly(s,me,b.owner) then
            local radius=(150-480/(math.max(1,b.level or 1)+5))/(s.map.k_lin or 1)
            if s.map.dist2(b.tile,tile)<=radius^2 then
                count+=1;if count>=(minimum or 1) then return true end
            end
        end
    end
    return false
end
function Weapons.hazard(s,tile,margin,imminentSeconds)
    local radii={[0]=30,[1]=100,[2]=1518,[3]=18,[4]=60,[5]=30,[6]=1.5,[7]=15,[8]=5}
    for _,n in pairs(s.nukes) do
        local radius=radii[n.kind]
        local remaining=(n.launch_tick or s.tick)+(n.flight_ticks or math.huge)-s.tick
        if radius and valid(s,n.to_tile) and (not imminentSeconds or remaining<=imminentSeconds*10) then
            if s.map.dist2(tile,n.to_tile)<=((radius+(margin or 0))/(s.map.k_lin or 1))^2 then return true end
        end
    end
    return false
end
function Weapons.threat(s,me)
    local r={hostile_silos=0,building_silos=0,ready_silos=0,hostile_sams=0,own_sams=0,own_sams_building=0,missiles_in_flight=0}
    for _,b in pairs(s.structures) do
        if not friendly(s,me,b.owner) then
            if b.kind==5 then
                r.hostile_silos+=1
                if (b.active_tick or 0)>s.tick then r.building_silos+=1
                elseif Weapons.ready(s,b,90) then r.ready_silos+=1 end
            elseif b.kind==4 then r.hostile_sams+=1 end
        elseif b.owner==me and b.kind==4 then
            r.own_sams+=1;if (b.active_tick or 0)>s.tick then r.own_sams_building+=1 end
        end
    end
    for _ in pairs(s.nukes) do r.missiles_in_flight+=1 end
    return r
end
function Weapons.allianceSafe(s,me,target)
    local proxy=setmetatable({are_allies=function(_,a,b) return b==target or s:are_allies(a,b) end},{__index=s})
    for _,n in pairs(s.nukes) do
        if n.owner==me then
            local kind=({[0]="atom",[1]="hydrogen",[2]="mirv",[3]="atom"})[n.kind]
            if kind and not Weapons.blastSafe(proxy,me,n.to_tile,kind) then return false end
        end
    end
    return true
end
return Weapons


end)()

local Cooperation = (function()

-- Team membership comes from the game. Friendship comes from Roblox's live roster.
local Cooperation={};Cooperation.__index=Cooperation
function Cooperation.new() return setmetatable({enabled=true,roster={},status={}},Cooperation) end
function Cooperation:setRoster(rows) self.roster=rows or {} end
function Cooperation:update(frame)
 local s=frame.state;local teams={};local count=0
 for _,o in pairs(s.owners) do if (o.team or 0)>0 and not teams[o.team] then teams[o.team]=true;count+=1 end end
 local names=s.team_names or {};local declared=#names
 self.teamMode=declared>0 or count>0;self.ownTeam=frame.info.team or 0
 local ownerNames={};for _,o in pairs(s.owners) do if o.kind==2 and o.alive then ownerNames[o.name]=(ownerNames[o.name] or 0)+1 end end
 local players={}
 for _,p in ipairs(self.roster) do
  local name=p.display_name
  if name and p.user_id and p.user_id>0 then
   if players[name]~=nil then players[name]=false else players[name]=p end
  end
 end
 self.friends={};local rows={}
 for id,o in pairs(s.owners) do
  local player=players[o.name]
  if id~=frame.me and o.alive and o.kind==2 and ownerNames[o.name]==1 and player and player.is_friend==true then
   local opposing=self.teamMode and self.ownTeam>0 and (o.team or 0)~=self.ownTeam
   if self.enabled and not opposing then self.friends[id]=true end
   table.insert(rows,{nation=id,user_id=player.user_id,opposing_team=opposing,help_enabled=self.enabled and not opposing,
    binding='unique live display-name match; nation ownership is not account-ID authenticated'})
  end
 end
 table.sort(rows,function(a,b) return a.nation<b.nation end)
 s.bot_friend_guard=self.friends
 self.status={mode=self.teamMode and 'teams' or 'free_for_all',team_count=math.max(declared,count),
  count_source=declared>0 and 'snapshot team names' or 'observed team IDs; may be incomplete',own_team=self.ownTeam,
  friends_enabled=self.enabled,friends=rows}
end
function Cooperation:isFriend(id) return self.enabled and (self.friends or {})[id]==true end
function Cooperation:aid(frame,a,ready)
 if not ready or a.incoming>0 or (a.available or 0)<a.home*.1 then return nil end
 local best,urgency,amount
 for id,o in pairs(frame.state.owners) do
  local teammate=self.ownTeam>0 and o.team==self.ownTeam
  if id~=frame.me and o.alive and (teammate or self:isFriend(id)) and frame.state:are_allies(frame.me,id) then
   local incoming=0
   for _,attack in pairs(frame.state.attacks) do if attack.target==id and not attack.retreating then incoming+=attack.troops or 0 end end
   local cap=math.max(1,o.max_troops or 0);local need=math.max(0,incoming*1.2-(o.troops or 0))
   if (o.troops or 0)<cap*.3 and a.home>(frame.info.max_troops or math.huge)*.6 then need=math.max(need,cap*.4-(o.troops or 0)) end
   local send=math.floor(math.min(need,a.home*.08,a.available*.5,math.max(0,cap-(o.troops or 0))))
   local score=incoming/math.max(1,o.troops or 0)+(self:isFriend(id) and .5 or 0)
   if send>=100 and (not urgency or score>urgency) then best,urgency,amount=id,score,send end
  end
 end
 if best then return {intent={type='donate',target=best,troops=amount},reserve=a.reserve,objective='defend',channel='support',cooldown=45,
  label='Sending limited troop support to '..frame.state:owner_name(best),plan={amount=amount,cooperative_support=true,support_urgency=urgency}} end
end
return Cooperation


end)()

local Core = (function()

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


end)()

local Atlas = (function()

-- Incremental topology of a frozen public ownership snapshot. Never authorizes orders.
local Atlas={};Atlas.__index=Atlas
local VALUE={[0]=8,[1]=7,[2]=8,[3]=2,[4]=4,[5]=6}
local function adjacent(m,t,fn)
 local x=t%m.W
 if x>0 then fn(t-1) end;if x<m.W-1 then fn(t+1) end
 if t>=m.W then fn(t-m.W) end;if t<m.N-m.W then fn(t+m.W) end
end
function Atlas.new() return setmetatable({summary={ready=false,components={},relations={}}},Atlas) end
function Atlas:update(frame,budget)
 if self.lastTick==frame.state.tick then return end
 self.lastTick=frame.state.tick
 local m,s=frame.map,frame.state
 budget=math.clamp(budget or 16384,1,65536)
 local w=self.work
 if not w then
  if self.finishedAt and frame.now-self.finishedAt<5 then return end
  if typeof(s.owner)~='buffer' or buffer.len(s.owner)~=m.N*4 then return end
  local owner=buffer.create(m.N*4);buffer.copy(owner,0,s.owner)
  w={owner=owner,labels=buffer.create(m.N*4),queue=buffer.create(m.N*4),scan=0,head=0,tail=0,
   components={},relations={},tick=s.tick,at=frame.now,me=frame.me,structures={}}
  for _,b in pairs(s.structures) do table.insert(w.structures,{owner=b.owner,kind=b.kind,tile=b.tile,level=b.level or 1}) end
  self.work=w
 end
 local function id(t) return buffer.readi32(w.owner,t*4) end
 local function edge(a,b)
  if a<=0 or b<=0 or a==b then return end
  w.relations[a]=w.relations[a] or {};w.relations[b]=w.relations[b] or {}
  w.relations[a][b]=(w.relations[a][b] or 0)+1;w.relations[b][a]=(w.relations[b][a] or 0)+1
 end
 for _=1,budget do
  if w.head<w.tail then
   local t=buffer.readu32(w.queue,w.head*4);w.head+=1
   local c=w.components[#w.components];c.land+=1
   adjacent(m,t,function(n)
    local other=id(n)
    if other==w.me then
     if buffer.readu32(w.labels,n*4)==0 then
      buffer.writeu32(w.labels,n*4,#w.components);buffer.writeu32(w.queue,w.tail*4,n);w.tail+=1
     end
    elseif m:is_contestable(n) then
     c.border+=1;c.neighbours[tostring(other)]=(c.neighbours[tostring(other)] or 0)+1
     if other==0 and #c.neutral_frontier<12 then table.insert(c.neutral_frontier,n) end
    elseif type(m.is_water)=='function' and m:is_water(n) or m.water and m.water[n] then c.coast+=1 end
   end)
  elseif w.scan<m.N then
   local t=w.scan;w.scan+=1;local other=id(t)
   if other>0 then
    if t%m.W<m.W-1 then edge(other,id(t+1)) end
    if t<m.N-m.W then edge(other,id(t+m.W)) end
   end
   if other==w.me and buffer.readu32(w.labels,t*4)==0 then
    table.insert(w.components,{id=#w.components+1,tile=t,land=0,asset_value=0,buildings=0,coast=0,border=0,neighbours={},neutral_frontier={}})
    buffer.writeu32(w.labels,t*4,#w.components);w.head=0;w.tail=1;buffer.writeu32(w.queue,0,t)
   end
  else
   local ownLand=0;for _,c in ipairs(w.components) do ownLand+=c.land end
   for _,b in ipairs(w.structures) do
    if b.owner==w.me and b.tile>=0 and b.tile<m.N then
     local c=w.components[buffer.readu32(w.labels,b.tile*4)]
     if c then c.buildings+=1;c.asset_value+=(VALUE[b.kind] or 1)*b.level end
    end
   end
   local main
   for _,c in ipairs(w.components) do
    c.share=c.land/math.max(1,ownLand)
    if not main or c.asset_value+c.land*.01>main.asset_value+main.land*.01 then main=c end
   end
   self.labels=w.labels;self.components=w.components;self.finishedAt=frame.now
   local rows=table.clone(w.components);table.sort(rows,function(a,b) return a.land>b.land end)
   while #rows>32 do table.remove(rows) end
   local relations={}
   for a,neighbors in pairs(w.relations) do
    local row={nation=a,neighbours={}}
    for b,length in pairs(neighbors) do table.insert(row.neighbours,{nation=b,edges=length}) end
    table.sort(row.neighbours,function(x,y) return x.edges>y.edges end)
    table.insert(relations,row)
   end
   table.sort(relations,function(a,b) return a.nation<b.nation end)
   self.summary={ready=true,snapshot_tick=w.tick,snapshot_at=w.at,completed_at=frame.now,own_land=ownLand,
    component_count=#w.components,components=rows,main_component=main and main.id,relations=relations,
    scope='Frozen public ownership; topology may be stale. Neutral frontier is sampled; component connectivity is exact for this snapshot.'}
   self.work=nil;return
  end
 end
end
function Atlas:component(frame,tile)
 if not self.labels or not tile or tile<0 or tile>=frame.map.N or frame.now-(self.summary.snapshot_at or 0)>30
  or frame.state:tile_owner(tile)~=frame.me then return nil end
 return self.components[buffer.readu32(self.labels,tile*4)]
end
function Atlas:siteRisk(frame,tile)
 local c=self:component(frame,tile);local exposure=0;local m=frame.map
 -- Short exact probes complement component boundaries; not an unseen attack forecast.
 local x,y=tile%m.W,tile//m.W;local radius=math.max(1,math.ceil(24/(m.k_lin or 1)))
 for _,d in ipairs({{1,0},{-1,0},{0,1},{0,-1},{1,1},{-1,-1},{1,-1},{-1,1}}) do
  for step=1,radius do
   local xx,yy=x+d[1]*step,y+d[2]*step
   if xx<0 or yy<0 or xx>=m.W or yy>=m.H then break end
   local id=frame.state:tile_owner(yy*m.W+xx)
   if id>0 and id~=frame.me and not frame.state:are_allies(frame.me,id) then exposure+=1-step/(radius+1);break end
  end
 end
 return math.clamp(exposure/4+(c and c.id~=self.summary.main_component and c.share<.15 and .25 or 0),0,1)
end
function Atlas:report(now)
 local row=table.clone(self.summary);row.age_seconds=row.snapshot_at and math.max(0,now-row.snapshot_at) or nil
 row.scanning=self.work~=nil;return row
end
return Atlas


end)()

local Profiles = (function()

-- Bounded evidence, not mind-reading. Cross-match names are weak identities.
local Profiles={};Profiles.__index=Profiles
local function number(v,limit) return type(v)=='number' and v==v and math.clamp(v,0,limit) or 0 end
local function key(o)
 if not o or o.kind~=2 or type(o.name)~='string' or #o.name==0 or #o.name>80 then return nil end
 return o.name
end
function Profiles.new(saved)
 local self=setmetatable({records={},session={},seen={},history={},clock=0},Profiles)
 if type(saved)=='table' and saved.version==1 and type(saved.records)=='table' then
  for i,r in ipairs(saved.records) do
   if i>128 then break end
   if type(r)=='table' and type(r.name)=='string' and #r.name>0 and #r.name<=80 then
    self.clock=math.max(self.clock,number(r.touch,1000000000))
    self.records[r.name]={name=r.name,betrayals=number(r.betrayals,100),attacks=number(r.attacks,100000),
     touch=number(r.touch,1000000000),attack_fraction=number(r.attack_fraction,1),naval=number(r.naval,100000),observations=number(r.observations,100000)}
   end
  end
 end
 return self
end
function Profiles:start(frame)
 if self.matchState==frame.state and self.me==frame.me then return end
 self.session={};self.seen={};self.units={};self.matchState=frame.state;self.me=frame.me;self.history={};self.lastTick=nil
end
function Profiles:record(o)
 local name=key(o);if not name then return nil end
 local r=self.records[name]
 if not r then
  local count=0;for _ in pairs(self.records) do count+=1 end
  if count>=128 then
   local oldest
   for name,row in pairs(self.records) do if not oldest or (row.touch or 0)<(self.records[oldest].touch or 0) then oldest=name end end
   if oldest then self.records[oldest]=nil end
  end
  r={name=name,betrayals=0,attacks=0,attack_fraction=0,naval=0,observations=0};self.records[name]=r
 end
 self.clock+=1;r.touch=self.clock
 return r
end
function Profiles:betrayed(frame,id)
 local r=self:record(frame.state.owners[id]);if r then r.betrayals+=1 end
 self.session[id]=self.session[id] or {};self.session[id].name=key(frame.state.owners[id]);self.session[id].betrayals=(self.session[id].betrayals or 0)+1
end
function Profiles:observe(frame)
 if self.matchState~=frame.state or self.me~=frame.me then self:start(frame) end
 local live={}
 for aid,a in pairs(frame.state.attacks) do
  live[aid]=true
  if a.attacker~=frame.me and not self.seen[aid] and not a.retreating then
   local o=frame.state.owners[a.attacker];local r=self:record(o)
   if r then
    local fraction=math.clamp((a.troops or 0)/math.max(1,(a.troops or 0)+(o.troops or 0)),0,1)
    r.attack_fraction=r.attacks==0 and fraction or r.attack_fraction*.8+fraction*.2;r.attacks+=1
    local m=self.session[a.attacker] or {attacks=0};m.attacks=(m.attacks or 0)+1
    m.name=key(o);m.against_us=(m.against_us or 0)+(a.target==frame.me and 1 or 0);self.session[a.attacker]=m
   end
  end
 end
 self.seen=live
 if not self.lastTick or frame.state.tick-self.lastTick>=100 then
  self.lastTick=frame.state.tick
  for id,o in pairs(frame.state.owners) do
   local r=id~=frame.me and o.alive and self:record(o)
   if r then r.observations+=1 end
  end
  local units={}
  for uid,u in pairs(frame.state.units or {}) do
   units[uid]=true
   if u.owner~=frame.me and u.kind==2 and not self.units[uid] then local r=self:record(frame.state.owners[u.owner]);if r then r.naval+=1 end end
  end
  self.units=units
 end
end
function Profiles:assessment(frame,id)
 local name=key(frame.state.owners[id]);local r=self.records[name];local m=self.session[id] or {}
 if m.name~=name then m={} end
 return {nation=id,identity='display name; cross-match identity uncertain',observed_attacks=r and r.attacks or 0,
  attack_fraction=r and r.attack_fraction or 0,naval_observations=r and r.naval or 0,
  betrayal_penalty=math.min(8,(m.betrayals or 0)*5+math.min(2,r and r.betrayals or 0)),
  confidence=r and math.min(1,r.attacks/10) or 0,against_us=m.against_us or 0}
end
function Profiles:export()
 local rows={};for _,r in pairs(self.records) do table.insert(rows,table.clone(r)) end
 table.sort(rows,function(a,b) return a.name<b.name end)
 return {version=1,scope='Local bounded observations, keyed by ambiguous display name; no automatic upload',records=rows}
end
function Profiles:report(frame)
 local rows={};for id,o in pairs(frame.state.owners) do if id~=frame.me and o.kind==2 then table.insert(rows,self:assessment(frame,id)) end end
 table.sort(rows,function(a,b) return a.nation<b.nation end);return rows
end
return Profiles


end)()

local Planner = (function()

-- Compare strategic alternatives; scores are transparent heuristics, not simulated futures.
local Planner={};Planner.__index=Planner
function Planner.new() return setmetatable({history={}},Planner) end
function Planner:update(frame,b,a,groups,atlas,profiles)
 local land=frame.info.tiles or 0
 if not self.checkpoint or land>self.checkpoint*1.03+10 then self.checkpoint=land;self.progressAt=frame.now end
 if land<(self.checkpoint or land)*.8 then self.checkpoint=land;self.progressAt=frame.now end
 local stalled=math.max(0,frame.now-(self.progressAt or frame.now))
 local core=b.core or {};local incoming=math.max(a.incoming or 0,core.incoming or 0)
 local acute=b.recover or core.critical or incoming>a.home*.15
 local opportunity=groups[0]~=nil
 for id,g in pairs(groups) do
  local o=frame.state.owners[id]
  if id>0 and o and (o.kind==1 or o.kind==0) and (o.troops or 0)<a.available*.4 then opportunity=true end
 end
 local rivalGrowth=0
 for _,row in ipairs(b.leaders or {}) do
  local o=frame.state.owners[row.nation]
  if o and not frame.state:are_allies(frame.me,row.nation) then
   local old=(self.leaders or {})[row.nation]
   if old and frame.now-old.at>=10 then rivalGrowth=math.max(rivalGrowth,(row.land-old.land)/math.max(1,old.land)) end
  end
 end
 if not self.leaderAt or frame.now-self.leaderAt>=30 then
  self.leaders={};for _,row in ipairs(b.leaders or {}) do self.leaders[row.nation]={land=row.land,at=frame.now} end
  self.leaderAt=frame.now
 end
 local waitingCost=math.min(10,stalled/15)+math.min(5,math.max(0,rivalGrowth)*10)
 b.permit_expansion=not acute and stalled>=30 and a.available>=a.home*.075 and (b.committed or 0)==0
 b.expansion_budget=b.permit_expansion and math.min(a.available,a.home*.12) or 0
 local rows={
  {kind='defend',score=acute and 30+incoming/math.max(1,a.home)*10 or core.at_risk and 7 or 1,reason=acute and 'Active invasion or recent losses' or 'Protect exposed core'},
  {kind='invest',score=7+(a.home/math.max(1,frame.info.max_troops or a.home)>.75 and 3 or 0),reason='Improve productive capacity and recruitment'},
  {kind='expand',score=(opportunity and 9 or 2)+waitingCost-(acute and 30 or 0),reason='Compare safe growth against the cost of waiting'},
  {kind='negotiate',score=(b.overextended and 12 or 4)+(core.at_risk and 2 or 0),reason='Reduce a visible strategic threat'},
  {kind='relocate',score=b.escape and 40 or 0,reason=b.relocation_reason or 'Preserve a viable replacement base'},
 }
 table.sort(rows,function(x,y) if x.score==y.score then return x.kind<y.kind end;return x.score>y.score end)
 local selected=rows[1]
 if self.selected and not acute and not b.escape then
  for _,row in ipairs(rows) do if row.kind==self.selected and row.score>=selected.score-1.5 then selected=row end end
 end
 if self.selected~=selected.kind then
  table.insert(self.history,{tick=frame.state.tick,objective=selected.kind,reason=selected.reason})
  if #self.history>32 then table.remove(self.history,1) end
 end
 self.selected=selected.kind
 self.report={objective=selected.kind,reason=selected.reason,alternatives=rows,stalled_seconds=stalled,
  waiting_cost=waitingCost,limited_expansion=b.permit_expansion,expansion_budget=b.expansion_budget,
  scope='Heuristic alternatives; all orders retain independent legality and reserve checks',history=self.history}
 b.planner=self.report
end
function Planner:choose(frame,actions)
 local ranked={};local best,bestScore
 for _,a in ipairs(actions) do
  local t=a.intent.type;local kind=a.objective or (t=='build' and 'invest' or t=='ally_request' and 'negotiate'
   or t=='ally_reply' and 'negotiate' or t=='ally_extend' and 'negotiate' or t=='move_warship' and 'defend' or 'expand')
  if a.escape then kind='relocate' end
  if t=='build' and (a.intent.kind=='sam' or a.intent.kind=='defense' or a.intent.kind=='warship') then kind='defend' end
  if t=='nuke' then kind='defend' end
  local score=0
  for _,row in ipairs(self.report and self.report.alternatives or {}) do if row.kind==kind then score=row.score end end
  if a.investment then score+=a.investment.score*.75 end
  if a.plan and a.plan.utility then score+=math.clamp(a.plan.utility,-5,10) end
  if t=='donate' then score+=5+math.min(18,((a.plan or {}).support_urgency or 0)*5) end
  if t=='ally_reply' then score+=25 elseif t=='ally_extend' then score+=8 end
  if a.objective=='expand' and a.intent.type=='attack' and frame.state:tile_owner(a.intent.tile)==0 then score+=2 end
  table.insert(ranked,{kind=kind,type=t,score=score,label=a.label})
  if not bestScore or score>bestScore then best,bestScore=a,score end
 end
 table.sort(ranked,function(a,b) return a.score>b.score end)
 if self.report then self.report.actions=ranked;self.report.chosen=best and best.label or 'No safe legal action available' end
 return best
end
return Planner


end)()

local Investment = (function()

-- Marginal benefit and exposure estimates. Production returns are proxies, not guaranteed cashflows.
local Investment={}
local function growth(h,cap) return math.max(0,(h^.73/4+10)*(1-h/math.max(1,cap))*10) end
function Investment.evaluate(policy,frame,kind,place,counts,levels)
 local cost=frame.ctx.rules:cost(kind);local info=frame.info;local cap=math.max(1,info.max_troops or 1)
 local risk=policy.riskCache and policy.riskCache[place.tile]
 if risk==nil then
  risk=policy.atlas and policy.atlas:siteRisk(frame,place.tile) or 0
  if policy.riskCache then policy.riskCache[place.tile]=risk end
 end
 local benefit,reason,proxy=0,'',nil
 if kind=='city' then
  local delta=growth(info.troops or 0,cap+250000)-growth(info.troops or 0,cap)
  benefit=4+math.min(12,delta/50)+((counts[0] or 0)==0 and 12 or 0)
  if (counts[2] or 0)==0 and (counts[0] or 0)>0 then benefit-=7 end
  reason='250K marginal capacity and growth at the current bank'
 elseif kind=='factory' then
  local link=policy:incomeLink(frame,place.tile,kind)
  benefit=link>0 and 15+math.min(6,link/5) or 2
  if (counts[2] or 0)==0 and (counts[0] or 0)>0 and link>0 then benefit+=10 end
  if (levels[0] or 0)>math.max(1,levels[2] or 0)*3 then benefit+=5 end
  proxy=link>0 and 2500 or nil;reason='Observed potential land-production link; actual routing is not guaranteed'
 elseif kind=='port' then
  local partners=0
  for _,b in pairs(frame.state.structures) do
   if b.kind==1 and b.owner~=frame.me and b.owner>0 and frame.state:are_allies(frame.me,b.owner)
    and type(frame.map.coast_body_of)=='function' and frame.map:coast_body_of(place.tile)>0
    and frame.map:coast_body_of(place.tile)==frame.map:coast_body_of(b.tile) then partners+=1 end
  end
  benefit=8+math.min(12,partners*3)+((counts[1] or 0)==0 and 8 or 0)
  proxy=partners>0 and 1000*math.min(4,partners) or nil;reason='Coastal access and visible allied trade partners'
 elseif kind=='sam' then benefit=35;reason='Coverage of exposed productive assets'
 elseif kind=='defense' then benefit=16;reason='Cover an observed threatened core'
 elseif kind=='silo' then benefit=5;reason='Future counterstrike option after production investment'
 end
 local priceFactor=125000/math.max(125000,cost)
 local score=benefit*priceFactor*(1-risk*.75)
 if kind=='sam' then score=40*(1-risk*.5) end
 if place.upgrade and kind=='city' then
  local level=1
  for _,b in pairs(frame.state.structures) do if b.owner==frame.me and b.kind==0 and b.tile==place.tile then level=b.level or 1 end end
  score/=1+(level-1)*.12
  reason..='; concentrated city levels increase asset-loss exposure'
 end
 return {kind=kind,cost=cost,score=score,risk=risk,upgrade=place.upgrade==true,
  estimated_payback_seconds=proxy and cost/proxy or nil,return_is_proxy=true,reason=reason}
end
return Investment


end)()

local Strategy = (function()

-- Strategic memory for the observed board; no hidden player inputs are assumed.
local Strategy={};Strategy.__index=Strategy


function Strategy.new(frame,profiles)
    local owners={};for sid,b in pairs(frame.state.structures) do owners[sid]=b.owner end
    local allies={};for id in pairs(frame.state.owners) do if frame.state:are_allies(frame.me,id) then allies[id]=true end end
    return setmetatable({campaigns={},campaignHistory={},peace={},structures=owners,timeline={},recoverUntil=0,board={},core=Core.new(),
        profiles=profiles or Profiles.new(),allies=allies,relationships={},distrust={},asked={},allianceSeq=frame.state.alliance_seq or 0},Strategy)
end
function Strategy:trustworthy(frame,id) return frame.now>=(self.distrust[id] or 0) end
function Strategy:canAsk(frame,id) return self:trustworthy(frame,id) and frame.now>=(self.asked[id] or 0) end
function Strategy:allianceEnded(frame,id,confirmed,reason)
    table.insert(self.relationships,{nation=id,tick=frame.state.tick,confirmed_betrayal=confirmed,reason=reason})
    if #self.relationships>32 then table.remove(self.relationships,1) end
    if confirmed then
        self.distrust[id]=frame.now+180;self.peace[id]=nil
        self.profiles:betrayed(frame,id)
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
        if not c.objective then
            local plan=action.plan or {};c.objective={kind=plan.objective_sid and 'capture_asset' or (s.owners[target] or {}).kind==1 and 'defeat_tribe' or 'secure_corridor',
                sid=plan.objective_sid,tile=action.intent.tile,status='active',started_tick=s.tick,
                initial_land=s.owners[me].tiles or 0,land_goal=math.max(100,math.floor((s.owners[me].tiles or 0)*.15))}
            c.budget=math.max((s.owners[me].troops or 0)*.35,(s.owners[me].troops or 0)*(action.intent.ratio or 0)*1.5);c.deadline=now+45
        end
        c.lastSent=now;c.sends+=1;c.spent+=(s.owners[me].troops or 0)*(action.intent.ratio or 0)
    elseif kind=='retreat' then
        local attack=s.attacks[action.intent.attack_id]
        if attack and attack.target>0 then
            local c=self.campaigns[attack.target]
            if c then c.pauseUntil=now+25;self:logCampaign(attack.target,c,action.label or "retreat") end
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
        if not enemy or not enemy.alive then self:logCampaign(id,c,"target no longer alive");self.campaigns[id]=nil
        else
            -- Another player taking enemy land is not evidence that our campaign works.
            local objective=c.objective
            if objective then
                local asset=objective.sid and s.structures[objective.sid]
                if asset and asset.owner==frame.me then
                    if not objective.captured_at then objective.captured_at=frame.now;c.lastProgress=frame.now end
                    local secure,total=0,0;local map=frame.map;local r=math.max(1,math.ceil(8/(map.k_lin or 1)))
                    for _,d in ipairs({{1,0},{-1,0},{0,1},{0,-1}}) do
                        local x,y=asset.tile%map.W+d[1]*r,asset.tile//map.W+d[2]*r
                        if x>=0 and y>=0 and x<map.W and y<map.H then
                            total+=1;if s:tile_owner(y*map.W+x)==frame.me then secure+=1 end
                        end
                    end
                    if secure>=math.max(1,total*.75) or frame.now-objective.captured_at>=8 then objective.status='complete' end
                end
                if objective.sid and (not asset or asset.owner~=frame.me and asset.owner~=id) then objective.status='lost' end
                if objective.tile and s:tile_owner(objective.tile)==frame.me and not c.foothold then
                    c.foothold=true;c.lastProgress=frame.now
                end
                if c.foothold and (frame.info.tiles or 0)>=(c.progressLand or objective.initial_land)+10 then
                    c.lastProgress=frame.now;c.progressLand=frame.info.tiles
                end
                if not objective.sid and objective.kind~='defeat_tribe' and c.foothold and (frame.info.tiles or 0)>=objective.initial_land+objective.land_goal then objective.status='complete' end
            end
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
    self.lastNow=frame.now
    self.adjacentAllies=allies or {}
    local s,home=frame.state,a.home
    local near={};for id in pairs(groups) do near[id]=true end
    for id,m in pairs(fronts or {}) do if frame.now-m.at<=8 then near[id]=true end end
    if self.atlas and self.atlas.summary.ready and frame.now-self.atlas.summary.snapshot_at<30 then
        for _,row in ipairs(self.atlas.summary.relations) do
            if row.nation==frame.me then for _,n in ipairs(row.neighbours) do near[n.nation]=true end end
        end
    end
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
                local estimate=self.profiles:assessment(frame,id)
                local weight=o.kind==2 and .5+estimate.confidence*math.max(0,estimate.attack_fraction-.5)*.3 or o.kind==0 and .28 or .1
                table.insert(pressures,bank*weight)
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
    -- A few neutral frontier samples do not make a destroyed economic core viable.
    -- Require sustained failure to recover rather than waiting for zero clearable tiles.
    local land=frame.info.tiles or 0
    if not self.recoveryHigh or land>self.recoveryHigh then self.recoveryHigh=land;self.lastRecoveryProgress=frame.now end
    if not self.recoveryCheckpoint or land<self.recoveryCheckpoint*.8 then self.recoveryCheckpoint=land end
    if land>=self.recoveryCheckpoint*1.1+20 then
        self.recoveryCheckpoint=land;self.lastRecoveryProgress=frame.now
    end
    local ruined=(core.owned_fraction or 1)<.15 and (core.protected_building_count or 0)==0
        and land<math.max(500,self.recoveryHigh*.1)
        and frame.now-(self.lastRecoveryProgress or frame.now)>=20
    local stranded=core.center_tile and ((core.clearable_tiles or 0)==0 and (core.friendly_fraction or 1)<.15 or ruined)
        and a.incoming==0 and (core.naval_incoming or 0)==0 and b.committed==0
    if stranded then self.strandedSince=self.strandedSince or frame.now else self.strandedSince=nil end
    b.escape=self.strandedSince~=nil and frame.now-self.strandedSince>=20
    b.relocation_reason=b.escape and (ruined and 'Economic core lost; local recovery has stalled' or 'No usable local expansion') or nil
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
    if not o or friendly(s,frame.me,id) or self.cooperation and self.cooperation:isFriend(id) then return false end
    if frame.now<(self.peace[id] or 0) or s:has_request(frame.me,id) then return false end
    if a.incoming>a.home*.2 then return false end
    if (self.core.summary.at_risk or self.core.summary.needs_buffer) and not self.core.fronts[id]
        and not (b.permit_expansion and o.kind~=2) then return false end
    if b.recover or b.overextended and o.kind~=1 then return false end
    local c=self.campaigns[id]
    if c and frame.now-(c.lastSent or c.started)>45 and not (a.targets or {})[id] then
        self.campaigns[id]=nil;c=nil
    end
    if c then
        if c.objective and c.objective.status~='active' then return false end
        if c.budget and c.spent>=c.budget or c.deadline and frame.now>c.deadline then return false end
        if frame.now<(c.pauseUntil or 0) then return false end
        if frame.now-(c.lastSent or -math.huge)<(o.kind==2 and 7 or o.kind==0 and 4.5 or 3) then return false end
        if c.sends>=3 and frame.now-c.lastProgress>8 then return false end
        if o.kind==2 and c.spent>a.home*.35 then return false end
    end
    if o.kind==2 and a.incoming>a.home*.1 then return false end
    return true
end
function Strategy:nuclearTarget(frame,id)
    if self.cooperation and self.cooperation:isFriend(id) then return false end
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
            if c and c.objective and c.objective.status=='complete' then why='Campaign objective secured; banking the gain'
            elseif c and c.objective and c.objective.status=='lost' then why='Campaign asset is gone; reassessing'
            elseif c and (c.budget and c.spent>=c.budget or c.deadline and frame.now>c.deadline) then why='Campaign budget or time limit reached'
            elseif (core.at_risk or core.needs_buffer) and away and not self.board.permit_expansion then
                why='Recalling a distant raid to protect the home and economic center'
            elseif self.cooperation and self.cooperation:isFriend(attack.target) then why='Recalling troops from a Roblox friend'
            elseif friendly(frame.state,frame.me,attack.target) then why='Recalling troops after an alliance changed'
            elseif self.board.recover or a.incoming>a.home*.5 then why='Recalling the largest raid to defend the whole territory'
            elseif c and c.captures>0 and o.kind==0 and ((self.board.human_neighbours or 0)>0
                or self.board.mode=='guard' or c.sends>=3 or frame.now-c.lastProgress>6) then
                why='Secured a country building; banking the gain and reassessing'
            elseif c and c.sends>=3 and frame.now-c.lastProgress>10 then why='Ending a stalled campaign; reassessing other fronts'
            elseif c and o.kind==2 and c.spent>a.home*.35 and frame.now-c.started>7 then why='Limiting exposure against a human player'
            end
            if why and (not priority or (attack.troops or 0)>priority) then best,priority,reason=attack,attack.troops or 0,why end
        elseif (self.board.recover or (self.core.summary.at_risk or self.core.summary.needs_buffer) and away and not self.board.permit_expansion)
            and (not priority or (attack.troops or 0)>priority) then
            best,priority,reason=attack,attack.troops or 0,'Recalling distant expansion to secure home and core buildings'
        end
    end
    if best then return {intent={type='retreat',attack_id=best.aid},channel='retreat',
        cooldown=(self.core.summary.critical or a.incoming>a.home*.5) and .6 or 3,label=reason} end
end
function Strategy:logCampaign(id,c,reason)
 table.insert(self.campaignHistory,{nation=id,objective=c.objective and table.clone(c.objective),spent=c.spent,budget=c.budget,
  sends=c.sends,captures=c.captures,reason=reason})
 if #self.campaignHistory>32 then table.remove(self.campaignHistory,1) end
end
function Strategy:campaignReport()
 local rows={}
 for id,c in pairs(self.campaigns) do
  table.insert(rows,{nation=id,objective=c.objective,budget=c.budget,spent=c.spent,sends=c.sends,captures=c.captures,
   last_progress=c.lastProgress,deadline=c.deadline,pause_until=c.pauseUntil})
 end
 table.sort(rows,function(a,b) return (a.last_progress or 0)>(b.last_progress or 0) end)
 while #rows>32 do table.remove(rows) end
 return rows
end
return Strategy


end)()

local Diplomacy = (function()

-- Benefits and risks are estimates from visible state, not promises of loyalty.
local Diplomacy={}

local function pose(s,u)
 local p=u.path or {};if #p==0 then return u.patrol_tile end
 local i=math.clamp(math.floor(math.max(0,s.tick-(u.start_tick or s.tick))*100/math.max(1,u.ticks_per_tile_x100 or 100))+1,1,#p)
 return p[i]
end
function Diplomacy.evaluate(policy,frame,id,a,groups,mode)
 local s=frame.state;local o=s.owners[id];local reasons={}
 local function veto(reason) return {nation=id,mode=mode,score=-100,eligible=false,reasons={reason}} end
 if not o or not o.alive or id==frame.me then return veto('not a live foreign nation') end
 if (o.traitor_until or 0)>s.tick then return veto('currently marked traitor') end
 if policy.strategy and not policy.strategy:trustworthy(frame,id) then return veto('recent confirmed betrayal or unresolved distrust') end
 if (a.targets or {})[id] then return veto('our land campaign is still active') end
 if not Weapons.allianceSafe(s,frame.me,id) then return veto('our in-flight weapons endanger this alliance') end
 local near=groups[id]~=nil or (policy.adjacentAllies or {})[id]==true
 local home=math.max(1,a.home or frame.info.troops or 1)
 local ratio=(o.troops or 0)/home
 local memory=policy.opponents[id] or {};local heat=memory.heat or 0
 local kind=o.kind==nil and 2 or o.kind
 local score=kind==2 and 4 or kind==0 and .5 or -3
 local function add(value,reason) score+=value;table.insert(reasons,reason) end
 table.insert(reasons,kind==2 and 'human partnership preferred' or kind==0 and 'country partnership needs concrete benefits' or 'tribe has limited strategic value')
 if policy.cooperation and policy.cooperation:isFriend(id) then add(12,'Roblox friend matched in live roster; cooperation enabled') end
 if near then add(2,'shared frontier can be stabilized') end
 add(math.min(3,math.log(1+ratio)*2),'relative army strength')
 if s:are_allies(frame.me,id) then add(1,'existing relationship') end
 local profile=policy.profiles and policy.profiles:assessment(frame,id)
 if profile and profile.betrayal_penalty>0 then add(-profile.betrayal_penalty,'persistent observed betrayal history; display-name identity uncertain across matches') end
 if heat>.2 then add(-math.min(6,heat*3),'recent observed aggression') end
 local enemies={};local shared=false;local direct=false
 for _,attack in pairs(s.attacks) do
  if not attack.retreating then
   if attack.target==frame.me and attack.attacker~=id then enemies[attack.attacker]=true end
   if attack.attacker==frame.me and attack.target>0 then enemies[attack.target]=true end
   if attack.attacker==id and attack.target==frame.me then direct=true end
  end
 end
 for _,attack in pairs(s.attacks) do
  if attack.attacker==id and enemies[attack.target] and not attack.retreating then shared=true end
 end
 if shared then add(4,'actively opposing a shared threat') end
 for enemy in pairs(enemies) do if s:are_allies(id,enemy) then add(-3,'also allied with a current enemy');break end end
 if direct then
  add(-6,'currently attacking us')
  if ratio>1.5 and (a.incoming or 0)>home*.2 then add(4,'peace could relieve an overwhelming attack') end
  if (a.incoming or 0)>home*.8 then add(12,'last-resort peace under an overwhelming invasion') end
 end
 if kind==0 and near and ratio<.6 then add(-5,'weak neighbouring country is an expansion opportunity') end
 local early=s.playing_since and s.playing_since>=0 and s.tick-s.playing_since<1200
 if kind==0 and early and heat<.1 and not direct then add(-2,'early country grace may reduce immediate alliance value; retaliation remains possible') end
 if kind==0 and near and ratio>3 and not (direct and (a.incoming or 0)>home*.8) then
  return veto('dominant bordering country could later betray and absorb us')
 end
 if near and (memory.landTrend or 0)>math.max(5,(o.tiles or 0)*.003) and ratio>1.5 then add(-4,'rapid observed expansion raises future domination risk') end
 local fleet=0
 for _,u in pairs(s.units or {}) do
  if u.owner==id and u.kind==2 then
   local t=pose(s,u)
   if t and t>=0 and t<frame.map.N and policy.strategy and policy.strategy.core:isSite(frame.map,t) then fleet+=1 end
  end
 end
 if fleet>0 then
  add(2,'alliance could reduce immediate naval pressure')
  if ratio>1.5 or fleet>1 then add(-4,'concentrated warships near our core create coercion risk') end
 end
 local ports={};for _,b in pairs(s.structures) do if b.kind==1 and b.owner==frame.me then table.insert(ports,b) end end
 local trade=false
 for _,b in pairs(s.structures) do
  if b.kind==1 and b.owner==id then for _,ours in ipairs(ports) do
   if type(frame.map.coast_body_of)=='function' then
    local body=frame.map:coast_body_of(ours.tile)
    if body>0 and body==frame.map:coast_body_of(b.tile) then trade=true end
   end
  end end
 end
 if trade then add(2,'ports share a water body; potential trade relationship') end
 if not near and not shared and not trade then add(-1,'limited visible local relevance') end
 local threshold=mode=='offer' and 7 or mode=='renew' and 4.5 or 4
 return {nation=id,mode=mode,score=score,eligible=score>=threshold,reasons=reasons,
  threshold=threshold,army_ratio=ratio,nearby_warships=fleet,shared_enemy=shared,potential_trade=trade}
end
return Diplomacy


end)()

local Recorder = (function()

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


end)()

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

function Policy.new(profiles)
    return setmetatable({cooperation=Cooperation.new(),profiles=profiles or Profiles.new(),state = nil, me = nil, cooldowns = {}, seed = 739391,
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
    if kind=='build' and action.intent.kind=='defense' then
        self.defenseBuilds=self.defenseBuilds or {};table.insert(self.defenseBuilds,now)
    end
    if self.strategy then self.strategy:sent(action,self.state,self.me,now) end
    if action.escape and self.strategy then self.strategy.core.relocation={tile=action.intent.tile,untilTime=now+300} end
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
    self.lastTick=nil;self.lastPlan=nil;self.history={};self.siteCache={};self.spatialTick=nil;self.defenseBuilds={}
    self.spawnPlan=nil
    self.profiles:start(frame)
    self.atlas=Atlas.new();self.planner=Planner.new()
    self.strategy=Strategy.new(frame,self.profiles)
    self.strategy.atlas=self.atlas
    self.strategy.cooperation=self.cooperation
    self.recorder=Recorder.new(frame)
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
    if self.strategy and self.strategy.board.permit_expansion and not self.strategy.core.fronts[g.id] then
        ceiling=math.min(ceiling,math.floor(a.home*.12))
    end
    if enemy.kind==2 then ceiling=math.min(ceiling,math.floor(a.home*.15)) end
    local campaign=self.strategy and self.strategy.campaigns[g.id]
    if campaign and campaign.budget then ceiling=math.min(ceiling,math.floor(math.max(0,campaign.budget-campaign.spent))) end
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
                m.landTrend=((info.tiles or 0)-(m.tiles or 0))/dt
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
    self.profiles:observe(frame)
    if self.recorder then self.recorder:observe(frame) end
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

function Policy:spawn(frame,reconsider)
    if not self:ready("spawn", frame.now) then return nil, "Waiting for spawn confirmation" end
    if reconsider then self.cooldowns.spawn=frame.now+.5 end
    local s, map, best, bestScore = frame.state, frame.map, nil, -math.huge
    for _ = 1, 160 do
        local tile = self:landSample(map, "land_list")
        if valid(map, tile) and map:is_contestable(tile) and s:tile_owner(tile) == 0 and not s:has_fallout(tile) then
            local score,detail = self:spawnScore(frame,tile)
            if score > bestScore then best, bestScore = tile, score;self.spawnPlan=detail end
        end
    end
    if reconsider and best then
        local current,currentDetail=self:spawnScore(frame,frame.info.spawn_tile)
        if bestScore<current+15 or frame.map.dist2(best,frame.info.spawn_tile)<(30/(frame.map.k_lin or 1))^2 then
            self.spawnPlan=currentDetail
            return nil,'Current spawn remains suitable; watching new player marks'
        end
    end
    if best then return {intent = {type = "spawn", tile = best}, channel = "spawn", cooldown = 2,
        label = "Choosing a starting territory"} end
    return nil, "Searching for unclaimed spawn land"
end

function Policy:fronts(frame)
    local s, map, me = frame.state, frame.map, frame.me
    local border = frame.ctx.borders.border
    if self.border ~= border then self.border, self.cursor = border, nil end
    if self.cursor ~= nil and border[self.cursor] == nil then self.cursor = nil end
    local groups, sites, seen = {}, {}, {}
    self.siteCache={};self.linkCache={};self.riskCache={};self.adjacentAllies={}
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
    if self.strategy then
        -- Give the home area its own local scan so distant coastline cannot
        -- consume the entire rotating frontier budget.
        for id,nearby in pairs(self.strategy.core.fronts) do
            local samples=table.clone(nearby.tiles);table.insert(samples,1,nearby.tile)
            for _,t in ipairs(samples) do
                if s:tile_owner(t)==id and s:borders_tile(me,t) and not s:has_fallout(t) and not Weapons.hazard(s,t,0,3) then
                    local g=groups[id]
                    if not g then g={id=id,tile=t,front=0,tiles={},seen={}};groups[id]=g end
                    if not g.seen[t] then
                        g.seen[t]=true;g.front+=1;table.insert(g.tiles,1,t)
                        if #g.tiles>12 then table.remove(g.tiles) end
                    end
                    if self.strategy:corePriority(frame,t)>self.strategy:corePriority(frame,g.tile) then g.tile=t end
                end
            end
        end
    end
    if self.atlas and self.atlas.summary.ready and frame.now-self.atlas.summary.snapshot_at<30 then
        for _,c in ipairs(self.atlas.summary.components) do
            site(c.tile,true)
            for _,t in ipairs(c.neutral_frontier) do
                if s:tile_owner(t)==0 and s:borders_tile(me,t) and not s:has_fallout(t) and not Weapons.hazard(s,t,0,3) then
                    local g=groups[0]
                    if not g then g={id=0,tile=t,front=0,tiles={},seen={}};groups[0]=g end
                    if not g.seen[t] then g.seen[t]=true;g.front+=1;if #g.tiles<12 then table.insert(g.tiles,t) end end
                end
            end
        end
    end
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
    local s=frame.state;self.diplomacyScores={}
    local function evaluate(id,mode)
        local result=Diplomacy.evaluate(self,frame,id,a,groups,mode)
        table.insert(self.diplomacyScores,result)
        table.sort(self.diplomacyScores,function(x,y) return x.score>y.score end)
        if #self.diplomacyScores>20 then table.remove(self.diplomacyScores) end
        return result
    end
    for id,o in pairs(s.owners) do
        if id~=frame.me and o.alive and s:has_request(id,frame.me) then
            local r=evaluate(id,'accept')
            return {intent={type='ally_reply',target=id,accept=r.eligible},plan={diplomacy=r},
                channel='diplomacy',cooldown=5,label=(r.eligible and 'Accepting useful alliance with ' or 'Declining low-value or risky alliance with ')..o.name}
        end
    end
    if type(s.alliance_info)=='function' then
        for id,o in pairs(s.owners) do
            local info=id~=frame.me and s:alliance_info(frame.me,id)
            if info and info.can_extend then
                local r=evaluate(id,'renew')
                if r.eligible then return {intent={type='ally_extend',target=id},plan={diplomacy=r},
                    channel='diplomacy',cooldown=8,label='Renewing a useful alliance with '..o.name} end
            end
        end
    end
    for id,o in pairs(s.owners) do
        local sameTeam=(frame.info.team or 0)>0 and frame.info.team==o.team
        if id~=frame.me and o.alive and friendly(s,frame.me,id) and not sameTeam and not self.cooperation:isFriend(id) and (o.traitor_until or 0)>s.tick
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

    local best
    for id,o in pairs(s.owners) do
        if id~=frame.me and o.alive and not s:are_allies(frame.me,id) and not s:has_request(frame.me,id)
            and (not self.strategy or self.strategy:canAsk(frame,id)) then
            local r=evaluate(id,'offer')
            if r.eligible and (not best or r.score>best.score) then best=r end
        end
    end
    if best then return {intent={type='ally_request',target=best.nation},plan={diplomacy=best},
        channel='diplomacy',cooldown=35,label='Offering a beneficial alliance to '..s:owner_name(best.nation)} end
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

function Policy:incomeLink(frame,tile,kind)
    if kind~='factory' and kind~='city' then return 0 end
    local cacheKey=kind..':'..tile
    if self.linkCache and self.linkCache[cacheKey]~=nil then return self.linkCache[cacheKey] end
    local s,map=frame.state,frame.map;local best=0
    for _,b in pairs(s.structures) do
        local partner=kind=='factory' and (b.kind==0 or b.kind==1) or kind=='city' and b.kind==2
        local distance=math.sqrt(map.dist2(tile,b.tile))*(map.k_lin or 1)
        if partner and b.owner==frame.me and distance>=15 and distance<=90 then
            local dx,dy=b.tile%map.W-tile%map.W,b.tile//map.W-tile//map.W
            local steps=math.max(math.abs(dx),math.abs(dy));local clear=true
            for i=0,steps do
                local t=math.floor(tile//map.W+dy*i/math.max(1,steps)+.5)*map.W+math.floor(tile%map.W+dx*i/math.max(1,steps)+.5)
                local owner=s:tile_owner(t)
                if not map:is_contestable(t) or s:has_fallout(t) or owner~=frame.me and not s:are_allies(frame.me,owner) then clear=false;break end
            end
            if clear then best=math.max(best,30-distance*.1) end
        end
    end
    if self.linkCache then self.linkCache[cacheKey]=best end
    return best
end
function Policy:build(frame, sites, kind, counts)
    if not self:ready("build", frame.now) then return nil end
    -- Apply the limit here too: emergency decisions call build directly.
    if kind=="defense" then
        local posts=0
        for _,b in pairs(frame.state.structures) do if b.owner==frame.me and b.kind==3 then posts+=1 end end
        local recent={}
        for _,at in ipairs(self.defenseBuilds or {}) do if frame.now-at<60 then table.insert(recent,at) end end
        self.defenseBuilds=recent
        if posts>=3 or #recent>=3 then return nil end
    end
    local rules = frame.ctx.rules
    local availability = rules:availability(kind)
    if not availability.ok then return nil end
    local levels={}
    for _,b in pairs(frame.state.structures) do if b.owner==frame.me then levels[b.kind]=(levels[b.kind] or 0)+(b.level or 1) end end
    local best, bestScore,bestInvestment
    for i = 1, math.min(320, #sites) do
        local place = rules:placement(kind, sites[i])
        if place.ok and valid(frame.map, place.tile) and self:siteSafe(frame,place.tile,kind) then
            local investment=Investment.evaluate(self,frame,kind,place,counts or {},levels)
            local score = (place.upgrade and -10 or 10)+investment.score*3
            score+=self:incomeLink(frame,place.tile,kind)
            if self.strategy then score+=self.strategy.core:buildScore(frame,place.tile,kind) end
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
                            and not Weapons.covered(frame.state,frame.me,b.tile,self.desiredSAMCoverage) then
                            local weight=b.kind==5 and 8 or 3
                            if self.strategy and self.strategy.core:isSite(frame.map,b.tile) then weight*=2 end
                            protected+=weight
                        end
                    end
                    if protected==0 then score=-math.huge else score+=protected*30 end
                end
            end
            if bestScore == nil or score > bestScore then best, bestScore,bestInvestment = place, score,investment end
        end
    end
    if best and bestScore>-math.huge then
        return {investment=bestInvestment,intent = {type = "build", kind = kind, tile = best.tile}, channel = "build", cooldown = 6,
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
    local levels={};for _,b in pairs(frame.state.structures) do if b.owner==frame.me then levels[b.kind]=(levels[b.kind] or 0)+(b.level or 1) end end
    local cityLevels=levels[0] or 0
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
    -- Do not continually buy cheaper upgrades while an uncovered productive core
    -- is saving for air defense. Imminent land defense is handled separately above.
    local saveSAM=exposed and nuclearThreat.ready_silos>0 and city+factory>=3 and factory>0 and (counts[4] or 0)<6
        and not (self.strategy and self.strategy.board.recover) and armies.incoming<armies.home*.15
    -- Protect the first city budget instead of spending every 50K on posts.
    if city==0 then table.insert(wanted,"city") end
    local coreRisk=self.strategy and self.strategy.core.summary.at_risk
    if (armies.incoming > armies.home * (city==0 and .6 or .2) or city>0 and coreRisk)
        and (counts[3] or 0) < 3 then table.insert(wanted, "defense") end
    if city > 0 and factory == 0 then table.insert(wanted, "factory") end
    if city > 0 and port == 0 then table.insert(wanted, "port") end
    if armies.home >= (frame.info.max_troops or math.huge) * .75 then table.insert(wanted, "city") end
    if factory < math.min(12,math.max(1, math.ceil(cityLevels / 3))) then table.insert(wanted, "factory") end
    if factory>0 and factory<math.min(12,math.max(1,math.ceil(cityLevels/3))) then table.insert(wanted,'factory') end
    if city>1 and port>0 and port<math.min(12,math.ceil(cityLevels/4)) then table.insert(wanted,'port') end
    if city >= 1 and factory > 0 and (frame.info.gold or 0)>=1750000 then
        if (counts[5] or 0) == 0 then table.insert(wanted,"silo") end
    end
    if (frame.info.gold or 0) > frame.ctx.rules:cost("city") * 2 then table.insert(wanted, "city") end
    self.economyPlan={reported_income=frame.info.income or 0,cities=city,factories=factory,ports=port,
        reserve=factory==0 and frame.ctx.rules:cost('factory') or port==0 and type(frame.ctx.borders.has_coast)=='function'
            and frame.ctx.borders:has_coast() and frame.ctx.rules:cost('port') or 0}
    self.economyPlan.trade_ships=0;self.economyPlan.cargo_units=0
    for _,u in pairs(frame.state.units or {}) do
        if u.owner==frame.me and u.kind==1 then self.economyPlan.trade_ships+=1 end
        if u.owner==frame.me and u.kind==3 then self.economyPlan.cargo_units+=1 end
    end
    if saveSAM then
        self.economyPlan.reserve=frame.ctx.rules:cost('sam')
        self.economyPlan.saving_for='sam'
    end
    local candidates,seen,best={},{},nil
    for _, kind in ipairs(wanted) do
        if seen[kind] then continue end;seen[kind]=true
        if saveSAM and kind~='sam' then continue end
        local action = self:build(frame, sites, kind, counts)
        if action then
            table.insert(candidates,action.investment)
            if not best or action.investment.score>best.investment.score then best=action end
        end
    end
    table.sort(candidates,function(a,b) return a.score>b.score end)
    self.economyPlan.candidates=candidates
    if best then self.economyPlan.next_kind=best.intent.kind;return best end
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
    local threat,threatScore,patrol,patrolScore
    for _,port in ipairs(ports) do
        local corePriority=self.strategy and self.strategy:corePriority(frame,port.tile) or 0
        neighbours(map,port.tile,function(t)
            if map:is_water(t) and (not patrolScore or corePriority>patrolScore) then patrol=t;patrolScore=corePriority end
        end)
        for _,u in pairs(s.units or {}) do
            local t=unitTile(s,u)
            if u.owner>0 and not friendly(s,frame.me,u.owner) and (u.kind==0 or u.kind==2)
                and valid(map,t) and map:is_water(t) then
                local distance=math.sqrt(map.dist2(t,port.tile))*(map.k_lin or 1)
                local value=(u.kind==0 and 180 or 130)-distance
                if value>0 then value+=corePriority*12 end
                if value>0 and (not threatScore or value>threatScore) then threat,threatScore=t,value end
            end
        end
    end
    local target=threat or patrol
    if not target then return nil end
    table.sort(ships,function(a,b)
        local ta,tb=unitTile(s,a),unitTile(s,b)
        return (valid(map,ta) and map.dist2(ta,target) or math.huge)<(valid(map,tb) and map.dist2(tb,target) or math.huge)
    end)
    local wanted=threat and math.min(3,#ports+1) or 1
    local economicReserve=self.economyPlan and self.economyPlan.reserve or 0
    if self.strategy and (self.strategy.core.summary.hostile_transports or 0)>0 then economicReserve=0 end
    if #ships<wanted and frame.ctx.rules:availability("warship").ok
        and (frame.info.gold or 0)>=frame.ctx.rules:cost('warship')+economicReserve
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

-- Score only observed destination safety. This is not a prediction of intent.
function Policy:landingScore(frame,tile,armies,escape)
    local score=0
    local radius=120/(frame.map.k_lin or 1)
    for id,o in pairs(frame.state.owners) do
        if id~=frame.me and o.alive and o.kind==2 and not friendly(frame.state,frame.me,id) then
            local center=o.label_tile or o.spawn_tile
            if valid(frame.map,center) then
                local d=math.sqrt(frame.map.dist2(tile,center))
                if d<radius then
                    local danger=(1-d/radius)*math.min(4,(o.troops or 0)/math.max(1,armies.home))
                    score-=danger*30
                    if escape and danger>.6 then return nil end
                end
            end
        end
    end
    -- Favor room to expand, instead of a one-tile beach beside a larger player.
    for _,delta in ipairs({-4,4,-4*frame.map.W,4*frame.map.W,-8,8,-8*frame.map.W,8*frame.map.W}) do
        local t=tile+delta
        if valid(frame.map,t) and frame.map.dist2(tile,t)<=64 and frame.map:is_contestable(t)
            and frame.state:tile_owner(t)==0 and not frame.state:has_fallout(t) then score+=2 end
    end
    return score
end

function Policy:naval(frame, armies,survival)
    local escape=survival or self.strategy and self.strategy.board.escape
    local limited=self.strategy and self.strategy.board.permit_expansion
    if escape and frame.ctx.rules:transports()>0 then return nil end
    if self.strategy and (self.strategy.board.mode~="develop" and not escape and not limited or (armies.enemyActive or 0)>0) then return nil end
    if self.strategy then
        local core=self.strategy.core.summary
        if core.at_risk and not escape and not limited then return nil end
    end
    if survival then armies=table.clone(armies);armies.reserve=armies.home*.9;armies.available=armies.home*.1 end
    if armies.incoming > 0 and not survival or not self:ready("boat", frame.now) or armies.available < armies.home * ((escape or limited) and .05 or .12) then return nil end
    -- One expedition at a time; do not fan out three unprotected beachheads.
    if frame.ctx.rules:transports() > 0 then return nil end
    local chosen, score
    for _ = 1, 120 do
        local tile = self:landSample(frame.map, "coast_list")
        if valid(frame.map, tile) and frame.map:is_coastal(tile) and not frame.state:has_fallout(tile) then
            local target = frame.state:tile_owner(tile)
            local owner = frame.state.owners[target]
            local weak = target == 0 or (owner and owner.alive and (owner.troops or 0) < armies.available * .2)
            if escape then weak=target==0 end
            if owner and owner.kind==2 and not escape then
                local pressure=self:opportunity(frame,target)
                local asset=false
                for _,b in pairs(frame.state.structures) do
                    if b.owner==target and frame.map.dist2(tile,b.tile)<(35/(frame.map.k_lin or 1))^2 then asset=true;break end
                end
                -- A weak bank alone is not a profitable distant human invasion.
                weak=weak and pressure>=.6 and asset and armies.home>(owner.troops or 0)*3
            end
            if self.strategy and not escape and self.strategy.core.summary.needs_buffer and self.strategy:corePriority(frame,tile)==0 and not limited then weak=false end
            if target>0 and self.strategy and not self.strategy:canTarget(frame,target,armies) then weak=false end
            if limited and owner and owner.kind==2 then weak=false end
            if target>0 and (armies.enemyActive or 0)>0 and not (armies.targets or {})[target] then weak=false end
            if self.cooperation:isFriend(target) then weak=false end
            if weak and not friendly(frame.state, frame.me, target) and frame.ctx.borders:can_reach_by_sea(tile) then
                local destination=self:landingScore(frame,tile,armies,escape)
                local value = (target == 0 and 10 or 20)+(destination or 0)
                local safe=destination~=nil
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
        if escape and amount then amount=math.min(amount,math.floor(armies.home*.1)) end
        if limited and amount then amount=math.min(amount,math.floor(armies.home*.12)) end
        if amount and amount<math.max(100,math.ceil(armies.home*.01)) then amount=nil end
        if amount then return {intent = {type = "boat", tile = chosen, ratio = amount/armies.home},escape=escape,survival=survival,
            reserve = reserve, objective="expand",plan={amount=amount,objective_tile=chosen},channel = "boat", cooldown = escape and 30 or 12,
            label = escape and "Establishing a small neutral foothold outside a trapped core" or "Sending a coastal landing"} end
    end
    return nil
end

function Policy:decide(frame)
    if self.state ~= frame.state or self.me ~= frame.me then self:reset(frame) end
    self.cooperation:update(frame)
    self:observe(frame)
    if not frame.info.alive then return nil, "Eliminated - waiting for the next match" end
    if not frame.info.spawned then return self:spawn(frame) end
    if frame.state.phase == 0 then return self:spawn(frame,true) end
    if frame.state.phase ~= 1 then return nil, "Match finished" end
    if not self.spatialTick or frame.state.tick-self.spatialTick>=2 then
        self.strategy:updateCore(frame);self.spatialTick=frame.state.tick
    end
    self.atlas:update(frame)
    local groups, sites = self:fronts(frame)
    local a = self:armies(frame, groups)
    local board=self.strategy:updateBoard(frame,groups,a,self.frontsSeen,self.adjacentAllies)
    self.planner:update(frame,board,a,groups,self.atlas,self.profiles)
    if self:ready("retreat",frame.now) then
        local reassess=self.strategy:review(frame,a)
        if reassess then return reassess end
    end
    if a.incoming > a.home * .75 and self:ready("retreat", frame.now) then
        for _, attack in ipairs(a.outgoing) do
            return {intent = {type = "retreat", attack_id = attack.aid}, channel = "retreat", cooldown = .6,
                label = "Recalling troops to defend"}
        end
    end
    if a.incoming>a.home*.5 then
        board.emergency=true
        local peace=self:diplomacy(frame,groups,a)
        if peace then return peace end
        local counter=self:strike(frame)
        if counter then return counter end
        if a.incoming>a.home*1.25 then
            local escape=self:naval(frame,a,true)
            if escape then return escape end
        end
        local defensive=self:build(frame,sites,'defense',{})
        if defensive then return defensive end
        board.emergency_reason='Defending; no affordable safe missile, peace order or escape is available'
        return nil,board.emergency_reason
    end
    -- Economy / defensive construction has its own cooldown and never drains
    -- the troop reserve. Observed structures (including construction) are used.
    local actions={}
    local function offer(action) if action then table.insert(actions,action) end end
    offer(self:economy(frame, sites, a))
    local diplomatic=self:diplomacy(frame,groups,a)
    offer(diplomatic)
    if not board.recover and (board.core.incoming or 0)==0 then offer(self.cooperation:aid(frame,a,self:ready("support",frame.now))) end
    local fleet=self:fleet(frame,a)
    offer(fleet)
    local strike=self:strike(frame)
    offer(strike)
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
                    plan.utility=value
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
    if best then best.objective='expand';offer(best) end
    if board.recover or a.incoming > a.home*.25 then
        return self.planner:choose(frame,actions),"Defending - holding reserves and reassessing the whole board"
    end
    if neutral and self:ready("attack", frame.now) and a.available > 200 and a.enemyActive == 0 then
        local surplus=math.max(0,a.home-self:growthTarget(frame.info))
        if a.neutralActive == 0 or surplus>a.home*.08 and (a.targets[0] or 0)<surplus*.5 then
            local amount,reserve=self:attackAmount(frame,a,0,true)
            if amount then offer({objective="expand",intent = {type = "attack", tile = neutral.tile, ratio = amount / a.home},
                reserve = reserve,plan={amount=amount,growth_target=self:growthTarget(frame.info),utility=5+math.min(2,math.log(1+neutral.front))+self.strategy:corePriority(frame,neutral.tile)},
                channel = "attack", cooldown = 2.5,
                label = self.strategy:corePriority(frame,neutral.tile)>0 and "Clearing a territory buffer around home and core buildings"
                    or "Expanding with a recruitment-aware troop budget"}) end
        end
    end
    local boat = self:naval(frame, a)
    offer(boat)
    local chosen=self.planner:choose(frame,actions)
    if chosen then return chosen end
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
    return {version="2.1.0",cooperation=self.cooperation.status,
        atlas=self.atlas and self.atlas:report(self.strategy and self.strategy.lastNow or 0) or {},
        planner=self.planner and self.planner.report or {},
        campaigns=self.strategy and self.strategy:campaignReport() or {},
        campaign_history=self.strategy and self.strategy.campaignHistory or {},
        opponent_profiles=self.state and self.profiles:report({state=self.state,me=self.me}) or {},
        opponent_observations=self.recorder and self.recorder:report() or {},
        runtime=self.runtime or {},last_waiting=self.lastWaiting,scope="Since the current observer snapshot; intent estimates are heuristic",
        diplomacy_candidates=self.diplomacyScores or {},
        nominal_runtime={poll_hz=10,core_scan_max_hz=5,order_max_hz=5},
        alliance_history=self.strategy and self.strategy.relationships or {},income=info and info.income or 0,
        economy=self.economyPlan or {},
        strategy=self.strategy and self.strategy.board or {},timeline=self.strategy and self.strategy.timeline or {},
        recruitment_target=info and self:growthTarget(info) or 0,spawn_plan=self.spawnPlan,
        tick=self.state and self.state.tick or 0,alive=info and info.alive or false,
        land=info and info.tiles or 0,troops=info and info.troops or 0,metrics=self.metrics,
        gold=info and info.gold or 0,allies=allies,traitors=traitors,navy=navy,recent_orders=self.history or {},
        nuclear_threat=self.state and Weapons.threat(self.state,self.me) or {},fallout_tiles=self.state and self.state.fallout_count or 0,
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
    local caps, lines = self.capabilities, {"RoWorld Bot 2.1.0 - client access diagnostics"}
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
    if live.now - self.lastSent < .2 then return false, "Waiting for the next order slot" end
    local s, me, rules = live.state, live.me, live.ctx.rules
    local intent = table.clone(action.intent)
    local kind = intent.type
    if not live.info.alive or s.phase == 2 then return false, "Match finished or nation eliminated" end
    if kind == "spawn" then
        if live.info.spawned and s.phase~=0 or not tileValid(live, intent.tile) or not live.map:is_contestable(intent.tile)
            or s:tile_owner(intent.tile) ~= 0 or s:has_fallout(intent.tile) then return false, "Spawn point changed" end
    else
        if not live.info.spawned or s.phase ~= 1 then return false, "Waiting for the playing phase" end
        if kind == "attack" or kind == "boat" then
            if not tileValid(live, intent.tile) or not live.map:is_contestable(intent.tile) or s:has_fallout(intent.tile) then
                return false, "Target is no longer claimable"
            end
            local target = s:tile_owner(intent.tile)
            if target == me or (target > 0 and (s:are_allies(me, target) or (s.bot_friend_guard or {})[target])) then return false, "Target is now friendly" end
            if target>0 and s:has_request(me,target) then return false,"Waiting for our alliance proposal before attacking" end
            if kind == "attack" and not s:borders_tile(me, intent.tile) then return false, "Target no longer borders your land" end
            if kind == "boat" and (not live.map:is_coastal(intent.tile) or not live.ctx.borders:can_reach_by_sea(intent.tile)
                or rules:transports() >= (s.rules.MAX_BOATS_PLAYER or 3)) then return false, "Sea route unavailable" end
            local troops = math.max(0, live.info.troops or 0)
            local incoming = 0
            for _, attack in pairs(s.attacks) do
                if attack.target == me and not attack.retreating then incoming += attack.troops or 0 end
            end
            local reserve = math.max(action.reserve or 0, troops * .35, incoming * 1.5)
            if action.survival then
                if kind~='boat' or target~=0 or incoming<=troops*1.25 or rules:transports()>0 then
                    return false,'Survival expedition conditions changed'
                end
                reserve=troops*.9
            end
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
                if Weapons.hazard(s,intent.tile,action.safety.margin) then return false,"Incoming strike threatens the construction site" end
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
                local allowed,reason=Weapons.canLaunch(s,me,intent.tile,intent.kind)
                if not allowed then return false,reason end
            end
        elseif kind=='donate' then
            local owner=s.owners[intent.target]
            if not owner or not owner.alive or intent.target==me or not s:are_allies(me,intent.target) then return false,'Support partner is no longer allied' end
            local incoming=0
            for _,a in pairs(s.attacks) do if a.target==me and not a.retreating then incoming+=a.troops or 0 end end
            local home=math.max(0,live.info.troops or 0)
            local reserve=math.max(action.reserve or 0,home*.65,incoming*1.5)
            if incoming>0 or type(intent.troops)~='number' or intent.troops~=intent.troops or intent.troops==math.huge then return false,'Holding support during an invasion or invalid budget' end
            intent.troops=math.floor(math.min(intent.troops,home*.08,math.max(0,home-reserve),math.max(0,(owner.max_troops or 0)-(owner.troops or 0))))
            if intent.troops<100 then return false,'No safe troop support budget' end
        elseif kind == "retreat" then
            local attack = s.attacks[intent.attack_id]
            if not attack or attack.attacker ~= me or attack.retreating then return false, "Attack already ended" end
        elseif kind=='ally_extend' then
            local info=type(s.alliance_info)=='function' and s:alliance_info(me,intent.target)
            if not info or not info.can_extend then return false,'Alliance renewal window changed or already requested' end
            if not Weapons.allianceSafe(s,me,intent.target) then return false,'Our strike endangers this alliance' end
            if (s.owners[intent.target].traitor_until or 0)>s.tick then return false,'Alliance partner is marked traitor' end
        elseif kind == "ally_reply" then
            if not s:has_request(intent.target, me) then return false, "Alliance request expired" end
            if intent.accept and not Weapons.allianceSafe(s,me,intent.target) then return false,"Our in-flight strike endangers this alliance" end
            local owner=s.owners[intent.target]
            if intent.accept and (not owner or not owner.alive or (owner.traitor_until or 0)>s.tick) then
                return false,"Alliance partner is no longer reliable"
            end
        elseif kind=="ally_request" or kind=="ally_break" then
            local owner=s.owners[intent.target]
            if not owner or not owner.alive or intent.target==me then return false,"Diplomacy target changed" end
            if kind=="ally_request" and (s:are_allies(me,intent.target) or s:has_request(me,intent.target)
                or (owner.traitor_until or 0)>s.tick) then return false,"Alliance request is no longer needed" end
            if kind=="ally_request" and not Weapons.allianceSafe(s,me,intent.target) then return false,"Our in-flight strike endangers this alliance" end
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
    local types={spawn=1,attack=2,boat=3,build=4,nuke=5,retreat=6,move_warship=7,ally_request=8,ally_reply=9,ally_break=10,donate=11,ally_extend=12}
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
function State:has_alliance(a,b) return self.alliances[key(a,b)]==true end
function State:alliance_info(a,b)
    if not self:has_alliance(a,b) then return nil end
    local k=key(a,b);local expires=self.alliance_expires[k] or -1;local flags=self.alliance_ext[k] or 0
    local mine=a<b and 1 or 2;local window=expires>=self.tick and expires<=self.tick+300
    local meAsked=bit32.band(flags,mine)~=0
    return {expires_at=expires,ticks_left=math.max(0,expires-self.tick),in_window=window,
        me_asked=meAsked,other_asked=bit32.band(flags,3-mine)~=0,
        can_extend=window and not meAsked and self.owners[a] and self.owners[a].alive and self.owners[b] and self.owners[b].alive or false}
end
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
        level=row[offset+5] or 1,active_tick=row[offset+6] or 0,shots=row[offset+7] or {}}
    s.structures[b.sid]=b;return b
end
local function nuke(s,row,offset)
    offset=offset or 0
    local n={uid=row[offset+1],kind=row[offset+2],owner=row[offset+3],from_tile=row[offset+4],
        to_tile=row[offset+5],launch_tick=row[offset+6],flight_ticks=row[offset+7]}
    s.nukes[n.uid]=n;return n
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
        alliances={},alliance_expires={},alliance_ext={},playing_since=data.playing_since or -1,
        requests={},built={},border={},alliance_events={},alliance_seq=0,fallout_count=0,mirvs_launched=data.mirvs_launched or 0,
        team_names=type(data.teams)=="table" and table.clone(data.teams) or {},local_owner=me,tick=data.t or 0,phase=data.phase or 0,loaded=false,
        rules={STRUCT_MIN_DIST=15/map.k_lin,MAX_BOATS_PLAYER=10}},State)
    for _,row in ipairs(data.owners or {}) do s.owners[row[1]]=owner(row) end
    for _,row in ipairs(data.structs or {}) do structure(s,row) end
    for _,row in ipairs(data.attacks or {}) do attack(s,row) end
    for _,row in ipairs(data.units or {}) do unit(s,row) end
    for _,row in ipairs(data.nukes or {}) do nuke(s,row) end
    for _,row in ipairs(data.allies or {}) do
        local k=key(row[1],row[2]);s.alliances[k]=true;s.alliance_expires[k]=row[3];s.alliance_ext[k]=row[4] or 0
    end
    for _,row in ipairs(data.requests or {}) do s.requests[row[1]*1024+row[2]]=row[3] or s.tick end
    for _,row in ipairs(data.built or {}) do
        s.built[row[1]]={};for i=0,15 do s.built[row[1]][i]=row[i+2] or 0 end
    end
    for t=0,map.N-1 do
        if s:has_fallout(t) then s.fallout_count+=1 end
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
        local tile=entry//256;assert(tile>=0 and tile<s.map.N)
        local before=s:has_fallout(tile);buffer.writeu8(s.flags,tile,entry%256)
        if before~=s:has_fallout(tile) then s.fallout_count+=before and -1 or 1 end
    end
    for i=1,#(d.stats or {}),6 do
        local row=d.stats;local info=s.owners[row[i]]
        if info then info.troops=row[i+2];info.gold=row[i+3];info.max_troops=row[i+4];info.income=row[i+5] end
    end
    for _,e in ipairs(d.ev or {}) do
        local kind,id=e[1],e[2]
        if kind==0 then s.owners[id]={id=id,name=tostring(e[3]),kind=e[5],team=e[6] or 0,alive=true,spawned=false,spawn_tile=-1,label_tile=-1,tiles=0,troops=0,gold=0,max_troops=0}
        elseif kind==1 and s.owners[id] then s.owners[id].alive=false
        elseif kind==2 then s.phase=id;if id==1 and s.playing_since<0 then s.playing_since=s.tick end
        elseif kind==3 and s.owners[id] then local info=s.owners[id];info.spawned=true;info.spawn_tile=e[3];info.label_tile=e[3]
        elseif kind==4 then local b=structure(s,e,1);built(s,b.owner,b.kind)
        elseif kind==5 and s.structures[id] then s.structures[id].owner=e[3]
        elseif kind==6 then s.structures[id]=nil
        elseif kind==9 then local u=unit(s,e,1);if u.kind==2 then built(s,u.owner,15) end
        elseif kind==10 and s.units[id] then s.units[id].path={e[3]};s.units[id].start_tick=s.tick
        elseif kind==11 then s.units[id]=nil
        elseif kind==12 then local n=nuke(s,e,1);if n.kind==2 then s.mirvs_launched+=1 end
        elseif kind==13 then s.nukes[id]=nil
        elseif kind==14 then attack(s,e,1)
        elseif kind==15 then s.attacks[id]=nil
        elseif kind==16 then s.requests[id*1024+e[3]]=e[4] or s.tick
        elseif kind==17 then
            local k=key(id,e[3]);s.alliances[k]=true;s.alliance_expires[k]=e[4] or s.tick+3000;s.alliance_ext[k]=0
            s.requests[id*1024+e[3]]=nil;s.requests[e[3]*1024+id]=nil
        elseif kind==18 then
            s.alliances[key(id,e[3])]=nil;s.alliance_seq+=1
            s.alliance_expires[key(id,e[3])]=nil;s.alliance_ext[key(id,e[3])]=nil
            table.insert(s.alliance_events,{seq=s.alliance_seq,a=id,b=e[3],breaker=e[4] or 0,expired=e[5]==true,tick=s.tick})
            if #s.alliance_events>64 then table.remove(s.alliance_events,1) end
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
        elseif kind==29 and s.nukes[e[3]] then s.nukes[e[3]].sam_sid=id
        elseif kind==30 and s:has_alliance(id,e[3]) then
            local k=key(id,e[3]);s.alliance_expires[k]=e[4];s.alliance_ext[k]=e[5] or 0
        elseif kind==32 and s.structures[id] then s.structures[id].shots=e[3]
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
        if Weapons.kinds[kind]~=nil then return Weapons.cost(s,kind) end
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
        local supported=KINDS[kind]~=nil or kind=="warship" or Weapons.kinds[kind]~=nil
        local info=ctx.state.owners[ctx.state.local_owner]
        local launcher=Weapons.kinds[kind]==nil or #Weapons.launchers(ctx.state,ctx.state.local_owner,0)>0
        local port=kind~="warship"
        if not port then for _,b in pairs(ctx.state.structures) do
            if b.owner==ctx.state.local_owner and b.kind==1 and b.active_tick<=ctx.state.tick then port=true;break end
        end end
        return {ok=supported and info.alive and info.spawned and ctx.state.phase==1 and info.gold>=self:cost(kind)
            and launcher and port and (kind~="port" or borders:has_coast()),cost=self:cost(kind)}
    end
    function rules:placement(kind,tile)
        local s,id,map=ctx.state,ctx.state.local_owner,ctx.state.map
        local result={ok=false,tile=tile}
        if Weapons.kinds[kind]~=nil then
            if not self:availability(kind).ok or tile<0 or tile>=map.N then return result end
            local target=s:tile_owner(tile)
            result.ok=target>0 and target~=id and not s:are_allies(id,target)
            return result
        end
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
panel.Size = UDim2.fromOffset(410, 318)
panel.Position = UDim2.new(1, -426, 0, 60)
panel.BackgroundColor3 = Color3.fromRGB(20, 29, 42)
panel.BorderSizePixel = 0
panel.Parent = gui
local corner = Instance.new("UICorner")
corner.CornerRadius = UDim.new(0, 10)
corner.Parent = panel
local title = Instance.new("TextLabel")
title.Name = "Title"
title.Size = UDim2.new(1, -24, 0, 22)
title.Position = UDim2.fromOffset(12, 8)
title.BackgroundTransparency = 1
title.Font = Enum.Font.GothamBold
title.TextSize = 14
title.TextColor3 = Color3.fromRGB(221, 231, 242)
title.Text = "RoWorld 2.1.0 | live strategy"
title.TextXAlignment = Enum.TextXAlignment.Left
title.Parent = panel
local button = Instance.new("TextButton")
button.Name = "Toggle"
button.Size = UDim2.new(1, -24, 0, 40)
button.Position = UDim2.fromOffset(12, 36)
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
status.Position = UDim2.fromOffset(12, 82)
status.BackgroundTransparency = 1
status.Font = Enum.Font.Gotham
status.TextSize = 13
status.TextColor3 = Color3.fromRGB(221, 231, 242)
status.TextWrapped = true
status.TextXAlignment = Enum.TextXAlignment.Left
status.Parent = panel

local stats = Instance.new("TextLabel")
stats.Name = "Stats"
stats.Size = UDim2.new(1, -24, 0, 88)
stats.Position = UDim2.fromOffset(12, 136)
stats.BackgroundTransparency = 1
stats.Font = Enum.Font.Gotham
stats.TextSize = 12
stats.TextColor3 = Color3.fromRGB(176, 206, 225)
stats.TextWrapped = true
stats.TextXAlignment = Enum.TextXAlignment.Left
stats.Text = "Waiting for observed match statistics"
stats.Parent = panel
local export = Instance.new("TextButton")
export.Name = "ExportReport"
export.Size = UDim2.new(1, -24, 0, 32)
export.Position = UDim2.fromOffset(12, 234)
export.Font = Enum.Font.GothamBold
export.TextSize = 13
export.TextColor3 = Color3.fromRGB(255, 255, 255)
export.BackgroundColor3 = Color3.fromRGB(48, 76, 102)
export.BorderSizePixel = 0
export.Text = "Save match report"
export.Parent = panel
local exportCorner = corner:Clone();exportCorner.Parent = export

local friendsButton=Instance.new("TextButton")
friendsButton.Name="FriendsToggle"
friendsButton.Size=UDim2.new(1,-24,0,30)
friendsButton.Position=UDim2.fromOffset(12,274)
friendsButton.Font=Enum.Font.GothamBold
friendsButton.TextSize=13
friendsButton.TextColor3=Color3.fromRGB(255,255,255)
friendsButton.BackgroundColor3=Color3.fromRGB(48,76,102)
friendsButton.BorderSizePixel=0
friendsButton.Parent=panel
local friendsCorner=corner:Clone();friendsCorner.Parent=friendsButton
api.helpFriends=not previous or previous.helpFriends~=false
local function paintFriends() friendsButton.Text="Help Roblox friends: "..(api.helpFriends and "ON" or "OFF") end
paintFriends()
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
local savedProfiles
local profileSource="new memory"
if previous and type(previous.profiles)=='function' then
    local ok,data=pcall(previous.profiles);if ok then savedProfiles=data;profileSource="previous instance memory" end
end
if not savedProfiles and type(readfile)=='function' then
    local ok,data=pcall(function()
        local text=readfile('RoWorld_Opponent_Profiles.json')
        if #text>262144 then return nil end
        return game:GetService('HttpService'):JSONDecode(text)
    end)
    if ok then savedProfiles=data;if data then profileSource="local JSON" end end
end
local profiles=Profiles.new(savedProfiles)
function api.profiles() return profiles:export() end
local policy = Policy.new(profiles)
local roster,friendCache={},{}
local friendLookup={status="waiting for Roblox roster"}
local function refreshRoster()
    if type(Services.Players.GetPlayers)~='function' then friendLookup.status='Roblox roster API unavailable';return end
    local ok,players=pcall(function() return Services.Players:GetPlayers() end)
    if not ok then friendLookup.status='Roblox roster lookup failed';return end
    friendLookup.status='live roster checked'
    local rows={}
    for _,player in ipairs(players) do
        if not api.alive then return end
        if player~=Services.Players.LocalPlayer then
            local uid=player.UserId
            if type(uid)~='number' or uid<=0 then continue end
            local cached=friendCache[uid]
            if not cached or os.clock()-cached.at>=60 then
                local success,value=pcall(function() return Services.Players.LocalPlayer:IsFriendsWithAsync(uid) end)
                if not success then success,value=pcall(function() return Services.Players.LocalPlayer:IsFriendsWith(uid) end) end
                cached={at=os.clock(),friend=success and value==true};friendCache[uid]=cached
                if not success then friendLookup.status='Friendship API failed; unverified players receive no friend priority' end
            end
            table.insert(rows,{user_id=uid,display_name=player.DisplayName~='' and player.DisplayName or player.Name,is_friend=cached.friend})
        end
    end
    roster=rows
end
-- Friendship lookup may yield; keep it outside the decision loop and adapter identity.
task.spawn(function()
    while api.alive do refreshRoster();task.wait(15) end
end)
table.insert(api.connections,friendsButton.Activated:Connect(function()
    api.helpFriends=not api.helpFriends;policy.cooperation.enabled=api.helpFriends
    if policy.state then policy.cooperation:update({state=policy.state,me=policy.me,info=policy.state.owners[policy.me]}) end
    paintFriends()
end))
local runtime={decisions=0,skipped=0,blocked_orders=0,last_decision_ms=0,mean_decision_ms=0,profile_source=profileSource,profile_storage=type(writefile)=="function" and "local JSON and memory" or "memory only"}
local function updateStats()
    local info=policy.state and policy.state.owners[policy.me]
    if not info then return end
    local b=policy.strategy and policy.strategy.board or {}
    local eco=policy.economyPlan or {}
    stats.Text=string.format("%s | Tick %d | Land %d | Troops %.0f / %.0f\nGold %.0f | Income %.0f | Incoming %.0f\n%s | Decision %.1f ms | Blocked %d\n%s",
        info.alive and (b.mode or 'observing') or 'eliminated',policy.state.tick or 0,info.tiles or 0,info.troops or 0,info.max_troops or 0,
        info.gold or 0,info.income or 0,b.incoming or 0,
        b.planner and ('Plan: '..b.planner.objective) or 'Observing strategy',runtime.last_decision_ms,runtime.blocked_orders,
        (policy.cooperation.status.mode=='teams' and ('Teams: '..policy.cooperation.status.team_count..' | Your team: '..policy.cooperation.status.own_team) or 'Free for all')..' | Friends matched: '..#(policy.cooperation.status.friends or {}))
end
local lastReport=-math.huge
local endReported=false
local reportState
local reportTag
function api.report() return policy:report() end
local function saveMatchReport(force,reason)
    if type(writefile)~="function" then return false,"Executor file writing unavailable" end
    if not policy.state then return false,"No match observed yet" end
    if not force and os.clock()-lastReport<30 then return false end
    local profileSaved,profileError=pcall(function()
        writefile('RoWorld_Opponent_Profiles.json',game:GetService('HttpService'):JSONEncode(profiles:export()))
    end)
    runtime.profile_write_error=not profileSaved and tostring(profileError) or nil
    lastReport=os.clock()
    local ok,encoded=pcall(function()
        local report=policy:report();report.saved_reason=reason
        return game:GetService("HttpService"):JSONEncode(report)
    end)
    if not ok then return false,tostring(encoded) end
    local saved,err=pcall(writefile,"RoWorld_Match_Report.json",encoded)
    if saved and force then
        reportTag=reportTag or (tostring(os.time()).."_"..tostring(math.floor(os.clock()*1000)))
        local archived,archiveError=pcall(writefile,"RoWorld_Match_Report_"..reportTag..".json",encoded)
        if not archived then return false,"Latest report saved; archive failed: "..tostring(archiveError) end
    end
    return saved,saved and "Saved RoWorld_Match_Report.json in executor workspace" or tostring(err)
end
table.insert(api.connections,export.Activated:Connect(function()
    local _,message=saveMatchReport(true,"manual export")
    repaint(message)
end))
local lastCommand, lastCommandAt = "", -math.huge
local evaluatedState,evaluatedTick,evaluatedAt
local function toggle()
    api.enabled = not api.enabled
    if api.enabled then
        policy = Policy.new(profiles)
        runtime={decisions=0,skipped=0,blocked_orders=0,last_decision_ms=0,mean_decision_ms=0,profile_source=profileSource,profile_storage=type(writefile)=="function" and "local JSON and memory" or "memory only"}
        evaluatedState,evaluatedTick,evaluatedAt=nil,nil,nil
        endReported=false;reportTag=nil
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
    saveMatchReport(true,"script replaced or closed")
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
                if evaluatedState==frame.state and evaluatedTick==frame.state.tick and frame.now-(evaluatedAt or 0)<.5 then
                    runtime.skipped+=1
                    return policy.lastWaiting or 'Watching for a fresh game update'
                end
                evaluatedState,evaluatedTick,evaluatedAt=frame.state,frame.state.tick,frame.now
                -- The normal client sends a rate-limited activity heartbeat
                -- from user input. Keep that same heartbeat while autoplay is on.
                if type(frame.session.note_activity) == "function" then frame.session:note_activity() end
                local started=os.clock()
                policy.cooperation.enabled=api.helpFriends
                policy.cooperation:setRoster(roster)
                local action, waiting = policy:decide(frame)
                local ms=(os.clock()-started)*1000
                runtime.decisions+=1;runtime.last_decision_ms=ms
                runtime.mean_decision_ms+=(ms-runtime.mean_decision_ms)/runtime.decisions
                runtime.friend_lookup=friendLookup
                policy.runtime=runtime
                policy.lastWaiting=action and action.label or waiting
                if not api.enabled or not api.alive then return end
                if action then
                    local sent, blocked = adapter:send(action, frame)
                    if sent then
                        policy:sent(action, frame.now)
                        lastCommand, lastCommandAt = action.label, os.clock()
                        return "Order sent: " .. action.label
                    else
                        runtime.blocked_orders+=1;runtime.last_blocked_reason=tostring(blocked)
                        policy.lastWaiting=blocked
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
                updateStats()
                if policy.state~=reportState then
                    reportState=policy.state;endReported=false;lastReport=-math.huge;reportTag=nil
                end
                local info=policy.state and policy.state.owners[policy.me]
                local ended=info and (not info.alive or policy.state.phase==2 or adapter.network.closed)
                saveMatchReport(ended and not endReported,ended and "match ended" or "periodic")
                if ended then endReported=true end
            else
                api.enabled = false
                runtime.last_error=tostring(message);policy.runtime=runtime
                saveMatchReport(true,"runtime error")
                repaint("Stopped after an error: " .. tostring(message))
                warn("[RoWorldBot] " .. tostring(message))
            end
        end
        task.wait(.1)
    end
end)
