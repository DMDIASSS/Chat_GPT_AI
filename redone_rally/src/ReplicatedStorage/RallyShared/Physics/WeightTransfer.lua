--!strict
-- WeightTransfer.luau
-- Dynamic weight transfer calculation (pitch, roll, heave, anti-roll bars).

local WeightTransfer = {}

export type ChassisDim = {
    Mass: number,
    Wheelbase: number,
    TrackWidth: number,
    CGHeight: number,
    WeightDistributionFront: number,
}

export type ARBConfig = {
    AntiRollFront: number,
    AntiRollRear: number,
    Stiffness: number,
}

export type WheelDisplacements = {
    FL: number,
    FR: number,
    RL: number,
    RR: number,
}

export type WheelLoads = {
    FL: number,
    FR: number,
    RL: number,
    RR: number,
}

local GRAVITY = 196.2 -- Roblox default gravity in studs/s^2

-- Calculates static and dynamic wheel normal loads based on acceleration and suspension deflection
function WeightTransfer.CalculateLoads(
    chassis: ChassisDim,
    arb: ARBConfig,
    localAccel: Vector3, -- X = right (lateral), Y = up (heave), Z = forward (longitudinal)
    displacements: WheelDisplacements,
    speed: number
): WheelLoads
    local totalWeight = chassis.Mass * GRAVITY
    local frontBaseWeight = totalWeight * chassis.WeightDistributionFront
    local rearBaseWeight = totalWeight * (1 - chassis.WeightDistributionFront)
    
    local staticFL = frontBaseWeight * 0.5
    local staticFR = frontBaseWeight * 0.5
    local staticRL = rearBaseWeight * 0.5
    local staticRR = rearBaseWeight * 0.5
    
    -- Longitudinal acceleration (Z axis): positive is forward acceleration, negative is braking
    -- Pitch transfer:
    -- Forward accel transfers load from Front to Rear.
    -- Braking (-localAccel.Z) transfers load from Rear to Front.
    local cgH = math.abs(chassis.CGHeight)
    local longDelta = (chassis.Mass * localAccel.Z * cgH) / math.max(1.0, chassis.Wheelbase)
    
    -- Lateral acceleration (X axis): positive is right turn (car sliding left), negative is left turn
    -- Roll transfer:
    -- Transfers load to outside wheels
    local latDeltaFront = (frontBaseWeight / totalWeight) * (chassis.Mass * localAccel.X * cgH) / math.max(1.0, chassis.TrackWidth)
    local latDeltaRear = (rearBaseWeight / totalWeight) * (chassis.Mass * localAccel.X * cgH) / math.max(1.0, chassis.TrackWidth)
    
    -- Anti-roll bar forces
    -- When outer suspension compresses more than inner suspension:
    local frontDiff = (displacements.FL - displacements.FR)
    local rearDiff = (displacements.RL - displacements.RR)
    
    local frontArbForce = arb.AntiRollFront * arb.Stiffness * frontDiff * 0.5
    local rearArbForce = arb.AntiRollRear * arb.Stiffness * rearDiff * 0.5
    
    -- Aerodynamic downforce (heave): Downforce increases with square of speed
    local aeroHeave = 0.5 * 1.2 * 0.35 * (speed * 0.28) ^ 2
    local aeroPerWheel = aeroHeave * 0.25
    
    -- Sum dynamic forces
    -- FL:
    -- Forward accel relieves FL; Right lateral transfers load to left; ARB balances
    local loadFL = staticFL - (longDelta * 0.5) - (latDeltaFront * 0.5) + frontArbForce + aeroPerWheel
    local loadFR = staticFR - (longDelta * 0.5) + (latDeltaFront * 0.5) - frontArbForce + aeroPerWheel
    local loadRL = staticRL + (longDelta * 0.5) - (latDeltaRear * 0.5) + rearArbForce + aeroPerWheel
    local loadRR = staticRR + (longDelta * 0.5) + (latDeltaRear * 0.5) - rearArbForce + aeroPerWheel
    
    -- Wheels cannot produce negative normal load (they lift off the ground)
    return {
        FL = math.max(0, loadFL),
        FR = math.max(0, loadFR),
        RL = math.max(0, loadRL),
        RR = math.max(0, loadRR),
    }
end

return WeightTransfer
