-- HowToDrift Assist 1.2.0 | farm / cool road autopilot
-- No downloads, admin remotes, or score submission.

local Controller = (function()
-- Pure planar controller. Yaw is positive to the left; units are studs/second.
local Controller = {}
local PI = math.pi
local function finite(v) return type(v) == "number" and v == v and math.abs(v) < math.huge end
local function number(v, fallback, lo, hi)
    return math.clamp(if finite(v) then v else fallback, lo, hi)
end
local function wrap(a) return (a + PI) % (2 * PI) - PI end
local function approach(a, b, delta) return a + math.clamp(b - a, -delta, delta) end
local function magnitude(x, z) return math.sqrt(x * x + z * z) end
local function limited(x, z, maximum)
    local m = magnitude(x, z)
    if m > maximum and m > 0 then return x * maximum / m, z * maximum / m end
    return x, z
end
Controller.finite, Controller.wrap = finite, wrap

function Controller.settings(raw)
    raw = if type(raw) == "table" then raw else {}
    return {
        angle = number(raw.angle, 35, 15, 75),
        cruiseKmh = number(raw.cruiseKmh, 65, 20, 500),
        power = number(raw.power, 1.25, 0.5, 4),
        speedMultiplier = number(raw.speedMultiplier, 1, 0.5, 2.5),
        strength = number(raw.strength, 0.85, 0, 1),
        mode = if raw.mode == "road" then "road" else "manual",
        side = if raw.side == "left" or raw.side == "right" then raw.side else "auto",
        style = if raw.style == "cool" then "cool" else "farm",
        farmTravel = if raw.farmTravel == "area" then "area" else "loop",
        farmRange = number(raw.farmRange,80,20,300),
    }
end

function Controller.new()
    return {side = 0, targetBeta = 0, velocityRate = 0, previousVelocityYaw = nil}
end

function Controller.measure(sample)
    for _, key in ipairs({"vx", "vz", "yaw", "yawRate"}) do
        if not finite(sample[key]) then return nil end
    end
    local speed = magnitude(sample.vx, sample.vz)
    if not finite(speed) or speed > 1e6 then return nil end
    if finite(sample.forwardSpeed) and finite(sample.sideSpeed) then
        return {speed=magnitude(sample.forwardSpeed,sample.sideSpeed),forward=sample.forwardSpeed,
            beta=math.atan2(sample.sideSpeed,math.abs(sample.forwardSpeed)),velocityYaw=math.atan2(-sample.vx,-sample.vz)}
    end
    local vx, vz = -math.sin(sample.yaw), -math.cos(sample.yaw)
    local forward = sample.vx * vx + sample.vz * vz
    local velocityYaw = if speed > 0.5 then math.atan2(-sample.vx, -sample.vz) else sample.yaw
    return {speed = speed, forward = forward, velocityYaw = velocityYaw,
        beta = if speed > 2 then wrap(sample.yaw - velocityYaw) else 0}
end

local function park(speed, reason)
    return {override = true, throttle = 0, brake = if speed > 3 then 1 else 0,
        steer = 0, handbrake = speed <= 3, ax = 0, az = 0, reason = reason, targetKmh = 0, targetAngle = 0}
end

function Controller.step(state, settings, sample, input, guide, dt)
    local m = Controller.measure(sample)
    if not m then return {reason = "Invalid vehicle telemetry", ax = 0, az = 0} end
    dt = number(dt, 1/60, 1/240, 0.05)
    input = input or {}
    local gas = number(input.throttle, 0, 0, 1)
    local brake = number(input.brake, 0, 0, 1)
    local steer = number(input.steer, 0, -1, 1)
    local auto = settings.mode == "road"
    local out = {override = auto, throttle = gas, brake = brake, steer = steer,
        handbrake = input.handbrake == true, ax = 0, az = 0,
        angle = math.deg(m.beta), speedKmh = m.speed * 1.2, reason = "Manual driving"}
    if sample.paused or sample.grounded < 3 or sample.upY < 0.55 then
        state.previousVelocityYaw, state.velocityRate, state.targetBeta = nil, 0, 0
        out.override = false
        out.reason = if sample.paused then sample.paused else "Waiting for grounded, upright car"
        return out
    end
    local cap = math.min(360, settings.cruiseKmh * settings.speedMultiplier * (if input.boost then 1.35 else 1)) / 1.2
    local targetSpeed = cap
    local desiredYaw = m.velocityYaw
    local side = if settings.side == "left" then 1 elseif settings.side == "right" then -1 else state.side
    if auto then
        if brake > 0.05 or input.handbrake then
            state.previousVelocityYaw, state.targetBeta, state.velocityRate = nil, 0, 0
            out.override = false
            out.reason = "Manual brake / handbrake override"
            return out
        end
        if not guide then return park(m.speed, "No road selected; use Nearest road") end
        if guide.blocked then return park(m.speed, guide.blocked) end
        desiredYaw = guide.yaw
        targetSpeed = math.min(targetSpeed, guide.speedLimit or cap)
        if guide.remaining and guide.remaining < math.huge then
            targetSpeed = math.min(targetSpeed, math.sqrt(2 * 40 * math.max(0, guide.remaining - 5)))
            if guide.remaining <= 5 then return park(m.speed, "End of road") end
        end
        if guide.offRoad then
            -- A large error can be a different elevation / unrelated road. Do not drive across it.
            return park(m.speed, "Outside selected road; drive onto it manually, then restart")
        end
        if settings.side == "auto" then
            if math.abs(guide.curvature or 0) > 0.0025 then side = math.sign(guide.curvature) end
            if side == 0 then side = 1 end
        end
        local headingError = math.abs(wrap(desiredYaw - m.velocityYaw))
        if headingError > math.rad(65) then targetSpeed = math.min(targetSpeed, 12) end
        out.throttle = math.clamp((targetSpeed - m.speed) * 0.1 + 0.28, 0, 1) * math.min(settings.power, 1)
        out.brake = if m.speed > 3 then math.clamp((m.speed - targetSpeed - 2) * 0.12, 0, 1) else 0
        out.handbrake = targetSpeed < 1 and m.speed <= 3
        -- Countersteer already exists in the original CarPhysics. A small curve input leaves it active.
        out.steer = math.clamp(-(guide.curvature or 0) * 14, -0.45, 0.45)
        local tau = 0.22
        local ax = (-math.sin(desiredYaw) * targetSpeed - sample.vx) / tau
        local az = (-math.cos(desiredYaw) * targetSpeed - sample.vz) / tau
        local maxAcceleration = 36 + 18 * settings.power
        out.ax, out.az = limited(ax, az, maxAcceleration)
        out.reason = "Following " .. (guide.name or "road")
    else
        if gas < 0.03 or brake > 0.03 or input.handbrake or m.forward < -2 then
            state.targetBeta, state.previousVelocityYaw, state.velocityRate = 0, nil, 0
            out.reason = "Manual control; hold throttle and choose a drift side"
            return out
        end
        if settings.side == "auto" and math.abs(steer) > 0.2 then side = -math.sign(steer) end
        local power = settings.power * (if input.boost then 1.5 else 1)
        local acceleration = 32 * (power - 1) * gas
        if m.speed > cap then acceleration = math.min(acceleration, -(m.speed - cap) * 7) end
        acceleration = math.clamp(acceleration, -65, 100)
        local travelYaw = if m.speed > 3 then m.velocityYaw else sample.yaw
        out.ax, out.az = -math.sin(travelYaw) * acceleration, -math.cos(travelYaw) * acceleration
        out.reason = if side == 0 then "Accelerating; A / D selects a drift side" else "Holding manual drift"
    end
    state.side = side
    local ramp = math.clamp((m.speed - 9) / 12, 0, 1)
    if auto and (math.abs(wrap(desiredYaw - m.velocityYaw)) > math.rad(65)
        or math.abs(guide.crossTrack or 0) > (guide.width or 36) * 0.42) then ramp = 0 end
    local betaTarget = math.rad(settings.angle) * side * ramp
    local previousTarget = state.targetBeta
    state.targetBeta = approach(state.targetBeta, betaTarget, math.rad(85) * dt)
    local targetBetaRate = (state.targetBeta-previousTarget)/dt
    local velocityRate = 0
    if state.previousVelocityYaw and m.speed > 8 then
        velocityRate = math.clamp(wrap(m.velocityYaw - state.previousVelocityYaw) / dt, -3, 3)
    end
    state.previousVelocityYaw = m.velocityYaw
    state.velocityRate += (velocityRate - state.velocityRate) * (1 - math.exp(-12 * dt))
    local targetRate = state.velocityRate + targetBetaRate + wrap(state.targetBeta - m.beta) * (5 + 3 * settings.strength)
    if auto and m.speed < 8 then
        targetRate = wrap(desiredYaw + state.targetBeta - sample.yaw) * 3
    end
    if (auto or side ~= 0) and settings.strength > 0 then
        targetRate = math.clamp(targetRate, -3, 3)
        local wanted = sample.yawRate + (targetRate - sample.yawRate) * (1 - math.exp(-16 * settings.strength * dt))
        out.yawRate = approach(sample.yawRate, wanted, 10 * dt)
    end
    out.targetKmh, out.targetAngle = targetSpeed * 1.2, math.deg(state.targetBeta)
    return out
end

return Controller

end)()

local Roads = (function()
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

end)()

local InputLease = (function()
-- Own only the game's input override we installed. Do not erase another controller's input.
local InputLease = {}
InputLease.__index = InputLease
function InputLease.new(player) return setmetatable({player = player, last = nil}, InputLease) end
function InputLease:write(command)
    local current = self.player:GetAttribute("DebugInput")
    if current ~= nil and current ~= self.last then return false, "DebugInput is in use by another controller" end
    local value = string.format("%.4f,%.4f,%.4f,%d", math.clamp(command.throttle or 0,0,1),
        math.clamp(command.brake or 0,0,1), math.clamp(command.steer or 0,-1,1), if command.handbrake then 1 else 0)
    self.player:SetAttribute("DebugInput", value)
    self.last = value
    return true
end
function InputLease:release()
    if self.last and self.player:GetAttribute("DebugInput") == self.last then self.player:SetAttribute("DebugInput", nil) end
    self.last = nil
end
return InputLease

end)()

local Rail = (function()

local Rail={}
local function wrap(a) return (a+math.pi)%(2*math.pi)-math.pi end
function Rail.new(path,projection,direction,anchor)
    return {path=path,s=projection.s,direction=direction or 1,speed=0,beta=0,side=1,loops=0,
        anchor=anchor or {path=path,s=projection.s,direction=direction or 1},links=0}
end
function Rail.reference(state)
    return state.anchor.reference
end
function Rail.home(state)
    state.path,state.s,state.direction=state.anchor.path,state.anchor.s,state.anchor.direction
    state.connectionKey,state.connection=nil,nil
    state.loops+=1
    return state.anchor.reference
end
function Rail.reverse(state,backwards)
    state.direction=-state.direction
    state.side=-state.side
    state.beta=-state.beta
    state.backwards=if backwards then not state.backwards else false
    state.connectionKey,state.connection=nil,nil
end
function Rail.rejectConnection(state,target)
    local key=tostring(state.path)..":"..state.direction
    state.rejected=state.rejected or {}
    state.rejected[key]=state.rejected[key] or {}
    state.rejected[key][target]=true
    state.connectionKey,state.connection=nil,nil
end
function Rail.step(state,settings,dt,braking,paths,travelScale)
    dt=math.clamp(dt,1/240,.1)
    local farm=settings.style~="cool"
    local path=state.path
    local requested=math.clamp(settings.cruiseKmh,20,500)/1.2
    local area=farm and settings.farmTravel=="area"
    if area and not state.area then
        local span=math.min(math.clamp(settings.farmRange or 80,20,300),path.total)
        local low=math.clamp(state.s-span*.5,0,path.total-span)
        state.area={low=low,high=low+span}
    elseif not area and state.area then state.area=nil;state.backwards=false end
    local _,a=Roads.point(path,state.s-state.direction*8)
    local _,b=Roads.point(path,state.s+state.direction*8)
    local curve=wrap(b-a)*state.direction/16
    local speed=requested
    local connection
    local remaining=if path.closed then math.huge elseif state.direction>0 then path.total-state.s else state.s
    if remaining<100 and not path.closed and not area then
        local key=tostring(path)..":"..state.direction
        if state.connectionKey~=key then
            state.connectionKey=key
            state.connection=Roads.connection(paths or {},path,state.direction,state.rejected and state.rejected[key])
        end
        connection=state.connection
    end
    if not farm then
        speed=math.min(speed,math.sqrt(32/math.max(math.abs(curve),.0001)))
        if remaining<100 and not connection then speed=math.min(speed,math.sqrt(2*24*math.max(0,remaining-1))) end
        if braking then speed=0 end
        state.speed+=math.clamp(speed-state.speed,-30*dt,20*dt)
    else
        -- Farm mode has no corner, segment-end, or spawn-loop speed reduction.
        state.speed=if braking then 0 else requested
    end
    state.s+=state.direction*state.speed*dt*(travelScale or 1)
    local jumped,joined=false,false
    local overshoot=if state.direction>0 then state.s-path.total else -state.s
    if area then
        for _=1,16 do
            if state.s>state.area.high then
                state.s=state.area.high-(state.s-state.area.high)
                Rail.reverse(state,true)
            elseif state.s<state.area.low then
                state.s=state.area.low+(state.area.low-state.s)
                Rail.reverse(state,true)
            else break end
        end
    elseif path.closed then state.s%=path.total
    elseif overshoot>=0 or (not farm and not connection and remaining<1.1 and state.speed<.5 and not braking) then
        if connection then
            state.path,state.s,state.direction=connection.path,connection.s,connection.direction
            state.s+=state.direction*math.max(0,overshoot)
            state.s=if state.path.closed then state.s%state.path.total else math.clamp(state.s,0,state.path.total)
            state.links+=1;joined=true
        else
            Rail.home(state);jumped=true
            if not farm then state.speed=0 end
        end
        state.connectionKey,state.connection=nil,nil
    end
    local p,h=Roads.point(state.path,state.s)
    if state.direction<0 then h+=math.pi end
    if farm then
        -- Client scoring's angle multiplier reaches its maximum at 60 degrees.
        -- Keep one side: forced side switches would cross zero and interrupt a drift.
        state.beta=math.rad(60)*state.side
    else
        if math.abs(curve)>.004 then state.side=math.sign(curve) end
        local magnitude=math.min(math.clamp(settings.angle,15,75),math.clamp(math.abs(curve)*state.speed*45,0,75))
        magnitude*=math.clamp(state.speed/14,0,1)
        local target=math.rad(magnitude)*state.side
        state.beta+=math.clamp(target-state.beta,-math.rad(65)*dt,math.rad(65)*dt)
    end
    -- Cool mode follows a flowing lane line, constrained by the entire angled car footprint.
    -- Farm mode stays on the road's centerline for a stable constant-angle run.
    local lateral=0
    if not farm then
        state.weaveDistance=(state.weaveDistance or 0)+state.speed*dt*(travelScale or 1)
        local footprint=math.sqrt((settings.halfWidth or 3)^2+(settings.halfLength or 5)^2)
        local margin=math.max(0,state.path.width*.5-footprint-2)
        local amplitude=math.min(margin*.65,state.path.width*.14,8*55^2/math.max(state.speed,15)^2)
        state.laneScale=math.min(1,(state.laneScale or 1)+dt*.04)
        amplitude*=state.laneScale
        if settings.offroad then amplitude*=.25 end
        local phase=state.weaveDistance/55
        local wave=amplitude*math.sin(phase)
        local line=math.clamp(curve*60,-1,1)*math.min(margin*.25,2)
        lateral=math.clamp(wave+line,-margin,margin)
        p={x=p.x-math.cos(h)*lateral,y=p.y,z=p.z+math.sin(h)*lateral}
        h+=math.atan2(amplitude/55*math.cos(phase),math.max(.4,1-curve*lateral))
    end
    local orientationBeta=if state.backwards then math.sign(state.beta)*(math.pi-math.abs(state.beta)) else state.beta
    if not farm then
        local wanted=h+orientationBeta
        state.bodyYaw=if state.bodyYaw then state.bodyYaw+math.clamp(wrap(wanted-state.bodyYaw),-2.4*dt,2.4*dt) else wanted
        orientationBeta=wrap(state.bodyYaw-h)
    else state.bodyYaw=nil end
    return {point=p,heading=h,bodyHeading=h+orientationBeta,beta=orientationBeta,speed=state.speed,
        targetAngle=math.deg(state.beta),jumped=jumped,joined=joined,curvature=curve,
        lateral=lateral,backwards=state.backwards==true,reference=if jumped then state.anchor.reference else nil}
end
return Rail

end)()

local Surface = (function()
-- Portable wheel-plane solver. All probes stay near the expected road elevation.
local Surface={}
local function vec(x,y,z) return {x=x,y=y,z=z} end
local function add(a,b) return vec(a.x+b.x,a.y+b.y,a.z+b.z) end
local function sub(a,b) return vec(a.x-b.x,a.y-b.y,a.z-b.z) end
local function mul(a,k) return vec(a.x*k,a.y*k,a.z*k) end
local function dot(a,b) return a.x*b.x+a.y*b.y+a.z*b.z end
local function cross(a,b) return vec(a.y*b.z-a.z*b.y,a.z*b.x-a.x*b.z,a.x*b.y-a.y*b.x) end
local function unit(a)
    local length=math.sqrt(dot(a,a))
    return if length>1e-6 then mul(a,1/length) else vec(0,1,0)
end
local function basis(heading,beta,up)
    local flat=vec(-math.sin(heading),0,-math.cos(heading))
    local travel=unit(sub(flat,mul(up,dot(flat,up))))
    local forward=add(mul(travel,math.cos(beta)),mul(cross(up,travel),math.sin(beta)))
    return forward,unit(cross(forward,up)),travel
end
local function offset(wheel,right,up,forward)
    return add(add(mul(right,wheel.x),mul(up,wheel.y)),mul(forward,-wheel.z))
end
function Surface.expected(reference,x,z)
    local up=reference.up or vec(0,1,0)
    return reference.y-(up.x*(x-reference.x)+up.z*(z-reference.z))/math.max(up.y,.35)
end
function Surface.probe(query,x,z,expected)
    -- The first origin is BELOW a normal tunnel roof. Never scan down from the sky.
    for _,rise in ipairs({.65,1.8}) do
        local hit=query(x,expected+rise,z,6+rise)
        if hit and not hit.offroad and hit.up.y>=.35 and math.abs(hit.y-expected)<=2.4 then return hit end
    end
    return nil
end
function Surface.solve(point,heading,beta,wheels,reference,query)
    if #wheels~=4 then return nil,"Four wheel attachments are required" end
    local expected=if point.y then point.y else Surface.expected(reference,point.x,point.z)
    local center=Surface.probe(query,point.x,point.z,expected)
    if not center then return nil,"Road surface missing at expected elevation" end
    local up=unit(center.up)
    local hits,forward,right,travel
    for _=1,2 do
        forward,right,travel=basis(heading,beta,up)
        hits={}
        for i,w in ipairs(wheels) do
            local o=offset(w,right,up,forward)
            local x,z=point.x+o.x,point.z+o.z
            local guess=center.y-(up.x*(x-point.x)+up.z*(z-point.z))/math.max(up.y,.35)
            local hit=Surface.probe(query,x,z,guess)
            if not hit then return nil,"Road missing below "..w.name end
            hits[i]=hit
        end
        -- Fit pitch and bank from the four actual wheel contacts in chassis coordinates.
        local front=mul(add(hits[1],hits[2]),.5)
        local rear=mul(add(hits[3],hits[4]),.5)
        local left=mul(add(hits[1],hits[3]),.5)
        local rightPoint=mul(add(hits[2],hits[4]),.5)
        local fitted=unit(cross(sub(rightPoint,left),sub(front,rear)))
        if fitted.y<0 then fitted=mul(fitted,-1) end
        if fitted.y<.35 then return nil,"Wheel plane too steep" end
        up=fitted
    end
    forward,right,travel=basis(heading,beta,up)
    local lower,upper,sum=-math.huge,math.huge,0
    for i,w in ipairs(wheels) do
        local o=offset(w,right,up,forward)
        local plane=dot(up,hits[i])-up.x*point.x-up.z*point.z-dot(up,o)
        local reach=w.reach
        -- Keep every tyre within the original suspension's contact/compression range.
        lower=math.max(lower,(plane+math.max(.35,reach-.9))/up.y)
        upper=math.min(upper,(plane+reach-.035)/up.y)
        sum+=(plane+reach-.235)/up.y
    end
    if lower>upper then return nil,"Terrain cannot support all four tyres" end
    local position=vec(point.x,math.clamp(sum/4,lower,upper),point.z)
    local distances={}
    for i,w in ipairs(wheels) do
        distances[i]=dot(up,sub(add(position,offset(w,right,up,forward)),hits[i]))
    end
    return {position=position,up=up,forward=forward,right=right,travel=travel,
        contacts=4,distances=distances,reference={x=center.x,y=center.y,z=center.z,up=up}}
end
Surface.basis=basis
return Surface

end)()

local Elevation = (function()
-- Spatial lookup for the game's replicated 3D race-course elevations.
local Elevation={}
function Elevation.new(paths)
    local index={cells={},count=0}
    for _,path in ipairs(paths) do
        for i=1,#path.points-1 do
            local a,b=path.points[i],path.points[i+1]
            if not a.y or not b.y then continue end
            local dx,dz=b.x-a.x,b.z-a.z
            local length=dx*dx+dz*dz
            if length<.01 or length>2500 then continue end
            local segment={a=a,b=b,dx=dx,dz=dz,length=length}
            for x=math.floor(math.min(a.x,b.x)/16),math.floor(math.max(a.x,b.x)/16) do
                for z=math.floor(math.min(a.z,b.z)/16),math.floor(math.max(a.z,b.z)/16) do
                    local key=x..":"..z
                    index.cells[key]=index.cells[key] or {}
                    table.insert(index.cells[key],segment)
                end
            end
            index.count+=1
        end
    end
    return index
end
function Elevation.height(index,x,z,expected,maximumDelta)
    if not index then return nil end
    local best,score=nil,math.huge
    for ix=math.floor(x/16)-1,math.floor(x/16)+1 do
        for iz=math.floor(z/16)-1,math.floor(z/16)+1 do
            for _,s in ipairs(index.cells[ix..":"..iz] or {}) do
                local t=math.clamp(((x-s.a.x)*s.dx+(z-s.a.z)*s.dz)/s.length,0,1)
                local distance=(x-s.a.x-s.dx*t)^2+(z-s.a.z-s.dz*t)^2
                local y=s.a.y+(s.b.y-s.a.y)*t
                local delta=math.abs(y-expected)
                if distance<=144 and delta<=(maximumDelta or 6) then
                    local value=distance+delta*delta*(if maximumDelta==math.huge then .0001 else .5)
                    if value<score then score=value;best=y end
                end
            end
        end
    end
    return best
end
return Elevation

end)()

-- Roblox client adapter and dashboard. No require(), admin calls, or remote downloads.
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Input = game:GetService("UserInputService")
local GuiService = game:GetService("GuiService")
local HttpService = game:GetService("HttpService")
local World = game:GetService("Workspace")
local player = Players.LocalPlayer
assert(player, "HowToDrift Assist must run on the client")
local playerGui = player:FindFirstChildOfClass("PlayerGui") or player:WaitForChild("PlayerGui", 10)
assert(playerGui, "PlayerGui not ready; join the game first")
local env = if type(getgenv) == "function" then getgenv() else _G
local old = rawget(env, "__HowToDriftAssist")
if type(old) == "table" and type(old.destroy) == "function" then pcall(old.destroy) end

local app = {version = "1.2.0", alive = true, enabled = true, connections = {},
    settings = Controller.settings({mode="road",style="farm",angle=35,cruiseKmh=85}), controller = Controller.new(), lease = InputLease.new(player),
    status = "Autodrive armed; sit in your own car", trace = {}, frames = 0,
    physicsWrites = 0, inputWrites = 0, peakControllerMs = 0, lastControllerMs = 0,
    peakUpdateMs = 0, lastUpdateMs = 0, routes = {},
    direction = 1, roadDirty = true, focused = true, keys = {}, lastError = nil}
env.__HowToDriftAssist = app
local function connect(event, fn)
    local c = event:Connect(fn)
    table.insert(app.connections, c)
    return c
end
local function finiteOrNil(v) return if Controller.finite(v) then v else nil end
local function primitive(value)
    local t = typeof(value)
    return if t == "string" or t == "boolean" or (t == "number" and Controller.finite(value)) then value else tostring(value)
end
local function release()
    app.lease:release()
    app.controller = Controller.new()
    app.rail=nil
    app.lastCommand = nil
end
function app.stop(reason)
    app.enabled = false
    release()
    app.status = reason or "Stopped; normal car controls restored"
end
function app.start()
    release()
    app.enabled = true
    app.lastError = nil
    app.previousS, app.guide, app.guideAt = nil, nil, nil
    app.status = "Waiting for your seated, network-owned car"
end
function app.nearestRoad()
    app.path, app.previousS, app.guide, app.guideAt = nil, nil, nil, nil
    app.direction, app.roadDirty = 1, true
    app.rail=nil
    app.loopAnchor,app.safeAnchor,app.surface=nil,nil,nil
end
function app.setStyle(style)
    app.settings.style=if style=="cool" then "cool" else "farm"
    if app.rail then app.rail.area=nil;app.rail.backwards=false end
end

local root, car, wheels = nil, nil, {}
local wheelGeometry={}
local function calibrateWheels()
    wheelGeometry={}
    for _,a in ipairs(wheels) do
        local front=a.Name:sub(1,1)=="F"
        local ride=car:GetAttribute(if front then "RideHeightF" else "RideHeightR") or 0
        local tire=car:GetAttribute(if front then "TireSize" else "TireSizeR") or car:GetAttribute("TireSize") or 100
        local scale=if tire==85 or tire==90 or tire==95 or tire==100 or tire==105 then tire/100 else 1
        local p=a.Position
        table.insert(wheelGeometry,{name=a.Name,x=p.X,y=p.Y,z=p.Z,reach=.84+ride+1.1*scale})
    end
    local width,length=0,0
    for _,w in ipairs(wheelGeometry) do width=math.max(width,math.abs(w.x));length=math.max(length,math.abs(w.z)) end
    app.settings.halfWidth=width+.8;app.settings.halfLength=length+1.5
end
local carCheckAt, roadCheckAt, traceAt, uiAt, obstacleAt = -math.huge, -math.huge, -math.huge, -math.huge, -math.huge
local groundParams, obstacleParams = RaycastParams.new(), RaycastParams.new()
groundParams.FilterType, obstacleParams.FilterType = Enum.RaycastFilterType.Exclude, Enum.RaycastFilterType.Exclude
groundParams.IgnoreWater, obstacleParams.IgnoreWater = true, true
groundParams.RespectCanCollide, obstacleParams.RespectCanCollide = true, true
local function findCar(now)
    local home=car and car:GetAttribute("HomeCF")
    local homeMoved=typeof(home)=="CFrame" and (
        (typeof(app.homeTransform)=="CFrame" and (home.Position-app.homeTransform.Position).Magnitude>500)
        or (app.homeInitialized and typeof(app.homeTransform)~="CFrame"))
    if now < carCheckAt and root and root.Parent and car and car.Parent and not homeMoved then return end
    carCheckAt = now + 0.5
    local found
    local cars = World:FindFirstChild("Cars")
    if cars then
        for _, model in ipairs(cars:GetChildren()) do
            if model:IsA("Model") and model:GetAttribute("OwnerUserId") == player.UserId then found = model; break end
        end
    end
    if found ~= car or (found and (not root or not root.Parent)) then
        release()
        car, root, wheels = found, nil, {}
        app.loopAnchor,app.safeAnchor,app.surface=nil,nil,nil
        app.previousS, app.guide, app.guideAt, app.path = nil, nil, nil, nil
        if found then
            local chassis = found:FindFirstChild("Chassis")
            if chassis and chassis:IsA("BasePart") then
                root = chassis
                for _, name in ipairs({"FL", "FR", "RL", "RR"}) do
                    local attachment = root:FindFirstChild(name)
                    if attachment and attachment:IsA("Attachment") then table.insert(wheels, attachment) end
                end
            end
        end
    end
    if homeMoved then app.nearestRoad() end
    app.homeTransform=car and car:GetAttribute("HomeCF")
    app.homeInitialized=car~=nil
    if root then calibrateWheels() end
    local filter = {}
    if cars then table.insert(filter, cars) end
    for _,p in ipairs(Players:GetPlayers()) do if p.Character then table.insert(filter,p.Character) end end
    groundParams.FilterDescendantsInstances = filter
    local obstacleFilter = {}
    if car then table.insert(obstacleFilter, car) end
    if player.Character then table.insert(obstacleFilter, player.Character) end
    obstacleParams.FilterDescendantsInstances = obstacleFilter
end

local minimapCache, watched = {}, {}
local raceName, raceText, racePath = nil, nil, nil
local courseCache={}
local function refreshRoads(now)
    local currentRace = player:GetAttribute("RaceCourse")
    if now < roadCheckAt and not app.roadDirty and currentRace == raceName then return end
    roadCheckAt, app.roadDirty = now + 2, false
    local paths, seen = {}, {}
    local minimap = ReplicatedStorage:FindFirstChild("Minimap")
    if minimap then
        for _, value in ipairs(minimap:GetChildren()) do
            if not value:IsA("StringValue") then continue end
            seen[value] = true
            local cached = minimapCache[value]
            if not cached or cached.text ~= value.Value then
                cached = {text = value.Value, paths = Roads.parseMinimap(value.Value, value.Name)}
                minimapCache[value] = cached
                if not watched[value] then
                    watched[value] = true
                    connect(value:GetPropertyChangedSignal("Value"), function() app.roadDirty = true end)
                end
            end
            for _, path in ipairs(cached.paths) do if #paths < 128 then table.insert(paths, path) end end
        end
    end
    -- Some maps expose road lines locally but are absent from the replicated minimap folder.
    for _,map in ipairs(World:GetChildren()) do
        if not map:IsA("Model") and not map:IsA("Folder") then continue end
        local value=map:FindFirstChild("MinimapLines") or map:FindFirstChild("MinimapPath")
        if value and value:IsA("StringValue") then
            seen[value]=true
            local cached=minimapCache[value]
            if not cached or cached.text~=value.Value then
                local data=value.Value
                if not data:find("|",1,true) then data="line|36|"..data end
                cached={text=value.Value,paths=Roads.parseMinimap(data,map.Name)}
                minimapCache[value]=cached
            end
            for _,path in ipairs(cached.paths) do if #paths<128 then table.insert(paths,path) end end
        end
    end
    for value in pairs(minimapCache) do if not seen[value] then minimapCache[value] = nil end end
    local courses = ReplicatedStorage:FindFirstChild("RaceCourses")
    local course = if type(currentRace) == "string" and courses then courses:FindFirstChild(currentRace) else nil
    local points = course and course:FindFirstChild("Points")
    local text = if points and points:IsA("StringValue") then points.Value else nil
    if currentRace ~= raceName or text ~= raceText then
        raceName, raceText = currentRace, text
        racePath = if text then Roads.parseRace(text, "Race "..currentRace, course:GetAttribute("Width")) else nil
        if racePath then
            local startS, length = course:GetAttribute("StartD"), course:GetAttribute("Length")
            if Controller.finite(startS) and Controller.finite(length) then
                racePath.finishS = math.clamp(startS + length, 0, racePath.total)
            end
        end
        if app.settings.mode == "road" then
            app.path, app.previousS, app.guide, app.guideAt = nil, nil, nil, nil
        end
    end
    local elevationChanged=false
    local coursePaths,courseSeen={},{}
    if courses then
        for _,folder in ipairs(courses:GetChildren()) do
            local pointsValue=folder:FindFirstChild("Points")
            if pointsValue and pointsValue:IsA("StringValue") then
                courseSeen[folder]=true
                local cached=courseCache[folder]
                if not cached or cached.text~=pointsValue.Value then
                    cached={text=pointsValue.Value,path=Roads.parseRace(pointsValue.Value,folder.Name,folder:GetAttribute("Width"))}
                    courseCache[folder]=cached;elevationChanged=true
                end
                if cached.path then table.insert(coursePaths,cached.path) end
            end
        end
    end
    for folder in pairs(courseCache) do if not courseSeen[folder] then courseCache[folder]=nil;elevationChanged=true end end
    if elevationChanged or not app.elevation then app.elevation=Elevation.new(coursePaths) end
    app.routes = paths
    app.racePath = racePath
    if app.path and not table.find(paths, app.path) and app.path ~= racePath then
        app.path, app.previousS, app.guide, app.guideAt = nil, nil, nil, nil
    end
    if app.loopAnchor and not table.find(paths,app.loopAnchor.path) and app.loopAnchor.path~=racePath then app.loopAnchor=nil end
    if app.safeAnchor and not table.find(paths,app.safeAnchor.path) and app.safeAnchor.path~=racePath then app.safeAnchor=nil end
end

local function readInput()
    local function down(a, b)
        return Input:IsKeyDown(Enum.KeyCode[a]) or (b ~= nil and Input:IsKeyDown(Enum.KeyCode[b]))
    end
    local throttle, brake = if down("W", "Up") then 1 else 0, if down("S", "Down") then 1 else 0
    local steer = (if down("D", "Right") then 1 else 0) - (if down("A", "Left") then 1 else 0)
    local handbrake = down("Space")
    if Input.GamepadEnabled then
        local ok, state = pcall(Input.GetGamepadState, Input, Enum.UserInputType.Gamepad1)
        if ok then
            for _, key in ipairs(state) do
                if key.KeyCode == Enum.KeyCode.Thumbstick1 and math.abs(key.Position.X) > 0.15 then steer = key.Position.X end
                if key.KeyCode == Enum.KeyCode.ButtonR2 then throttle = math.max(throttle, key.Position.Z) end
                if key.KeyCode == Enum.KeyCode.ButtonL2 then brake = math.max(brake, key.Position.Z) end
                if key.KeyCode == Enum.KeyCode.ButtonA and key.UserInputState == Enum.UserInputState.Begin then handbrake = true end
            end
        end
    end
    return {throttle = throttle, brake = brake, steer = steer, handbrake = handbrake,
        boost = down("LeftShift", "RightShift")}
end

local function sampleCar()
    if not root or not car then return nil, "Spawn / enter your own car" end
    if car:GetAttribute("OwnerUserId")~=player.UserId then return nil, "Waiting for your own car" end
    local humanoid = player.Character and player.Character:FindFirstChildOfClass("Humanoid")
    if not humanoid or not humanoid.SeatPart or not humanoid.SeatPart:IsDescendantOf(car) then return nil, "Sit in your own car" end
    if car:GetAttribute("NetOwner") ~= player.UserId then return nil, "Waiting for your car's network ownership" end
    if root.Anchored then return nil, "Car is anchored / parked" end
    local cf, velocity, angular = root.CFrame, root.AssemblyLinearVelocity, root.AssemblyAngularVelocity
    local mass = root.AssemblyMass
    if not Controller.finite(mass) or mass <= 0 then return nil, "Invalid car mass" end
    local count = 0
    local floorX,floorY,floorZ,normalX,normalY,normalZ=0,0,0,0,0,0
    for _, attachment in ipairs(wheels) do
        local front = attachment.Name:sub(1,1) == "F"
        local ride = car:GetAttribute(if front then "RideHeightF" else "RideHeightR")
        local tire = car:GetAttribute(if front then "TireSize" else "TireSizeR")
        if not front and tire==nil then tire=car:GetAttribute("TireSize") end
        local scale = if tire==85 or tire==90 or tire==95 or tire==100 or tire==105 then tire/100 else 1
        -- Match the uploaded suspension rest + ride height + tyre radius, with 5 cm tolerance.
        local reach = 0.84 + (if Controller.finite(ride) then math.clamp(ride, -0.6, 1.5) else 0) + 1.1*scale + 0.05
        local hit = World:Raycast(attachment.WorldPosition, -cf.UpVector*reach, groundParams)
        if hit and hit.Normal.Y > 0.35 then
            count+=1;floorX+=hit.Position.X;floorY+=hit.Position.Y;floorZ+=hit.Position.Z
            normalX+=hit.Normal.X;normalY+=hit.Normal.Y;normalZ+=hit.Normal.Z
        end
    end
    return {x = root.Position.X, y = root.Position.Y, z = root.Position.Z,
        vx = velocity.X, vz = velocity.Z, vy = velocity.Y,
        yaw = math.atan2(-cf.LookVector.X, -cf.LookVector.Z), yawRate = angular.Y,
        grounded = count, upY = cf.UpVector.Y, mass = mass,
        forwardSpeed=velocity:Dot(cf.LookVector),sideSpeed=velocity:Dot(cf.RightVector),
        floor=if count>=3 then {x=floorX/count,y=floorY/count,z=floorZ/count,
            up={x=normalX/count,y=normalY/count,z=normalZ/count}} else nil}
end

local palette = {bg = Color3.fromRGB(17,21,29), panel = Color3.fromRGB(27,33,45),
    ink = Color3.fromRGB(235,241,250), dim = Color3.fromRGB(153,170,190),
    accent = Color3.fromRGB(61,196,177), red = Color3.fromRGB(177,65,80)}
local function make(class, props, parent)
    local o = Instance.new(class)
    for k, v in pairs(props) do o[k] = v end
    o.Parent = parent
    return o
end
local function corner(parent, radius) make("UICorner", {CornerRadius=UDim.new(0,radius or 8)}, parent) end
local gui = make("ScreenGui", {Name="HowToDriftAssist", ResetOnSpawn=false, IgnoreGuiInset=true,
    DisplayOrder=95, ZIndexBehavior=Enum.ZIndexBehavior.Sibling}, playerGui)
app.gui = gui
local panel = make("Frame", {Name="Panel", Size=UDim2.fromOffset(364,520),
    Position=UDim2.new(1,-382,0,80), BackgroundColor3=palette.bg, BorderSizePixel=0}, gui)
corner(panel,12)
local scale = make("UIScale", {Scale=1}, panel)
local header = make("TextLabel", {Name="Header", Size=UDim2.new(1,-80,0,46), Position=UDim2.fromOffset(14,0),
    BackgroundTransparency=1, Text="DRIFT ASSIST  1.2.0", TextColor3=palette.ink,
    TextSize=17, Font=Enum.Font.GothamBold, TextXAlignment=Enum.TextXAlignment.Left, Active=true}, panel)
local function button(name, text, position, size, parent, callback)
    local b = make("TextButton", {Name=name, Text=text, Position=position, Size=size, BackgroundColor3=palette.panel,
        BorderSizePixel=0, TextColor3=palette.ink, TextSize=13, Font=Enum.Font.GothamBold, AutoButtonColor=true}, parent)
    corner(b,7)
    connect(b.Activated, callback)
    return b
end
local minimized = false
local body = make("ScrollingFrame", {Name="Body", Position=UDim2.fromOffset(12,48), Size=UDim2.new(1,-24,1,-60),
    BackgroundTransparency=1, BorderSizePixel=0, ScrollBarThickness=3, CanvasSize=UDim2.fromOffset(0,535),
    ScrollingDirection=Enum.ScrollingDirection.Y}, panel)
button("Minimize", "_", UDim2.new(1,-69,0,9), UDim2.fromOffset(27,27), panel, function()
    minimized = not minimized
    body.Visible = not minimized
    panel.Size = UDim2.fromOffset(364, if minimized then 46 else 520)
end)
button("Close", "x", UDim2.new(1,-36,0,9), UDim2.fromOffset(27,27), panel, function() app.destroy() end)
local startButton = button("Start", "Start  [F6]", UDim2.fromOffset(0,0), UDim2.new(1,-6,0,38), body, function()
    if app.enabled then app.stop() else app.start() end
end)
local modeButton = button("Mode", "Farm mode", UDim2.fromOffset(0,46), UDim2.new(0.5,-4,0,34), body, function()
    app.setStyle(if app.settings.style=="farm" then "cool" else "farm")
end)
local travelButton=button("FarmTravel", "Farm: Loop", UDim2.new(.5,3,0,46), UDim2.new(.5,-9,0,34), body,function()
    app.settings.farmTravel=if app.settings.farmTravel=="loop" then "area" else "loop"
    if app.rail then app.rail.area=nil;app.rail.backwards=false end
end)
local sideButton = button("Side", "Reverse", UDim2.new(0.62,3,0,85), UDim2.new(0.38,-9,0,30), body, function()
    app.direction=-app.direction
    if app.rail then Rail.reverse(app.rail,app.settings.style=="farm" and app.settings.farmTravel=="area") end
    app.guideAt=nil
end)
button("Rejoin","Rejoin nearest road [F7]",UDim2.fromOffset(0,85),UDim2.new(.62,-4,0,30),body,app.nearestRoad)
local sliderRefresh = {}
local draggingSlider, draggingPanel
local function slider(key, label, low, high, increment, suffix, y)
    local row = make("Frame", {Name=key, BackgroundTransparency=1, Position=UDim2.fromOffset(0,y), Size=UDim2.new(1,-6,0,58)}, body)
    make("TextLabel", {BackgroundTransparency=1, Size=UDim2.new(1,-92,0,24), Text=label,
        TextColor3=palette.dim, TextSize=13, Font=Enum.Font.Gotham, TextXAlignment=Enum.TextXAlignment.Left}, row)
    local value = make("TextBox", {Name="Value", Position=UDim2.new(1,-89,0,0), Size=UDim2.fromOffset(87,25),
        BackgroundColor3=palette.panel, BorderSizePixel=0, TextColor3=palette.ink, TextSize=13,
        Font=Enum.Font.GothamBold, ClearTextOnFocus=false}, row)
    corner(value,5)
    local track = make("TextButton", {Name="Track", Position=UDim2.fromOffset(0,36), Size=UDim2.new(1,-4,0,7),
        Text="", BackgroundColor3=palette.panel, BorderSizePixel=0, AutoButtonColor=false}, row)
    corner(track,4)
    local fill = make("Frame", {Size=UDim2.fromScale(0,1), BackgroundColor3=palette.accent, BorderSizePixel=0}, track)
    corner(fill,4)
    local knob = make("Frame", {Size=UDim2.fromOffset(13,13), AnchorPoint=Vector2.new(0.5,0.5),
        Position=UDim2.fromScale(0,0.5), BackgroundColor3=palette.ink, BorderSizePixel=0}, track)
    corner(knob,7)
    local function refresh()
        local fraction = (app.settings[key]-low)/(high-low)
        fill.Size, knob.Position = UDim2.fromScale(fraction,1), UDim2.fromScale(fraction,0.5)
        if not value:IsFocused() then
            value.Text = if key=="angle" and app.settings.style=="farm" then "60 auto" else string.format(if increment >= 1 then "%.0f%s" else "%.2f%s", app.settings[key], suffix)
        end
        value.TextEditable=key~="angle" or app.settings.style~="farm"
    end
    local function set(v)
        if key=="angle" and app.settings.style=="farm" then refresh();return end
        if Controller.finite(v) then
            app.settings[key] = math.clamp(math.floor(v/increment+0.5)*increment, low, high)
        end
        refresh()
    end
    local function drag(x)
        local fraction = math.clamp((x-track.AbsolutePosition.X)/math.max(track.AbsoluteSize.X,1),0,1)
        set(low+(high-low)*fraction)
    end
    connect(track.InputBegan, function(input)
        if input.UserInputType == Enum.UserInputType.MouseButton1 or input.UserInputType == Enum.UserInputType.Touch then
            draggingSlider = {input=input, drag=drag}
            drag(input.Position.X)
        end
    end)
    connect(value.FocusLost, function() set(tonumber(value.Text:match("[%-%d%.]+"))) end)
    sliderRefresh[key] = refresh
    refresh()
end
slider("angle", "Cool maximum angle / Farm auto", 15,75,1," deg",125)
slider("cruiseKmh", "Speed (Farm: 25+ km/h)",20,500,1," km/h",183)
slider("farmRange", "Farm area length (studs)",20,300,1,"",241)
local status = make("TextLabel", {Name="Status", Position=UDim2.fromOffset(0,305), Size=UDim2.new(1,-8,0,61),
    BackgroundTransparency=1, Text=app.status, TextWrapped=true, TextYAlignment=Enum.TextYAlignment.Top,
    TextXAlignment=Enum.TextXAlignment.Left, Font=Enum.Font.Gotham, TextSize=13, TextColor3=palette.dim}, body)
local telemetry = make("TextLabel", {Name="Telemetry", Position=UDim2.fromOffset(0,370), Size=UDim2.new(1,-8,0,59),
    BackgroundTransparency=1, Text="No car telemetry", TextWrapped=true, TextYAlignment=Enum.TextYAlignment.Top,
    TextXAlignment=Enum.TextXAlignment.Left, Font=Enum.Font.Code, TextSize=12, TextColor3=palette.ink}, body)

function app.report()
    local attributes = {}
    if car then
        for _, name in ipairs({"OwnerUserId","NetOwner","CarId","EngineStage","Turbo","WeightStage","TyreStage",
            "DriftAssist","Drivetrain","RideHeightF","RideHeightR","SteerLock","TireSize","TireSizeR"}) do
            local value = car:GetAttribute(name)
            if value ~= nil then attributes[name] = primitive(value) end
        end
    end
    local settings = Controller.settings(app.settings)
    return {version=app.version, place_id=game.PlaceId, enabled=app.enabled, status=app.status,
        settings=settings, car=if car then car.Name else nil, attributes=attributes,
        admin_granted=player:GetAttribute("Admin")==true, route=if app.path then app.path.name else nil,
        route_count=#app.routes, direction=app.direction, last_sample=app.lastSample, last_command=app.lastCommand,
        last_obstacle=app.lastObstacle, last_error=app.lastError, controller_frames=app.frames,
        physics_writes=app.physicsWrites, input_writes=app.inputWrites, last_controller_ms=app.lastControllerMs,
        peak_controller_ms=app.peakControllerMs, last_update_ms=app.lastUpdateMs, peak_update_ms=app.peakUpdateMs, trace=app.trace,
        recoveries=app.recoveries or 0, last_surface_error=app.lastSurfaceError,last_surface_error_at=app.lastSurfaceErrorAt,
        surface=if app.surface then {position=app.surface.position,normal=app.surface.up,contacts=app.surface.contacts,
            wheel_distances=app.surface.distances} else nil,
        drift_pay=player:GetAttribute("DriftPay"),drift_pay_why=player:GetAttribute("DriftPayWhy"),
        elevation_segments=app.elevation and app.elevation.count,
        note="Farm/Cool kinematic autopilot. Farm uses the client angle bonus cap at 60 degrees. Server payouts and live contact are not guaranteed."}
end
button("Diagnostics", "Save diagnostics", UDim2.fromOffset(0,438), UDim2.new(1,-6,0,33), body, function()
    local ok, text = pcall(function() return HttpService:JSONEncode(app.report()) end)
    if not ok then app.status = "Diagnostics encode failed: "..tostring(text); return end
    if type(writefile) == "function" then
        local saved, err = pcall(writefile, "HowToDrift_Diagnostics.json", text)
        app.status = if saved then "Saved HowToDrift_Diagnostics.json in executor workspace" else "Save failed: "..tostring(err)
    elseif type(setclipboard) == "function" then
        local copied = pcall(setclipboard, text)
        app.status = if copied then "Diagnostics copied to clipboard" else "Clipboard unavailable"
    else
        print(text)
        app.status = "File writing unavailable; diagnostics printed in F9 console"
    end
end)
make("TextLabel", {Name="Help", Position=UDim2.fromOffset(0,482), Size=UDim2.new(1,-8,0,57),
    BackgroundTransparency=1, Text="F6 Start/Stop | F7 Rejoin | S / Space Brake\nFarm: fixed 60 deg, Loop or Area reverse.\nCool: flowing lane line, automatic corner speed.",
    TextWrapped=true, TextYAlignment=Enum.TextYAlignment.Top, TextXAlignment=Enum.TextXAlignment.Left,
    Font=Enum.Font.Gotham, TextSize=11, TextColor3=palette.dim}, body)

connect(header.InputBegan, function(input)
    if input.UserInputType == Enum.UserInputType.MouseButton1 or input.UserInputType == Enum.UserInputType.Touch then
        draggingPanel = {input=input, position=input.Position, origin=panel.Position}
    end
end)
connect(Input.InputChanged, function(input)
    if draggingSlider and (input == draggingSlider.input or input.UserInputType == Enum.UserInputType.MouseMovement) then
        draggingSlider.drag(input.Position.X)
    elseif draggingPanel and (input == draggingPanel.input or input.UserInputType == Enum.UserInputType.MouseMovement) then
        local delta = input.Position-draggingPanel.position
        local origin = draggingPanel.origin
        panel.Position = UDim2.new(origin.X.Scale,origin.X.Offset+delta.X,origin.Y.Scale,origin.Y.Offset+delta.Y)
    end
end)
connect(Input.InputEnded, function(input)
    if input.UserInputType == Enum.UserInputType.MouseButton1 or input.UserInputType == Enum.UserInputType.Touch then
        if draggingSlider and (input == draggingSlider.input or input.UserInputType == Enum.UserInputType.MouseButton1) then draggingSlider = nil end
        if draggingPanel and (input == draggingPanel.input or input.UserInputType == Enum.UserInputType.MouseButton1) then draggingPanel = nil end
    end
end)
connect(Input.InputBegan, function(input, processed)
    if processed or Input:GetFocusedTextBox() then return end
    if input.KeyCode == Enum.KeyCode.F6 then if app.enabled then app.stop() else app.start() end
    elseif input.KeyCode == Enum.KeyCode.F7 then app.nearestRoad()
    end
end)
connect(Input.WindowFocusReleased, function() app.focused=false; app.lease:release() end)
connect(Input.WindowFocused, function() app.focused=true end)
connect(player.CharacterRemoving, function() release(); carCheckAt=-math.huge end)

local function frame(dt)
    local now = os.clock()
    if now-uiAt > 0.1 then
        uiAt = now
        startButton.Text = if app.enabled then "Stop  [F6]" else "Start  [F6]"
        startButton.BackgroundColor3 = if app.enabled then palette.red else palette.accent
        modeButton.Text = if app.settings.style=="farm" then "Farm mode" else "Cool mode"
        travelButton.Text = if app.settings.farmTravel=="area" then "Farm: Area reverse" else "Farm: Loop"
        sideButton.Text = "Reverse"
        for _,refresh in pairs(sliderRefresh) do refresh() end
        status.Text = app.status
        local s, cmd = app.lastSample, app.lastCommand
        if s then
            local m = Controller.measure(s)
            telemetry.Text = if m then string.format("%.1f km/h | angle %+.1f / %+.1f deg\nRoad: %s\nGround %d/4 | controller %.2f ms",m.speed*1.2,
                math.deg(m.beta),cmd and cmd.targetAngle or 0,app.path and app.path.name or "none",s.grounded,app.lastControllerMs) else "Invalid telemetry"
        else telemetry.Text="No seated car telemetry" end
        local camera = World.CurrentCamera
        if camera then scale.Scale=math.clamp(math.min(camera.ViewportSize.Y/720,camera.ViewportSize.X/600),0.5,1) end
    end
    if not app.enabled then return end
    findCar(now)
    local sample, reason = sampleCar()
    if not sample then release(); app.status=reason; app.lastSample=nil; return end
    app.lastSample = sample
    local pause
    if not app.focused then pause="Paused while game is unfocused"
    elseif Input:GetFocusedTextBox() then pause="Paused while typing"
    elseif GuiService.MenuIsOpen then pause="Paused in Roblox menu"
    elseif player:GetAttribute("InGarage") then pause="Paused in garage"
    elseif player:GetAttribute("Replaying") or player:GetAttribute("Spectating") then pause="Paused during replay / spectating"
    elseif dt > 0.2 then pause="Paused after a long frame" end
    local goAt=player:GetAttribute("RaceGoAt")
    if Controller.finite(goAt) and World:GetServerTimeNow()<goAt then pause="Waiting for race countdown" end
    local externalInput=player:GetAttribute("DebugInput")
    if externalInput~=nil and externalInput~=app.lease.last then
        app.stop("Another controller owns DebugInput; stop it before starting this one")
        return
    end
    if pause then app.lease:release(); app.status=pause; return end
    local input = readInput()
    refreshRoads(now)
    if not app.path then
        if app.racePath then app.path,app.direction=app.racePath,1
        else app.path,app.direction=Roads.nearest(app.routes,sample,sample.yaw) end
        app.direction=app.direction or 1
    end
    if not app.path then
        release();app.status="Waiting for road data; drive near a loaded road"
        return
    end
    local started=os.clock()
    if not app.rail or app.rail.path~=app.path then
        local projection=Roads.project(app.path,sample,nil,sample.yaw)
        if not projection then release();app.status="Waiting for a valid road";return end
        app.rail=Rail.new(app.path,projection,app.direction)
        app.recoveries=(app.recoveries or 0)+1
    end
    local function query(x,y,z,length)
        local hit=World:Raycast(Vector3.new(x,y,z),Vector3.new(0,-length,0),groundParams)
        if not hit then return nil end
        local offroad=hit.Material==Enum.Material.Grass or hit.Material==Enum.Material.LeafyGrass or hit.Material==Enum.Material.Mud
        return {x=hit.Position.X,y=hit.Position.Y,z=hit.Position.Z,
            up={x=hit.Normal.X,y=hit.Normal.Y,z=hit.Normal.Z},offroad=offroad}
    end
    local reference=if app.surface then app.surface.reference else sample.floor
    if not reference then
        reference={x=sample.x,y=sample.y-2,z=sample.z,up={x=0,y=1,z=0}}
    end
    if not app.loopAnchor then
        local home=car:GetAttribute("HomeCF")
        local homePosition=if typeof(home)=="CFrame" then home.Position else nil
        local anchorPath,anchorDirection,projection=app.path,app.direction,nil
        if homePosition and (homePosition-root.Position).Magnitude<5000 then
            anchorPath,anchorDirection,projection=Roads.nearest(app.routes,
                {x=homePosition.X,y=homePosition.Y-2,z=homePosition.Z},math.atan2(-home.LookVector.X,-home.LookVector.Z))
            if projection and projection.distance>30 then projection=nil end
        end
        if projection then
            app.loopAnchor={path=anchorPath,s=projection.s,direction=anchorDirection,
                reference={x=projection.x,y=homePosition.Y-2,z=projection.z,up={x=0,y=1,z=0}}}
        else
            app.loopAnchor={path=app.path,s=app.rail.s,direction=app.rail.direction,reference=reference}
        end
    end
    app.rail.anchor=app.loopAnchor
    app.settings.offroad=player:GetAttribute("DriftPayWhy")=="offroad"
    local oldPlan=table.clone(app.rail)
    local up=reference.up
    local _,planHeading=Roads.point(app.rail.path,app.rail.s)
    local slope=-(up.x*(-math.sin(planHeading))+up.z*(-math.cos(planHeading)))/math.max(up.y,.35)
    local travelScale=1/math.sqrt(1+slope*slope)
    local pose=Rail.step(app.rail,app.settings,dt,input.brake>.1 or input.handbrake,app.routes,travelScale)
    if pose.reference then reference=pose.reference end
    local expected=if pose.point.y then pose.point.y else Surface.expected(reference,pose.point.x,pose.point.z)
    local hint=Elevation.height(app.elevation,pose.point.x,pose.point.z,expected,if app.surface then 6 else math.huge)
    if hint and not pose.point.y and (not app.surface or math.abs(hint-expected)<1.25) then
        reference={x=pose.point.x,y=hint,z=pose.point.z,up=reference.up}
    end
    local surface,why=Surface.solve(pose.point,pose.heading,pose.beta,wheelGeometry,reference,query)
    if not surface then app.lastSurfaceError,app.lastSurfaceErrorAt=why,now end
    if not surface and app.settings.style=="cool" then
        -- A flowing line can approach a narrow verge. Retry the center before leaving the pavement.
        local center,h=Roads.point(app.rail.path,app.rail.s)
        if app.rail.direction<0 then h+=math.pi end
        local originalReference=if app.surface then app.surface.reference else reference
        surface,why=Surface.solve(center,h,pose.beta,wheelGeometry,originalReference,query)
        if surface then
            pose.point,pose.heading,pose.lateral=center,h,0
            app.rail.laneScale=math.min(app.rail.laneScale or 1,.25)
        end
    end
    if not surface and pose.joined then
        -- A geometric connection may lead into unloaded or unsupported terrain. Try another exit.
        Rail.rejectConnection(oldPlan,app.rail.path)
        app.rail.rejected=oldPlan.rejected
    end
    if not surface then
        app.surfaceBlockedSince=app.surfaceBlockedSince or now
    else app.surfaceBlockedSince=nil end
    local recover=app.settings.style=="farm" or pose.jumped or (app.surfaceBlockedSince and now-app.surfaceBlockedSince>.5)
    if not surface and recover and app.safeAnchor then
        -- Retry a validated part of this map instead of waiting at a broken segment forever.
        Rail.home(app.rail)
        local saved=app.rail.anchor
        app.rail.path,app.rail.s,app.rail.direction=app.safeAnchor.path,app.safeAnchor.s,app.safeAnchor.direction
        local p,h=Roads.point(app.rail.path,app.rail.s)
        if app.rail.direction<0 then h+=math.pi end
        pose.point,pose.heading,pose.jumped=p,h,true
        surface,why=Surface.solve(p,h,pose.beta,wheelGeometry,app.safeAnchor.reference,query)
        if app.settings.style=="cool" then app.rail.speed=0;pose.speed=0 end
        app.rail.anchor=saved
    end
    if not surface then
        app.rail=oldPlan
        app.lastSurfaceError=why
        app.lease:release()
        root.AssemblyLinearVelocity=Vector3.zero
        app.status="Waiting for road at its known height: "..tostring(why)
        return
    end
    app.surfaceBlockedSince=nil
    app.surface=surface
    app.path,app.direction=app.rail.path,app.rail.direction
    if not app.safeAnchor then
        app.safeAnchor={path=app.path,s=app.rail.s,direction=app.direction,reference=surface.reference}
    end
    if app.loopAnchor.path==app.path and math.abs(app.loopAnchor.s-app.rail.s)<6 then
        app.loopAnchor.reference=surface.reference
    end
    local p=surface.position
    local targetPosition=Vector3.new(p.x,p.y,p.z)
    local r,n,f=surface.right,surface.up,surface.forward
    local targetCF=CFrame.fromMatrix(targetPosition,Vector3.new(r.x,r.y,r.z),Vector3.new(n.x,n.y,n.z),Vector3.new(-f.x,-f.y,-f.z))
    local gap=(root.Position-targetPosition).Magnitude
    if gap>10 or sample.upY<.55 or pose.jumped then app.recoveries=(app.recoveries or 0)+1 end
    local ok,err=app.lease:write({throttle=if pose.speed>2 then .6 else 0,brake=0,steer=0,handbrake=false})
    if not ok then app.stop(err);return end
    car:PivotTo(targetCF*root.CFrame:Inverse()*car:GetPivot())
    local v=surface.travel
    root.AssemblyLinearVelocity=Vector3.new(v.x,v.y,v.z)*pose.speed
    root.AssemblyAngularVelocity=Vector3.zero
    app.physicsWrites+=1;app.inputWrites+=1;app.frames+=1
    app.status=(if app.settings.style=="cool" then "Cool line: " elseif app.settings.farmTravel=="area" then "Farm area: " else "Farm loop: ")..app.path.name
    app.lastCommand={targetAngle=pose.targetAngle,targetKmh=pose.speed*1.2,override=true,reason=app.status,
        lateral=pose.lateral,contacts=surface.contacts,backwards=pose.backwards,loops=app.rail.loops,connections=app.rail.links}
    local command=app.lastCommand
    local guide=nil
    app.lastControllerMs=(os.clock()-started)*1000
    app.peakControllerMs=math.max(app.peakControllerMs,app.lastControllerMs)
    if now-traceAt>=0.5 then
        traceAt=now
        local m=Controller.measure(sample)
        table.insert(app.trace,{at=now,speed_kmh=m and m.speed*1.2,angle=m and math.deg(m.beta),target_angle=command.targetAngle,
            grounded=sample.grounded,status=app.status,cross_track=guide and finiteOrNil(guide.crossTrack)})
        if #app.trace>240 then table.remove(app.trace,1) end
    end
end

function app.destroy()
    if not app.alive then return end
    app.stop()
    app.alive=false
    for _, c in ipairs(app.connections) do pcall(function() c:Disconnect() end) end
    gui:Destroy()
    if rawget(env,"__HowToDriftAssist")==app then env.__HowToDriftAssist=nil end
end
connect(gui.AncestryChanged,function(_,parent) if not parent then app.destroy() end end)
connect(RunService.PreSimulation,function(dt)
    if not app.alive then return end
    local started=os.clock()
    local ok,err=xpcall(function() frame(dt) end,function(message) return tostring(message) end)
    app.lastUpdateMs=(os.clock()-started)*1000
    app.peakUpdateMs=math.max(app.peakUpdateMs,app.lastUpdateMs)
    if not ok then
        app.lastError=tostring(err)
        app.stop("Stopped after error: "..tostring(err))
        warn("[HowToDrift Assist] "..tostring(err))
    end
end)
print("[HowToDrift Assist 1.2.0] Farm/Cool autopilot armed. F6 Stop/Start; F7 Rejoin. Farm Loop / Area reverse; speed up to 500 km/h.")
