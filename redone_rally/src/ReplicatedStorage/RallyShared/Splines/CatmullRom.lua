--!strict
-- CatmullRom.luau
-- Centripetal Catmull-Rom (alpha = 0.5) 3D spline evaluator with arc-length parameterization.

export type SplineSample = {
    Position: Vector3,
    Tangent: Vector3,
    Curvature: number,
    Distance: number,
    Progress: number,
}

local CatmullRom = {}

local function getKnot(pA: Vector3, pB: Vector3, tA: number, alpha: number): number
    local d = (pB - pA).Magnitude
    return tA + math.pow(math.max(1e-4, d), alpha)
end

function CatmullRom.EvaluateSegment(
    p0: Vector3, p1: Vector3, p2: Vector3, p3: Vector3,
    t: number,
    alpha: number?
): Vector3
    local a = alpha or 0.5 -- 0.5 = Centripetal (avoids self-intersections and cusps)
    
    local t0 = 0
    local t1 = getKnot(p0, p1, t0, a)
    local t2 = getKnot(p1, p2, t1, a)
    local t3 = getKnot(p2, p3, t2, a)
    
    local globalT = t1 + t * (t2 - t1)
    
    local a1 = (t1 - globalT) / (t1 - t0) * p0 + (globalT - t0) / (t1 - t0) * p1
    local a2 = (t2 - globalT) / (t2 - t1) * p1 + (globalT - t1) / (t2 - t1) * p2
    local a3 = (t3 - globalT) / (t3 - t2) * p2 + (globalT - t2) / (t3 - t2) * p3
    
    local b1 = (t2 - globalT) / (t2 - t0) * a1 + (globalT - t0) / (t2 - t0) * a2
    local b2 = (t3 - globalT) / (t3 - t1) * a2 + (globalT - t1) / (t3 - t1) * a3
    
    return (t2 - globalT) / (t2 - t1) * b1 + (globalT - t1) / (t2 - t1) * b2
end

function CatmullRom.EvaluateTangent(
    p0: Vector3, p1: Vector3, p2: Vector3, p3: Vector3,
    t: number
): Vector3
    local eps = 0.005
    local tPrev = math.clamp(t - eps, 0, 1)
    local tNext = math.clamp(t + eps, 0, 1)
    local posPrev = CatmullRom.EvaluateSegment(p0, p1, p2, p3, tPrev)
    local posNext = CatmullRom.EvaluateSegment(p0, p1, p2, p3, tNext)
    local diff = posNext - posPrev
    if diff.Magnitude < 1e-4 then
        return (p2 - p1).Unit
    end
    return diff.Unit
end

-- Generates evenly spaced samples along a sequence of control points
function CatmullRom.GenerateUniformSpline(
    controlPoints: { Vector3 },
    stepDistance: number
): { SplineSample }
    local count = #controlPoints
    if count < 4 then
        error("CatmullRom: At least 4 control points required")
    end
    
    -- Subdivide segments and calculate cumulative arc length
    type SubPoint = { Pos: Vector3, SegmentIdx: number, LocalT: number }
    local densePoints: { SubPoint } = {}
    local stepsPerSegment = 24
    
    for i = 1, count - 3 do
        local p0, p1, p2, p3 = controlPoints[i], controlPoints[i + 1], controlPoints[i + 2], controlPoints[i + 3]
        for s = 0, stepsPerSegment - 1 do
            local t = s / stepsPerSegment
            local pos = CatmullRom.EvaluateSegment(p0, p1, p2, p3, t)
            table.insert(densePoints, { Pos = pos, SegmentIdx = i, LocalT = t })
        end
    end
    -- Add final endpoint
    local finalP0, finalP1, finalP2, finalP3 = controlPoints[count - 3], controlPoints[count - 2], controlPoints[count - 1], controlPoints[count]
    table.insert(densePoints, { Pos = finalP2, SegmentIdx = count - 3, LocalT = 1.0 })
    
    -- Cumulative distances
    local arcLengths: { number } = { 0 }
    local totalDist = 0
    for i = 2, #densePoints do
        local d = (densePoints[i].Pos - densePoints[i - 1].Pos).Magnitude
        totalDist += d
        table.insert(arcLengths, totalDist)
    end
    
    -- Resample at uniform stepDistance
    local samples: { SplineSample } = {}
    local currentDist = 0
    local denseIdx = 1
    local totalDense = #densePoints
    
    while currentDist <= totalDist do
        while denseIdx < totalDense and arcLengths[denseIdx + 1] < currentDist do
            denseIdx += 1
        end
        
        local pA = densePoints[denseIdx].Pos
        local pB = densePoints[math.min(totalDense, denseIdx + 1)].Pos
        local distA = arcLengths[denseIdx]
        local distB = arcLengths[math.min(totalDense, denseIdx + 1)]
        local segLen = math.max(1e-4, distB - distA)
        local alpha = math.clamp((currentDist - distA) / segLen, 0, 1)
        local interpPos = pA:Lerp(pB, alpha)
        
        table.insert(samples, {
            Position = interpPos,
            Tangent = Vector3.new(0, 0, 1), -- Will be resolved in secondary pass
            Curvature = 0,
            Distance = currentDist,
            Progress = currentDist / math.max(1, totalDist),
        })
        
        currentDist += stepDistance
    end
    
    -- Compute tangents and curvatures via discrete differential geometry
    local nSamples = #samples
    for i = 1, nSamples do
        local prevPos = (i > 1) and samples[i - 1].Position or (samples[1].Position - (samples[2].Position - samples[1].Position))
        local nextPos = (i < nSamples) and samples[i + 1].Position or (samples[nSamples].Position + (samples[nSamples].Position - samples[nSamples - 1].Position))
        
        local tanVec = (nextPos - prevPos)
        local tanUnit = (tanVec.Magnitude > 1e-4) and tanVec.Unit or Vector3.new(0, 0, 1)
        samples[i].Tangent = tanUnit
        
        -- Curvature in horizontal (X, Z) plane
        if i > 1 and i < nSamples then
            local t1 = (samples[i].Position - samples[i - 1].Position).Unit
            local t2 = (samples[i + 1].Position - samples[i].Position).Unit
            local angleDelta = math.atan2(t2.Z, t2.X) - math.atan2(t1.Z, t1.X)
            -- Normalize angle delta to [-pi, pi]
            while angleDelta > math.pi do angleDelta -= 2 * math.pi end
            while angleDelta < -math.pi do angleDelta += 2 * math.pi end
            local ds = math.max(0.1, (samples[i + 1].Position - samples[i - 1].Position).Magnitude * 0.5)
            samples[i].Curvature = angleDelta / ds
        end
    end
    
    return samples
end

return CatmullRom
