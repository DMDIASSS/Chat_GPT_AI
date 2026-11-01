-- RoWorld weapon observations and conservative launch checks shared by both routes.
local Weapons={}
Weapons.kinds={atom=0,hydrogen=1,mirv=2,scatter=5}
Weapons.costs={atom=750000,hydrogen=5000000,mirv=25000000,scatter=3750000}
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
function Weapons.slots(s,b,cooldown)
    if (b.active_tick or 0)>s.tick or type(b.shots)~='table' then return 0 end
    local busy=0
    for _,stamp in ipairs(b.shots) do if stamp+cooldown>s.tick then busy+=1 end end
    return math.max(0,(b.level or 1)-busy)
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
    -- Scatter children land up to 46 full-map units away, then blast another
    -- 18 units. Include cell-rounding error in the collateral/hazard envelope.
    return (kind=="hydrogen" and 100 or kind=="mirv" and 1518 or kind=='scatter' and 66 or 30)/(map.k_lin or 1)
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
-- A bounded upper estimate of interception opportunities over the whole volley.
-- Shots, active times and 90-tick reloads are public; future construction,
-- interception randomness and hidden rapid-reload unlocks remain uncertain.
function Weapons.scatterAssessment(s,me,tile,limit,committed)
    local map=s.map;local k=map.k_lin or 1;local launchers={};local free=0
    for _,b in pairs(s.structures) do if b.owner==me and b.kind==5 then
        local slots=Weapons.slots(s,b,90)
        if slots>0 then free+=slots;table.insert(launchers,b) end
    end end
    if free==0 then return nil,'No reloaded silo capacity' end
    table.sort(launchers,function(a,b)
        local da=math.abs(a.tile%map.W-tile%map.W)+math.abs(a.tile//map.W-tile//map.W)
        local db=math.abs(b.tile%map.W-tile%map.W)+math.abs(b.tile//map.W-tile//map.W)
        return da==db and a.tile<b.tile or da<db
    end)
    -- A six-launch plan cannot consume more than the nearest six ready slots.
    -- Include ties because the server may choose either equally near silo.
    local relevant,slots,lastDistance={},0,nil
    for _,b in ipairs(launchers) do
        local d=math.abs(b.tile%map.W-tile%map.W)+math.abs(b.tile//map.W-tile//map.W)
        if slots>=6 and d~=lastDistance then break end
        table.insert(relevant,b);slots+=Weapons.slots(s,b,90);lastDistance=d
    end
    launchers=relevant
    local sams={};local flights={};local nearLaunch={}
    for _,launcher in ipairs(launchers) do
        local arc=Weapons.arc(map,launcher.tile,tile);local length=0
        for i=2,#arc do length+=math.sqrt((arc[i].x-arc[i-1].x)^2+(arc[i].y-arc[i-1].y)^2) end
        table.insert(flights,math.max(1,math.ceil(length*k/10)))
        for sid,b in pairs(s.structures) do if b.kind==4 and not friendly(s,me,b.owner) then
            local reach=(150-480/(math.max(1,b.level or 1)+5))/k
            local covers=false
            for i,p in ipairs(arc) do
                local q=arc[math.min(i+1,#arc)]
                local pad=math.sqrt((q.x-p.x)^2+(q.y-p.y)^2)+48/k+2
                local dx,dy=b.tile%map.W+.5-p.x,b.tile//map.W+.5-p.y
                -- Including the full arc is conservative even outside the
                -- game's targetable endpoint regions; never miss launch-side SAMs.
                if dx*dx+dy*dy<=(reach+pad)^2 then covers=true;break end
            end
            if covers then sams[sid]=b
                if map.dist2(b.tile,launcher.tile)<=(300/k)^2 then nearLaunch[sid]=true end
            end
        end end
    end
    local earliest,latest=math.huge,0
    for _,n in ipairs(flights) do earliest=math.min(earliest,n);latest=math.max(latest,n) end
    local x,y=tile%map.W,tile//map.W;local ring=math.ceil(46/k+1)
    -- At map edges some children cannot be placed. Do not promise a full payload.
    local payload=x>=ring and y>=ring and x<map.W-ring and y<map.H-ring and 5 or 1
    local ceiling=math.min(6,limit or 6,free+(committed or 0))
    for count=1,ceiling do
        local capacity,levels=0,0
        for sid,b in pairs(sams) do
            levels+=b.level or 1
            local first=s.tick+(nearLaunch[sid] and 0 or math.max(0,earliest-45))
            local last=s.tick+latest+(count-1)*10+12
            if nearLaunch[sid] then last=math.min(last,s.tick+45+(count-1)*10+12) end
            for slot=1,(b.level or 1) do
                local readyAt=math.max(b.active_tick or 0,((b.shots or {})[slot] or -100000)+90)
                local start=math.max(first,readyAt)
                if start<=last then capacity+=1+math.floor((last-start)/90) end
            end
        end
        if count*payload>=capacity+(capacity>0 and 2 or 0) then
            local coverage={};for sid,b in pairs(sams) do coverage[tostring(sid)]=b.level or 1 end
            return {count=count,minimum_payload=payload,interception_budget=capacity,sam_levels=levels,
                coverage=coverage,free_silo_slots=free,flight_ticks=latest,
                scope='Estimated saturation; random child impacts and future enemy changes are not guaranteed'}
        end
    end
    return nil,'Observed SAM capacity exceeds the bounded volley or ready silo capacity'
end
function Weapons.canLaunch(s,me,tile,kind,salvo)
    if Weapons.kinds[kind]==nil or not valid(s,tile) then return false,"Unsupported weapon or target" end
    local id=s:tile_owner(tile)
    if id==0 or friendly(s,me,id) then return false,"Target is no longer hostile" end
    if s:has_request(me,id) then return false,"Our alliance proposal is still pending" end
    if s:has_fallout(tile) then return false,"Target is already a fallout zone" end
    if not Weapons.blastSafe(s,me,tile,kind) then return false,"Friendly territory is inside the possible strike area" end
    local launchers=Weapons.launchers(s,me,tile)
    if #launchers==0 then return false,"No missile silo is ready" end
    if kind=='scatter' then
        if salvo then
            local current,why=Weapons.scatterAssessment(s,me,tile,6,salvo.sent or 0)
            if not current or current.count>salvo.total then return false,why or 'SAM capacity changed; reassess the salvo' end
            for sid,level in pairs(current.coverage) do
                if level>((salvo.coverage or {})[sid] or 0) then return false,'New or upgraded SAM coverage; reassess the salvo' end
            end
        else
            local q,why=Weapons.scatterAssessment(s,me,tile,1)
            if not q then return false,why end
        end
        return true
    end
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
    local radii={[0]=30,[1]=100,[2]=1518,[3]=18,[4]=60,[5]=66,[6]=1.5,[7]=15,[8]=5}
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
 local rows={};local radii={[0]=30,[1]=100,[2]=1518,[3]=18,[4]=60,[5]=66,[6]=1.5,[7]=15,[8]=5}
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
            local kind=({[0]="atom",[1]="hydrogen",[2]="mirv",[3]="atom",[5]='scatter'})[n.kind]
            if kind and not Weapons.blastSafe(proxy,me,n.to_tile,kind) then return false end
        end
    end
    return true
end
return Weapons
