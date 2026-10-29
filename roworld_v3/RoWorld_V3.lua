-- RoWorld 3.0.0 | independent observation / candidate policy
-- No OpenFront weights; no external runtime downloads.
local Weapons=(function()
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
-- Alerts use observed impact points and conservative blast radii, not launch intent.
function Weapons.alerts(s,me)
 local rows={};local radii={[0]=30,[1]=100,[2]=1518,[3]=18,[4]=60,[5]=30,[6]=1.5,[7]=15,[8]=5}
 for uid,n in pairs(s.nukes) do
  local radius=radii[n.kind]
  if radius and n.owner~=me and valid(s,n.to_tile) then
   local r=radius/(s.map.k_lin or 1);local assets=0;local allied=0
   for _,b in pairs(s.structures) do
    if s.map.dist2(b.tile,n.to_tile)<=r*r then
     if b.owner==me then assets+=1 elseif s:are_allies(me,b.owner) then allied+=1 end
    end
   end
   local hit=s:tile_owner(n.to_tile)==me or assets>0
   -- Supplement exact asset checks with bounded probes for unbuilt owned land.
   local x,y=n.to_tile%s.map.W,n.to_tile//s.map.W
   for _,d in ipairs({{1,0},{-1,0},{0,1},{0,-1},{1,1},{-1,-1},{1,-1},{-1,1}}) do
    for _,fraction in ipairs({.25,.5,.75}) do
     local xx,yy=math.floor(x+d[1]*r*fraction),math.floor(y+d[2]*r*fraction)
     if xx>=0 and yy>=0 and xx<s.map.W and yy<s.map.H and s:tile_owner(yy*s.map.W+xx)==me then hit=true end
    end
   end
   if hit or allied>0 then
    table.insert(rows,{uid=uid,owner=n.owner,kind=n.kind,target_tile=n.to_tile,hits_us=hit,own_assets=assets,allied_assets=allied,
     eta_seconds=math.max(0,((n.launch_tick or s.tick)+(n.flight_ticks or 0)-s.tick)/10),
     coverage_at_target=Weapons.covered(s,me,n.to_tile,1),scope='Observed flight; interception and blast outcomes uncertain; unbuilt land probes may miss narrow holdings'})
   end
  end
 end
 table.sort(rows,function(a,b) if a.hits_us~=b.hits_us then return a.hits_us end;return a.eta_seconds<b.eta_seconds end)
 while #rows>16 do table.remove(rows) end
 return rows
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

local Cooperation=(function()
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

local Profiles=(function()
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

local Recorder=(function()
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

local Adapter=(function()
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
    local caps, lines = self.capabilities, {"RoWorld Bot 3.0.0 - client access diagnostics"}
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
            if (action.plan or {}).defensive_counter then
                local active=false
                for _,a in pairs(s.attacks) do if a.attacker==target and a.target==me and not a.retreating then active=true end end
                if not active then return false,'Attacker stopped; reassessing counterattack' end
                reserve=math.max(reserve,math.ceil((live.info.max_troops or 0)*.42))
            end
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

local Wire=(function()
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

local Mirror=(function()
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

local Network=(function()
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

local Schema=(function()
-- Versioned RoWorld features. No OpenFront checkpoint is compatible with this schema.
local Schema = {
    version = 'roworld-observation-v1', context = 204, action = 48, hidden = 32,
    max_candidates = 96, prior_scale = 1, decision_ticks = 10,
    types = {'wait','spawn','expand','attack','boat','retreat','city','factory','port',
        'defense','sam','silo','warship','move_warship','ally_request','ally_accept',
        'ally_reject','ally_extend','donate','atom','hydrogen','mirv','ally_break'},
}
Schema.ids = {}
for i,name in ipairs(Schema.types) do Schema.ids[name]=i end
Schema.globals = {'phase_spawn','phase_play','match_minutes','home_log','capacity_log',
    'home_fraction','gold_log','land_fraction','income_log','incoming_ratio','committed_ratio',
    'reserve_ratio','available_ratio','neutral_front_log','foreign_fronts','human_fronts',
    'strongest_neighbor_ratio','city_levels','factory_levels','port_levels','posts','sams',
    'silos','ships','transports','missile_alerts','own_team','team_count','nearby_allies',
    'leader_land_ratio','own_traitor','front_scan_coverage'}
Schema.arguments = {'troop_fraction','cost_fraction','target_home_ratio','target_land_ratio',
    'target_gold_log','target_human','target_country','target_tribe','actual_ally','protected_friend',
    'incoming_from_target','pressure_on_target','already_committed_to_target','useful_assets',
    'target_ally_army_ratio','distance_to_core','flatness','coastal','fallout','upgrade','level',
    'quantity_needed_ratio','threat_exposure','estimated_payback','policy_prior'}
function Schema.clamp(x,lo,hi)
    if type(x)~='number' or x~=x or math.abs(x)==math.huge then return 0 end
    return math.clamp(x,lo or -8,hi or 8)
end
function Schema.log(x) return math.log(1+math.max(0,x or 0))/16 end
return Schema

end)()

local Geography=(function()
-- Bounded, current-state geometry. Every proposed destination is checked again at send time.
local Geography = {}

function Geography.valid(m,t) return type(t)=='number' and t%1==0 and t>=0 and t<m.N end
function Geography.neighbors(m,t,fn)
    local x=t%m.W
    if x>0 then fn(t-1) end;if x<m.W-1 then fn(t+1) end
    if t>=m.W then fn(t-m.W) end;if t<m.N-m.W then fn(t+m.W) end
end
function Geography.magnitude(m,t)
    local bytes=m.bytes or m.tile_bytes or m.terr
    return bytes and bit32.band(buffer.readu8(bytes,t),31) or 0
end
function Geography.sample(m,list,index)
    local b=m[list]
    if typeof(b)~='buffer' or buffer.len(b)<4 then return nil end
    return buffer.readi32(b,(index%(buffer.len(b)//4))*4)
end
function Geography.anchor(frame,old)
    local s,m,me=frame.state,frame.map,frame.me
    -- Retain the original economic home while it remains ours. Recenter only after loss.
    if Geography.valid(m,old) and s:tile_owner(old)==me then return old end
    local best,weight=nil,-1
    for _,b in pairs(s.structures) do
        if b.owner==me then
            local value=({[0]=4,[1]=3,[2]=5,[3]=0,[4]=2,[5]=1})[b.kind] or 0
            value*=b.level or 1
            if value>weight or value==weight and (not best or b.tile<best) then best,weight=b.tile,value end
        end
    end
    if best then return best end
    for _,t in ipairs({frame.info.spawn_tile or -1,frame.info.label_tile or -1}) do
        if Geography.valid(m,t) and s:tile_owner(t)==me then return t end
    end
    local candidate
    for t in pairs(frame.ctx.borders.border) do if s:tile_owner(t)==me and (not candidate or t<candidate) then candidate=t end end
    return candidate or 0
end
function Geography.fronts(frame,cursor)
    local s,m,me=frame.state,frame.map,frame.me
    local border=frame.ctx.borders.border
    local keys={};for t in pairs(border) do table.insert(keys,t) end;table.sort(keys)
    local count=#keys;local groups={};local near={};local sites={};local seen={}
    local budget=math.min(count,4096);local offset=count>0 and (cursor or 0)%count or 0
    for i=1,budget do
        local t=keys[(offset+i-1)%count+1]
        if s:tile_owner(t)==me then
            if #sites<64 then table.insert(sites,t) end
            Geography.neighbors(m,t,function(n)
                local id=s:tile_owner(n)
                if id>0 and id~=me then near[id]=true end
                if id~=me and m:is_contestable(n) and not s:has_fallout(n) and not seen[n] then
                    seen[n]=true
                    local g=groups[id];if not g then g={id=id,tile=n,front=0,tiles={}};groups[id]=g end
                    g.front+=1
                    if #g.tiles<8 then table.insert(g.tiles,n) end
                    if n<g.tile then g.tile=n end
                end
            end)
        end
    end
    return groups,near,sites,offset+budget,count>0 and budget/count or 1
end
function Geography.safe(frame,t,kind)
    local s,m=frame.state,frame.map
    local margin=(kind=='defense' or kind=='sam') and 8 or 18
    if not Geography.valid(m,t) or s:tile_owner(t)~=frame.me or s:has_fallout(t)
        or Weapons.hazard(s,t,margin) then return false,margin end
    local r=math.ceil(margin/(m.k_lin or 1));local x,y=t%m.W,t//m.W
    for yy=math.max(0,y-r),math.min(m.H-1,y+r) do
        for xx=math.max(0,x-r),math.min(m.W-1,x+r) do
            if (xx-x)^2+(yy-y)^2<=r*r then
                local p=yy*m.W+xx
                if s:has_fallout(p) or s:tile_owner(p)~=frame.me and (m:is_contestable(p) or kind~='port') then
                    return false,margin
                end
            end
        end
    end
    return true,margin
end
function Geography.sites(frame,anchor,frontSites)
    local m=frame.map;local seen={};local sites={}
    local function add(t)
        if Geography.valid(m,t) and not seen[t] and frame.state:tile_owner(t)==frame.me then
            seen[t]=true;table.insert(sites,t)
        end
    end
    add(anchor)
    local spacing=math.max(1,math.ceil(12/(m.k_lin or 1)))
    local x,y=anchor%m.W,anchor//m.W
    for dy=-3,3 do for dx=-3,3 do
        local xx,yy=x+dx*spacing,y+dy*spacing
        if xx>=0 and yy>=0 and xx<m.W and yy<m.H then add(yy*m.W+xx) end
    end end
    for _,b in pairs(frame.state.structures) do if b.owner==frame.me then add(b.tile) end end
    for _,t in ipairs(frontSites or {}) do if m:is_coastal(t) then add(t) end end
    -- The original spawn can remain owned while its neighborhood becomes unsafe.
    -- Search other holdings too, rather than silently saving forever at that point.
    for i=1,64 do add(Geography.sample(m,'land_list',(frame.state.tick or 0)*31337+i*104729)) end
    return sites
end
function Geography.landing(frame,t,anchor,escape)
    local s,m=frame.state,frame.map
    if s:borders_tile(frame.me,t) then return nil end
    local x,y=anchor%m.W,anchor//m.W;local dx,dy=t%m.W-x,t//m.W-y
    local water=false;local samples=math.min(64,math.max(math.abs(dx),math.abs(dy)))
    for i=1,samples do
        local p=math.floor(y+dy*i/samples)*m.W+math.floor(x+dx*i/samples)
        local wet=type(m.is_water)=='function' and m:is_water(p) or m.water and m.water[p]
        if wet then water=true;break end
    end
    if not water and not escape then return nil end
    local room=0;local tx,ty=t%m.W,t//m.W
    local r=math.max(1,math.ceil(20/(m.k_lin or 1)))
    for _,d in ipairs({{1,0},{-1,0},{0,1},{0,-1},{1,1},{1,-1},{-1,1},{-1,-1}}) do
        local xx,yy=tx+d[1]*r,ty+d[2]*r
        if xx>=0 and yy>=0 and xx<m.W and yy<m.H then
            local p=yy*m.W+xx
            if m:is_contestable(p) and s:tile_owner(p)==0 and not s:has_fallout(p) then room+=1 end
        end
    end
    local danger=0
    for id,p in pairs(s.owners) do
        local center=p.label_tile or p.spawn_tile
        if id~=frame.me and p.alive and p.kind==2 and not s:are_allies(frame.me,id) and Geography.valid(m,center) then
            local distance=math.sqrt(m.dist2(t,center))*(m.k_lin or 1)
            if distance<120 then danger+=math.max(0,1-distance/120)*(p.troops or 0)/math.max(1,frame.info.troops or 0) end
        end
    end
    if danger>.75 then return nil end
    return room*.15-danger*4+(water and .4 or 0)
end
function Geography.spawnScore(frame,t)
    local s,m=frame.state,frame.map
    if not Geography.valid(m,t) or not m:is_contestable(t) or s:has_fallout(t) then return nil end
    local owner=s:tile_owner(t)
    if owner~=0 and not (s.phase==0 and owner==frame.me and t==frame.info.spawn_tile) then return nil end
    local score,open,water,players=0,0,0,0
    local r=math.max(2,math.ceil(40/(m.k_lin or 1)));local x,y=t%m.W,t//m.W
    for dy=-2,2 do for dx=-2,2 do
        local xx,yy=x+dx*r/2,y+dy*r/2
        if xx>=0 and yy>=0 and xx<m.W and yy<m.H then
            local p=math.floor(yy)*m.W+math.floor(xx)
            if m:is_contestable(p) then
                if s:tile_owner(p)==0 then open+=1;score+=1-Geography.magnitude(m,p)/40 end
            else water+=1 end
        end
    end end
    local nearest=math.huge
    for id,o in pairs(s.owners) do
        local p=o.spawn_tile
        if id~=frame.me and o.alive and Geography.valid(m,p) then
            local d=math.sqrt(m.dist2(t,p))*(m.k_lin or 1)
            if o.kind==2 then
                nearest=math.min(nearest,d)
                if d<140 then players+=1;score-=(140-d)*.14 end
            elseif o.kind==1 and d<100 then score+=1 end
        end
    end
    score+=math.min(3,water*.3)+math.min(200,nearest)*.03
    if open<8 then score-=20 end
    return score,{neutral_samples=open,water_samples=water,nearby_humans=players,nearest_human=nearest<math.huge and nearest or -1}
end
return Geography

end)()

local Observe=(function()
local Observe={}



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

end)()

local Actions=(function()
-- RoWorld candidate decoder: engine-feasible proposals plus explicit, separate risk filters.
local Actions={}



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

end)()

local Neural=(function()
-- Small residual actor-critic. Same equations as training/model.py; no runtime Python.
local Neural={}

local function finite(n) return type(n)=='number' and n==n and math.abs(n)<1e6 end
local shapes={context={Schema.hidden,Schema.context},action={Schema.hidden,Schema.action},
    fusion={Schema.hidden,Schema.hidden},score={1,Schema.hidden},value={1,Schema.hidden}}
function Neural.validate(weights)
    if type(weights)~='table' or weights.schema~=Schema.version or weights.version~=1 then return nil,'Model schema mismatch' end
    for name,shape in pairs(shapes) do
        local layer=weights[name]
        if type(layer)~='table' or type(layer.w)~='table' or type(layer.b)~='table' or #layer.w~=shape[1] or #layer.b~=shape[1] then return nil,'Bad layer '..name end
        for i=1,shape[1] do
            if type(layer.w[i])~='table' or #layer.w[i]~=shape[2] or not finite(layer.b[i]) then return nil,'Bad shape '..name end
            for _,v in ipairs(layer.w[i]) do if not finite(v) then return nil,'Non-finite model' end end
        end
    end
    return weights
end
local function linear(layer,x,relu)
    local y={}
    for i,row in ipairs(layer.w) do
        local n=layer.b[i]
        for j,w in ipairs(row) do n+=w*x[j] end
        y[i]=relu and math.max(0,n) or n
    end
    return y
end
function Neural.score(weights,context,candidates)
    local logits={}
    if not weights then for i,a in ipairs(candidates) do logits[i]=a.bias or 0 end;return logits,0 end
    local state=linear(weights.context,context,true)
    local fused=linear(weights.fusion,state,true)
    for i,a in ipairs(candidates) do
        local token=linear(weights.action,a.features,true)
        local dot=0;for j,v in ipairs(token) do dot+=v*fused[j] end
        local residual=dot/math.sqrt(Schema.hidden)+linear(weights.score,token,false)[1]
        logits[i]=(a.bias or 0)+residual
    end
    return logits,linear(weights.value,fused,false)[1]
end
function Neural.pick(logits,uniform)
    local best=1;for i=2,#logits do if logits[i]>logits[best] then best=i end end
    local z=0;local probs={}
    for i,v in ipairs(logits) do probs[i]=math.exp(math.clamp(v-logits[best],-80,0));z+=probs[i] end
    for i,v in ipairs(probs) do probs[i]=v/z end
    if uniform then
        local sum=0
        for i,p in ipairs(probs) do sum+=p;if uniform<=sum then return i,probs end end
    end
    return best,probs
end
return Neural

end)()

local Agent=(function()
-- New v3 decision core. Does not call v2 Policy, Strategy or Planner.
local Agent={};Agent.__index=Agent







function Agent.new(profiles,weights)
    local valid,reason
    if weights then valid,reason=Neural.validate(weights) end
    return setmetatable({profiles=profiles or Profiles.new(),cooperation=Cooperation.new(),weights=valid,
        modelStatus=valid and 'loaded residual policy' or reason or 'built-in policy; no trained model loaded',
        seed=739391,cooldowns={},campaigns={},distrust={},postPurchases={},outcome={},history={},metrics={orders=0}},Agent)
end
function Agent:random(n) self.seed=self.seed*48271%2147483647;return self.seed%math.max(1,n) end
function Agent:reset(frame)
    self.state,self.me=frame.state,frame.me;self.anchor=nil;self.frontCursor=0;self.lastTick=nil;self.observation=nil
    self.cooldowns={};self.campaigns={};self.distrust={};self.postPurchases={};self.outcome={};self.history={};self.lastObservation=nil
    self.lastSentAt,self.lastSentKind,self.pending,self.lastRejected,self.lastWaiting=nil,nil,nil,nil,nil
    self.blocked=false
    self.metrics={orders=0,peakLand=frame.info.tiles or 0};self.profiles:start(frame);self.recorder=Recorder.new(frame)
    self.allianceSeq=frame.state.alliance_seq or 0;self.missileHistory={};self.missilesSeen={}
end
function Agent:prepare(frame)
    if self.state~=frame.state or self.me~=frame.me or self.lastTick and frame.state.tick<self.lastTick then self:reset(frame) end
    self.cooperation:update(frame);self.profiles:observe(frame);self.recorder:observe(frame)
    self.lastTick=frame.state.tick
    self.phase,self.ownAlive=frame.state.phase,frame.info.alive
    for _,event in ipairs(frame.state.alliance_events or {}) do
        if (event.seq or 0)>self.allianceSeq and event.breaker and event.breaker>0 and event.breaker~=frame.me
            and (event.a==frame.me or event.b==frame.me) then
            self.profiles:betrayed(frame,event.breaker);self.distrust[event.breaker]=frame.now+180
        end
    end
    self.allianceSeq=frame.state.alliance_seq or 0
    for i=#self.postPurchases,1,-1 do if frame.now-self.postPurchases[i]>=60 then table.remove(self.postPurchases,i) end end
    for id,c in pairs(self.campaigns) do
        local p=frame.state.owners[id]
        if not p or not p.alive then self.campaigns[id]=nil
        else
            if (p.tiles or 0)<c.last_land then c.progress_at=frame.now;c.last_land=p.tiles or 0 end
            if frame.now>=c.deadline then
                if frame.now>=c.deadline+15 then self.campaigns[id]=nil else c.pause_until=c.deadline+15 end
            end
        end
    end
    local o=Observe.read(frame,self)
    local prev=self.lastObservation
    local dt=prev and math.max(1,o.tick-prev.tick) or 1
    self.outcome={prev and Schema.clamp(((frame.info.tiles or 0)-prev.land)/math.max(1,prev.land)) or 0,
        prev and Schema.clamp((o.home-prev.home)/math.max(1,prev.home)) or 0,
        prev and Schema.clamp(((frame.info.gold or 0)-prev.gold)/math.max(1000,prev.gold)) or 0,
        self.lastSentKind and self.lastSentKind/#Schema.types or 0,self.blocked and 1 or 0,
        Schema.clamp(dt/100),self.lastSentAt and Schema.clamp((frame.now-self.lastSentAt)/30) or 0,
        self.pending and 1 or 0}
    for i=1,8 do o.context[Schema.context-8+i]=self.outcome[i] end
    self.lastObservation={tick=o.tick,home=o.home,gold=frame.info.gold or 0,land=frame.info.tiles or 0}
    self.missileAlerts=o.alerts
    for _,a in ipairs(o.alerts) do if not self.missilesSeen[a.uid] then
        self.missilesSeen[a.uid]=true;table.insert(self.missileHistory,a)
        if #self.missileHistory>32 then table.remove(self.missileHistory,1) end
    end end
    self.metrics.peakLand=math.max(self.metrics.peakLand,frame.info.tiles or 0)
    self.observation=o
    local candidates,filtered=Actions.generate(frame,o,self)
    local logits,value=Neural.score(self.weights,o.context,candidates)
    self.candidates=candidates;self.logits=logits;self.value=value;self.filtered=filtered
    self.board={mode=o.incoming>o.home*.6 and 'defend' or 'observe-and-compare',incoming=o.incoming,
        reserve=o.reserve,available=o.available,candidate_count=#candidates,model=self.modelStatus,
        planner={objective='compare legal candidates'}}
    return o,candidates,logits,value
end
function Agent:decide(frame)
    self.evaluated=false
    if self.state==frame.state and self.lastTick==frame.state.tick then return nil,self.lastWaiting or 'Waiting for the next authoritative tick' end
    if self.state==frame.state and self.me==frame.me and self.lastTick and frame.state.tick>=self.lastTick
        and frame.state.tick-self.lastTick<Schema.decision_ticks and self.phase==frame.state.phase and self.ownAlive==frame.info.alive then
        return nil,self.lastWaiting or 'Watching between one-second decisions'
    end
    self.evaluated=true
    local _,candidates,logits=self:prepare(frame)
    local chosen,probs=Neural.pick(logits,self.stochastic and (self:random(1000000)+.5)/1000000 or nil)
    self.selected=chosen;self.probabilities=probs
    local a=candidates[chosen];self.board.planner.objective=a.kind;self.lastWaiting=a.label
    if a.kind=='wait' then self.pending=nil;return nil,a.label end
    self.pending=a;return a,a.label
end
function Agent:sent(action,now)
    self.cooldowns[action.channel]=now+action.cooldown
    self.lastSentAt=now;self.lastSentKind=Schema.ids[action.kind];self.blocked=false;self.pending=nil
    self.metrics.orders+=1
    local intent=action.intent
    self.metrics[intent.type]=(self.metrics[intent.type] or 0)+1
    if intent.type=='build' and intent.kind=='defense' then table.insert(self.postPurchases,now) end
    local target=intent.target or intent.tile and self.state:tile_owner(intent.tile)
    if intent.type=='attack' and target and target>0 then
        local amount=(self.state.owners[self.me].troops or 0)*(intent.ratio or 0)
        local c=self.campaigns[target]
        if not c then
            c={started=now,deadline=now+75,budget=math.max(amount,(self.state.owners[self.me].troops or 0)*.55),
                spent=0,progress_at=now,pause_until=0,last_land=(self.state.owners[target] or {}).tiles or 0}
            self.campaigns[target]=c
        end
        c.spent+=amount
    end
    table.insert(self.history,{tick=self.state.tick,kind=action.kind,target=target,tile=intent.tile,
        ratio=intent.ratio,cost=action.cost,label=action.label})
    if #self.history>64 then table.remove(self.history,1) end
end
function Agent:rejected(reason)
    self.blocked=true;self.lastRejected=tostring(reason);self.pending=nil
end
function Agent:report()
    if not self.observation then return {version='3.0.0',schema=Schema.version,status='no observed match'} end
    local ranked={};for i,a in ipairs(self.candidates or {}) do table.insert(ranked,{kind=a.kind,score=self.logits[i],
        probability=self.probabilities and self.probabilities[i],intent=a.intent,label=a.label}) end
    table.sort(ranked,function(a,b) return a.score>b.score end)
    local o=self.observation;local diplomatic={};for id,r in pairs(o.diplomacy) do
        table.insert(diplomatic,{nation=id,allied=r.allied,same_team=r.same_team,friend=r.friend,
            outgoing_request=r.outgoing_request,incoming_request=r.incoming_request,expiry=r.expiry})
    end
    return {version='3.0.0',schema=Schema.version,policy=self.modelStatus,competitive_strength_verified=false,
        tick=self.state.tick,observation_tick=o.tick,observation_age_ticks=math.max(0,self.state.tick-o.tick),
        decision_interval_ticks=Schema.decision_ticks,me=self.me,own=self.state.owners[self.me],metrics=self.metrics,runtime=self.runtime,
        board=self.board,actions=self.history,candidates=ranked,filtered_by_risk=self.filtered,
        cooperation=self.cooperation.status,public_players=o.players,exact_diplomacy=diplomatic,public_alliance_pairs=o.relationships,
        exact_attacks=o.attacks,exact_units=o.units,exact_missiles=o.missiles,context=o.context,
        missile_alerts=self.missileAlerts,missile_alert_history=self.missileHistory,nuclear_threat=o.nuclearThreat,
        public_observations=self.recorder:report(),opponent_profiles=self.profiles:report({state=self.state,me=self.me}),
        observation_scope='Current public client observations; no hidden intent, private country timers or invented action labels',
        last_rejected=self.lastRejected}
end
return Agent

end)()

local ModelWeights=nil
local Policy=Agent
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
title.Text = "RoWorld 3.0.0 | observation agent"
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
    local alert=env.__RoWorldBot and env.__RoWorldBot.missileWarning
    if not alert and env.__RoWorldBot then alert=env.__RoWorldBot.allyWarning end
    if alert then message=alert.."\n"..(message or '') end
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
local policy = Policy.new(profiles,ModelWeights)
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
    local b=policy.board or {}
    local eco={}
    stats.Text=string.format("%s | Tick %d | Land %d | Troops %.0f / %.0f\nGold %.0f | Income %.0f | Incoming %.0f\n%s | Decision %.1f ms | Blocked %d\n%s",
        info.alive and (b.mode or 'observing') or 'eliminated',policy.state.tick or 0,info.tiles or 0,info.troops or 0,info.max_troops or 0,
        info.gold or 0,info.income or 0,b.incoming or 0,
        b.planner and ('Plan: '..b.planner.objective..' | '..(policy.weights and 'learned model' or 'built-in policy')..' | '..(b.candidate_count or 0)..' choices') or 'Observing strategy',runtime.last_decision_ms,runtime.blocked_orders,
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
    api.missileWarning=nil;api.allyWarning=nil
    if api.enabled then
        policy = Policy.new(profiles,ModelWeights)
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
                if policy.evaluated then
                    runtime.decisions+=1;runtime.last_decision_ms=ms
                    runtime.mean_decision_ms+=(ms-runtime.mean_decision_ms)/runtime.decisions
                else runtime.skipped+=1 end
                runtime.friend_lookup=friendLookup
                local alert=(policy.missileAlerts or {})[1]
                api.missileWarning=alert and string.format("MISSILE ALERT: %s | %.1fs | %d own assets",alert.hits_us and 'our territory' or 'allied assets',alert.eta_seconds,alert.own_assets) or nil
                local neighbor=nil
                api.allyWarning=neighbor and string.format('Alliance risk: neighbor has %.1fx our home troops',neighbor.home_ratio) or nil
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
                        runtime.blocked_orders+=1;runtime.last_blocked_reason=tostring(blocked);policy:rejected(blocked)
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
