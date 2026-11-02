--!strict
-- StageManager.luau
-- Procedural stage generator supporting Point-to-Point rally stages, rich post-processing graphics & climate presets,
-- wide grounded terrain embankments, ground-snapped 3D Backseat Rally & ForgeGUI Toolbox props,
-- start gate, split checkpoints, finish gate, and continuous endless mode.

local Workspace = game:GetService("Workspace")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Lighting = game:GetService("Lighting")

local CatmullRom = require(ReplicatedStorage.RallyShared.Splines.CatmullRom)
local BishopFrame = require(ReplicatedStorage.RallyShared.Splines.BishopFrame)
local CurvatureAnalyzer = require(ReplicatedStorage.RallyShared.Splines.CurvatureAnalyzer)
local SurfaceConfig = require(ReplicatedStorage.RallyShared.Config.SurfaceConfig)

export type StageConfig = {
	Seed: number,
	LengthStuds: number,
	RoadWidth: number,
	SegmentLength: number,
	Curviness: number,
	ElevationRange: number,
	Weather: string?,
}

local StageManager = {}

local DEFAULT_STAGE_CONFIG: StageConfig = {
	Seed = 42,
	LengthStuds = 3500, -- ~1 kilometer rally stage
	RoadWidth = 24, -- Wide enough for high-speed rally drifts
	SegmentLength = 16, -- 16 studs per road slice
	Curviness = 1.0,
	ElevationRange = 55,
	Weather = "Clear",
}

-- Active stage cache
local activeStageFolder: Folder? = nil
local activeSamples: { CatmullRom.SplineSample } = {}
local activePaceNotes: { CurvatureAnalyzer.PaceNote } = {}
local currentWeather = "Clear"

-- Helper to clone a 3D prop from ReplicatedStorage.BackseatAssets.Props and plant its bottom on targetCF
local function spawn3DProp(propName: string, targetCF: CFrame, parent: Instance): Model?
	local assets = ReplicatedStorage:FindFirstChild("BackseatAssets")
	local props = assets and assets:FindFirstChild("Props")
	local template = props and props:FindFirstChild(propName) :: Model?
	if not template then
		return nil
	end
	local clone = template:Clone()
	-- Ensure all parts in prop are anchored and non-floating
	for _, desc in ipairs(clone:GetDescendants()) do
		if desc:IsA("BasePart") then
			desc.Anchored = true
		end
	end
	-- Compute bounding box so bottom of model sits flush on targetCF.Position.Y
	local ok, bboxCF, bboxSize = pcall(function()
		return clone:GetBoundingBox()
	end)
	if ok and bboxCF and bboxSize then
		local pivotCF = clone:GetPivot()
		local bottomY = bboxCF.Position.Y - (bboxSize.Y * 0.5)
		local pivotToBottom = pivotCF.Position.Y - bottomY
		clone:PivotTo(targetCF * CFrame.new(0, math.max(0, pivotToBottom - 0.35), 0))
	else
		clone:PivotTo(targetCF)
	end
	clone.Parent = parent
	return clone
end

function StageManager.SetWeather(weatherName: string)
	currentWeather = weatherName
	Workspace:SetAttribute("WeatherPreset", weatherName)

	Lighting.GlobalShadows = true
	Lighting.EnvironmentDiffuseScale = 1.0
	Lighting.EnvironmentSpecularScale = 1.0
	Lighting.ShadowSoftness = 0.22

	local atmo = Lighting:FindFirstChildOfClass("Atmosphere")
	if not atmo then
		atmo = Instance.new("Atmosphere")
		atmo.Parent = Lighting
	end

	local bloom = Lighting:FindFirstChildOfClass("BloomEffect")
	if not bloom then
		bloom = Instance.new("BloomEffect")
		bloom.Parent = Lighting
	end
	bloom.Intensity = 0.45
	bloom.Size = 24
	bloom.Threshold = 1.8

	local sunRays = Lighting:FindFirstChildOfClass("SunRaysEffect")
	if not sunRays then
		sunRays = Instance.new("SunRaysEffect")
		sunRays.Parent = Lighting
	end
	sunRays.Intensity = 0.14
	sunRays.Spread = 0.65

	local cc = Lighting:FindFirstChildOfClass("ColorCorrectionEffect")
	if not cc then
		cc = Instance.new("ColorCorrectionEffect")
		cc.Parent = Lighting
	end

	if weatherName == "Rain" then
		Lighting.ClockTime = 16.5
		Lighting.Brightness = 1.5
		Lighting.OutdoorAmbient = Color3.fromRGB(85, 95, 110)
		Lighting.FogEnd = 900
		Lighting.FogColor = Color3.fromRGB(115, 128, 142)
		atmo.Density = 0.42
		atmo.Offset = 0.15
		atmo.Color = Color3.fromRGB(140, 152, 168)
		atmo.Decay = Color3.fromRGB(95, 105, 118)
		atmo.Haze = 2.2
		cc.Contrast = 0.10
		cc.Saturation = -0.08
		cc.TintColor = Color3.fromRGB(235, 242, 255)
	elseif weatherName == "NightFog" then
		Lighting.ClockTime = 21.2
		Lighting.Brightness = 0.6
		Lighting.OutdoorAmbient = Color3.fromRGB(32, 38, 52)
		Lighting.FogEnd = 450
		Lighting.FogColor = Color3.fromRGB(28, 34, 46)
		atmo.Density = 0.52
		atmo.Offset = 0.1
		atmo.Color = Color3.fromRGB(45, 55, 75)
		atmo.Decay = Color3.fromRGB(22, 28, 40)
		atmo.Haze = 3.0
		cc.Contrast = 0.16
		cc.Saturation = -0.05
		cc.TintColor = Color3.fromRGB(215, 228, 255)
	elseif weatherName == "Autumn" then
		Lighting.ClockTime = 15.8
		Lighting.Brightness = 2.6
		Lighting.OutdoorAmbient = Color3.fromRGB(135, 112, 92)
		Lighting.FogEnd = 2200
		Lighting.FogColor = Color3.fromRGB(215, 182, 145)
		atmo.Density = 0.30
		atmo.Offset = 0.2
		atmo.Color = Color3.fromRGB(235, 195, 150)
		atmo.Decay = Color3.fromRGB(175, 125, 85)
		atmo.Haze = 1.4
		cc.Contrast = 0.14
		cc.Saturation = 0.18
		cc.TintColor = Color3.fromRGB(255, 244, 228)
	else -- "Clear"
		Lighting.ClockTime = 15.1
		Lighting.Brightness = 2.85
		Lighting.OutdoorAmbient = Color3.fromRGB(118, 128, 138)
		Lighting.FogEnd = 3000
		Lighting.FogColor = Color3.fromRGB(188, 208, 230)
		atmo.Density = 0.26
		atmo.Offset = 0.22
		atmo.Color = Color3.fromRGB(198, 216, 238)
		atmo.Decay = Color3.fromRGB(130, 152, 178)
		atmo.Haze = 0.9
		cc.Contrast = 0.12
		cc.Saturation = 0.14
		cc.TintColor = Color3.fromRGB(255, 252, 245)
	end
end

function StageManager.GenerateControlPoints(config: StageConfig): { Vector3 }
	local rng = Random.new(config.Seed)
	local points: { Vector3 } = {}

	local numControlPoints = math.max(12, math.floor(config.LengthStuds / 140))
	local stepZ = config.LengthStuds / numControlPoints

	local currentX = 0
	local currentY = 12
	local currentZ = 0
	local headingAngle = 0

	for i = 1, numControlPoints + 3 do
		table.insert(points, Vector3.new(currentX, currentY, currentZ))

		-- Keep the first 4 control points gently aligned so the start area is clean and readable
		if i <= 3 then
			headingAngle = headingAngle * 0.4
		else
			local turnRoll = rng:NextNumber()
			local deltaAngle = 0
			if turnRoll < 0.15 then
				deltaAngle = rng:NextNumber(0.65, 1.15) * (rng:NextInteger(0, 1) == 1 and 1 or -1)
			elseif turnRoll < 0.45 then
				deltaAngle = rng:NextNumber(0.30, 0.64) * (rng:NextInteger(0, 1) == 1 and 1 or -1)
			else
				deltaAngle = rng:NextNumber(-0.24, 0.24)
			end
			headingAngle = math.clamp(headingAngle + deltaAngle * config.Curviness, -1.25, 1.25)
		end

		local segDist = stepZ * rng:NextNumber(0.88, 1.12)
		currentX += math.sin(headingAngle) * segDist
		currentZ += math.cos(headingAngle) * segDist

		local elevNoise = math.noise(i * 0.22, config.Seed * 0.07, 0.5)
		currentY = 12 + elevNoise * config.ElevationRange * 0.5
	end

	return points
end

function StageManager.BuildStage(customConfig: StageConfig?): Folder
	local config: StageConfig = if type(customConfig) == "table" then customConfig else DEFAULT_STAGE_CONFIG

	StageManager.SetWeather(config.Weather or currentWeather)

	-- Hide default grey checkerboard Baseplate so the rally stage environment looks authentic
	local baseplate = Workspace:FindFirstChild("Baseplate") :: BasePart?
	if baseplate then
		baseplate.Transparency = 1.0
		baseplate.CanCollide = false
	end

	-- Cleanup old stage
	local existing = Workspace:FindFirstChild("RallyStage")
	if existing then
		existing:Destroy()
	end

	local stageFolder = Instance.new("Folder")
	stageFolder.Name = "RallyStage"
	stageFolder.Parent = Workspace
	activeStageFolder = stageFolder

	local roadFolder = Instance.new("Folder")
	roadFolder.Name = "Roadbed"
	roadFolder.Parent = stageFolder

	local checkpointFolder = Instance.new("Folder")
	checkpointFolder.Name = "Checkpoints"
	checkpointFolder.Parent = stageFolder

	local sceneryFolder = Instance.new("Folder")
	sceneryFolder.Name = "Scenery"
	sceneryFolder.Parent = stageFolder

	-- Distant Forest Valley Floor beneath the entire stage
	local valleyFloor = Instance.new("Part")
	valleyFloor.Name = "StageValleyFloor"
	valleyFloor.Size = Vector3.new(2048, 4, 2048)
	valleyFloor.Position = Vector3.new(0, -18, config.LengthStuds * 0.45)
	valleyFloor.Anchored = true
	valleyFloor.CanCollide = true
	valleyFloor.Material = Enum.Material.LeafyGrass
	valleyFloor.Color = (currentWeather == "Autumn") and Color3.fromRGB(95, 78, 42) or Color3.fromRGB(48, 76, 38)
	valleyFloor:SetAttribute("SurfaceType", "Grass")
	valleyFloor.Parent = sceneryFolder

	-- 1. Generate Spline & Uniform Samples
	local controlPoints = StageManager.GenerateControlPoints(config)
	local samples = CatmullRom.GenerateUniformSpline(controlPoints, config.SegmentLength)
	activeSamples = samples

	-- 2. Analyze Curvature for Banked Frames & Co-Driver Pace Notes
	local curvatures: { number } = {}
	for i = 1, #samples do
		local iPrev = math.max(1, i - 1)
		local iNext = math.min(#samples, i + 1)
		local k, sign = CurvatureAnalyzer.ComputeDiscreteCurvature(
			samples[iPrev].Position,
			samples[i].Position,
			samples[iNext].Position
		)
		table.insert(curvatures, k * sign)
	end

	local frames = BishopFrame.GenerateFrames(samples, curvatures, 8.0) -- Max 8 deg bank

	-- 3. Generate Pace Notes & Store in ReplicatedStorage for Co-Driver & Companion Tablet
	local paceNotes = CurvatureAnalyzer.AnalyzeStage(samples)
	activePaceNotes = paceNotes

	local sharedNotesFolder = ReplicatedStorage:FindFirstChild("ActiveStageData")
	if sharedNotesFolder then
		sharedNotesFolder:Destroy()
	end
	sharedNotesFolder = Instance.new("Folder")
	sharedNotesFolder.Name = "ActiveStageData"

	local totalDistValue = Instance.new("NumberValue")
	totalDistValue.Name = "TotalDistance"
	totalDistValue.Value = samples[#samples].Distance
	totalDistValue.Parent = sharedNotesFolder

	local notesContainer = Instance.new("Folder")
	notesContainer.Name = "PaceNotes"
	notesContainer.Parent = sharedNotesFolder

	for idx, note in ipairs(paceNotes) do
		local noteVal = Instance.new("Configuration")
		noteVal.Name = string.format("Note_%03d", idx)
		local dist = (note :: any).Distance or note.DistanceAlongTrack or 0
		local desc = note.Description or CurvatureAnalyzer.FormatPaceNote(note)
		noteVal:SetAttribute("Index", idx)
		noteVal:SetAttribute("Position", note.Position)
		noteVal:SetAttribute("Distance", dist)
		noteVal:SetAttribute("EndDistance", (note :: any).EndDistance or (dist + (note.CornerLength or 30)))
		noteVal:SetAttribute("Direction", note.Direction)
		noteVal:SetAttribute("Severity", note.Severity)
		noteVal:SetAttribute("Modifier", note.Modifier or "")
		noteVal:SetAttribute("IsCrest", (note :: any).IsCrest or (note.Modifier == "Crest"))
		noteVal:SetAttribute("IsJump", (note :: any).IsJump or (note.Modifier == "Jump"))
		noteVal:SetAttribute("Description", desc)
		noteVal:SetAttribute("Text", desc)
		noteVal.Parent = notesContainer
	end
	-- A small, unstreamed route polyline gives every client the same distance
	-- reference, including while drifting or facing back along a hairpin.
	sharedNotesFolder:SetAttribute("Seed", config.Seed)
	sharedNotesFolder:SetAttribute("SampleCount", #samples)
	sharedNotesFolder:SetAttribute("NoteCount", #paceNotes)
	local route = Instance.new("Folder")
	route.Name = "RouteSamples"
	route.Parent = sharedNotesFolder
	for i, sample in ipairs(samples) do
		local point = Instance.new("Configuration")
		point.Name = string.format("Point_%04d", i)
		point:SetAttribute("Position", sample.Position)
		point:SetAttribute("Distance", sample.Distance)
		point.Parent = route
	end
	sharedNotesFolder.Parent = ReplicatedStorage

	-- 4. Extrude Roadbed Slices, Grounded Verges, Wide Forest Embankments & Ground-Snapped 3D Scenery
	local totalSamples = #samples
	local treeModels = { "Spruce1", "Spruce2", "Birch1" }
	local rockModels = { "Rock1", "Rock2" }
	local propRng = Random.new(config.Seed + 101)

	local vergeColor = (currentWeather == "Autumn") and Color3.fromRGB(108, 86, 44) or Color3.fromRGB(58, 92, 44)
	local bankColor = (currentWeather == "Autumn") and Color3.fromRGB(92, 74, 38) or Color3.fromRGB(48, 78, 38)

	for i = 1, totalSamples - 1 do
		local fA = frames[i]
		local fB = frames[i + 1]

		-- Select surface type based on progress (or Wet if Rain preset)
		local prog = i / totalSamples
		local sType = "Gravel"
		if prog < 0.25 then
			sType = (currentWeather == "Rain") and "Wet" or "Tarmac"
		elseif prog < 0.70 then
			sType = "Gravel"
		else
			sType = "Mud"
		end
		local surfaceProps = SurfaceConfig.Get(sType)

		local midPos = (fA.Position + fB.Position) * 0.5
		local length = (fB.Position - fA.Position).Magnitude
		local dir = (fB.Position - fA.Position).Unit
		local avgUp = (fA.Normal + fB.Normal).Unit
		local avgRight = dir:Cross(avgUp).Unit
		local trueUp = avgRight:Cross(dir).Unit

		-- Horizontal (unbanked) frame for roadside terrain banks & upright scenery placement
		local flatDir = Vector3.new(dir.X, 0, dir.Z)
		if flatDir.Magnitude < 0.01 then
			flatDir = Vector3.new(0, 0, 1)
		else
			flatDir = flatDir.Unit
		end
		local flatRight = flatDir:Cross(Vector3.yAxis).Unit
		local flatUp = flatRight:Cross(dir).Unit
		local flatSliceCF = CFrame.fromMatrix(midPos, flatRight, flatUp, -dir)
		local function bankY(point: Vector3): number
			return midPos.Y - (0.15 + flatUp:Dot(Vector3.new(point.X-midPos.X, 0, point.Z-midPos.Z))) / math.max(0.01, flatUp.Y)
		end

		-- Road slice part (orthonormal matrix without tilt or chord skew)
		local roadSlice = Instance.new("Part")
		roadSlice.Name = string.format("Road_%04d", i)
		roadSlice.Size = Vector3.new(config.RoadWidth, 1.2, length + 0.6)
		roadSlice.CFrame = CFrame.fromMatrix(midPos, avgRight, trueUp, -dir)
		roadSlice.Material = surfaceProps.Material
		roadSlice.Color = surfaceProps.Color
		roadSlice.Anchored = true
		roadSlice.CanCollide = true
		roadSlice.TopSurface = Enum.SurfaceType.Smooth
		roadSlice.BottomSurface = Enum.SurfaceType.Smooth
		roadSlice:SetAttribute("SurfaceType", sType)
		roadSlice:SetAttribute("Distance", samples[i].Distance)
		roadSlice.Parent = roadFolder

		-- Solid Subgrade Earth Foundation directly beneath Roadbed + Verges + Wide Forest Embankments
		-- Extends 160 studs wide (80 studs on each side of road center!) so NO tree or prop ever floats in the air!
		local bankTotalWidth = config.RoadWidth + 140
		local bankHeight = 26
		local terrainBase = Instance.new("Part")
		terrainBase.Name = "TerrainEmbankment"
		terrainBase.Size = Vector3.new(bankTotalWidth, bankHeight, length + 2.2)
		-- Top surface of terrainBase sits at midPos.Y - 0.15 (flush just below the road top at midPos.Y + 0.6)
		terrainBase.CFrame = flatSliceCF * CFrame.new(0, -(bankHeight * 0.5) - 0.15, 0)
		terrainBase.Material = Enum.Material.LeafyGrass
		terrainBase.Color = bankColor
		terrainBase.Anchored = true
		terrainBase.CanCollide = true
		terrainBase.TopSurface = Enum.SurfaceType.Smooth
		terrainBase:SetAttribute("SurfaceType", "Grass")
		terrainBase.Parent = roadFolder

		-- Left and Right verge shoulders (8 studs wide each, flush with road edge)
		local curbWidth = 8.0
		local curbHeight = 1.1
		local curbOffset = (config.RoadWidth * 0.5) + (curbWidth * 0.5)

		local leftCurb = Instance.new("Part")
		leftCurb.Name = "LeftVerge"
		leftCurb.Size = Vector3.new(curbWidth, curbHeight, length + 0.8)
		leftCurb.CFrame = roadSlice.CFrame * CFrame.new(-curbOffset, -0.08, 0)
		leftCurb.Material = Enum.Material.Grass
		leftCurb.Color = vergeColor
		leftCurb.Anchored = true
		leftCurb.CanCollide = true
		leftCurb:SetAttribute("SurfaceType", "Grass")
		leftCurb.Parent = roadFolder

		local rightCurb = Instance.new("Part")
		rightCurb.Name = "RightVerge"
		rightCurb.Size = Vector3.new(curbWidth, curbHeight, length + 0.8)
		rightCurb.CFrame = roadSlice.CFrame * CFrame.new(curbOffset, -0.08, 0)
		rightCurb.Material = Enum.Material.Grass
		rightCurb.Color = vergeColor
		rightCurb.Anchored = true
		rightCurb.CanCollide = true
		rightCurb:SetAttribute("SurfaceType", "Grass")
		rightCurb.Parent = roadFolder

		-- Ground-snapped 3D Forest Trees & Rocks right alongside the road (on every slice!)
		-- Ground surface Y on the embankment is midPos.Y - 0.15
		local groundSurfaceY = midPos.Y - 0.15
		for _, side in ipairs({ -1, 1 }) do
			-- Inner roadside trees (15 to 27 studs from road center — right next to the verge!)
			if i % 2 == 0 or side == 1 then
				local tName = treeModels[propRng:NextInteger(1, #treeModels)]
				local latDist = (config.RoadWidth * 0.5) + propRng:NextNumber(5.5, 16.5)
				local zJitter = propRng:NextNumber(-5.0, 5.0)
				local worldPt = (flatSliceCF * CFrame.new(side * latDist, 0, zJitter)).Position
				local yaw = propRng:NextNumber(0, math.pi * 2)
				local treeCF = CFrame.new(worldPt.X, bankY(worldPt), worldPt.Z) * CFrame.Angles(0, yaw, 0)
				if not spawn3DProp(tName, treeCF, sceneryFolder) then
					local tree = Instance.new("Part")
					tree.Name = "RallyTree"
					tree.Shape = Enum.PartType.Cylinder
					tree.Size = Vector3.new(20, 2.6, 2.6)
					tree.CFrame = CFrame.new(worldPt.X, bankY(worldPt) + 10, worldPt.Z) * CFrame.Angles(0, 0, math.pi / 2)
					tree.Material = Enum.Material.Wood
					tree.Color = Color3.fromRGB(90, 60, 35)
					tree.Anchored = true
					tree.Parent = sceneryFolder
				end
			end

			-- Outer forest canopy trees (28 to 52 studs from road center for dense forest backdrop)
			if i % 2 == 1 then
				local tName2 = treeModels[propRng:NextInteger(1, #treeModels)]
				local latDist2 = (config.RoadWidth * 0.5) + propRng:NextNumber(18.0, 42.0)
				local zJitter2 = propRng:NextNumber(-6.0, 6.0)
				local worldPt2 = (flatSliceCF * CFrame.new(side * latDist2, 0, zJitter2)).Position
				local yaw2 = propRng:NextNumber(0, math.pi * 2)
				local treeCF2 = CFrame.new(worldPt2.X, bankY(worldPt2), worldPt2.Z) * CFrame.Angles(0, yaw2, 0)
				spawn3DProp(tName2, treeCF2, sceneryFolder)
			end
		end

		-- Place 3D Rocks & Red/White Marker Poles right on the road shoulder
		if i % 4 == 0 then
			local rSide = (i % 8 == 0) and 1 or -1
			local rName = rockModels[propRng:NextInteger(1, #rockModels)]
			local rockLat = (config.RoadWidth * 0.5) + propRng:NextNumber(6.0, 14.0)
			local rockPt = (flatSliceCF * CFrame.new(rSide * rockLat, 0, 0)).Position
			local rockCF = CFrame.new(rockPt.X, bankY(rockPt), rockPt.Z)
				* CFrame.Angles(0, propRng:NextNumber(0, math.pi * 2), 0)
			spawn3DProp(rName, rockCF, sceneryFolder)

			local poleSide = -rSide
			local poleLat = (config.RoadWidth * 0.5) + 2.2
			local polePt = (flatSliceCF * CFrame.new(poleSide * poleLat, 0, 0)).Position
			local poleCF = CFrame.new(polePt.X, bankY(polePt) + 0.1, polePt.Z)
				* CFrame.fromMatrix(Vector3.zero, flatRight, flatUp, -flatDir)
			spawn3DProp("MarkerPole", poleCF, sceneryFolder)
		end

		-- Place Chevron signs & HayBales / TireBarriers on outside of sharp turns
		local curv = curvatures[i] or 0
		if i % 3 == 0 and math.abs(curv) >= 0.0018 then
			local outsideSide = (curv < 0) and 1 or -1
			local chevLat = (config.RoadWidth * 0.5) + 4.2
			local chevPt = (flatSliceCF * CFrame.new(outsideSide * chevLat, 0, 0)).Position
			local chevCF = CFrame.new(chevPt.X, bankY(chevPt) + 0.1, chevPt.Z)
				* CFrame.fromMatrix(Vector3.zero, flatRight, flatUp, -flatDir)
			spawn3DProp("ChevronSign", chevCF, sceneryFolder)
			if i % 6 == 0 then
				local barrierName = "HayBale"
				local barLat = (config.RoadWidth * 0.5) + 3.2
				local barPt = (flatSliceCF * CFrame.new(outsideSide * barLat, 0, 4)).Position
				local barCF = CFrame.new(barPt.X, bankY(barPt) + 0.1, barPt.Z)
					* CFrame.fromMatrix(Vector3.zero, flatRight, flatUp, -flatDir)
				spawn3DProp(barrierName, barCF, sceneryFolder)
			end
		end
	end

	-- 5. Construct Start Gate (Gantry, Red/Green Lights, 3D StartArch & Service Area)
	local startFrame = frames[4] or frames[2]
	local startGroundY = startFrame.Position.Y - 0.15
	local startGantry = Instance.new("Model")
	startGantry.Name = "StartGantry"
	startGantry.Parent = checkpointFolder

	spawn3DProp("StartArch", startFrame.CFrame * CFrame.new(0, 0.2, 0), startGantry)
	spawn3DProp("TimeControlBoard", startFrame.CFrame * CFrame.new(-config.RoadWidth * 0.5 - 4.0, 0.1, -6), startGantry)
	spawn3DProp("ServiceTent", startFrame.CFrame * CFrame.new(config.RoadWidth * 0.5 + 12, 0.1, 10), startGantry)
	spawn3DProp("Flag", startFrame.CFrame * CFrame.new(-config.RoadWidth * 0.5 - 4.5, 0.1, 8), startGantry)
	spawn3DProp("Flag", startFrame.CFrame * CFrame.new(config.RoadWidth * 0.5 + 4.5, 0.1, 8), startGantry)

	local startPostL = Instance.new("Part")
	startPostL.Name = "PostL"
	startPostL.Size = Vector3.new(1.5, 16, 1.5)
	startPostL.CFrame = startFrame.CFrame * CFrame.new(-config.RoadWidth * 0.5 - 2, 8, 0)
	startPostL.Anchored = true
	startPostL.Material = Enum.Material.Metal
	startPostL.Color = Color3.fromRGB(180, 30, 30)
	startPostL.Parent = startGantry

	local startPostR = Instance.new("Part")
	startPostR.Name = "PostR"
	startPostR.Size = Vector3.new(1.5, 16, 1.5)
	startPostR.CFrame = startFrame.CFrame * CFrame.new(config.RoadWidth * 0.5 + 2, 8, 0)
	startPostR.Anchored = true
	startPostR.Material = Enum.Material.Metal
	startPostR.Color = Color3.fromRGB(180, 30, 30)
	startPostR.Parent = startGantry

	local startBeam = Instance.new("Part")
	startBeam.Name = "GantryBeam"
	startBeam.Size = Vector3.new(config.RoadWidth + 6, 2.5, 2.5)
	startBeam.CFrame = startFrame.CFrame * CFrame.new(0, 16, 0)
	startBeam.Anchored = true
	startBeam.Material = Enum.Material.DiamondPlate
	startBeam.Color = Color3.fromRGB(40, 40, 40)
	startBeam.Parent = startGantry

	-- 5 Countdown Red/Green Lights
	for lightIdx = 1, 5 do
		local lightPart = Instance.new("Part")
		lightPart.Name = "GantryLight_" .. lightIdx
		lightPart.Shape = Enum.PartType.Ball
		lightPart.Size = Vector3.new(1.6, 1.6, 1.6)
		local lightX = -6 + (lightIdx - 1) * 3
		lightPart.CFrame = startBeam.CFrame * CFrame.new(lightX, 0, 1.4)
		lightPart.Material = Enum.Material.Neon
		lightPart.Color = Color3.fromRGB(40, 220, 60)
		lightPart.Anchored = true
		lightPart.CanCollide = false
		lightPart.Parent = startGantry
	end

	-- Physical Start Trigger (Fires StageRemotes.StageStart on car contact)
	local startTrigger = Instance.new("Part")
	startTrigger.Name = "StartTrigger"
	startTrigger.Size = Vector3.new(config.RoadWidth + 10, 14, 6)
	startTrigger.CFrame = startFrame.CFrame * CFrame.new(0, 7, 0)
	startTrigger.Transparency = 1.0
	startTrigger.CanCollide = false
	startTrigger.Anchored = true
	startTrigger:SetAttribute("IsStartTrigger", true)
	startTrigger.Parent = startGantry

	-- Start Spawn Point (placed behind StartTrigger on Road_0003 so car sits cleanly on its suspension)
	local startSpawn = Instance.new("CFrameValue")
	startSpawn.Name = "SpawnCFrame"
	startSpawn.Value = startFrame.CFrame * CFrame.new(0, 2.55, 14)
	startSpawn.Parent = startGantry

	-- 6. Construct Split Checkpoints at 25%, 50%, 75%
	local splitFractions = { 0.25, 0.50, 0.75 }
	for splitIdx, frac in ipairs(splitFractions) do
		local splitSampleIdx = math.clamp(math.floor(totalSamples * frac), 2, totalSamples - 2)
		local splitFrame = frames[splitSampleIdx]

		local splitGate = Instance.new("Model")
		splitGate.Name = "SplitGate_" .. splitIdx
		splitGate.Parent = checkpointFolder

		local trigger = Instance.new("Part")
		trigger.Name = "Trigger"
		trigger.Size = Vector3.new(config.RoadWidth + 10, 14, 4)
		trigger.CFrame = splitFrame.CFrame * CFrame.new(0, 7, 0)
		trigger.Transparency = 1.0
		trigger.CanCollide = false
		trigger.Anchored = true
		trigger:SetAttribute("SplitIndex", splitIdx)
		trigger:SetAttribute("Distance", samples[splitSampleIdx].Distance)
		trigger:SetAttribute("IsCheckpoint", true)
		trigger.Parent = splitGate

		local markerL = Instance.new("Part")
		markerL.Size = Vector3.new(1.5, 10, 1.5)
		markerL.CFrame = splitFrame.CFrame * CFrame.new(-config.RoadWidth * 0.5 - 2, 5, 0)
		markerL.Color = Color3.fromRGB(240, 190, 20)
		markerL.Material = Enum.Material.Neon
		markerL.Anchored = true
		markerL.Parent = splitGate

		local markerR = Instance.new("Part")
		markerR.Size = Vector3.new(1.5, 10, 1.5)
		markerR.CFrame = splitFrame.CFrame * CFrame.new(config.RoadWidth * 0.5 + 2, 5, 0)
		markerR.Color = Color3.fromRGB(240, 190, 20)
		markerR.Material = Enum.Material.Neon
		markerR.Anchored = true
		markerR.Parent = splitGate
	end

	-- 7. Construct Finish Gate (Flying Finish + 3D FinishArch & RaceSign)
	local finishIdx = totalSamples - 2
	local finishFrame = frames[finishIdx]
	local finishGate = Instance.new("Model")
	finishGate.Name = "FinishGate"
	finishGate.Parent = checkpointFolder

	spawn3DProp("FinishArch", finishFrame.CFrame * CFrame.new(0, 0.1, 0), finishGate)
	spawn3DProp("TimeControlBoard", finishFrame.CFrame * CFrame.new(-config.RoadWidth * 0.5 - 4.0, 0.1, 6), finishGate)
	spawn3DProp("RaceSign", finishFrame.CFrame * CFrame.new(config.RoadWidth * 0.5 + 4.5, 0.1, 6), finishGate)
	spawn3DProp("Flag", finishFrame.CFrame * CFrame.new(-config.RoadWidth * 0.5 - 4.5, 0.1, -6), finishGate)
	spawn3DProp("Flag", finishFrame.CFrame * CFrame.new(config.RoadWidth * 0.5 + 4.5, 0.1, -6), finishGate)

	local finishTrigger = Instance.new("Part")
	finishTrigger.Name = "FinishTrigger"
	finishTrigger.Size = Vector3.new(config.RoadWidth + 12, 16, 5)
	finishTrigger.CFrame = finishFrame.CFrame * CFrame.new(0, 8, 0)
	finishTrigger.Transparency = 1.0
	finishTrigger.CanCollide = false
	finishTrigger.Anchored = true
	finishTrigger:SetAttribute("IsFinishGate", true)
	finishTrigger:SetAttribute("Distance", samples[finishIdx].Distance)
	finishTrigger.Parent = finishGate

	local fPostL = Instance.new("Part")
	fPostL.Size = Vector3.new(2, 18, 2)
	fPostL.CFrame = finishFrame.CFrame * CFrame.new(-config.RoadWidth * 0.5 - 2, 9, 0)
	fPostL.Anchored = true
	fPostL.Color = Color3.fromRGB(30, 30, 30)
	fPostL.Parent = finishGate

	local fPostR = Instance.new("Part")
	fPostR.Size = Vector3.new(2, 18, 2)
	fPostR.CFrame = finishFrame.CFrame * CFrame.new(config.RoadWidth * 0.5 + 2, 9, 0)
	fPostR.Anchored = true
	fPostR.Color = Color3.fromRGB(30, 30, 30)
	fPostR.Parent = finishGate

	local fBanner = Instance.new("Part")
	fBanner.Name = "FinishBanner"
	fBanner.Size = Vector3.new(config.RoadWidth + 6, 3.5, 1.5)
	fBanner.CFrame = finishFrame.CFrame * CFrame.new(0, 18, 0)
	fBanner.Color = Color3.fromRGB(230, 230, 230)
	fBanner.Anchored = true
	fBanner.Parent = finishGate

	return stageFolder
end

function StageManager.GetStartCFrame(): CFrame
	if activeStageFolder then
		local gantry = activeStageFolder:FindFirstChild("Checkpoints")
		if gantry then
			local startG = gantry:FindFirstChild("StartGantry")
			if startG then
				local spawnVal = startG:FindFirstChild("SpawnCFrame") :: CFrameValue?
				if spawnVal then
					return spawnVal.Value
				end
			end
		end
	end
	return CFrame.new(0, 15, 0)
end

function StageManager.GetSamples(): { CatmullRom.SplineSample }
	return activeSamples
end

local activeChunks: { [number]: Model } = {}
local CHUNK_POOL_LIMIT = 5

function StageManager.GenerateChunk(chunkIndex: number, startCFrame: CFrame?, length: number?): (Model, CFrame, number)
	local stageFolder = Workspace:FindFirstChild("RallyStage")
	if not stageFolder then
		stageFolder = Instance.new("Folder")
		stageFolder.Name = "RallyStage"
		stageFolder.Parent = Workspace
	end

	local chunksFolder = stageFolder:FindFirstChild("Chunks") :: Folder?
	if not chunksFolder then
		chunksFolder = Instance.new("Folder")
		chunksFolder.Name = "Chunks"
		chunksFolder.Parent = stageFolder
	end

	local chunkLength = length or 800
	local roadWidth = 24
	local segmentLen = 16

	local startCF = startCFrame
	if not startCF then
		if activeSamples and #activeSamples > 0 then
			local lastS = activeSamples[#activeSamples]
			startCF = CFrame.lookAt(lastS.Position, lastS.Position + lastS.Tangent)
		else
			startCF = CFrame.new(0, 5, 0)
		end
	end

	local rng = Random.new(1000 + chunkIndex * 73)
	local controlPoints: { Vector3 } = {}

	local p0 = (startCF :: CFrame).Position
	local fwd = (startCF :: CFrame).LookVector
	table.insert(controlPoints, p0 - fwd * 120)
	table.insert(controlPoints, p0)

	local numPoints = math.max(5, math.floor(chunkLength / 140))
	local stepDist = chunkLength / numPoints
	local curPos = p0
	local heading = math.atan2(fwd.X, fwd.Z)

	for i = 1, numPoints + 1 do
		if i > 1 then
			local turnDelta = rng:NextNumber(-0.65, 0.65)
			heading = heading + turnDelta
		end
		local d = stepDist * rng:NextNumber(0.9, 1.1)
		local elev = math.noise(i * 0.35, chunkIndex * 1.7, 0.5) * 20
		curPos = curPos + Vector3.new(math.sin(heading) * d, elev * 0.25, math.cos(heading) * d)
		table.insert(controlPoints, curPos)
	end

	local chunkSamples = CatmullRom.GenerateUniformSpline(controlPoints, segmentLen)
	local curvatures: { number } = {}
	for i = 1, #chunkSamples do
		local iPrev = math.max(1, i - 1)
		local iNext = math.min(#chunkSamples, i + 1)
		local k, sign = CurvatureAnalyzer.ComputeDiscreteCurvature(
			chunkSamples[iPrev].Position,
			chunkSamples[i].Position,
			chunkSamples[iNext].Position
		)
		table.insert(curvatures, k * sign)
	end

	local chunkFrames = BishopFrame.GenerateFrames(chunkSamples, curvatures, 8.0)

	local chunkModel = Instance.new("Model")
	chunkModel.Name = string.format("Chunk_%03d", chunkIndex)
	chunkModel.Parent = chunksFolder

	local surfaces = { "Gravel", "Tarmac", "Mud", "Wet" }
	local chunkSurface = surfaces[(chunkIndex % #surfaces) + 1]
	local surfaceProps = SurfaceConfig.Get(chunkSurface)

	local startDist = (chunkIndex - 1) * chunkLength

	for i = 1, #chunkSamples - 1 do
		local fA = chunkFrames[i]
		local fB = chunkFrames[i + 1]

		local midPos = (fA.Position + fB.Position) * 0.5
		local sLen = (fB.Position - fA.Position).Magnitude
		local dir = (fB.Position - fA.Position).Unit
		local avgUp = (fA.Normal + fB.Normal).Unit
		local right = dir:Cross(avgUp).Unit
		local trueUp = right:Cross(dir).Unit

		local roadSlice = Instance.new("Part")
		roadSlice.Name = string.format("RoadSlice_%d", i)
		roadSlice.Size = Vector3.new(roadWidth, 1.2, sLen + 1.2)
		roadSlice.CFrame = CFrame.fromMatrix(midPos, right, trueUp, -dir)
		roadSlice.Material = surfaceProps.Material
		roadSlice.Color = surfaceProps.Color
		roadSlice.Anchored = true
		roadSlice.CanCollide = true
		roadSlice.TopSurface = Enum.SurfaceType.Smooth
		roadSlice.BottomSurface = Enum.SurfaceType.Smooth
		roadSlice:SetAttribute("SurfaceType", chunkSurface)
		roadSlice:SetAttribute("Distance", startDist + chunkSamples[i].Distance)
		roadSlice.Parent = chunkModel

		local curbWidth = 6.0
		local curbHeight = 1.0
		local curbOffset = (roadWidth * 0.5) + (curbWidth * 0.5)

		local leftCurb = Instance.new("Part")
		leftCurb.Name = "LeftVerge"
		leftCurb.Size = Vector3.new(curbWidth, curbHeight, sLen + 0.8)
		leftCurb.CFrame = roadSlice.CFrame * CFrame.new(-curbOffset, -0.1, 0)
		leftCurb.Material = Enum.Material.Grass
		leftCurb.Color = Color3.fromRGB(60, 95, 45)
		leftCurb.Anchored = true
		leftCurb.CanCollide = true
		leftCurb:SetAttribute("SurfaceType", "Grass")
		leftCurb.Parent = chunkModel

		local rightCurb = Instance.new("Part")
		rightCurb.Name = "RightVerge"
		rightCurb.Size = Vector3.new(curbWidth, curbHeight, sLen + 0.8)
		rightCurb.CFrame = roadSlice.CFrame * CFrame.new(curbOffset, -0.1, 0)
		rightCurb.Material = Enum.Material.Grass
		rightCurb.Color = Color3.fromRGB(60, 95, 45)
		rightCurb.Anchored = true
		rightCurb.CanCollide = true
		rightCurb:SetAttribute("SurfaceType", "Grass")
		rightCurb.Parent = chunkModel
	end

	activeChunks[chunkIndex] = chunkModel
	local oldestChunkToKeep = chunkIndex - CHUNK_POOL_LIMIT
	for idx, cModel in pairs(activeChunks) do
		if idx < oldestChunkToKeep then
			cModel:Destroy()
			activeChunks[idx] = nil
		end
	end

	local lastFrame = chunkFrames[#chunkFrames]
	local endCFrame = lastFrame.CFrame
	local endDistance = startDist + chunkSamples[#chunkSamples].Distance

	return chunkModel, endCFrame, endDistance
end

function StageManager.GetPaceNotes(): { CurvatureAnalyzer.PaceNote }
	return activePaceNotes
end

return StageManager
