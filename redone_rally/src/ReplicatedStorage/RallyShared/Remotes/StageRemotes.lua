--!strict
-- StageRemotes.luau
-- Manages RemoteEvents and RemoteFunctions for stage lifecycle, split timing, and co-driver coordination.

local ReplicatedStorage = game:GetService("ReplicatedStorage")
local RunService = game:GetService("RunService")

local StageRemotes = {}

local FOLDER_NAME = "RallyRemotes"

function StageRemotes.GetOrCreateRemotes(): Folder
    local folder = ReplicatedStorage:FindFirstChild(FOLDER_NAME) :: Folder?
    if not folder then
        if RunService:IsServer() or not RunService:IsRunning() then
            folder = Instance.new("Folder")
            folder.Name = FOLDER_NAME
            
            -- RemoteEvents
            local events = {
                "StageStart",
                "SplitCrossed",
                "StageFinished",
                "PaceNoteTriggered",
                "CompanionSync",
                "TelemetryPacket",
                "SelectVehicle",
                "ApplySettings",
                "SyncGhostTelemetry",
            }
            for _, evtName in ipairs(events) do
                local evt = Instance.new("RemoteEvent")
                evt.Name = evtName
                evt.Parent = folder
            end
            
            -- RemoteFunctions
            local functions = {
                "RequestVehicleSpawn",
                "RequestStageRegen",
                "ToggleStageMode",
            }
            for _, fnName in ipairs(functions) do
                local fn = Instance.new("RemoteFunction")
                fn.Name = fnName
                fn.Parent = folder
            end
            
            folder.Parent = ReplicatedStorage
        else
            folder = ReplicatedStorage:WaitForChild(FOLDER_NAME, 10) :: Folder
        end
    end
    return folder :: Folder
end

function StageRemotes.GetEvent(eventName: string): RemoteEvent
    local folder = StageRemotes.GetOrCreateRemotes()
    local evt = folder:WaitForChild(eventName, 5) :: RemoteEvent
    return evt
end

function StageRemotes.GetFunction(functionName: string): RemoteFunction
    local folder = StageRemotes.GetOrCreateRemotes()
    local fn = folder:WaitForChild(functionName, 5) :: RemoteFunction
    return fn
end

return StageRemotes
