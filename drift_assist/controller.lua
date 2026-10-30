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
