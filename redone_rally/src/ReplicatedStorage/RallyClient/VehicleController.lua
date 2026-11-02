--!strict
-- VehicleController.luau
-- 60 FPS client-side rally vehicle physics driver.
-- Handles player inputs (UserInputService + VehicleSeat), 4-wheel raycast simulation, Pacejka slip integration,
-- progressive flywheel/clutch engine RPM & gearbox, 7-layer Backseat Rally audio modulation,
-- per-wheel surface dust particles, anti-lag exhaust backfire, and real-time collision deformation.

local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local UserInputService = game:GetService("UserInputService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Workspace = game:GetService("Workspace")

local CarProfiles = require(ReplicatedStorage.RallyShared.Config.CarProfiles)
local RaycastSuspension = require(ReplicatedStorage.RallyShared.Physics.RaycastSuspension)
local DeformationModel = require(ReplicatedStorage.RallyShared.Physics.DeformationModel)
local Steering = require(ReplicatedStorage.RallyShared.Physics.Steering)

type CarTuning = CarProfiles.CarTuning

export type VehicleTelemetry = {
	SpeedKmh: number,
	SpeedMph: number,
	RPM: number,
	Gear: number,
	GearString: string,
	Throttle: number,
	Brake: number,
	Handbrake: boolean,
	Steer: number,
	SlipAngleDeg: number,
	IsGrounded: boolean,
	TotalDamage: number,
	SurfaceName: string,
	TransmissionMode: string,
	BoostBar: number?,
	HandlingDegradation: DeformationModel.HandlingDegradation?,
}

local VehicleController = {}

local activeVehicle: Model? = nil
local touchConnection: RBXScriptConnection? = nil
local activeTuning: CarTuning = CarProfiles.Cars.KazeRS
local currentGear = 1
local prevGear = 1
local currentRPM = 1000
local flywheelRPM = 1000
local currentBoostBar = -0.5
local shiftTimer = 0
local lastShiftClock = 0
local lastImpactClock = 0
local currentSteer = 0
local targetSteer = 0
local lastSteerDirection = 0
local steeringRateScale = 1
local throttle = 0
local prevThrottle = 0
local brake = 0
local handbrake = false
local isManual = false
local wheelSpinAngle = 0
local lastBackfireClock = 0

local prevVelocity = Vector3.zero
local damageZones: DeformationModel.DamageZones = {
	Front = 0,
	Rear = 0,
	Left = 0,
	Right = 0,
	Roof = 0,
}

local telemetry: VehicleTelemetry = {
	SpeedKmh = 0,
	SpeedMph = 0,
	RPM = 1000,
	Gear = 1,
	GearString = "1",
	Throttle = 0,
	Brake = 0,
	Handbrake = false,
	Steer = 0,
	SlipAngleDeg = 0,
	IsGrounded = false,
	TotalDamage = 0,
	SurfaceName = "Tarmac",
	TransmissionMode = "AUTO",
	BoostBar = -0.5,
}

local function playGearShiftSound(vehicle: Model?)
	if not vehicle or not vehicle.PrimaryPart then
		return
	end
	local sndFolder = vehicle.PrimaryPart:FindFirstChild("VehicleSounds")
	local shiftSnd = sndFolder and sndFolder:FindFirstChild("GearShift") :: Sound?
	if shiftSnd then
		shiftSnd.PlaybackSpeed = 0.92 + math.random() * 0.16
		shiftSnd:Play()
	end
end

local function triggerExhaustBackfire(vehicle: Model?)
	if not vehicle or not vehicle.PrimaryPart then
		return
	end
	local now = os.clock()
	if now - lastBackfireClock < 0.30 then
		return
	end
	lastBackfireClock = now

	local sndFolder = vehicle.PrimaryPart:FindFirstChild("VehicleSounds")
	if sndFolder then
		local bfSnd = sndFolder:FindFirstChild("Backfire") :: Sound?
		local bovSnd = sndFolder:FindFirstChild("TurboBlowOff") :: Sound?
		if bovSnd then
			bovSnd.PlaybackSpeed = 0.95 + math.random() * 0.12
			bovSnd:Play()
		end
		if bfSnd then
			bfSnd.PlaybackSpeed = 0.88 + math.random() * 0.24
			bfSnd:Play()
		end
	end

	local panels = vehicle:FindFirstChild("BodyPanels")
	local exhaust = panels and panels:FindFirstChild("Exhaust")
	local att = exhaust and exhaust:FindFirstChild("BackfireAttachment")
	if att then
		local flame = att:FindFirstChild("BackfireFlame") :: ParticleEmitter?
		local light = att:FindFirstChild("BackfireLight") :: PointLight?
		if flame then
			flame:Emit(16)
		end
		if light then
			light.Brightness = 5.0
			task.delay(0.11, function()
				if light and light.Parent then
					light.Brightness = 0
				end
			end)
		end
	end
end

-- Input mapping (E/Q shift, T toggles Manual/Auto, Space handbrake)
UserInputService.InputBegan:Connect(function(input, processed)
	-- Native vehicle controls can consume the key before this listener runs.
	-- Record steering direction unless a text box owns keyboard input.
	if not UserInputService:GetFocusedTextBox() then
		if input.KeyCode == Enum.KeyCode.A or input.KeyCode == Enum.KeyCode.Left then
			lastSteerDirection = -1
			return
		elseif input.KeyCode == Enum.KeyCode.D or input.KeyCode == Enum.KeyCode.Right then
			lastSteerDirection = 1
			return
		end
	end
	if processed then
		return
	end
	if input.KeyCode == Enum.KeyCode.Space then
		handbrake = true
	elseif input.KeyCode == Enum.KeyCode.E then
		if currentGear < #activeTuning.Transmission.Ratios then
			currentGear += 1
			shiftTimer = math.max(0.08, activeTuning.Transmission.ShiftTime or 0.12)
			lastShiftClock = os.clock()
			playGearShiftSound(activeVehicle)
		end
	elseif input.KeyCode == Enum.KeyCode.Q then
		if currentGear > -1 then
			currentGear -= 1
			shiftTimer = math.max(0.08, activeTuning.Transmission.ShiftTime or 0.12)
			lastShiftClock = os.clock()
			playGearShiftSound(activeVehicle)
			if currentRPM > activeTuning.Engine.Redline * 0.60 then
				triggerExhaustBackfire(activeVehicle)
			end
		end
	elseif input.KeyCode == Enum.KeyCode.T then
		isManual = not isManual
	end
end)

UserInputService.InputEnded:Connect(function(input)
	if input.KeyCode == Enum.KeyCode.Space then handbrake = false end
end)
UserInputService.WindowFocusReleased:Connect(function()
	handbrake = false
	lastSteerDirection = 0
end)

function VehicleController.SetSteeringRateScale(value: number)
	steeringRateScale = math.clamp(value, 0.5, 1.5)
end

function VehicleController.GetTelemetry(): VehicleTelemetry
	return telemetry
end

function VehicleController.GetActiveVehicle(): Model?
	return activeVehicle
end

function VehicleController.SetActiveVehicle(vehicle: Model?)
	if activeVehicle == vehicle then
		return
	end
	if touchConnection then
		touchConnection:Disconnect()
		touchConnection = nil
	end
	activeVehicle = vehicle
	currentSteer, targetSteer, wheelSpinAngle = 0, 0, 0
	if vehicle then
		local carId = vehicle:GetAttribute("CarId") :: string? or "KazeRS"
		activeTuning = CarProfiles.Get(carId)
		currentRPM = activeTuning.Engine.IdleRPM
		flywheelRPM = activeTuning.Engine.IdleRPM
		currentGear = 1
		prevGear = 1
		prevVelocity = Vector3.zero
		damageZones = { Front = 0, Rear = 0, Left = 0, Right = 0, Roof = 0 }

		local primary = vehicle.PrimaryPart
		if primary then
			touchConnection = primary.Touched:Connect(function(hitPart: BasePart)
				if not hitPart or not activeVehicle or not activeVehicle.PrimaryPart then
					return
				end
				-- Ignore road slices, grass verges, terrain banks, and own vehicle/character parts
				if hitPart:IsDescendantOf(activeVehicle) then
					return
				end
				local player = Players.LocalPlayer
				if player and player.Character and hitPart:IsDescendantOf(player.Character) then
					return
				end
				if hitPart:GetAttribute("SurfaceType") ~= nil or hitPart:GetAttribute("IsCheckpoint") or hitPart:GetAttribute("IsStartTrigger") or hitPart:GetAttribute("IsFinishGate") then
					return
				end
				if not hitPart.CanCollide then
					return
				end

				local now = os.clock()
				if now - lastImpactClock < 0.22 then
					return
				end
				local speed = activeVehicle.PrimaryPart.AssemblyLinearVelocity.Magnitude
				if speed >= 14 then
					lastImpactClock = now
					local fakePrevVel = activeVehicle.PrimaryPart.AssemblyLinearVelocity * 1.45
					local currVel = activeVehicle.PrimaryPart.AssemblyLinearVelocity * 0.45
					DeformationModel.ApplyImpact(activeVehicle, fakePrevVel, currVel, hitPart.Position, damageZones)
				end
			end)
		end
	end
end

-- Check if LocalPlayer is seated in or owns a rally vehicle
local function checkSeatedVehicle()
	local player = Players.LocalPlayer
	local character = player and player.Character
	local humanoid = character and character:FindFirstChildOfClass("Humanoid")
	local seat = humanoid and humanoid.SeatPart

	if seat and (seat:IsA("VehicleSeat") or seat:IsA("Seat")) then
		local vehicle = seat:FindFirstAncestorWhichIsA("Model")
		if vehicle and (vehicle:GetAttribute("IsRallyVehicle") or vehicle.Parent == Workspace:FindFirstChild("Cars") or vehicle:FindFirstChild("Body")) then
			VehicleController.SetActiveVehicle(vehicle)
			return
		end
	end

	-- Fallback: bind to the player's spawned rally vehicle in Workspace.RallyVehicles or Workspace.Cars
	for _, folderName in ipairs({ "RallyVehicles", "Cars" }) do
		local vehiclesFolder = Workspace:FindFirstChild(folderName)
		if vehiclesFolder and player then
			for _, v in ipairs(vehiclesFolder:GetChildren()) do
				if v:IsA("Model") and (v:GetAttribute("IsRallyVehicle") or v:FindFirstChild("Body")) then
					local ownerId = v:GetAttribute("OwnerUserId")
					if ownerId == player.UserId then
						VehicleController.SetActiveVehicle(v)
						return
					end
				end
			end
		end
	end

	if activeVehicle and not activeVehicle.Parent then
		VehicleController.SetActiveVehicle(nil)
	end
end

-- 60 FPS Physics Loop
RunService.Heartbeat:Connect(function(dt)
	checkSeatedVehicle()

	local vehicle = activeVehicle
	if not vehicle or not vehicle.PrimaryPart then
		return
	end

	local primaryPart = vehicle.PrimaryPart
	local seat = vehicle:FindFirstChild("VehicleSeat") :: VehicleSeat?
	local chassisCF = primaryPart.CFrame
	local linVel = primaryPart.AssemblyLinearVelocity
	local forwardVel = chassisCF.LookVector:Dot(linVel)
	local speedStudsPerSec = linVel.Magnitude
	local speedKmh = speedStudsPerSec * 1.09728
	local speedMph = speedKmh * 0.621371

	-- 1. Read Inputs from BOTH UserInputService AND VehicleSeat.ThrottleFloat / SteerFloat
	local wDown = UserInputService:IsKeyDown(Enum.KeyCode.W) or UserInputService:IsKeyDown(Enum.KeyCode.Up)
	local sDown = UserInputService:IsKeyDown(Enum.KeyCode.S) or UserInputService:IsKeyDown(Enum.KeyCode.Down)
	local aDown = UserInputService:IsKeyDown(Enum.KeyCode.A) or UserInputService:IsKeyDown(Enum.KeyCode.Left)
	local dDown = UserInputService:IsKeyDown(Enum.KeyCode.D) or UserInputService:IsKeyDown(Enum.KeyCode.Right)

	local seatThrottle = seat and seat.ThrottleFloat or 0
	local seatSteer = seat and seat.SteerFloat or 0
	if seatThrottle > 0.1 then
		wDown = true
	elseif seatThrottle < -0.1 then
		sDown = true
	end
	-- Keyboard reversals keep the rack where it is. If both keys overlap,
	-- the most recently pressed direction wins. Seat input remains analog.
	local degradation = DeformationModel.GetHandlingDegradation(damageZones, vehicle)
	local speedFactor = math.clamp(1.0 - (speedKmh / 200.0) * 0.45, 0.48, 1.0)
	local rawSteer = seatSteer
	if aDown and dDown then rawSteer = lastSteerDirection
	elseif aDown then rawSteer = -1
	elseif dDown then rawSteer = 1 end
	if UserInputService:GetFocusedTextBox() then
		rawSteer = 0
		wDown, sDown, handbrake = false, false, false
	end
	targetSteer = math.clamp((rawSteer * speedFactor + degradation.SteeringBias) * degradation.MaxSteerMultiplier, -1, 1)
	currentSteer = Steering.Step(currentSteer, targetSteer, dt, activeTuning.Steering, math.abs(rawSteer) < 0.01, steeringRateScale)

	-- Throttle and Brake
	prevThrottle = throttle
	if wDown then
		if forwardVel < -4 and currentGear == 1 then
			throttle = 0
			brake = 1
		else
			if currentGear == -1 and not isManual and forwardVel > -2 then
				currentGear = 1
			end
			throttle = 1
			brake = 0
		end
	elseif sDown then
		if forwardVel > 4 and currentGear >= 1 then
			throttle = 0
			brake = 1
		else
			if not isManual then
				currentGear = -1
			end
			throttle = 1
			brake = 0
		end
	else
		throttle = 0
		brake = 0
	end

	-- Brief torque interruption during gear shifts for authentic rally feel
	if shiftTimer > 0 then
		shiftTimer = math.max(0, shiftTimer - dt)
	end
	local effectiveThrottle = (shiftTimer > 0) and (throttle * 0.15) or throttle

	-- Anti-lag exhaust pop & turbo blow-off when lifting off throttle at high RPM
	if prevThrottle > 0.5 and throttle == 0 and currentRPM > activeTuning.Engine.Redline * 0.65 then
		triggerExhaustBackfire(vehicle)
	end

	-- 2. Progressive Flywheel, Clutch & Gearbox Simulation
	local ratios = activeTuning.Transmission.Ratios
	local idleRPM = activeTuning.Engine.IdleRPM
	local redline = activeTuning.Engine.Redline

	-- Realistic top speed (km/h) per gear for a 6-speed rally gearbox
	local gearTopSpeedsKmh = { 52, 84, 118, 152, 186, 222 }
	local gearMaxKmh = 52
	if currentGear >= 1 and currentGear <= #ratios then
		gearMaxKmh = gearTopSpeedsKmh[currentGear] or (45 + currentGear * 30)
	end

	-- Wheel-driven RPM based on current forward speed and gear
	local wheelCoupledRPM = idleRPM + (math.abs(speedKmh) / math.max(25, gearMaxKmh)) * (redline - idleRPM)

	-- Progressive flywheel revving (never jumps instantaneously to 3800 RPM!)
	if throttle > 0 then
		local revRate = (2600 + (1.0 - math.clamp(currentGear / 6, 0, 0.7)) * 1800) * throttle
		flywheelRPM = math.min(redline, flywheelRPM + revRate * dt)
		-- Couple flywheel to wheel speed (allowing slight clutch slip / wheelspin flare in lower gears)
		local maxClutchFlare = idleRPM + (redline - idleRPM) * (handbrake and 0.92 or math.clamp(0.38 + (speedKmh / gearMaxKmh) * 0.68, 0.38, 1.0))
		flywheelRPM = math.clamp(math.max(wheelCoupledRPM, flywheelRPM), idleRPM, maxClutchFlare)
	else
		-- Engine braking decay toward wheelCoupledRPM / idleRPM
		local targetCoastRPM = (speedKmh > 4) and math.max(idleRPM, wheelCoupledRPM) or idleRPM
		flywheelRPM = flywheelRPM + (targetCoastRPM - flywheelRPM) * math.clamp(dt * 6.5, 0, 1)
	end

	-- Automatic transmission shift points with hysteresis cooldown
	local now = os.clock()
	if not isManual and (now - lastShiftClock > 0.42) then
		if currentGear > 0 then
			if flywheelRPM >= redline * 0.91 and currentGear < #ratios and speedKmh >= gearMaxKmh * 0.80 then
				currentGear += 1
				shiftTimer = math.max(0.08, activeTuning.Transmission.ShiftTime or 0.12)
				lastShiftClock = now
				flywheelRPM *= 0.72 -- Authentic RPM drop on upshift!
			elseif speedKmh < (gearTopSpeedsKmh[currentGear - 1] or 0) * 0.68 and currentGear > 1 then
				currentGear -= 1
				shiftTimer = 0.08
				lastShiftClock = now
				flywheelRPM = math.min(redline * 0.88, flywheelRPM * 1.28)
			end
		end
	end

	if currentGear ~= prevGear then
		playGearShiftSound(vehicle)
		if currentGear > prevGear and currentRPM > redline * 0.70 then
			triggerExhaustBackfire(vehicle)
		end
		prevGear = currentGear
	end

	-- Rev-limiter flutter near redline & idle lope
	local revLimiterBounce = 0
	if throttle > 0 and flywheelRPM >= redline * 0.96 then
		revLimiterBounce = math.sin(now * 55) * 145
	elseif throttle == 0 and speedKmh < 3 then
		revLimiterBounce = math.sin(now * 16) * 24
	end
	currentRPM = math.clamp(flywheelRPM + revLimiterBounce, idleRPM - 30, redline)

	-- Turbo boost pressure (-0.6 bar vacuum at idle -> +2.2 bar under high-RPM load)
	local rpmNorm = math.clamp((currentRPM - idleRPM) / math.max(1000, redline - idleRPM), 0, 1)
	local targetBoost = (throttle > 0) and (-0.2 + rpmNorm * 2.4 * throttle) or -0.6
	currentBoostBar = currentBoostBar + (targetBoost - currentBoostBar) * math.clamp(dt * 8.0, 0, 1)

	-- Calculate Gear Ratio
	local activeRatio = 1.0
	if currentGear == -1 then
		activeRatio = -3.4
	elseif currentGear > 0 and currentGear <= #ratios then
		activeRatio = ratios[currentGear]
	end

	-- 3. Raycast filter
	local rayFilter = RaycastParams.new()
	rayFilter.FilterType = Enum.RaycastFilterType.Exclude
	local excludeList: { Instance } = { vehicle }
	local debrisFolder = Workspace:FindFirstChild("RallyDebris")
	if debrisFolder then
		table.insert(excludeList, debrisFolder)
	end
	local player = Players.LocalPlayer
	if player and player.Character then
		table.insert(excludeList, player.Character)
	end
	rayFilter.FilterDescendantsInstances = excludeList

	-- 4. Solve 4-wheel suspension physics with handling degradation damping
	local suspResult = RaycastSuspension.Solve(
		vehicle,
		dt,
		activeTuning,
		currentSteer,
		effectiveThrottle,
		brake,
		handbrake,
		activeRatio,
		currentRPM,
		rayFilter,
		degradation.DampingMultiplier
	)

	-- 5. Apply forces and stabilized torques to Center of Mass
	local vectorForce = primaryPart:FindFirstChild("ChassisForce", true) :: VectorForce?
	local torque = primaryPart:FindFirstChild("ChassisTorque", true) :: Torque?

	if vectorForce then
		vectorForce.Force = suspResult.NetForce
	end
	if torque then
		torque.Torque = suspResult.NetTorque
	end

	-- 6. Animate visual wheels (properly oriented along -Z forward!) & modulate per-wheel dust particles
	local wheelLinearSpeed = forwardVel
	if throttle > 0 and math.abs(forwardVel) < 25 then
		wheelLinearSpeed = (currentGear == -1 and -1 or 1) * math.max(math.abs(forwardVel), throttle * 22)
	end
	wheelSpinAngle = (wheelSpinAngle + (wheelLinearSpeed / math.max(0.5, activeTuning.Tyres.Radius)) * dt) % (math.pi * 2)

	local wheelsFolder = vehicle:FindFirstChild("VisualWheels")
	if wheelsFolder then
		for wName, state in pairs(suspResult.Wheels) do
			local motor = primaryPart:FindFirstChild("Motor_" .. wName) :: Motor6D?
			if motor then
				local isLeft = state.VisualOffset.X < 0
				local sideDmg = isLeft and damageZones.Left or damageZones.Right
				local damageCamber = (isLeft and 1 or -1) * (sideDmg * 0.18)
				motor.C0 = CFrame.new(state.VisualOffset)
					* CFrame.Angles(0, state.SteerAngle, damageCamber)
					* CFrame.Angles(wheelSpinAngle, 0, 0)
			end

			local visualWheel = wheelsFolder:FindFirstChild("Visual_" .. wName)
			local dustAtt = visualWheel and visualWheel:FindFirstChild("DustAttachment")
			local emitter = dustAtt and dustAtt:FindFirstChild("WheelDust") :: ParticleEmitter?
			if emitter then
				emitter.Color = ColorSequence.new(state.TireParticleColor)
				if state.IsGrounded and (speedKmh > 10 or (throttle > 0 and speedKmh > 3)) then
					local isLoose = (state.SurfaceName ~= "Tarmac")
					local slipFactor = math.clamp(math.abs(state.SlipAngle) / 16.0, 0, 1)
					if isLoose then
						emitter.Rate = math.clamp((speedKmh * 0.55) + (slipFactor * 55) + (throttle * 18), 0, 90)
					else
						emitter.Rate = (slipFactor > 0.30 or handbrake) and math.clamp(slipFactor * 40, 0, 45) or 0
					end
				else
					emitter.Rate = 0
				end
			end
		end
	end

	-- 7. Modulate 7-Layer Vehicle Audio (EngineIdle, EngineRev, GravelSkid, TarmacSkid)
	local maxSlip = 0
	for _, w in pairs(suspResult.Wheels) do
		if math.abs(w.SlipAngle) > maxSlip then
			maxSlip = math.abs(w.SlipAngle)
		end
	end

	local sndFolder = primaryPart:FindFirstChild("VehicleSounds")
	if sndFolder then
		local idleSnd = sndFolder:FindFirstChild("EngineIdle") :: Sound?
		local revSnd = sndFolder:FindFirstChild("EngineRev") :: Sound?
		local gravelSnd = sndFolder:FindFirstChild("GravelSkid") :: Sound?
		local tarmacSnd = sndFolder:FindFirstChild("TarmacSkid") :: Sound?

		if idleSnd then
			if not idleSnd.IsPlaying then
				idleSnd:Play()
			end
			idleSnd.PlaybackSpeed = 0.82 + rpmNorm * 0.62
			idleSnd.Volume = 0.48 * (1.0 - rpmNorm * 0.50)
		end
		if revSnd then
			if not revSnd.IsPlaying then
				revSnd:Play()
			end
			revSnd.PlaybackSpeed = 0.68 + rpmNorm * 1.28
			revSnd.Volume = (0.18 + rpmNorm * 0.68) * (0.60 + throttle * 0.40)
		end

		local isGrounded = suspResult.GroundedCount >= 2
		local skidIntensity = isGrounded
				and math.clamp((maxSlip - 4.5) / 20.0 + (handbrake and speedKmh > 12 and 0.65 or 0), 0, 1)
			or 0
		local isTarmac = (suspResult.DominantSurface == "Tarmac")

		if gravelSnd then
			if not gravelSnd.IsPlaying then
				gravelSnd:Play()
			end
			local gravelRoll = (not isTarmac and isGrounded) and math.clamp(speedKmh / 120.0, 0, 0.38) or 0
			gravelSnd.Volume = (not isTarmac) and math.clamp(gravelRoll + skidIntensity * 0.55, 0, 0.80) or 0
			gravelSnd.PlaybackSpeed = 0.85 + math.clamp(speedKmh / 150.0, 0, 0.42)
		end
		if tarmacSnd then
			if not tarmacSnd.IsPlaying then
				tarmacSnd:Play()
			end
			tarmacSnd.Volume = isTarmac and (skidIntensity * 0.68) or 0
			tarmacSnd.PlaybackSpeed = 0.92 + skidIntensity * 0.24
		end
	end

	-- 8. Velocity-impulse collision damage check (supplements Touched handler)
	local currentVel = primaryPart.AssemblyLinearVelocity
	if prevVelocity ~= Vector3.zero then
		local horizPrev = Vector3.new(prevVelocity.X, 0, prevVelocity.Z)
		local horizCurr = Vector3.new(currentVel.X, 0, currentVel.Z)
		local deltaV = (horizPrev - horizCurr).Magnitude
		if deltaV >= 12 and (os.clock() - lastImpactClock > 0.22) then
			lastImpactClock = os.clock()
			local impactDir = (horizPrev - horizCurr).Unit
			local contactWorld = primaryPart.Position + impactDir * 4.0
			DeformationModel.ApplyImpact(vehicle, prevVelocity, currentVel, contactWorld, damageZones)
		end
	end
	prevVelocity = currentVel

	-- 9. Update Telemetry
	local gearStr = "N"
	if currentGear == -1 then
		gearStr = "R"
	elseif currentGear > 0 then
		gearStr = tostring(currentGear)
	end

	telemetry = {
		SpeedKmh = speedKmh,
		SpeedMph = speedMph,
		RPM = currentRPM,
		Gear = currentGear,
		GearString = gearStr,
		Throttle = throttle,
		Brake = brake,
		Handbrake = handbrake,
		Steer = currentSteer,
		SlipAngleDeg = maxSlip,
		IsGrounded = suspResult.GroundedCount >= 2,
		TotalDamage = (damageZones.Front + damageZones.Rear + damageZones.Left + damageZones.Right + damageZones.Roof) / 5,
		SurfaceName = suspResult.DominantSurface,
		TransmissionMode = isManual and "MANUAL [T]" or "AUTO [T]",
		BoostBar = currentBoostBar,
		HandlingDegradation = degradation,
	}
end)

return VehicleController
