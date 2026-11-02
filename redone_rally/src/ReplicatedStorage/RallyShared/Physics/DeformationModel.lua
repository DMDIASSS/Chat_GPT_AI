--!strict
-- DeformationModel.luau
-- Zoned collision damage (5 zones), real-time 3D panel crumpling/denting (via PanelWeld C1 offsets),
-- collision sparks/sound feedback, and progressive 3D body panel detachment into Workspace.RallyDebris.

local Workspace = game:GetService("Workspace")
local Debris = game:GetService("Debris")

export type DamageZones = {
	Front: number,
	Rear: number,
	Left: number,
	Right: number,
	Roof: number,
}

export type DamageResult = {
	ImpactSeverity: "None" | "Light" | "Medium" | "Heavy" | "Knockout",
	DeltaV: number,
	PrimaryZone: string,
	TotalDamage: number,
	DetachedParts: { BasePart },
}

export type HandlingDegradation = {
	SteeringBias: number, -- Pull towards damaged side (-1.0 to 1.0)
	DampingMultiplier: number, -- Reduced damping on shocks (0.45 to 1.0)
	MaxSteerMultiplier: number, -- Reduced steering lock (0.65 to 1.0)
	DetachedPanelCount: number, -- Number of body panels detached into debris
}

local DeformationModel = {}

local DETACHMENT_THRESHOLDS: { [string]: number } = {
	PlateFront = 0.12,
	PlateRear = 0.12,
	HeadlightL = 0.22,
	HeadlightR = 0.22,
	Headlight1 = 0.22,
	Headlight2 = 0.22,
	TaillightL = 0.24,
	TaillightR = 0.24,
	TailLampL = 0.24,
	TailLampR = 0.24,
	BrakeLightL = 0.25,
	BrakeLightR = 0.25,
	MirrorL = 0.18,
	MirrorR = 0.18,
	BumperFront = 0.35,
	BumperRear = 0.35,
	FrontDetail = 0.32,
	Grille = 0.28,
	MudFlaps = 0.30,
	Exhaust = 0.38,
	Hood = 0.48,
	BonnetScoop = 0.42,
	BonnetVents = 0.40,
	DoorL = 0.52,
	DoorR = 0.52,
	Spoiler = 0.44,
	RoofSpoiler = 0.44,
	LightPod = 0.36,
}

local ZONE_WEIGHTS: { [string]: number } = {
	Front = 0.55,
	Rear = 0.45,
	Left = 0.40,
	Right = 0.40,
	Roof = 0.35,
}

local function getPartZone(partName: string): string
	if
		string.find(partName, "Rear")
		or string.find(partName, "Tail")
		or string.find(partName, "BrakeLight")
		or string.find(partName, "Spoiler")
		or string.find(partName, "Exhaust")
		or string.find(partName, "MudFlaps")
	then
		return "Rear"
	elseif string.find(partName, "Left") or string.find(partName, "MirrorL") or string.find(partName, "DoorL") then
		return "Left"
	elseif string.find(partName, "Right") or string.find(partName, "MirrorR") or string.find(partName, "DoorR") then
		return "Right"
	elseif string.find(partName, "Roof") then
		return "Roof"
	end
	return "Front"
end

function DeformationModel.ClassifyImpact(deltaV: number): string
	if deltaV >= 70 then
		return "Knockout"
	elseif deltaV >= 38 then
		return "Heavy"
	elseif deltaV >= 16 then
		return "Medium"
	elseif deltaV >= 5 then
		return "Light"
	end
	return "None"
end

function DeformationModel.ResolveImpactZone(chassisCFrame: CFrame, contactPoint: Vector3): string
	local localPt = chassisCFrame:PointToObjectSpace(contactPoint)
	local x = localPt.X
	local y = localPt.Y
	local z = localPt.Z

	if y > 1.8 then
		return "Roof"
	elseif z < -1.5 then
		return "Front"
	elseif z > 1.5 then
		return "Rear"
	elseif x > 0.6 then
		return "Right"
	elseif x < -0.6 then
		return "Left"
	end
	return "Front"
end

function DeformationModel.ApplyImpact(
	chassis: Model,
	prevVel: Vector3,
	currVel: Vector3,
	contactPoint: Vector3,
	damageZones: DamageZones
): DamageResult
	local deltaV = (prevVel - currVel).Magnitude
	local severity = DeformationModel.ClassifyImpact(deltaV)

	local detached: { BasePart } = {}
	if severity == "None" then
		return {
			ImpactSeverity = "None",
			DeltaV = deltaV,
			PrimaryZone = "None",
			TotalDamage = 0,
			DetachedParts = detached,
		}
	end

	local primaryPart = chassis.PrimaryPart
	if not primaryPart then
		return {
			ImpactSeverity = severity,
			DeltaV = deltaV,
			PrimaryZone = "None",
			TotalDamage = 0,
			DetachedParts = detached,
		}
	end

	-- Determine true impact point if caller passed primaryPart.Position
	local effectiveContact = contactPoint
	if (contactPoint - primaryPart.Position).Magnitude < 0.25 then
		local impulseDir = (prevVel - currVel)
		if impulseDir.Magnitude > 0.1 then
			effectiveContact = primaryPart.Position + impulseDir.Unit * 3.5
		else
			effectiveContact = (primaryPart.CFrame * CFrame.new(0, 0, -4.0)).Position
		end
	end

	local zone = DeformationModel.ResolveImpactZone(primaryPart.CFrame, effectiveContact)
	local damageIncrement = (deltaV / 55.0) * (ZONE_WEIGHTS[zone] or 0.45)

	if zone == "Front" then
		damageZones.Front = math.clamp(damageZones.Front + damageIncrement, 0, 1)
	elseif zone == "Rear" then
		damageZones.Rear = math.clamp(damageZones.Rear + damageIncrement, 0, 1)
	elseif zone == "Left" then
		damageZones.Left = math.clamp(damageZones.Left + damageIncrement, 0, 1)
	elseif zone == "Right" then
		damageZones.Right = math.clamp(damageZones.Right + damageIncrement, 0, 1)
	elseif zone == "Roof" then
		damageZones.Roof = math.clamp(damageZones.Roof + damageIncrement, 0, 1)
	end

	local totalDamage = (damageZones.Front + damageZones.Rear + damageZones.Left + damageZones.Right + damageZones.Roof) / 5

	-- Trigger Collision Sparks & Crash Sound
	local sparkAtt = primaryPart:FindFirstChild("ImpactSparkAttachment") :: Attachment?
	if sparkAtt then
		sparkAtt.Position = primaryPart.CFrame:PointToObjectSpace(effectiveContact)
		local sparkEmitter = sparkAtt:FindFirstChild("ImpactSparks") :: ParticleEmitter?
		if sparkEmitter then
			sparkEmitter:Emit(math.clamp(math.floor(deltaV * 1.2), 10, 45))
		end
	end
	local sndFolder = primaryPart:FindFirstChild("VehicleSounds")
	local crashSnd = sndFolder and sndFolder:FindFirstChild("CrashImpact") :: Sound?
	if crashSnd then
		crashSnd.Volume = math.clamp(deltaV / 35.0, 0.35, 1.0)
		crashSnd.PlaybackSpeed = 0.75 + math.random() * 0.35
		crashSnd:Play()
	end

	-- 1. Visibly Crumple / Dent / Skew 3D Body Panels in the Impact Zone
	local panelsFolder = chassis:FindFirstChild("BodyPanels")
	if panelsFolder then
		for _, part in ipairs(panelsFolder:GetChildren()) do
			if part:IsA("BasePart") and not part:GetAttribute("Detached") then
				local pZone = getPartZone(part.Name)
				if pZone == zone or part.Name == "Shell" then
					local weld = part:FindFirstChild("PanelWeld") :: Weld?
					if weld then
						local scale = (part.Name == "Shell") and 0.22 or 0.65
						local dentIntensity = math.clamp(damageIncrement * scale, 0.04, 0.45)
						local dentOffset = Vector3.new(
							(math.random() - 0.5) * dentIntensity * 0.8,
							(math.random() - 0.3) * dentIntensity * 0.6,
							(zone == "Front" and 1 or (zone == "Rear" and -1 or 0)) * dentIntensity * 0.9
						)
						local dentRot = CFrame.Angles(
							(math.random() - 0.5) * dentIntensity * 0.45,
							(math.random() - 0.5) * dentIntensity * 0.35,
							(math.random() - 0.5) * dentIntensity * 0.45
						)
						weld.C1 = weld.C1 * CFrame.new(dentOffset) * dentRot
					end
				end
			end
		end
	end

	-- 2. Check for Part Detachments into Workspace.RallyDebris
	local debrisFolder = Workspace:FindFirstChild("RallyDebris") :: Folder?
	if not debrisFolder then
		debrisFolder = Instance.new("Folder")
		debrisFolder.Name = "RallyDebris"
		debrisFolder.Parent = Workspace
	end

	for partName, threshold in pairs(DETACHMENT_THRESHOLDS) do
		local part = chassis:FindFirstChild(partName, true) :: BasePart?
		if part and part:IsA("BasePart") and not part:GetAttribute("Detached") then
			local partZone = getPartZone(partName)
			local zoneDmg = (zone == partZone) and damageZones[partZone] or (totalDamage * 0.85)
			if zoneDmg >= threshold then
				part:SetAttribute("Detached", true)

				-- Break welds / constraints
				for _, child in ipairs(part:GetDescendants()) do
					if child:IsA("Weld") or child:IsA("Motor6D") or child:IsA("WeldConstraint") then
						child:Destroy()
					end
				end
				if part.Parent then
					for _, parentChild in ipairs(part.Parent:GetChildren()) do
						if parentChild:IsA("Weld") or parentChild:IsA("Motor6D") or parentChild:IsA("WeldConstraint") then
							if (parentChild :: any).Part1 == part or (parentChild :: any).Part0 == part then
								parentChild:Destroy()
							end
						end
					end
				end

				part.Transparency = 0.0
				part.CanCollide = true
				part.Anchored = false
				part.Parent = debrisFolder

				local randomImpulse = Vector3.new(
					(math.random() - 0.5) * 45,
					math.random() * 28 + 14,
					(math.random() - 0.5) * 45
				)
				part.AssemblyLinearVelocity = currVel + randomImpulse
				part.AssemblyAngularVelocity = Vector3.new(
					(math.random() - 0.5) * 18,
					(math.random() - 0.5) * 18,
					(math.random() - 0.5) * 18
				)

				Debris:AddItem(part, 15)
				table.insert(detached, part)
			end
		end
	end

	return {
		ImpactSeverity = severity,
		DeltaV = deltaV,
		PrimaryZone = zone,
		TotalDamage = totalDamage,
		DetachedParts = detached,
	}
end

function DeformationModel.GetHandlingDegradation(damageZones: DamageZones, vehicle: Model?): HandlingDegradation
	local leftRightDiff = (damageZones.Right - damageZones.Left)
	local steeringBias = math.clamp(leftRightDiff * 0.35, -0.40, 0.40)

	local detachedCount = 0
	if vehicle then
		for partName in pairs(DETACHMENT_THRESHOLDS) do
			local p = vehicle:FindFirstChild(partName, true)
			if not p or p:GetAttribute("Detached") then
				detachedCount += 1
			end
		end
	end

	local frontLoss = damageZones.Front * 0.30
	local panelLoss = math.min(0.35, detachedCount * 0.05)
	local dampingMult = math.clamp(1.0 - (frontLoss + panelLoss), 0.45, 1.0)
	local steerAuthority = math.clamp(1.0 - (damageZones.Front * 0.25), 0.65, 1.0)

	return {
		SteeringBias = steeringBias,
		DampingMultiplier = dampingMult,
		MaxSteerMultiplier = steerAuthority,
		DetachedPanelCount = detachedCount,
	}
end

return DeformationModel
