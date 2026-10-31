-- Independent reader for this game's replicated minimap lines and 3D race points.
local Roads = {}
local function finite(v) return type(v) == "number" and v == v and math.abs(v) < 1e7 end
local function wrap(a) return (a + math.pi) % (2 * math.pi) - math.pi end
local function yaw(x, z) return math.atan2(-x, -z) end

function Roads.path(name, points, closed, width)
    local pts = {}
    for _, p in ipairs(points) do
        if finite(p.x) and finite(p.z) and (p.y == nil or finite(p.y)) then
            local last = pts[#pts]
            if not last or (p.x - last.x)^2 + (p.z - last.z)^2 > 0.01 then table.insert(pts, p) end
        end
        if #pts >= 20000 then break end
    end
    if #pts < 2 then return nil end
    if closed and (pts[1].x - pts[#pts].x)^2 + (pts[1].z - pts[#pts].z)^2 > 0.01 then
        table.insert(pts, pts[1])
    end
    local cum = {0}
    for i = 2, #pts do
        local a, b = pts[i-1], pts[i]
        cum[i] = cum[i-1] + math.sqrt((a.x - b.x)^2 + (a.z - b.z)^2)
    end
    if cum[#cum] < 2 then return nil end
    return {name = name, points = pts, closed = closed == true, width = if finite(width) then math.clamp(width, 8, 180) else 36,
        cum = cum, total = cum[#cum]}
end

function Roads.parseMinimap(text, name)
    local result = {}
    if type(text) ~= "string" or #text > 2000000 then return result end
    for line in text:gmatch("[^\r\n]+") do
        local kind, w, data = line:match("^(%a+)|([%d%.]+)|(.*)$")
        if (kind == "line" or kind == "loop") and #result < 128 then
            local pts = {}
            for x, z in data:gmatch("([%-%d%.]+),([%-%d%.]+)") do
                table.insert(pts, {x = tonumber(x), z = tonumber(z)})
                if #pts >= 20000 then break end
            end
            local path = Roads.path((name or "Road") .. " #" .. (#result+1), pts, kind == "loop", tonumber(w))
            if path then table.insert(result, Roads.smooth(path)) end
        end
    end
    return result
end

function Roads.parseRace(text, name, width)
    if type(text) ~= "string" or #text > 2000000 then return nil end
    local pts = {}
    for x, y, z in text:gmatch("([%-%d%.]+),([%-%d%.]+),([%-%d%.]+)") do
        table.insert(pts, {x = tonumber(x), y = tonumber(y), z = tonumber(z)})
        if #pts >= 20000 then break end
    end
    -- Race points include start / finish run-outs. They are finite courses, not closed minimap loops.
    return Roads.path(name or "Race", pts, false, width)
end

function Roads.point(path, distance)
    local s = if path.closed then distance % path.total else math.clamp(distance, 0, path.total)
    local lo, hi = 1, #path.points - 1
    while lo < hi do
        local mid = math.ceil((lo + hi) / 2)
        if path.cum[mid] <= s then lo = mid else hi = mid - 1 end
    end
    local a, b = path.points[lo], path.points[lo+1]
    local length = path.cum[lo+1] - path.cum[lo]
    local t = if length > 0 then (s-path.cum[lo]) / length else 0
    return {x = a.x + (b.x-a.x)*t, z = a.z + (b.z-a.z)*t,
        y = if a.y and b.y then a.y + (b.y-a.y)*t else nil}, yaw(b.x-a.x, b.z-a.z)
end

function Roads.smooth(path)
    -- The minimap is quantized into short stair-step segments, not a steering spline.
    -- Uniform samples and a bounded binomial filter remove those artificial sharp corners.
    local count=math.clamp(math.ceil(path.total/6),2,19999)
    local pts={}
    for i=0,(if path.closed then count-1 else count) do
        table.insert(pts,(Roads.point(path,path.total*i/count)))
    end
    local n=#pts
    local weights={1,4,6,4,1}
    for _=1,3 do
        local filtered={}
        for i,p in ipairs(pts) do
            if not path.closed and (i==1 or i==n) then filtered[i]=p;continue end
            local x,z=0,0
            for j=-2,2 do
                local index=if path.closed then (i+j-1)%n+1 else math.clamp(i+j,1,n)
                x+=pts[index].x*weights[j+3];z+=pts[index].z*weights[j+3]
            end
            filtered[i]={x=x/16,z=z/16}
        end
        pts=filtered
    end
    return Roads.path(path.name,pts,path.closed,path.width) or path
end

function Roads.project(path, position, previousS, heading)
    local best, score = nil, math.huge
    for i = 1, #path.points-1 do
        local a, b = path.points[i], path.points[i+1]
        local dx, dz = b.x-a.x, b.z-a.z
        local ll = dx*dx + dz*dz
        if ll < 0.01 then continue end
        local t = math.clamp(((position.x-a.x)*dx + (position.z-a.z)*dz)/ll, 0, 1)
        local s = path.cum[i] + (path.cum[i+1]-path.cum[i])*t
        local separation = if previousS then math.abs(s-previousS) else 0
        if path.closed then separation = math.min(separation, path.total-separation) end
        if previousS and separation > 80 then continue end
        local px, pz = a.x+dx*t, a.z+dz*t
        local distance = math.sqrt((position.x-px)^2 + (position.z-pz)^2)
        local height = if a.y and b.y and position.y then math.abs(position.y-(a.y+(b.y-a.y)*t)) else 0
        local candidate = distance + math.max(0, height-6)*4
        local roadYaw = yaw(dx,dz)
        if heading and previousS == nil then
            candidate += math.min(math.abs(wrap(roadYaw-heading)), math.abs(wrap(roadYaw+math.pi-heading)))*2
        end
        if candidate < score then
            score = candidate
            best = {s = s, distance = distance, height = height, yaw = roadYaw, x = px, z = pz, score = score}
        end
    end
    return best
end

function Roads.nearest(paths, position, heading)
    local bestPath, bestProjection
    for _, path in ipairs(paths) do
        local p = Roads.project(path, position, nil, heading)
        if p and (not bestProjection or p.score < bestProjection.score) then bestPath, bestProjection = path, p end
    end
    if not bestPath then return nil end
    local direction = if math.abs(wrap(bestProjection.yaw-heading)) <= math.pi/2 then 1 else -1
    return bestPath, direction, bestProjection
end

function Roads.connection(paths,current,direction,excluded)
    local endpoint,h=Roads.point(current,if direction>0 then current.total else 0)
    h+=if direction<0 then math.pi else 0
    local best,score=nil,math.huge
    for _,path in ipairs(paths) do
        if path==current or (excluded and excluded[path]) then continue end
        local p=Roads.project(path,endpoint,nil,h)
        if not p or p.distance>math.min(14,(path.width+current.width)*.2) or p.height>4 then continue end
        for _,dir in ipairs({1,-1}) do
            local remaining=if dir>0 then path.total-p.s else p.s
            local turn=math.abs(wrap(p.yaw+(if dir<0 then math.pi else 0)-h))
            -- Do not select an overlapping duplicate that immediately runs out of road.
            if (path.closed or remaining>18) and turn<math.rad(100) then
                local s=p.distance*3+turn*12+p.height*6
                if s<score then score=s;best={path=path,s=p.s,direction=dir} end
            end
        end
    end
    return best
end

function Roads.guide(path, direction, position, speed, heading, previousS)
    local projected = Roads.project(path, position, previousS, heading)
    if not projected then return nil end
    local lookahead = math.clamp(12 + speed*0.65, 18, 75)
    local target = Roads.point(path, projected.s + direction*lookahead)
    local step = math.clamp(speed*0.15+5, 5, 16)
    local _, t0 = Roads.point(path, projected.s - direction*step/2)
    local _, t1 = Roads.point(path, projected.s + direction*step/2)
    if direction < 0 then t0, t1 = t0+math.pi, t1+math.pi end
    local curvature = wrap(t1-t0)/step
    local tangent = t0 + wrap(t1-t0)*0.5
    local signedCrossTrack = -(position.x-projected.x)*math.cos(tangent)+(position.z-projected.z)*math.sin(tangent)
    -- Follow the local tangent with lateral error feedback. A far-away point alone cuts hairpins.
    -- The small curvature lead compensates the controller's velocity-response time.
    local targetYaw = tangent-math.atan2(signedCrossTrack*1.5,math.max(speed,8))+curvature*speed*0.22
    -- Preview braking before tight corners, rather than waiting until already in them.
    local speedLimit = math.huge
    for i = 0, 12 do
        local d = i*8
        local _, a = Roads.point(path, projected.s+direction*(d-step/2))
        local _, b = Roads.point(path, projected.s+direction*(d+step/2))
        local k = math.abs(wrap(b-a))/step
        if k > 0.0001 then speedLimit = math.min(speedLimit, math.sqrt(32/k + 2*32*d)) end
    end
    local remaining = if path.closed then math.huge elseif direction > 0 then path.total-projected.s else projected.s
    return {yaw = targetYaw, curvature = curvature, speedLimit = speedLimit, s = projected.s,
        remaining = remaining, crossTrack = projected.distance, signedCrossTrack = signedCrossTrack, width = path.width, name = path.name,
        offRoad = projected.distance > path.width*0.65+8 or projected.height > 18,
        target = target, direction = direction}
end

return Roads
