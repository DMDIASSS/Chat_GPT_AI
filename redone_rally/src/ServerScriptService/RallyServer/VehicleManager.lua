--!strict
-- VehicleManager.luau
-- Rally car builder and spawner.
-- Assembles a physically accurate rally chassis with 4 raycast wheel mounts, Center of Mass VectorForce/Torque,
-- genuine 3D MeshPart car shells & properly oriented 3D wheels from ReplicatedStorage.BackseatAssets,
-- detachable/deformable panels, collision sparks/audio, tire dust emitters, anti-lag exhaust backfire, and driver seat.

local Workspace = game:GetService("Workspace")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local PhysicsService = game:GetService("PhysicsService")

local CarProfiles = require(ReplicatedStorage.RallyShared.Config.CarProfiles)
local RaycastSuspension = require(ReplicatedStorage.RallyShared.Physics.RaycastSuspension)
type CarTuning = CarProfiles.CarTuning

local VehicleManager = {}

local CAR_TEMPLATE_MAP: { [string]: string } = {
	BrennerS1 = "GroupB",
	KazeRS = "Sedan",
	FalkeE3 = "Saloon",
	KumoR1 = "Hybrid",
	FrecciaHF = "Coupe",
}

local CAR_LIVERY_MAP: { [string]: { Primary: Color3, Trim: Color3, Rim: Color3 } } = {
	BrennerS1 = {
		Primary = Color3.fromRGB(242, 238, 226), -- Group B Audi cream white
		Trim = Color3.fromRGB(235, 175, 25),     -- Rally yellow wing/trim
		Rim = Color3.fromRGB(235, 235, 235),
	},
	KazeRS = {
		Primary = Color3.fromRGB(22, 68, 195),   -- Subaru 555 World Rally Blue
		Trim = Color3.fromRGB(230, 185, 40),     -- Gold livery trim
		Rim = Color3.fromRGB(225, 180, 45),      -- Gold rally rims
	},
	FalkeE3 = {
		Primary = Color3.fromRGB(235, 238, 242), -- E30 Alpine White
		Trim = Color3.fromRGB(190, 30, 38),      -- M-Sport crimson trim
		Rim = Color3.fromRGB(185, 190, 198),
	},
	KumoR1 = {
		Primary = Color3.fromRGB(28, 30, 36),    -- Rally1 Carbon/Stealth
		Trim = Color3.fromRGB(215, 28, 38),      -- GR Red aero trim
		Rim = Color3.fromRGB(45, 48, 54),
	},
	FrecciaHF = {
		Primary = Color3.fromRGB(195, 28, 32),   -- Italian Rosso Corsa
		Trim = Color3.fromRGB(240, 200, 40),     -- HF Yellow trim
		Rim = Color3.fromRGB(230, 225, 210),
	},
}

local BODY_PAINT_PARTS: { [string]: boolean } = {
	Shell = true,
	DoorL = true,
	DoorR = true,
	RoofVent = true,
	BonnetScoop = true,
	MirrorL = true,
	MirrorR = true,
	FuelCap = true,
}

local TRIM_PAINT_PARTS: { [string]: boolean } = {
	RoofSpoiler = true,
	FrontDetail = true,
	BonnetVents = true,
	LightPod = true,
}

local function ensureCollisionGroups()
	pcall(function()
		PhysicsService:RegisterCollisionGroup("RallyVehicles")
		PhysicsService:RegisterCollisionGroup("RallyDebris")
		PhysicsService:CollisionGroupSetCollidable("RallyVehicles", "RallyDebris", false)
	end)
end

local function createWheelDustEmitter(parent: BasePart): ParticleEmitter
	local att = Instance.new("Attachment")
	att.Name = "DustAttachment"
	att.Position = Vector3.new(0, -0.6, 0.4)
	att.Parent = parent

	local emitter = Instance.new("ParticleEmitter")
	emitter.Name = "WheelDust"
	emitter.Color = ColorSequence.new(Color3.fromRGB(165, 142, 112))
	emitter.Size = NumberSequence.new({
		NumberSequenceKeypoint.new(0, 0.9),
		NumberSequenceKeypoint.new(0.4, 2.8),
		NumberSequenceKeypoint.new(1, 5.2),
	})
	emitter.Transparency = NumberSequence.new({
		NumberSequenceKeypoint.new(0, 0.30),
		NumberSequenceKeypoint.new(0.6, 0.62),
		NumberSequenceKeypoint.new(1, 1.0),
	})
	emitter.Lifetime = NumberRange.new(0.45, 1.0)
	emitter.Rate = 0
	emitter.Speed = NumberRange.new(8, 22)
	emitter.SpreadAngle = Vector2.new(28, 28)
	emitter.RotSpeed = NumberRange.new(-100, 100)
	emitter.Acceleration = Vector3.new(0, 3.5, 0)
	emitter.Drag = 2.2
	emitter.Parent = att
	return emitter
end

function VehicleManager.BuildVehicleModel(carId: string, tuning: CarTuning): Model
	ensureCollisionGroups()

	local model = Instance.new("Model")
	model.Name = tuning.DisplayName or carId
	model:SetAttribute("CarId", carId)
	model:SetAttribute("IsRallyVehicle", true)

	local chassisFolder = Instance.new("Folder")
	chassisFolder.Name = "BodyPanels"
	chassisFolder.Parent = model

	local wheelsFolder = Instance.new("Folder")
	wheelsFolder.Name = "VisualWheels"
	wheelsFolder.Parent = model

	local livery = CAR_LIVERY_MAP[carId] or CAR_LIVERY_MAP.KazeRS

	-- 1. Main Rigid Chassis Body (PrimaryPart, invisible low-friction physics hull)
	local body = Instance.new("Part")
	body.Name = "Body"
	body.Size = Vector3.new(tuning.Chassis.TrackWidth - 0.5, 1.2, tuning.Chassis.Wheelbase - 0.4)
	body.Material = Enum.Material.SmoothPlastic
	body.Color = livery.Primary
	body.Transparency = 1.0 -- Invisible physics core; 3D shell provides visuals
	body.CanCollide = true
	body.Anchored = false
	body.Massless = false
	body.TopSurface = Enum.SurfaceType.Smooth
	body.BottomSurface = Enum.SurfaceType.Smooth

	-- Zero-friction skidplate physical properties so bottoming out never snags on road slices
	local volume = body.Size.X * body.Size.Y * body.Size.Z
	local targetDensity = math.clamp(tuning.Chassis.Mass / volume, 0.7, 50.0)
	pcall(function()
		body.CustomPhysicalProperties = PhysicalProperties.new(targetDensity, 0.02, 0.0, 100.0, 100.0)
	end)

	pcall(function()
		body.CollisionGroup = "RallyVehicles"
	end)
	body.Parent = model
	model.PrimaryPart = body

	local driverEye = Instance.new("Attachment")
	driverEye.Name = "DriverEye"
	driverEye.Position = tuning.Chassis.DriverEye or Vector3.new(-1.35, 2.2, 1)
	driverEye.Parent = body

	-- Center of Mass Attachment & Forces
	local comAttachment = Instance.new("Attachment")
	comAttachment.Name = "ChassisForces"
	comAttachment.Position = Vector3.new(0, 0, 0)
	comAttachment.Parent = body

	local vectorForce = Instance.new("VectorForce")
	vectorForce.Name = "ChassisForce"
	vectorForce.Attachment0 = comAttachment
	vectorForce.RelativeTo = Enum.ActuatorRelativeTo.World
	vectorForce.ApplyAtCenterOfMass = true
	vectorForce.Force = Vector3.zero
	vectorForce.Parent = body

	local torque = Instance.new("Torque")
	torque.Name = "ChassisTorque"
	torque.Attachment0 = comAttachment
	torque.RelativeTo = Enum.ActuatorRelativeTo.World
	torque.Torque = Vector3.zero
	torque.Parent = body

	-- Collision Sparks Emitter on Chassis
	local sparkAtt = Instance.new("Attachment")
	sparkAtt.Name = "ImpactSparkAttachment"
	sparkAtt.Position = Vector3.new(0, -0.2, -tuning.Chassis.Wheelbase * 0.45)
	sparkAtt.Parent = body

	local sparkEmitter = Instance.new("ParticleEmitter")
	sparkEmitter.Name = "ImpactSparks"
	sparkEmitter.Color = ColorSequence.new({
		ColorSequenceKeypoint.new(0, Color3.fromRGB(255, 245, 180)),
		ColorSequenceKeypoint.new(0.5, Color3.fromRGB(255, 150, 40)),
		ColorSequenceKeypoint.new(1, Color3.fromRGB(220, 50, 20)),
	})
	sparkEmitter.LightEmission = 1.0
	sparkEmitter.Size = NumberSequence.new({
		NumberSequenceKeypoint.new(0, 0.35),
		NumberSequenceKeypoint.new(1, 0.0),
	})
	sparkEmitter.Transparency = NumberSequence.new(0, 1)
	sparkEmitter.Lifetime = NumberRange.new(0.15, 0.38)
	sparkEmitter.Rate = 0
	sparkEmitter.Speed = NumberRange.new(22, 48)
	sparkEmitter.SpreadAngle = Vector2.new(75, 75)
	sparkEmitter.Acceleration = Vector3.new(0, -60, 0)
	sparkEmitter.Parent = sparkAtt

	-- 2. Four Wheel Mount Attachments (-Z is Front along LookVector, +Z is Rear)
	local halfTrack = tuning.Chassis.TrackWidth * 0.5
	local halfBase = tuning.Chassis.Wheelbase * 0.5
	local mountOffsets = {}
	for _, id in ipairs({ "WheelFL", "WheelFR", "WheelRL", "WheelRR" }) do
		mountOffsets[id] = RaycastSuspension.GetMountOffset(id, tuning)
	end

	for wName, offset in pairs(mountOffsets) do
		local att = Instance.new("Attachment")
		att.Name = wName
		att.Position = offset
		att.Parent = body
	end

	-- 3. Visual Wheel Assemblies with Motor6D + Correctly Oriented 3D Wheel Meshes + Dust Emitters
	local wheelRadius = tuning.Tyres.Radius
	local wheelWidth = 0.85
	local backseatAssets = ReplicatedStorage:FindFirstChild("BackseatAssets")
	local wheelTemplate = backseatAssets and backseatAssets:FindFirstChild("Wheel") :: Model?

	for wName, offset in pairs(mountOffsets) do
		local wheelPart = Instance.new("Part")
		wheelPart.Name = "Visual_" .. wName
		wheelPart.Shape = Enum.PartType.Block
		wheelPart.Size = Vector3.new(wheelWidth, wheelRadius * 2, wheelRadius * 2)
		wheelPart.Material = Enum.Material.SmoothPlastic
		wheelPart.Color = Color3.fromRGB(30, 30, 30)
		wheelPart.Transparency = 1.0
		wheelPart.CanCollide = false
		wheelPart.Anchored = false
		wheelPart.Massless = true
		local sag = wName:sub(6, 6) == "F" and tuning.Suspension.SagFront or tuning.Suspension.SagRear
		local drop = math.clamp(tuning.Suspension.Travel, 0.2, 4) - sag
		wheelPart.CFrame = body.CFrame * CFrame.new(offset.X, offset.Y - drop, offset.Z)
		wheelPart.Parent = wheelsFolder

		local motor = Instance.new("Motor6D")
		motor.Name = "Motor_" .. wName
		motor.Part0 = body
		motor.Part1 = wheelPart
		motor.C0 = CFrame.new(offset.X, offset.Y - drop, offset.Z)
		motor.C1 = CFrame.new(0, 0, 0)
		motor.Parent = body

		createWheelDustEmitter(wheelPart)

		if wheelTemplate then
			local wClone = wheelTemplate:Clone()
			wClone.Name = "Mesh3D"
			-- The supplied wheel is a left wheel with an X axle. Its imported
			-- mesh rotations were changed in the redone file; restore the saved
			-- Coupe wheel orientation before mirroring it onto the right side.
			local sourcePivot = wClone:GetPivot()
			for _, part in ipairs(wClone:GetDescendants()) do
				if part:IsA("MeshPart") and (part.Name == "Tyre" or part.Name == "Rim" or part.Name == "Nuts" or part.Name == "Barrel") then
					local offsetCF = sourcePivot:ToObjectSpace(part.CFrame)
					part.CFrame = sourcePivot * CFrame.new(offsetCF.Position) * CFrame.Angles(0, math.pi, 0)
				end
			end
			local tyre = wClone:FindFirstChild("Tyre") :: BasePart?
			if tyre then wClone:ScaleTo((wheelRadius * 2) / math.max(0.1, tyre.Size.Y)) end
			local sideRotation = offset.X > 0 and CFrame.Angles(0, math.pi, 0) or CFrame.identity
			wClone:PivotTo(wheelPart.CFrame * sideRotation)
			for _, desc in ipairs(wClone:GetDescendants()) do
				if desc:IsA("BasePart") then
					if desc.Name == "Rim" then
						desc.Color = livery.Rim
					end
					desc.Anchored = false
					desc.CanCollide = false
					desc.Massless = true
					local wWeld = Instance.new("WeldConstraint")
					wWeld.Part0 = wheelPart
					wWeld.Part1 = desc
					wWeld.Parent = desc
				end
			end
			wClone.Parent = wheelPart
		else
			-- Fallback cylinder visual if BackseatAssets.Wheel is absent
			local fallbackCyl = Instance.new("Part")
			fallbackCyl.Name = "FallbackTire"
			fallbackCyl.Shape = Enum.PartType.Cylinder
			fallbackCyl.Size = Vector3.new(wheelWidth, wheelRadius * 2, wheelRadius * 2)
			fallbackCyl.Material = Enum.Material.Rubber
			fallbackCyl.Color = Color3.fromRGB(28, 28, 30)
			fallbackCyl.CanCollide = false
			fallbackCyl.Anchored = false
			fallbackCyl.Massless = true
			fallbackCyl.CFrame = wheelPart.CFrame
			fallbackCyl.Parent = wheelPart
			local wWeld = Instance.new("WeldConstraint")
			wWeld.Part0 = wheelPart
			wWeld.Part1 = fallbackCyl
			wWeld.Parent = fallbackCyl
		end
	end

	-- 4. Mount 3D Car Exterior & Interior from ReplicatedStorage.BackseatAssets.Cars
	local carsAssets = backseatAssets and backseatAssets:FindFirstChild("Cars")
	local templateName = CAR_TEMPLATE_MAP[carId] or "Sedan"
	local carTemplate = carsAssets and carsAssets:FindFirstChild(templateName) :: Model?

	if carTemplate then
		local shellClone = carTemplate:Clone()
		-- Align 3D shell with physics body
		shellClone:PivotTo(body.CFrame)
		for _, child in ipairs(shellClone:GetChildren()) do
			if child:IsA("BasePart") and child.Name ~= "Root" then
				if BODY_PAINT_PARTS[child.Name] then
					child.Color = livery.Primary
				elseif TRIM_PAINT_PARTS[child.Name] then
					child.Color = livery.Trim
				end
				child.Anchored = false
				child.CanCollide = false
				child.Massless = true
				child.Parent = chassisFolder

				-- Use a regular Weld (with C0/C1) so DeformationModel can visibly crumple/dent/tilt panels on impact!
				local weld = Instance.new("Weld")
				weld.Name = "PanelWeld"
				weld.Part0 = body
				weld.Part1 = child
				weld.C0 = body.CFrame:ToObjectSpace(child.CFrame)
				weld.C1 = CFrame.identity
				weld.Parent = child

				-- Add anti-lag backfire flame + light to Exhaust
				if child.Name == "Exhaust" then
					local flameAtt = Instance.new("Attachment")
					flameAtt.Name = "BackfireAttachment"
					flameAtt.Position = Vector3.new(0, 0, 0.35)
					flameAtt.Parent = child

					local flame = Instance.new("ParticleEmitter")
					flame.Name = "BackfireFlame"
					flame.Color = ColorSequence.new({
						ColorSequenceKeypoint.new(0, Color3.fromRGB(120, 200, 255)),
						ColorSequenceKeypoint.new(0.4, Color3.fromRGB(255, 160, 30)),
						ColorSequenceKeypoint.new(1, Color3.fromRGB(220, 50, 15)),
					})
					flame.LightEmission = 1.0
					flame.Size = NumberSequence.new({
						NumberSequenceKeypoint.new(0, 0.45),
						NumberSequenceKeypoint.new(0.5, 0.85),
						NumberSequenceKeypoint.new(1, 0.0),
					})
					flame.Transparency = NumberSequence.new({
						NumberSequenceKeypoint.new(0, 0.0),
						NumberSequenceKeypoint.new(1, 1.0),
					})
					flame.Lifetime = NumberRange.new(0.06, 0.14)
					flame.Rate = 0
					flame.Speed = NumberRange.new(18, 32)
					flame.SpreadAngle = Vector2.new(12, 12)
					flame.Parent = flameAtt

					local light = Instance.new("PointLight")
					light.Name = "BackfireLight"
					light.Color = Color3.fromRGB(255, 150, 40)
					light.Brightness = 0
					light.Range = 10
					light.Parent = flameAtt
				end
			end
		end
		shellClone:Destroy()
	end

	-- Ensure named detachable structural bumpers/panels exist for DeformationModel
	local function addPanel(name: string, size: Vector3, localPos: Vector3, color: Color3, mat: Enum.Material, trans: number): BasePart
		local part = Instance.new("Part")
		part.Name = name
		part.Size = size
		part.Color = color
		part.Material = mat
		part.Transparency = trans
		part.CanCollide = false
		part.Anchored = false
		part.Massless = true
		part.CFrame = body.CFrame * CFrame.new(localPos)
		part.Parent = chassisFolder

		local weld = Instance.new("Weld")
		weld.Name = "PanelWeld"
		weld.Part0 = body
		weld.Part1 = part
		weld.C0 = CFrame.new(localPos)
		weld.C1 = CFrame.identity
		weld.Parent = part
		return part
	end

	local panelTrans = carTemplate and 1.0 or 0.0
	addPanel("BumperFront", Vector3.new(tuning.Chassis.TrackWidth, 0.6, 0.7), Vector3.new(0, -0.3, -halfBase - 0.8), Color3.fromRGB(35, 35, 35), Enum.Material.SmoothPlastic, panelTrans)
	addPanel("BumperRear", Vector3.new(tuning.Chassis.TrackWidth, 0.6, 0.7), Vector3.new(0, -0.3, halfBase + 0.8), Color3.fromRGB(35, 35, 35), Enum.Material.SmoothPlastic, panelTrans)
	addPanel("Hood", Vector3.new(tuning.Chassis.TrackWidth - 0.6, 0.3, halfBase * 0.7), Vector3.new(0, 0.5, -halfBase * 0.5), livery.Primary, Enum.Material.SmoothPlastic, panelTrans)
	addPanel("Spoiler", Vector3.new(tuning.Chassis.TrackWidth - 0.2, 0.35, 0.9), Vector3.new(0, 1.5, halfBase + 0.6), livery.Trim, Enum.Material.SmoothPlastic, panelTrans)
	addPanel("HeadlightL", Vector3.new(0.6, 0.35, 0.25), Vector3.new(-halfTrack * 0.7, 0.2, -halfBase - 0.7), Color3.fromRGB(240, 240, 255), Enum.Material.Neon, panelTrans)
	addPanel("HeadlightR", Vector3.new(0.6, 0.35, 0.25), Vector3.new(halfTrack * 0.7, 0.2, -halfBase - 0.7), Color3.fromRGB(240, 240, 255), Enum.Material.Neon, panelTrans)

	-- Real headlight beams for night/fog/rain driving
	for _, side in ipairs({ -1, 1 }) do
		local beamAtt = Instance.new("Attachment")
		beamAtt.Name = (side < 0) and "HeadlightBeamL" or "HeadlightBeamR"
		beamAtt.Position = Vector3.new(side * halfTrack * 0.65, 0.2, -halfBase - 0.8)
		beamAtt.Parent = body

		local spot = Instance.new("SpotLight")
		spot.Name = "RallyHeadlight"
		spot.Color = Color3.fromRGB(255, 248, 225)
		spot.Brightness = 2.5
		spot.Range = 65
		spot.Angle = 48
		spot.Face = Enum.NormalId.Front
		spot.Shadows = true
		spot.Parent = beamAtt
	end

	-- 5. Attach 7-Layer Audio Assets + Crash Impact Audio
	local soundsFolder = Instance.new("Folder")
	soundsFolder.Name = "VehicleSounds"
	soundsFolder.Parent = body

	local function addSound(name: string, soundId: string, volume: number, looped: boolean)
		local snd = Instance.new("Sound")
		snd.Name = name
		snd.SoundId = soundId
		snd.Volume = volume
		snd.Looped = looped
		snd.RollOffMaxDistance = 150
		snd.RollOffMinDistance = 10
		snd.Parent = soundsFolder
		return snd
	end

	addSound("EngineIdle", "rbxassetid://79745038579097", 0.55, true)
	addSound("EngineRev", "rbxassetid://109499866672746", 0.0, true)
	addSound("TurboBlowOff", "rbxassetid://8064513314", 0.65, false)
	addSound("Backfire", "rbxassetid://116973892997526", 0.75, false)
	addSound("GearShift", "rbxassetid://95172561097886", 0.55, false)
	addSound("GravelSkid", "rbxassetid://122588557195414", 0.0, true)
	addSound("TarmacSkid", "rbxassetid://103922979659462", 0.0, true)
	addSound("CrashImpact", "rbxassetid://95172561097886", 0.85, false)

	-- 6. Vehicle Seat (positioned inside left-hand driver bucket seat)
	local seat = Instance.new("VehicleSeat")
	seat.Name = "VehicleSeat"
	seat.Size = Vector3.new(1.8, 0.6, 1.8)
	seat.CFrame = body.CFrame * CFrame.new(-1.35, -0.1, 0.6)
	seat.Transparency = 1.0
	seat.CanCollide = false
	seat.Anchored = false
	seat.Massless = true
	seat.MaxSpeed = 0 -- Custom raycast physics handles propulsion
	seat.Torque = 0
	seat.TurnSpeed = 0
	seat.Parent = model

	local seatWeld = Instance.new("WeldConstraint")
	seatWeld.Part0 = body
	seatWeld.Part1 = seat
	seatWeld.Parent = seat

	-- Guarantee ZERO anchored parts anywhere in the vehicle hierarchy
	for _, desc in ipairs(model:GetDescendants()) do
		if desc:IsA("BasePart") then
			desc.Anchored = false
		end
	end

	return model
end

function VehicleManager.SpawnVehicle(carId: string, spawnCFrame: CFrame, player: Player?): Model
	if type(carId) ~= "string" or not CarProfiles.Cars[carId] then carId = "KazeRS" end
	local vehiclesFolder = Workspace:FindFirstChild("RallyVehicles") :: Folder?
	if not vehiclesFolder then
		vehiclesFolder = Instance.new("Folder")
		vehiclesFolder.Name = "RallyVehicles"
		vehiclesFolder.Parent = Workspace
	end

	-- Remove any previous vehicle belonging to this player OR any leftover unowned Edit-mode preview vehicle!
	for _, existing in ipairs(vehiclesFolder:GetChildren()) do
		if existing:IsA("Model") then
			local ownerId = existing:GetAttribute("OwnerUserId")
			if player then
				if ownerId == nil or ownerId == player.UserId then
					existing:Destroy()
				end
			elseif ownerId == nil then
				existing:Destroy()
			end
		end
	end

	local tuning = CarProfiles.Get(carId)
	local vehicle = VehicleManager.BuildVehicleModel(carId, tuning)
	if player then
		vehicle:SetAttribute("OwnerUserId", player.UserId)
	end

	vehicle.Parent = vehiclesFolder
	if vehicle.PrimaryPart then
		vehicle:PivotTo(spawnCFrame)
	end

	-- If player provided, seat player and assign network ownership to player for 0-latency client physics
	if player and vehicle.PrimaryPart then
		local primary = vehicle.PrimaryPart
		player.ReplicationFocus = primary
		local seat = vehicle:FindFirstChild("VehicleSeat") :: VehicleSeat?

		pcall(function()
			primary:SetNetworkOwner(player)
		end)

		if seat then
			seat:GetPropertyChangedSignal("Occupant"):Connect(function()
				if seat.Occupant and primary.Parent then
					pcall(function()
						primary:SetNetworkOwner(player)
					end)
				end
			end)
		end

		local character = player.Character
		if character then
			local humanoid = character:FindFirstChildOfClass("Humanoid")
			if humanoid and seat then
				task.defer(function()
					if character.Parent and seat.Parent then
						character:PivotTo(seat.CFrame * CFrame.new(0, 1.5, 0))
						seat:Sit(humanoid)
						pcall(function()
							primary:SetNetworkOwner(player)
						end)
					end
				end)
			end
		end
	end

	return vehicle
end

return VehicleManager
