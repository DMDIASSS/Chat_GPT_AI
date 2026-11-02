--!strict
-- GhostClient.luau
-- Manages translucent Personal Best (PB) ghost car playback and delta calculation.
-- Interpolates ghost vehicle along previous best run using TelemetryCodec.

local RunService = game:GetService("RunService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Workspace = game:GetService("Workspace")
local Players = game:GetService("Players")

local TelemetryCodec = require(ReplicatedStorage.RallyShared.TelemetryCodec)
local CarProfiles = require(ReplicatedStorage.RallyShared.Config.CarProfiles)
local VehicleController = require(script.Parent.VehicleController)
local StageRemotes = require(ReplicatedStorage.RallyShared.Remotes.StageRemotes)

type RunTelemetry = TelemetryCodec.RunTelemetry

local GhostClient = {}

local personalBestRun: RunTelemetry? = nil
local currentActiveRun: RunTelemetry? = nil
local recordingActive = false
local playbackActive = false
local recordTimer = 0
local stageStartTime = 0

local ghostModel: Model? = nil
local ghostEnabled = true

-- Build translucent holographic ghost car model
local function buildGhostVehicleModel(carId: string): Model
    local tuning = CarProfiles.Get(carId)
    local model = Instance.new("Model")
    model.Name = "PB_Ghost_" .. carId
    model:SetAttribute("IsGhostVehicle", true)
    
    local body = Instance.new("Part")
    body.Name = "Body"
    body.Size = Vector3.new(tuning.Chassis.TrackWidth + 0.4, 1.4, tuning.Chassis.Wheelbase + 1.2)
    body.Material = Enum.Material.Neon
    body.Color = Color3.fromRGB(80, 220, 255)
    body.Transparency = 0.55
    body.CanCollide = false
    body.Anchored = true
    body.CastShadow = false
    body.Parent = model
    model.PrimaryPart = body
    
    -- Translucent cabin
    local cabin = Instance.new("Part")
    cabin.Name = "Cabin"
    cabin.Size = Vector3.new(tuning.Chassis.TrackWidth - 0.6, 0.9, tuning.Chassis.Wheelbase * 0.55)
    cabin.Material = Enum.Material.Glass
    cabin.Color = Color3.fromRGB(180, 240, 255)
    cabin.Transparency = 0.65
    cabin.CanCollide = false
    cabin.Anchored = true
    cabin.CFrame = body.CFrame * CFrame.new(0, 1.15, -0.2)
    cabin.Parent = model
    
    -- Translucent wheels (-halfBase Front, +halfBase Rear)
    local halfTrack = tuning.Chassis.TrackWidth * 0.5
    local halfBase = tuning.Chassis.Wheelbase * 0.5
    local wheelRadius = tuning.Tyres.Radius
    local offsets = {
        Vector3.new(-halfTrack, tuning.Chassis.CGHeight, -halfBase),
        Vector3.new(halfTrack, tuning.Chassis.CGHeight, -halfBase),
        Vector3.new(-halfTrack, tuning.Chassis.CGHeight, halfBase),
        Vector3.new(halfTrack, tuning.Chassis.CGHeight, halfBase),
    }
    for idx, off in ipairs(offsets) do
        local w = Instance.new("Part")
        w.Name = "GhostWheel_" .. idx
        w.Shape = Enum.PartType.Cylinder
        w.Size = Vector3.new(0.85, wheelRadius * 2, wheelRadius * 2)
        w.Material = Enum.Material.Neon
        w.Color = Color3.fromRGB(100, 230, 255)
        w.Transparency = 0.65
        w.CanCollide = false
        w.Anchored = true
        w.CFrame = body.CFrame * CFrame.new(off) * CFrame.Angles(0, 0, math.pi / 2)
        w.Parent = model
    end
    
    local highlight = Instance.new("Highlight")
    highlight.Name = "GhostHighlight"
    highlight.FillColor = Color3.fromRGB(60, 210, 255)
    highlight.FillTransparency = 0.72
    highlight.OutlineColor = Color3.fromRGB(140, 245, 255)
    highlight.OutlineTransparency = 0.25
    highlight.Parent = model
    
    model.Parent = Workspace
    return model
end

GhostClient.BuildGhostVehicleModel = buildGhostVehicleModel

function GhostClient.SetGhostEnabled(enabled: boolean)
    ghostEnabled = enabled
    if ghostModel then
        ghostModel.Parent = enabled and Workspace or nil
    end
end

function GhostClient.GetPersonalBest(): RunTelemetry?
    return personalBestRun
end

function GhostClient.SetPersonalBest(run: RunTelemetry)
    personalBestRun = run
end

-- Stage Start remote listener: start recording and ghost playback
local startEvent = StageRemotes.GetEvent("StageStart")
startEvent.OnClientEvent:Connect(function(timestamp)
    stageStartTime = timestamp or os.clock()
    recordingActive = true
    playbackActive = (personalBestRun ~= nil and #personalBestRun.Frames > 0)
    recordTimer = 0
    
    local vehicle = VehicleController.GetActiveVehicle()
    local carId = vehicle and vehicle:GetAttribute("CarId") :: string or "KazeRS"
    
    currentActiveRun = {
        CarId = carId,
        TotalTime = 0,
        StageSeed = 42,
        Frames = {},
    }
    
    if playbackActive and personalBestRun and ghostEnabled then
        if ghostModel then ghostModel:Destroy() end
        ghostModel = buildGhostVehicleModel(personalBestRun.CarId)
    end
end)

-- Stage Finished remote listener: finalize PB
local finishEvent = StageRemotes.GetEvent("StageFinished")
finishEvent.OnClientEvent:Connect(function(timestamp)
    if recordingActive and currentActiveRun then
        recordingActive = false
        playbackActive = false
        currentActiveRun.TotalTime = (timestamp or os.clock()) - stageStartTime
        
        -- If faster than previous PB, update PB
        if not personalBestRun or currentActiveRun.TotalTime < personalBestRun.TotalTime then
            personalBestRun = currentActiveRun
            print(string.format("[GhostClient] New Personal Best saved! Time: %.3f s", personalBestRun.TotalTime))
        end
    end
end)

-- 20 Hz recording & 60 FPS playback
RunService.Heartbeat:Connect(function(dt)
    local vehicle = VehicleController.GetActiveVehicle()
    if not vehicle or not vehicle.PrimaryPart then return end
    
    -- Record frames
    if recordingActive and currentActiveRun then
        recordTimer += dt
        if recordTimer >= TelemetryCodec.SAMPLE_INTERVAL then
            recordTimer -= TelemetryCodec.SAMPLE_INTERVAL
            local cf = vehicle.PrimaryPart.CFrame
            local vel = vehicle.PrimaryPart.AssemblyLinearVelocity
            local telem = VehicleController.GetTelemetry()
            local t = os.clock() - stageStartTime
            
            table.insert(currentActiveRun.Frames, TelemetryCodec.CreateFrame(
                t, cf, vel, telem.Steer, telem.Throttle, telem.RPM, telem.Gear
            ))
        end
    end
    
    -- Playback ghost
    if playbackActive and personalBestRun and ghostModel and ghostModel.PrimaryPart and ghostEnabled then
        local t = os.clock() - stageStartTime
        local interpCF, _, _, _ = TelemetryCodec.SampleAt(personalBestRun, t)
        ghostModel:PivotTo(interpCF)
        
        if t > personalBestRun.TotalTime + 3.0 then
            playbackActive = false
            ghostModel.Parent = nil
        end
    end
end)

return GhostClient
