--!strict
-- MainClient.luau
-- Client coordinator for vehicle physics, camera controller, co-driver engine, and PB ghost system.

local ReplicatedStorage = game:GetService("ReplicatedStorage")

print("[RallyClient] Initializing client subsystems...")

local rallyClientFolder = ReplicatedStorage:WaitForChild("RallyClient")
local VehicleController = require(rallyClientFolder:WaitForChild("VehicleController"))
local CameraController = require(rallyClientFolder:WaitForChild("CameraController"))
local CoDriverClient = require(rallyClientFolder:WaitForChild("CoDriverClient"))
local GhostClient = require(rallyClientFolder:WaitForChild("GhostClient"))

-- Connect stage remotes
local StageRemotes = require(ReplicatedStorage.RallyShared.Remotes.StageRemotes)
local splitEvent = StageRemotes.GetEvent("SplitCrossed")
local finishEvent = StageRemotes.GetEvent("StageFinished")

splitEvent.OnClientEvent:Connect(function(splitIndex, distance, timestamp)
    print(string.format("[RallyClient] Checkpoint %d cleared! Dist: %.1fm", splitIndex, distance * 0.28))
end)

finishEvent.OnClientEvent:Connect(function(timestamp)
    print("[RallyClient] Stage finished! Stop control reached.")
end)

print("[RallyClient] Dirt Rally 2.0 Client initialized successfully.")
