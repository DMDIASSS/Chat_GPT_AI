--!strict
-- MainServer.luau
-- Authoritative server entry point for rally lifecycle, stage management, weather presets,
-- single-vehicle-per-player spawning (preventing duplicate/anchored cars), multiplayer co-driver companion sync, and split timing.

local Players = game:GetService("Players")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Workspace = game:GetService("Workspace")

local StageRemotes = require(ReplicatedStorage.RallyShared.Remotes.StageRemotes)
local StageManager = require(script.Parent.StageManager)
local VehicleManager = require(script.Parent.VehicleManager)

-- Initialize remotes
local remotesFolder = StageRemotes.GetOrCreateRemotes()
local splitEvent = StageRemotes.GetEvent("SplitCrossed")
local finishEvent = StageRemotes.GetEvent("StageFinished")
local startEvent = StageRemotes.GetEvent("StageStart")
local companionEvent = StageRemotes.GetEvent("CompanionSync")
local applySettingsEvent = StageRemotes.GetEvent("ApplySettings")
local spawnFunc = StageRemotes.GetFunction("RequestVehicleSpawn")
local regenFunc = StageRemotes.GetFunction("RequestStageRegen")
local toggleStageFunc = StageRemotes.GetFunction("ToggleStageMode")
local selectVehicleEvent = StageRemotes.GetEvent("SelectVehicle")

-- Setup ReplicaRequestData responder for Backseat Rally client handshake
local remoteFolder = ReplicatedStorage:FindFirstChild("RemoteEvents")
if not remoteFolder then
	remoteFolder = Instance.new("Folder")
	remoteFolder.Name = "RemoteEvents"
	remoteFolder.Parent = ReplicatedStorage
end
local replicaReq = remoteFolder:FindFirstChild("ReplicaRequestData") :: RemoteEvent?
if not replicaReq then
	replicaReq = Instance.new("RemoteEvent")
	replicaReq.Name = "ReplicaRequestData"
	replicaReq.Parent = remoteFolder
end
replicaReq.OnServerEvent:Connect(function(plr)
	replicaReq:FireClient(plr)
end)

-- Tag and initialize any existing cars in Workspace.Cars
local CollectionService = game:GetService("CollectionService")
local existingCars = Workspace:FindFirstChild("Cars")
if existingCars then
	for _, car in ipairs(existingCars:GetChildren()) do
		if car:IsA("Model") then
			CollectionService:AddTag(car, "Car")
			local body = car:FindFirstChild("Body") :: BasePart?
			if body then
				body.Anchored = false
			end
			car:SetAttribute("RunState", "Idle")
			car:SetAttribute("DriverUserId", 0)
			car:SetAttribute("OwnerUserId", 0)
		end
	end
end

-- Current stage mode: "PineForest" vs "Procedural"
local currentStageMode = "Procedural"

local savedVisibility: { [BasePart]: any } = setmetatable({}, { __mode = "k" })
local function showStage(folder: Instance?, visible: boolean)
    if not folder then return end
    for _,part in ipairs(folder:GetDescendants()) do
        if part:IsA("BasePart") then
            if not savedVisibility[part] then
                savedVisibility[part] = {part.Transparency,part.CanCollide,part.CanTouch,part.CanQuery}
            end
            local saved = savedVisibility[part]
            part.Transparency = visible and saved[1] or 1
            part.CanCollide = visible and saved[2] or false
            part.CanTouch = visible and saved[3] or false
            part.CanQuery = visible and saved[4] or false
        end
    end
end
local function setStageVisibility(mode: string): boolean
    local world = Workspace:FindFirstChild("World")
    local pineForest = world and world:FindFirstChild("Stage_PineForest")
    local proceduralStage = Workspace:FindFirstChild("RallyStage")
    if mode ~= "PineForest" and mode ~= "Procedural" then return false end
    if mode == "PineForest" and not pineForest then return false end
    if mode == "Procedural" and not proceduralStage then return false end
    showStage(pineForest,mode=="PineForest")
    showStage(proceduralStage,mode=="Procedural")
    currentStageMode = mode
    return true
end

toggleStageFunc.OnServerInvoke = function(player: Player, targetMode: string?)
    local newMode = targetMode or (currentStageMode == "Procedural" and "PineForest" or "Procedural")
    if not setStageVisibility(newMode) then return currentStageMode end
    -- Only move the requesting player's car, never a friend's arbitrary first car.
    local vehicles = Workspace:FindFirstChild("RallyVehicles")
    if vehicles then
        for _,car in ipairs(vehicles:GetChildren()) do
            if car:IsA("Model") and car.PrimaryPart and car:GetAttribute("OwnerUserId")==player.UserId then
                car:PivotTo(newMode=="Procedural" and StageManager.GetStartCFrame() or CFrame.new(0,10,0))
                car.PrimaryPart.AssemblyLinearVelocity = Vector3.zero
                car.PrimaryPart.AssemblyAngularVelocity = Vector3.zero
            end
        end
    end
    return newMode
end

-- Track start trigger and spawn debounces
local playerStartTimes: { [Player]: number } = {}
local playerSpawnDebounce: { [Player]: number } = {}
local playerSelectedCar: { [Player]: string } = {}

-- Clear any leftover Edit-mode preview vehicles before spawning Play-mode vehicles
local initialVehiclesFolder = Workspace:FindFirstChild("RallyVehicles")
if initialVehiclesFolder then
	initialVehiclesFolder:ClearAllChildren()
end

-- Build initial procedural stage
print("[RallyServer] Building procedural stage...")
local stage = StageManager.BuildStage()
print(
	"[RallyServer] Stage generated with "
		.. #StageManager.GetSamples()
		.. " segments and "
		.. #StageManager.GetPaceNotes()
		.. " pace notes."
)

local function spawnCarForPlayer(player: Player, carIdOverride: string?): Model?
	local now = os.clock()
	local lastSpawn = playerSpawnDebounce[player]
	if not carIdOverride and lastSpawn and (now - lastSpawn < 1.5) then
		return nil
	end
	playerSpawnDebounce[player] = now

	local carId = carIdOverride or playerSelectedCar[player] or "KazeRS"
	playerSelectedCar[player] = carId
	local startCF = StageManager.GetStartCFrame()
	return VehicleManager.SpawnVehicle(carId, startCF, player)
end

-- Vehicle spawn handler
spawnFunc.OnServerInvoke = function(player: Player, carId: string)
	return spawnCarForPlayer(player, carId or "KazeRS")
end

-- Vehicle selection remote listener
selectVehicleEvent.OnServerEvent:Connect(function(player: Player, carId: string)
	spawnCarForPlayer(player, carId or "KazeRS")
end)

-- Multiplayer Co-Driver Companion Tablet broadcast
companionEvent.OnServerEvent:Connect(function(sender: Player, noteIdx: number, desc: string, sev: number?, dir: string?)
	companionEvent:FireAllClients(noteIdx, desc, sev or 4, dir or "Straight")
end)

-- Weather / stage settings listener
applySettingsEvent.OnServerEvent:Connect(function(player: Player, settingKey: string, settingValue: any)
	if settingKey == "Weather" and type(settingValue) == "string" then
		StageManager.SetWeather(settingValue)
	end
end)

-- Forward declaration of trigger setup
local setupCheckpointTriggers: () -> ()

-- Stage regen handler (supports custom seed and optional weather preset)
local lastGenerationClock = -math.huge
regenFunc.OnServerInvoke = function(player: Player, newSeed: number?, weatherPreset: string?)
	if os.clock() - lastGenerationClock < 3 then return false end
	lastGenerationClock = os.clock()
	local seed = type(newSeed)=="number" and newSeed==newSeed and math.clamp(math.floor(newSeed),1,999999) or math.random(1,999999)
	StageManager.BuildStage({
		Seed = seed,
		LengthStuds = 3500,
		RoadWidth = 24,
		SegmentLength = 16,
		Curviness = 1.0,
		ElevationRange = 55,
		Weather = type(weatherPreset)=="string" and weatherPreset or "Clear",
	})
	task.defer(setupCheckpointTriggers)
	setStageVisibility("Procedural")
	playerStartTimes = {}
	-- A regenerated route replaces the shared road; bring every driver with it.
	for _,driver in ipairs(Players:GetPlayers()) do
		spawnCarForPlayer(driver, playerSelectedCar[driver] or "KazeRS")
	end
	return true
end

-- Stage checkpoint, start & finish touch connections
setupCheckpointTriggers = function()
	local stageFolder = Workspace:WaitForChild("RallyStage", 10)
	if not stageFolder then
		return
	end
	local checkpointsFolder = stageFolder:WaitForChild("Checkpoints", 10)
	if not checkpointsFolder then
		return
	end

	for _, child in ipairs(checkpointsFolder:GetChildren()) do
		-- 1. Start Gantry Trigger
		local startTrigger = child:FindFirstChild("StartTrigger") :: BasePart?
		if startTrigger and startTrigger:GetAttribute("IsStartTrigger") then
			startTrigger.Touched:Connect(function(hit)
				local car = hit:FindFirstAncestorWhichIsA("Model")
				if car and car:GetAttribute("IsRallyVehicle") then
					local seat = car:FindFirstChild("VehicleSeat") :: VehicleSeat?
					local ownerId = car:GetAttribute("OwnerUserId")
					local player = (seat and seat.Occupant and Players:GetPlayerFromCharacter(seat.Occupant.Parent))
						or (ownerId and Players:GetPlayerByUserId(ownerId))
					if player then
						local now = os.clock()
						local lastStart = playerStartTimes[player] or 0
						if now - lastStart > 5.0 then
							playerStartTimes[player] = now
							startEvent:FireClient(player, now)
						end
					end
				end
			end)
		end

		-- 2. Split Checkpoint Triggers
		local trigger = child:FindFirstChild("Trigger") :: BasePart?
		if trigger and trigger:GetAttribute("IsCheckpoint") then
			local splitIdx = trigger:GetAttribute("SplitIndex") :: number
			local dist = trigger:GetAttribute("Distance") :: number
			trigger.Touched:Connect(function(hit)
				local car = hit:FindFirstAncestorWhichIsA("Model")
				if car and car:GetAttribute("IsRallyVehicle") then
					local seat = car:FindFirstChild("VehicleSeat") :: VehicleSeat?
					local ownerId = car:GetAttribute("OwnerUserId")
					local player = (seat and seat.Occupant and Players:GetPlayerFromCharacter(seat.Occupant.Parent))
						or (ownerId and Players:GetPlayerByUserId(ownerId))
					if player then
						splitEvent:FireClient(player, splitIdx, dist, os.clock())
					end
				end
			end)
		end

		-- 3. Finish Gate Trigger
		local finishTrigger = child:FindFirstChild("FinishTrigger") :: BasePart?
		if finishTrigger and finishTrigger:GetAttribute("IsFinishGate") then
			finishTrigger.Touched:Connect(function(hit)
				local car = hit:FindFirstAncestorWhichIsA("Model")
				if car and car:GetAttribute("IsRallyVehicle") then
					local seat = car:FindFirstChild("VehicleSeat") :: VehicleSeat?
					local ownerId = car:GetAttribute("OwnerUserId")
					local player = (seat and seat.Occupant and Players:GetPlayerFromCharacter(seat.Occupant.Parent))
						or (ownerId and Players:GetPlayerByUserId(ownerId))
					if player then
						finishEvent:FireClient(player, os.clock())
					end
				end
			end)
		end
	end
end

task.defer(setupCheckpointTriggers)

-- Player lifecycle: auto-spawn single vehicle on join
local function onPlayerAdded(player: Player)
	player.CharacterAdded:Connect(function()
		task.wait(0.8)
		spawnCarForPlayer(player)
	end)
	if player.Character then
		task.spawn(function()
			task.wait(0.8)
			spawnCarForPlayer(player)
		end)
	end
end

Players.PlayerAdded:Connect(onPlayerAdded)
for _, p in ipairs(Players:GetPlayers()) do
	onPlayerAdded(p)
end

Players.PlayerRemoving:Connect(function(player)
	playerStartTimes[player] = nil
	playerSpawnDebounce[player] = nil
	playerSelectedCar[player] = nil
end)

print("[RallyServer] Rally server initialized successfully.")
