--!strict
-- PacejkaModel.luau
-- 3-stage piecewise rational slip curve (parabolic rise -> drift plateau -> quadratic tail falloff)
-- plus standard Pacejka Magic Formula and combined slip ellipse calculations.

local PacejkaModel = {}

export type SlipParams = {
    PeakSlip: number,     -- Deg at peak grip (e.g. 6.5)
    DriftWindow: number,  -- Width of drift plateau in deg (e.g. 24.0)
    Plateau: number,      -- Grip ratio across plateau (e.g. 0.92)
    Tail: number,         -- Terminal grip ratio at 90 deg slip (e.g. 0.75)
}

-- Piecewise Rational Slip Curve formulation
function PacejkaModel.EvaluatePiecewise(slipAngleDeg: number, params: SlipParams): number
    local absAngle = math.abs(slipAngleDeg)
    local peak = math.max(0.1, params.PeakSlip)
    local plateau = params.Plateau
    local tail = params.Tail
    local driftWindow = math.max(1.0, params.DriftWindow)
    
    if absAngle <= peak then
        -- Stage 1: Quadratic / Parabolic rise (smooth tangential peak at 1.0)
        local r = absAngle / peak
        return r * (2 - r)
    end
    
    local driftEnd = peak + driftWindow
    if absAngle <= driftEnd then
        -- Stage 2: Drift plateau (forgiving drift window)
        local t = (absAngle - peak) / driftWindow
        return 1.0 + (plateau - 1.0) * t
    end
    
    -- Stage 3: Terminal quadratic tail falloff
    local range = math.max(1.0, 90 - driftEnd)
    local u = math.clamp((absAngle - driftEnd) / range, 0, 1)
    local smoothU = u * (2 - u)
    return plateau + (tail - plateau) * smoothU
end

-- Classical Pacejka Magic Formula: F(x) = D * sin(C * atan(B * x - E * (B * x - atan(B * x))))
function PacejkaModel.EvaluateMagicFormula(
    slip: number,
    B: number,
    C: number,
    D: number,
    E: number
): number
    local Bx = B * slip
    local curve = Bx - E * (Bx - math.atan(Bx))
    return D * math.sin(C * math.atan(curve))
end

-- Combined Slip calculation using friction ellipse
-- Ensures total traction does not exceed available tire friction budget
function PacejkaModel.CalculateCombinedForces(
    normalForce: number,
    lateralSlipAngleDeg: number,
    longitudinalSlipRatio: number,
    params: SlipParams,
    lateralFrictionCoeff: number,
    longitudinalFrictionCoeff: number
): (number, number)
    local rawLateralFactor = PacejkaModel.EvaluatePiecewise(lateralSlipAngleDeg, params)
    local maxLateralForce = normalForce * lateralFrictionCoeff * rawLateralFactor
    
    -- Longitudinal slip curve (0.0 to 1.0 ratio)
    local absLongSlip = math.abs(longitudinalSlipRatio)
    local longFactor = 1.0
    if absLongSlip <= 0.15 then
        longFactor = absLongSlip / 0.15 * (2 - (absLongSlip / 0.15))
    else
        longFactor = math.max(0.7, 1.0 - (absLongSlip - 0.15) * 0.35)
    end
    local maxLongitudinalForce = normalForce * longitudinalFrictionCoeff * longFactor
    
    -- Friction Ellipse coupling:
    -- (Fx / F_x0)^2 + (Fy / F_y0)^2 <= 1.0
    local peakLong = normalForce * longitudinalFrictionCoeff
    local peakLat = normalForce * lateralFrictionCoeff
    local normX = (peakLong > 0) and (maxLongitudinalForce / peakLong) or 0
    local normY = (peakLat > 0) and (maxLateralForce / peakLat) or 0
    local combinedMagnitude = math.sqrt(normX * normX + normY * normY)
    
    local lateralForce = maxLateralForce
    local longitudinalForce = maxLongitudinalForce
    
    if combinedMagnitude > 1.0 then
        local scale = 1.0 / combinedMagnitude
        lateralForce *= scale
        longitudinalForce *= scale
    end
    
    return lateralForce, longitudinalForce
end

return PacejkaModel
