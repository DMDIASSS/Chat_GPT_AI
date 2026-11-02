--!strict
-- BishopFrame.luau
-- Parallel transport (Rotation-Minimizing Frame / Bishop Frame) generator.
-- Singularity-free road orientation and dynamic banking/camber calculations.

export type OrientedFrame = {
    Position: Vector3,
    Tangent: Vector3,
    Normal: Vector3,
    Binormal: Vector3,
    BankingAngle: number,
    CFrame: CFrame,
}

local BishopFrame = {}

local function toVec3(v: any): Vector3
    if typeof(v) == "Vector3" then
        return v
    end
    return v.Position
end

-- Generates Bishop Frames along a sequence of 3D positions (or SplineSamples) with banking
function BishopFrame.ComputeFrames(
    positions: { any },
    curvatures: { number }?,
    bankingStrength: number?
): { OrientedFrame }
    local count = #positions
    if count < 2 then
        error("BishopFrame: At least 2 positions required")
    end
    
    local maxBank = math.rad(bankingStrength or 8)
    local frames: { OrientedFrame } = {}
    
    -- Initial tangent
    local t0 = (toVec3(positions[2]) - toVec3(positions[1])).Unit
    -- Initial reference normal (upward pointing, orthogonalized to tangent)
    local globalUp = Vector3.new(0, 1, 0)
    if math.abs(t0:Dot(globalUp)) > 0.95 then
        globalUp = Vector3.new(1, 0, 0)
    end
    local n0 = (globalUp - (t0:Dot(globalUp)) * t0).Unit
    local b0 = t0:Cross(n0).Unit
    
    local prevT = t0
    local prevN = n0
    local prevB = b0
    
    for i = 1, count do
        local currentPos = toVec3(positions[i])
        local currentT: Vector3
        
        if i == count then
            currentT = prevT
        else
            local diff = toVec3(positions[i + 1]) - currentPos
            currentT = (diff.Magnitude > 1e-4) and diff.Unit or prevT
        end
        
        -- Parallel transport of normal vector N
        local transportN: Vector3
        if i == 1 then
            transportN = n0
        else
            local v = prevT:Cross(currentT)
            local c = prevT:Dot(currentT)
            if c < -0.9999 then
                -- Direct 180 reversal fallback
                transportN = -prevN
            else
                -- Rodrigues rotation / vector projection
                local nProj = prevN - (currentT:Dot(prevN)) * currentT
                transportN = (nProj.Magnitude > 1e-4) and nProj.Unit or prevN
            end
        end
        
        local currentB = currentT:Cross(transportN).Unit
        
        -- Banking calculation based on curvature: theta = atan(v^2 * curvature / g)
        local curv = (curvatures and curvatures[i]) or 0
        local bankAngle = math.clamp(curv * 16, -maxBank, maxBank)
        
        -- Rotate N and B around T by bankAngle
        local cosB = math.cos(bankAngle)
        local sinB = math.sin(bankAngle)
        local bankedN = (transportN * cosB + currentB * sinB).Unit
        local bankedB = currentT:Cross(bankedN).Unit
        
        -- Form Roblox CFrame with LookVector = currentT, UpVector = bankedN, RightVector = bankedB
        local frameCFrame = CFrame.fromMatrix(currentPos, bankedB, bankedN, -currentT)
        
        table.insert(frames, {
            Position = currentPos,
            Tangent = currentT,
            Normal = bankedN,
            Binormal = bankedB,
            BankingAngle = bankAngle,
            CFrame = frameCFrame,
        })
        
        prevT = currentT
        prevN = transportN
        prevB = currentB
    end
    
    return frames
end

BishopFrame.GenerateFrames = BishopFrame.ComputeFrames

return BishopFrame
