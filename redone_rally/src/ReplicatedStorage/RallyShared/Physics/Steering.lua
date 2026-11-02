--!strict
-- A single rack position, expressed as a fraction of MaxAngle.
-- Changing direction only changes the target; it never resets the rack.
local Steering = {}

function Steering.Step(current: number, target: number, dt: number, tuning: any, released: boolean, scale: number?): number
    local angle = math.clamp(tuning.MaxAngle or 35, 1, 80)
    local rate = released and (tuning.ReturnRateDegrees or 75) or (tuning.TurnRateDegrees or 60)
    local step = math.clamp(rate, 5, 300) * math.clamp(scale or 1, 0.5, 1.5)
        * math.clamp(dt, 0, 0.1) / angle
    target = math.clamp(target, -1, 1)
    current = math.clamp(current, -1, 1)
    return current + math.clamp(target - current, -step, step)
end

return Steering
