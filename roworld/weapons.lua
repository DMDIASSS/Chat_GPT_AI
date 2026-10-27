-- RoWorld weapon observations and conservative launch checks shared by both routes.
local Weapons={}
Weapons.kinds={atom=0,hydrogen=1,mirv=2}
Weapons.costs={atom=750000,hydrogen=5000000,mirv=25000000}
local function valid(s,t) return type(t)=="number" and t>=0 and t<s.map.N end
local function friendly(s,me,id) return id==me or id>0 and s:are_allies(me,id) end
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
        if friendly(s,me,id) and valid(s,o.spawn_tile) and s:tile_owner(o.spawn_tile)==id
            and map.dist2(tile,o.spawn_tile)<=radius*radius then return false end
    end
    for yy=math.max(0,y-r),math.min(map.H-1,y+r) do
        for xx=math.max(0,x-r),math.min(map.W-1,x+r) do
            if (xx-x)^2+(yy-y)^2<=radius*radius and friendly(s,me,s:tile_owner(yy*map.W+xx)) then return false end
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
