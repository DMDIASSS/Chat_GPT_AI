--!strict
-- RaycastSuspension.luau
-- Stabilized 4-wheel raycast suspension & chassis dynamics solver.
-- Implements Backseat Rally's calibrated gravity (75 studs/s^2), normalized spring-damper equations,
-- Pacejka combined slip curves, anti-roll bars, low-speed viscous damping, and hard velocity firewalls.

local Workspace = game:GetService("Workspace")

local CarProfiles = require(script.Parent.Parent.Config.CarProfiles)
local SurfaceConfig = require(script.Parent.Parent.Config.SurfaceConfig)
local PacejkaModel = require(script.Parent.PacejkaModel)

type CarTuning = CarProfiles.CarTuning
type SurfaceProperties = SurfaceConfig.SurfaceProperties

export type WheelState = {
	WheelId: string,
	RayOrigin: Vector3,
	RayDirection: Vector3,
	HitPart: BasePart?,
	HitPosition: Vector3,
	HitNormal: Vector3,
	HitMaterial: Enum.Material,
	SurfaceTag: string?,
	SurfaceName: string,
	TireParticleColor: Color3,
	IsGrounded: boolean,
	Compression: number,
	Displacement: number,
	SuspensionLength: number,
	SpringForce: number,
	DamperForce: number,
	NormalLoad: number,
	SlipAngle: number,
	SlipRatio: number,
	SteerAngle: number,
	DriveTorque: number,
	BrakeTorque: number,
	LateralForce: Vector3,
	LongitudinalForce: Vector3,
	TotalWheelForce: Vector3,
	ContactVelocity: Vector3,
	VisualOffset: Vector3,
}

export type SuspensionResult = {
	Wheels: { [string]: WheelState },
	NetForce: Vector3,
	NetTorque: Vector3,
	GroundedCount: number,
	DominantSurface: string,
}

local RaycastSuspension = {}

-- Local offsets relative to chassis primary part
local MOUNT_Y = 0.25
local DEFAULT_MOUNTS: { [string]: Vector3 } = {
	WheelFL = Vector3.new(-2.7, MOUNT_Y, -4.3),
	WheelFR = Vector3.new(2.7, MOUNT_Y, -4.3),
	WheelRL = Vector3.new(-2.7, MOUNT_Y, 4.3),
	WheelRR = Vector3.new(2.7, MOUNT_Y, 4.3),
}

-- Previous state tracking for damping derivative
local wheelPrevDisplacement: { [Instance]: { [string]: number } } = setmetatable({}, { __mode = "k" })

function RaycastSuspension.GetMountOffset(wheelId: string, tuning: CarTuning): Vector3
	local halfTrack = tuning.Chassis.TrackWidth * 0.5
	local halfBase = tuning.Chassis.Wheelbase * 0.5
	local front = wheelId == "WheelFL" or wheelId == "WheelFR"
	local travel = math.clamp(tuning.Suspension.Travel, 0.2, 4)
	local sag = front and tuning.Suspension.SagFront or tuning.Suspension.SagRear
	local mountY = (tuning.Chassis.WheelCenterY or -0.7) + travel - (sag or 0.45)
	local centerZ = tuning.Chassis.AxleOffset or 0
	if wheelId == "WheelFL" then return Vector3.new(-halfTrack, mountY, centerZ - halfBase)
	elseif wheelId == "WheelFR" then return Vector3.new(halfTrack, mountY, centerZ - halfBase)
	elseif wheelId == "WheelRL" then return Vector3.new(-halfTrack, mountY, centerZ + halfBase)
	elseif wheelId == "WheelRR" then return Vector3.new(halfTrack, mountY, centerZ + halfBase) end
	return DEFAULT_MOUNTS[wheelId] or Vector3.zero
end

function RaycastSuspension.Solve(
	chassis: Model,
	dt: number,
	tuning: CarTuning,
	steerInput: number,
	throttleInput: number,
	brakeInput: number,
	handbrakeActive: boolean,
	gearRatio: number,
	engineRPM: number,
	raycastFilter: RaycastParams?,
	dampingMultiplier: number?
): SuspensionResult
	local primaryPart = chassis.PrimaryPart
	if not primaryPart then
		error("RaycastSuspension: Chassis missing PrimaryPart")
	end

	local safeDt = math.clamp(dt, 1 / 240, 1 / 20)
	local cframe = primaryPart.CFrame
	local linVel = primaryPart.AssemblyLinearVelocity
	local angVel = primaryPart.AssemblyAngularVelocity

	-- Velocity firewall: prevents any physics explosion from flinging vehicle
	if linVel.Magnitude > 220 then
		primaryPart.AssemblyLinearVelocity = linVel.Unit * 220
		linVel = primaryPart.AssemblyLinearVelocity
	end
	if angVel.Magnitude > 7.0 then
		primaryPart.AssemblyAngularVelocity = angVel.Unit * 7.0
		angVel = primaryPart.AssemblyAngularVelocity
	end

	local assemblyMass = primaryPart.AssemblyMass
	if not assemblyMass or assemblyMass <= 10 or assemblyMass ~= assemblyMass then
		assemblyMass = tuning.Chassis.Mass
	end

	-- Backseat Rally calibrated gravity (75 studs/s^2)
	local calibratedGravity = 75.0
	local worldGravity = Workspace.Gravity > 1 and Workspace.Gravity or 196.2
	-- Counter-force to reduce default Roblox gravity down to calibratedGravity
	local counterGravity = Vector3.new(0, assemblyMass * (worldGravity - calibratedGravity), 0)

	local quarterMass = assemblyMass * 0.25
	local travel = math.clamp(tuning.Suspension.Travel, 0.2, 4)
	local tyreRadius = tuning.Tyres.Radius
	local restLength = travel + tyreRadius

	-- Cache prev displacements
	if not wheelPrevDisplacement[chassis] then
		wheelPrevDisplacement[chassis] = {
			WheelRL = 0,
			WheelRR = 0,
			WheelFL = 0,
			WheelFR = 0,
		}
	end
	local prevDisps = wheelPrevDisplacement[chassis]

	local wheelIds = { "WheelFL", "WheelFR", "WheelRL", "WheelRR" }
	local wheelStates: { [string]: WheelState } = {}
	local groundedCount = 0
	local dominantSurface = "Gravel"

	-- Step 1: Raycasting & suspension compression
	for _, wId in ipairs(wheelIds) do
		local isFront = (wId == "WheelFL" or wId == "WheelFR")
		local mountAttachment = primaryPart:FindFirstChild(wId) :: Attachment?
		local mountLocal = mountAttachment and mountAttachment.Position or RaycastSuspension.GetMountOffset(wId, tuning)
		local mountWorld = cframe:PointToWorldSpace(mountLocal)

		local downDir = -cframe.UpVector
		local rayLength = restLength + 0.4
		local rayResult = Workspace:Raycast(mountWorld, downDir * rayLength, raycastFilter)

		local isGrounded = false
		local hitDist = restLength
		local hitPart: BasePart? = nil
		local hitPos = mountWorld + downDir * restLength
		local hitNorm = cframe.UpVector
		local hitMat = Enum.Material.Asphalt
		local surfaceTag: string? = nil
		local surfaceProps = SurfaceConfig.Surfaces.Gravel

		if rayResult and rayResult.Instance and rayResult.Distance <= restLength + 0.15 then
			isGrounded = true
			hitDist = math.clamp(rayResult.Distance, tyreRadius * 0.4, restLength)
			hitPart = rayResult.Instance
			hitPos = rayResult.Position
			hitNorm = rayResult.Normal
			hitMat = rayResult.Material
			surfaceTag = hitPart:GetAttribute("SurfaceType") :: string?
			surfaceProps = SurfaceConfig.Detect(hitPart, hitMat)
			dominantSurface = surfaceProps.Name
			groundedCount += 1
		end

		local bumpNoise = 0
		if isGrounded and linVel.Magnitude > 3.0 then
			local freq = surfaceProps.BumpFrequency * 0.08
			bumpNoise = math.noise(hitPos.X * freq, hitPos.Z * freq, 0.37) * surfaceProps.BumpAmplitude * 0.5
		end

		local displacement = isGrounded and math.clamp((restLength - hitDist) + bumpNoise, 0, travel) or 0
		local compression = displacement / math.max(0.01, travel)

		local visualSuspDrop = math.clamp(hitDist - tyreRadius, 0, travel)
		wheelStates[wId] = {
			WheelId = wId,
			RayOrigin = mountWorld,
			RayDirection = downDir,
			HitPart = hitPart,
			HitPosition = hitPos,
			HitNormal = hitNorm,
			HitMaterial = hitMat,
			SurfaceTag = surfaceTag,
			SurfaceName = surfaceProps.Name,
			TireParticleColor = surfaceProps.TireParticleColor,
			IsGrounded = isGrounded,
			Compression = compression,
			Displacement = displacement,
			SuspensionLength = visualSuspDrop + tyreRadius,
			SpringForce = 0,
			DamperForce = 0,
			NormalLoad = 0,
			SlipAngle = 0,
			SlipRatio = 0,
			SteerAngle = 0,
			DriveTorque = 0,
			BrakeTorque = 0,
			LateralForce = Vector3.zero,
			LongitudinalForce = Vector3.zero,
			TotalWheelForce = Vector3.zero,
			ContactVelocity = Vector3.zero,
			VisualOffset = Vector3.new(mountLocal.X, mountLocal.Y - visualSuspDrop, mountLocal.Z),
		}
	end

	-- Anti-Roll Bar calculation
	local sagFront = tuning.Suspension.SagFront or 0.45
	local sagRear = tuning.Suspension.SagRear or 0.42
	local arbFrontK = (calibratedGravity / sagFront) * (tuning.Suspension.AntiRollFront or 0.5) * quarterMass
	local arbRearK = (calibratedGravity / sagRear) * (tuning.Suspension.AntiRollRear or 0.35) * quarterMass

	local frontRollDelta = (wheelStates.WheelFL.Displacement - wheelStates.WheelFR.Displacement) * arbFrontK
	local rearRollDelta = (wheelStates.WheelRL.Displacement - wheelStates.WheelRR.Displacement) * arbRearK

	-- Drivetrain thrust calculation
	local totalDriveTorque = 0
	if throttleInput > 0 and gearRatio ~= 0 then
		local tMultiplier = 0.85
		for _, pt in ipairs(tuning.Engine.TorqueCurve) do
			if engineRPM >= pt[1] then
				tMultiplier = pt[2]
			end
		end
		local firstGearRatio = math.abs(tuning.Transmission.Ratios[1] or 3.5)
		local normalizedGear = math.clamp(math.abs(gearRatio) / firstGearRatio, 0.25, 1.25)
		local signDir = (gearRatio < 0) and -1 or 1
		totalDriveTorque = signDir * throttleInput * tMultiplier * normalizedGear * (assemblyMass * calibratedGravity * 0.95) * tyreRadius
	end

	-- Steering geometry
	local maxSteerDeg = tuning.Steering.MaxAngle
	local ackermann = tuning.Steering.Ackermann
	local baseSteerRad = math.rad(steerInput * maxSteerDeg)

	local netForce = counterGravity
	local netTorque = Vector3.zero

	local suspForces: { [string]: number } = {}

	-- Step 2: Individual wheel force computation
	for _, wId in ipairs(wheelIds) do
		local state = wheelStates[wId]
		local isFront = (wId == "WheelFL" or wId == "WheelFR")
		local isLeft = (wId == "WheelFL" or wId == "WheelRL")

		-- Steering orientation
		local wheelSteer = 0
		if wId == "WheelFL" then
			wheelSteer = -baseSteerRad * (1 + (steerInput > 0 and -ackermann or ackermann))
		elseif wId == "WheelFR" then
			wheelSteer = -baseSteerRad * (1 + (steerInput > 0 and ackermann or -ackermann))
		end
		state.SteerAngle = wheelSteer

		if not state.IsGrounded then
			prevDisps[wId] = 0
			suspForces[wId] = 0
			continue
		end

		local sag = isFront and sagFront or sagRear
		local kNorm = calibratedGravity / math.max(0.1, sag)

		local dDisp = (state.Displacement - (prevDisps[wId] or state.Displacement)) / safeDt
		prevDisps[wId] = state.Displacement

		local bumpRate = 0.38
		local reboundRate = 0.55
		local zeta = (dDisp >= 0) and bumpRate or reboundRate
		local cNorm = 2.0 * zeta * math.sqrt(kNorm)

		-- Normalized spring and damper per unit mass
		local springNorm = state.Displacement * kNorm
		local damperNorm = dDisp * cNorm
		local totalNorm = springNorm + damperNorm

		-- Bump stop rate above 80% compression
		if state.Compression > 0.80 then
			totalNorm += kNorm * 1.5 * (state.Displacement - travel * 0.80)
		end

		-- Convert normalized acceleration to force
		local wheelSuspF = math.max(0, totalNorm * quarterMass)

		-- Apply anti-roll bar delta
		if isFront then
			wheelSuspF += (isLeft and frontRollDelta or -frontRollDelta)
		else
			wheelSuspF += (isLeft and rearRollDelta or -rearRollDelta)
		end
		wheelSuspF = math.max(0, wheelSuspF)
		suspForces[wId] = wheelSuspF

		state.SpringForce = springNorm * quarterMass
		state.DamperForce = damperNorm * quarterMass
		state.NormalLoad = wheelSuspF

		local wheelSteer = state.SteerAngle

		local wheelRot = cframe * CFrame.Angles(0, wheelSteer, 0)
		local wheelForward = wheelRot.LookVector
		local wheelRight = wheelRot.RightVector

		local mountAttachment = primaryPart:FindFirstChild(wId) :: Attachment?
		local mountLocal = mountAttachment and mountAttachment.Position or RaycastSuspension.GetMountOffset(wId, tuning)
		local rMountWorld = cframe:VectorToWorldSpace(mountLocal)

		local contactVel = linVel + angVel:Cross(rMountWorld)
		state.ContactVelocity = contactVel

		local vForward = contactVel:Dot(wheelForward)
		local vLateral = contactVel:Dot(wheelRight)

		-- Slip angle calculation
		local slipAngleDeg = 0
		if contactVel.Magnitude > 1.5 then
			slipAngleDeg = math.deg(math.atan2(vLateral, math.max(2.5, math.abs(vForward))))
		end
		state.SlipAngle = slipAngleDeg

		-- Drivetrain torque share
		local frontShare = tuning.Transmission.FrontShare
		local wheelDriveTorque = isFront and ((totalDriveTorque * frontShare) * 0.5) or ((totalDriveTorque * (1 - frontShare)) * 0.5)
		state.DriveTorque = wheelDriveTorque

		local wheelBrakeForce = 0
		if brakeInput > 0 then
			local bias = isFront and tuning.Brakes.FrontBias or (1 - tuning.Brakes.FrontBias)
			wheelBrakeForce = brakeInput * (assemblyMass * calibratedGravity * 1.1) * bias
		end
		if handbrakeActive and not isFront then
			wheelBrakeForce += (assemblyMass * calibratedGravity * 0.6)
		end
		state.BrakeTorque = wheelBrakeForce

		-- Surface parameters
		local surface = SurfaceConfig.Detect(state.HitPart, state.HitMaterial)
		local slipParams: PacejkaModel.SlipParams = {
			PeakSlip = surface.PeakSlip or tuning.Tyres.PeakSlip,
			DriftWindow = surface.DriftWindow or tuning.Tyres.DriftWindow,
			Plateau = surface.Plateau or tuning.Tyres.Plateau,
			Tail = surface.Tail or tuning.Tyres.Tail,
		}

		local effectiveLatGrip = tuning.Tyres.LateralGrip * surface.Lateral
		if handbrakeActive and not isFront then
			effectiveLatGrip *= 0.35
		end

		local driveForce = wheelDriveTorque / math.max(0.2, tyreRadius)
		local brakeForce = (math.abs(vForward) > 0.5) and (-math.sign(vForward) * math.min(math.abs(vForward) * quarterMass * 8.0, wheelBrakeForce)) or 0
		local rollingResist = (math.abs(vForward) > 0.5) and (-math.sign(vForward) * wheelSuspF * surface.RollingResistance * 0.25) or 0
		local netLongitudinal = driveForce + brakeForce + rollingResist

		local longSlipRatio = math.clamp((math.abs(driveForce) > 0 and 0.25 or 0.0) - (vForward / 150.0), -1.0, 1.0)
		state.SlipRatio = longSlipRatio

		local latMag, longMag = PacejkaModel.CalculateCombinedForces(
			wheelSuspF,
			slipAngleDeg,
			longSlipRatio,
			slipParams,
			effectiveLatGrip * 1.25,
			tuning.Tyres.LongitudinalGrip * surface.Longitudinal * 1.25
		)

		-- Viscous low-speed lateral damping
		local latDamper = math.clamp(math.abs(vLateral) / 5.0, 0, 1)
		local latForce = (-wheelRight * math.sign(vLateral)) * (latMag * latDamper)
		local longForce = wheelForward * (math.sign(netLongitudinal) * math.min(math.abs(netLongitudinal), longMag))

		-- Pure upward vertical support force
		local suspForce = cframe.UpVector * wheelSuspF

		local totalForce = latForce + longForce + suspForce
		state.LateralForce = latForce
		state.LongitudinalForce = longForce
		state.TotalWheelForce = totalForce

		netForce += totalForce
		-- Yaw and in-plane moments
		netTorque += rMountWorld:Cross(latForce + longForce)
	end

	-- Suspension pitch and roll angular moments (Backseat Rally formulation)
	local fFL = suspForces.WheelFL or 0
	local fFR = suspForces.WheelFR or 0
	local fRL = suspForces.WheelRL or 0
	local fRR = suspForces.WheelRR or 0

	local halfBase = tuning.Chassis.Wheelbase * 0.5
	local halfTrack = tuning.Chassis.TrackWidth * 0.5

	-- Pitch torque: (Front - Rear) * halfBase
	local pitchTorque = ((fFL + fFR) - (fRL + fRR)) * halfBase
	-- Roll torque: (Left - Right) * halfTrack
	local rollTorque = ((fFL + fRL) - (fFR + fRR)) * halfTrack

	local localSuspTorque = Vector3.new(pitchTorque, 0, -rollTorque)
	netTorque += cframe:VectorToWorldSpace(localSuspTorque)

	-- Aerodynamic drag
	local speed = linVel.Magnitude
	if speed > 5 then
		local aeroDrag = -linVel.Unit * (0.38 * speed * speed)
		netForce += aeroDrag
	end

	-- 3-Axis Angular Stabilization (prevents oscillations and rolling over)
	local localAngVel = cframe:VectorToObjectSpace(angVel)
	local angDampingLocal = Vector3.new(
		-localAngVel.X * assemblyMass * 16.0, -- Pitch damping
		-localAngVel.Y * assemblyMass * (12.0 + tuning.Steering.Stability * 6.0), -- Yaw stability
		-localAngVel.Z * assemblyMass * 22.0  -- Roll damping
	)
	netTorque += cframe:VectorToWorldSpace(angDampingLocal)

	-- LandAssist: upright righting assist if tilted beyond normal rally angles
	local upDot = cframe.UpVector:Dot(Vector3.yAxis)
	if upDot < 0.88 then
		local rightingAxis = cframe.UpVector:Cross(Vector3.yAxis)
		if rightingAxis.Magnitude > 0.001 then
			local tiltSeverity = math.clamp(1.0 - upDot, 0, 1.0)
			netTorque += rightingAxis.Unit * (tiltSeverity * assemblyMass * calibratedGravity * 1.2)
		end
	end

	-- Hard firewall safety clamp
	if netForce.Magnitude > 450000 then
		netForce = netForce.Unit * 450000
	end
	if netTorque.Magnitude > 600000 then
		netTorque = netTorque.Unit * 600000
	end

	-- NaN protection
	if netForce.X ~= netForce.X or netForce.Y ~= netForce.Y or netForce.Z ~= netForce.Z then
		netForce = Vector3.zero
	end
	if netTorque.X ~= netTorque.X or netTorque.Y ~= netTorque.Y or netTorque.Z ~= netTorque.Z then
		netTorque = Vector3.zero
	end

	return {
		Wheels = wheelStates,
		NetForce = netForce,
		NetTorque = netTorque,
		GroundedCount = groundedCount,
		DominantSurface = dominantSurface,
	}
end

return RaycastSuspension
