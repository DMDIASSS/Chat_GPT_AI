--!strict
-- ReplayGui.luau
-- Interactive Dirt Rally 2.0 replay controller GUI with timeline scrubber, play/pause, camera angle selector, and rewind.

local Players = game:GetService("Players")
local UserInputService = game:GetService("UserInputService")
local RunService = game:GetService("RunService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local TweenService = game:GetService("TweenService")

local TelemetryCodec = require(ReplicatedStorage.RallyShared.TelemetryCodec)
local GhostClient = require(ReplicatedStorage.RallyClient.GhostClient)
local CameraController = require(ReplicatedStorage.RallyClient.CameraController)
local VehicleController = require(ReplicatedStorage.RallyClient.VehicleController)

local player = Players.LocalPlayer
local playerGui = player:WaitForChild("PlayerGui")

-- Replay state
local isReplayActive = false
local replayVehicle: Model? = nil
local function stopReplay()
    isReplayActive = false
    CameraController.SetReplayTarget(nil)
    if replayVehicle then replayVehicle:Destroy(); replayVehicle = nil end
end
local function startReplay(carId: string)
    stopReplay()
    local live = VehicleController.GetActiveVehicle()
    if live then
        replayVehicle = live:Clone()
        for _,part in ipairs(replayVehicle:GetDescendants()) do
            if part:IsA("BasePart") then
                part.Anchored, part.CanCollide, part.CanTouch, part.CanQuery = true, false, false, false
            elseif part:IsA("LuaSourceContainer") or part:IsA("Constraint") or part:IsA("JointInstance") or part:IsA("Sound") then
                part:Destroy()
            end
        end
        replayVehicle:SetAttribute("IsRallyVehicle", false)
        replayVehicle.Name = "LocalReplay"
        replayVehicle.Parent = workspace
    else replayVehicle = GhostClient.BuildGhostVehicleModel(carId) end
    isReplayActive = true
    CameraController.SetReplayTarget(replayVehicle)
    CameraController.SetMode("TracksideDirector")
end
local isPaused = false
local replayTime = 0.0
local playbackSpeed = 1.0

-- Create ScreenGui
local screenGui = playerGui:FindFirstChild("ReplayGui") :: ScreenGui?
if not screenGui then
    screenGui = Instance.new("ScreenGui")
    screenGui.Name = "ReplayGui"
    screenGui.ResetOnSpawn = false
    screenGui.ZIndexBehavior = Enum.ZIndexBehavior.Sibling
    screenGui.Enabled = false
    screenGui.Parent = playerGui
end

-- Bottom Replay Control Bar
local controlBar = Instance.new("Frame")
controlBar.Name = "ControlBar"
controlBar.Size = UDim2.new(0, 680, 0, 75)
controlBar.Position = UDim2.new(0.5, -340, 1, -95)
controlBar.BackgroundColor3 = Color3.fromRGB(15, 18, 24)
controlBar.BackgroundTransparency = 0.25
controlBar.BorderSizePixel = 0
controlBar.Parent = screenGui

local barCorner = Instance.new("UICorner")
barCorner.CornerRadius = UDim.new(0, 10)
barCorner.Parent = controlBar

local barStroke = Instance.new("UIStroke")
barStroke.Color = Color3.fromRGB(60, 75, 95)
barStroke.Thickness = 1.2
barStroke.Parent = controlBar

-- Title & Time
local timeLabel = Instance.new("TextLabel")
timeLabel.Name = "TimeLabel"
timeLabel.Size = UDim2.new(0, 150, 0, 24)
timeLabel.Position = UDim2.new(0, 20, 0, 10)
timeLabel.BackgroundTransparency = 1
timeLabel.Font = Enum.Font.RobotoMono
timeLabel.Text = "00:00.000 / 00:00.000"
timeLabel.TextColor3 = Color3.fromRGB(240, 240, 240)
timeLabel.TextSize = 13
timeLabel.TextXAlignment = Enum.TextXAlignment.Left
timeLabel.Parent = controlBar

-- Timeline Track
local timelineTrack = Instance.new("Frame")
timelineTrack.Name = "TimelineTrack"
timelineTrack.Size = UDim2.new(1, -40, 0, 8)
timelineTrack.Position = UDim2.new(0, 20, 0, 36)
timelineTrack.BackgroundColor3 = Color3.fromRGB(35, 42, 54)
timelineTrack.BorderSizePixel = 0
timelineTrack.Parent = controlBar

local trackCorner = Instance.new("UICorner")
trackCorner.CornerRadius = UDim.new(0, 4)
trackCorner.Parent = timelineTrack

local timelineFill = Instance.new("Frame")
timelineFill.Name = "TimelineFill"
timelineFill.Size = UDim2.new(0, 0, 1, 0)
timelineFill.BackgroundColor3 = Color3.fromRGB(255, 215, 30)
timelineFill.BorderSizePixel = 0
timelineFill.Parent = timelineTrack

-- Scrubber Needle
local scrubberNeedle = Instance.new("Frame")
scrubberNeedle.Name = "ScrubberNeedle"
scrubberNeedle.Size = UDim2.new(0, 6, 0, 16)
scrubberNeedle.Position = UDim2.new(0, 0, 0.5, -8)
scrubberNeedle.BackgroundColor3 = Color3.fromRGB(255, 255, 255)
scrubberNeedle.BorderSizePixel = 0
scrubberNeedle.Parent = timelineTrack

-- Buttons Container
local btnContainer = Instance.new("Frame")
btnContainer.Name = "Buttons"
btnContainer.Size = UDim2.new(0, 320, 0, 26)
btnContainer.Position = UDim2.new(0.5, -160, 1, -28)
btnContainer.BackgroundTransparency = 1
btnContainer.Parent = controlBar

local btnLayout = Instance.new("UIListLayout")
btnLayout.FillDirection = Enum.FillDirection.Horizontal
btnLayout.HorizontalAlignment = Enum.HorizontalAlignment.Center
btnLayout.VerticalAlignment = Enum.VerticalAlignment.Center
btnLayout.Padding = UDim.new(0, 8)
btnLayout.Parent = btnContainer

local function makeBtn(text: string, callback: () -> ())
    local btn = Instance.new("TextButton")
    btn.Size = UDim2.new(0, 52, 0, 24)
    btn.BackgroundColor3 = Color3.fromRGB(28, 34, 44)
    btn.Font = Enum.Font.GothamBold
    btn.Text = text
    btn.TextColor3 = Color3.fromRGB(220, 230, 240)
    btn.TextSize = 12
    btn.BorderSizePixel = 0
    btn.Parent = btnContainer
    
    local c = Instance.new("UICorner")
    c.CornerRadius = UDim.new(0, 4)
    c.Parent = btn
    
    btn.MouseButton1Click:Connect(callback)
    return btn
end

-- Play/Pause Button
local playBtn = makeBtn("⏸ PAUSE", function()
    isPaused = not isPaused
    playBtn.Text = isPaused and "▶ PLAY" or "⏸ PAUSE"
end)

-- Rewind 5s
makeBtn("⏮ -5s", function()
    replayTime = math.max(0, replayTime - 5.0)
end)

-- Forward 5s
makeBtn("⏭ +5s", function()
    local pb = GhostClient.GetPersonalBest()
    if pb then
        replayTime = math.min(pb.TotalTime, replayTime + 5.0)
    end
end)

-- Restart
makeBtn("↺ RESTART", function()
    replayTime = 0
end)

-- Camera Selector in Replay
local camBtn = makeBtn("📷 CAM", function()
    local m = CameraController.GetMode()
    if m == "DynamicChase" then
        CameraController.SetMode("TracksideDirector")
    elseif m == "TracksideDirector" then
        CameraController.SetMode("Cockpit")
    elseif m == "Cockpit" then
        CameraController.SetMode("Chase")
    else
        CameraController.SetMode("DynamicChase")
    end
end)

-- Close Replay Button
local exitBtn = Instance.new("TextButton")
exitBtn.Size = UDim2.new(0, 80, 0, 24)
exitBtn.Position = UDim2.new(1, -95, 0, 10)
exitBtn.BackgroundColor3 = Color3.fromRGB(180, 40, 40)
exitBtn.Font = Enum.Font.GothamBold
exitBtn.Text = "✕ EXIT"
exitBtn.TextColor3 = Color3.fromRGB(255, 255, 255)
exitBtn.TextSize = 11
exitBtn.BorderSizePixel = 0
exitBtn.Parent = controlBar

local exitCorner = Instance.new("UICorner")
exitCorner.CornerRadius = UDim.new(0, 4)
exitCorner.Parent = exitBtn

exitBtn.MouseButton1Click:Connect(function()
    stopReplay()
    screenGui.Enabled = false
end)

-- Toggle Replay Mode: 'R'
UserInputService.InputBegan:Connect(function(input, processed)
    if not processed and input.KeyCode == Enum.KeyCode.R then
        local pb = GhostClient.GetPersonalBest()
        if pb and #pb.Frames > 0 then
            isReplayActive = not isReplayActive
            screenGui.Enabled = isReplayActive
            if isReplayActive then
                replayTime = 0
                isPaused = false
                startReplay(pb.CarId)
            else
                stopReplay()
            end
        else
            -- If no PB yet, record dummy or alert
            print("[Replay] Complete a stage run first to record replay telemetry!")
        end
    end
end)

-- Replay Update Loop
RunService.RenderStepped:Connect(function(dt)
    if not isReplayActive then return end
    
    local pb = GhostClient.GetPersonalBest()
    if not pb or pb.TotalTime <= 0 then return end
    
    if not isPaused then
        replayTime += dt * playbackSpeed
        if replayTime > pb.TotalTime then
            replayTime = 0 -- Loop replay
        end
    end
    
    -- Update Timeline UI
    local ratio = math.clamp(replayTime / pb.TotalTime, 0, 1)
    timelineFill.Size = UDim2.new(ratio, 0, 1, 0)
    scrubberNeedle.Position = UDim2.new(ratio, -3, 0.5, -8)
    
    local curM = math.floor(replayTime / 60)
    local curS = replayTime % 60
    local totM = math.floor(pb.TotalTime / 60)
    local totS = pb.TotalTime % 60
    timeLabel.Text = string.format("%02d:%05.2f / %02d:%05.2f", curM, curS, totM, totS)
    
    -- Sample telemetry at replayTime and drive active vehicle visualization
    if replayVehicle and replayVehicle.PrimaryPart then
        local interpCF, interpVel, interpSteer, interpRPM = TelemetryCodec.SampleAt(pb, replayTime)
        replayVehicle:PivotTo(interpCF)
        replayVehicle.PrimaryPart.AssemblyLinearVelocity = interpVel
        CameraController.SetReplaySteer(interpSteer)
    end
end)

print("[RallyGui] Replay Controller GUI initialized successfully.")
