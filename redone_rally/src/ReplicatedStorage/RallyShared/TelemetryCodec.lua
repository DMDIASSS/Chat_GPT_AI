--!strict
-- TelemetryCodec.luau
-- 20 Hz rally telemetry recorder, interpolator, and codec.
-- Records CFrame, velocity, steering angle, throttle, gear, and RPM for replay and PB ghost cars.

export type TelemetryFrame = {
    Time: number,
    Position: Vector3,
    Rotation: CFrame, -- Orientation only
    Velocity: Vector3,
    Steer: number,
    Throttle: number,
    RPM: number,
    Gear: number,
}

export type RunTelemetry = {
    CarId: string,
    TotalTime: number,
    StageSeed: number,
    Frames: { TelemetryFrame },
}

local TelemetryCodec = {}

-- Sample rate: 20 Hz (0.05 seconds per frame)
TelemetryCodec.SAMPLE_INTERVAL = 0.05

function TelemetryCodec.CreateFrame(
    time: number,
    cframe: CFrame,
    velocity: Vector3,
    steer: number,
    throttle: number,
    rpm: number,
    gear: number
): TelemetryFrame
    return {
        Time = time,
        Position = cframe.Position,
        Rotation = cframe.Rotation,
        Velocity = velocity,
        Steer = steer,
        Throttle = throttle,
        RPM = rpm,
        Gear = gear,
    }
end

-- Interpolates between two recorded telemetry frames at query time t
function TelemetryCodec.SampleAt(run: RunTelemetry, t: number): (CFrame, Vector3, number, number)
    local frames = run.Frames
    local count = #frames
    if count == 0 then
        return CFrame.identity, Vector3.zero, 0, 1000
    end
    if t <= frames[1].Time then
        local f = frames[1]
        return CFrame.new(f.Position) * f.Rotation, f.Velocity, f.Steer, f.RPM
    end
    if t >= frames[count].Time then
        local f = frames[count]
        return CFrame.new(f.Position) * f.Rotation, f.Velocity, f.Steer, f.RPM
    end
    
    -- Binary search for enclosing keyframes
    local low = 1
    local high = count
    while low <= high do
        local mid = math.floor((low + high) * 0.5)
        if frames[mid].Time < t then
            low = mid + 1
        else
            high = mid - 1
        end
    end
    
    local idxA = math.clamp(high, 1, count - 1)
    local idxB = idxA + 1
    local fA = frames[idxA]
    local fB = frames[idxB]
    
    local span = fB.Time - fA.Time
    local alpha = (span > 1e-4) and ((t - fA.Time) / span) or 0
    alpha = math.clamp(alpha, 0, 1)
    
    -- Hermite cubic interpolation for position
    local p0 = fA.Position
    local p1 = fB.Position
    local v0 = fA.Velocity * span
    local v1 = fB.Velocity * span
    
    local a2 = alpha * alpha
    local a3 = a2 * alpha
    local h00 = 2 * a3 - 3 * a2 + 1
    local h10 = a3 - 2 * a2 + alpha
    local h01 = -2 * a3 + 3 * a2
    local h11 = a3 - a2
    
    local interpPos = h00 * p0 + h10 * v0 + h01 * p1 + h11 * v1
    local interpRot = fA.Rotation:Lerp(fB.Rotation, alpha)
    local interpVel = fA.Velocity:Lerp(fB.Velocity, alpha)
    local interpSteer = fA.Steer + (fB.Steer - fA.Steer) * alpha
    local interpRPM = fA.RPM + (fB.RPM - fA.RPM) * alpha
    
    return CFrame.new(interpPos) * interpRot, interpVel, interpSteer, interpRPM
end

return TelemetryCodec
