--!strict
-- Project onto ordered road segments, independent of the driver's heading.
local StageProgress = {}

function StageProgress.Project(samples: { any }, position: Vector3, previousDistance: number?): (number, number)
    local bestDistance, bestError = 0, math.huge
    local bestScore = math.huge
    for i = 1, #samples - 1 do
        local a, b = samples[i], samples[i + 1]
        local delta = b.Position - a.Position
        local lengthSquared = delta:Dot(delta)
        if lengthSquared < 1e-8 then continue end
        local t = math.clamp((position - a.Position):Dot(delta) / lengthSquared, 0, 1)
        local offset = position - (a.Position + delta * t)
        local errorSquared = offset:Dot(offset)
        local distance = a.Distance + (b.Distance - a.Distance) * t
        -- At a crossing, favor the current section. A reset still reacquires
        -- the whole route because this penalty is bounded.
        local penalty = previousDistance and math.min(225, math.abs(distance - previousDistance) * 0.15) or 0
        local score = errorSquared + penalty
        if score < bestScore then
            bestScore, bestError, bestDistance = score, errorSquared, distance
        end
    end
    return bestDistance, math.sqrt(bestError)
end

function StageProgress.Lookahead(speed: number, severity: number, leadSeconds: number): number
    local safeSpeed = math.max(0, speed)
    local cornerSpeed = ({ [1] = 20, [2] = 30, [3] = 44, [4] = 58, [5] = 76, [6] = 95, [7] = 14, [8] = 22 })[severity] or 95
    local braking = math.max(0, safeSpeed * safeSpeed - cornerSpeed * cornerSpeed) / 80
    return math.clamp(25 + safeSpeed * math.clamp(leadSeconds, 1.5, 5) + braking, 35, 650)
end

return StageProgress
