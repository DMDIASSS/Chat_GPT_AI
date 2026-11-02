--!strict
-- DirtRallyHud.luau
-- Authentic DiRT Rally 2.0 HUD Interface (mirrors RallyHudGui).
--
-- Layout specifications:
-- 1. Top-Left: Bold white italic MM:SS.mmm stage timer without background box.
-- 2. Left-Edge: Vertical stage progress bar divided into 4 sectors with checkered flag top,
--               filling green below, and red/white diamond marker (◆).
-- 3. Top-Center: Skewed square pacenote badges with color-coded borders
--               (Red = 1/Hairpin, Orange = 2, Yellow = 3, Green = 4-6) and modifier badges ("Don't Cut").
-- 4. Bottom-Right: Circular tachometer (0-8 RPM ring with redline, inner boost gauge,
--                  large italic gear on left, digital speed with dimmed leading zeros on right, handbrake warning light).

local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Workspace = game:GetService("Workspace")

local VehicleController = require(ReplicatedStorage.RallyClient.VehicleController)
local CameraController = require(ReplicatedStorage.RallyClient.CameraController)
local CoDriverClient = require(ReplicatedStorage.RallyClient.CoDriverClient)
local StageRemotes = require(ReplicatedStorage.RallyShared.Remotes.StageRemotes)

local player = Players.LocalPlayer
local playerGui = player:WaitForChild("PlayerGui")

-- Build HUD ScreenGui
local screenGui = playerGui:FindFirstChild("DirtRallyHud") :: ScreenGui?
if not screenGui then
    screenGui = Instance.new("ScreenGui")
    screenGui.Name = "DirtRallyHud"
    screenGui.ResetOnSpawn = false
    screenGui.ZIndexBehavior = Enum.ZIndexBehavior.Sibling
    screenGui.Parent = playerGui
end

--------------------------------------------------------------------------------
-- 1. TOP-LEFT: Stage Timer (Bold white italic MM:SS.mmm without background box)
--------------------------------------------------------------------------------
local timerContainer = Instance.new("Frame")
timerContainer.Name = "TimerContainer"
timerContainer.Size = UDim2.new(0, 320, 0, 80)
timerContainer.Position = UDim2.new(0, 35, 0, 25)
timerContainer.BackgroundTransparency = 1.0 -- NO background box
timerContainer.BorderSizePixel = 0
timerContainer.Parent = screenGui

local timerTitle = Instance.new("TextLabel")
timerTitle.Name = "StageTimerTitle"
timerTitle.Size = UDim2.new(1, 0, 0, 16)
timerTitle.Position = UDim2.new(0, 0, 0, 0)
timerTitle.BackgroundTransparency = 1
timerTitle.Font = Enum.Font.GothamBold
timerTitle.Text = "STAGE TIME"
timerTitle.TextColor3 = Color3.fromRGB(180, 195, 210)
timerTitle.TextSize = 11
timerTitle.TextXAlignment = Enum.TextXAlignment.Left
timerTitle.Parent = timerContainer

local stageTimerLabel = Instance.new("TextLabel")
stageTimerLabel.Name = "StageTimerLabel"
stageTimerLabel.Size = UDim2.new(1, 0, 0, 38)
stageTimerLabel.Position = UDim2.new(0, 0, 0, 18)
stageTimerLabel.BackgroundTransparency = 1
stageTimerLabel.RichText = true
stageTimerLabel.Font = Enum.Font.GothamBold
stageTimerLabel.Text = "<i><b>00:00.000</b></i>"
stageTimerLabel.TextColor3 = Color3.fromRGB(255, 255, 255)
stageTimerLabel.TextSize = 32
stageTimerLabel.TextXAlignment = Enum.TextXAlignment.Left
stageTimerLabel.Parent = timerContainer

local splitDeltaLabel = Instance.new("TextLabel")
splitDeltaLabel.Name = "SplitDeltaLabel"
splitDeltaLabel.Size = UDim2.new(1, 0, 0, 20)
splitDeltaLabel.Position = UDim2.new(0, 0, 0, 56)
splitDeltaLabel.BackgroundTransparency = 1
splitDeltaLabel.RichText = true
splitDeltaLabel.Font = Enum.Font.RobotoMono
splitDeltaLabel.Text = ""
splitDeltaLabel.TextColor3 = Color3.fromRGB(70, 240, 110)
splitDeltaLabel.TextSize = 14
splitDeltaLabel.TextXAlignment = Enum.TextXAlignment.Left
splitDeltaLabel.Parent = timerContainer

--------------------------------------------------------------------------------
-- 2. LEFT-EDGE: Vertical Stage Progress Bar
-- Divided into 4 sectors with checkered flag top, green fill below, diamond marker
--------------------------------------------------------------------------------
local progressContainer = Instance.new("Frame")
progressContainer.Name = "ProgressContainer"
progressContainer.Size = UDim2.new(0, 40, 0, 340)
progressContainer.Position = UDim2.new(0, 25, 0.5, -170)
progressContainer.BackgroundTransparency = 1.0
progressContainer.BorderSizePixel = 0
progressContainer.Parent = screenGui

-- Checkered flag icon at top
local finishFlag = Instance.new("TextLabel")
finishFlag.Name = "FinishFlag"
finishFlag.Size = UDim2.new(0, 26, 0, 20)
finishFlag.Position = UDim2.new(0.5, -13, 0, 0)
finishFlag.BackgroundTransparency = 1
finishFlag.Text = "🏁"
finishFlag.TextSize = 16
finishFlag.Parent = progressContainer

-- Vertical track background
local trackLength = 300
local trackBar = Instance.new("Frame")
trackBar.Name = "TrackBar"
trackBar.Size = UDim2.new(0, 8, 0, trackLength)
trackBar.Position = UDim2.new(0.5, -4, 0, 24)
trackBar.BackgroundColor3 = Color3.fromRGB(40, 48, 60)
trackBar.BorderSizePixel = 0
trackBar.Parent = progressContainer

local trackCorner = Instance.new("UICorner")
trackCorner.CornerRadius = UDim.new(0, 4)
trackCorner.Parent = trackBar

-- Green fill bar that fills upwards below player marker
local greenFill = Instance.new("Frame")
greenFill.Name = "GreenFill"
greenFill.Size = UDim2.new(1, 0, 0, 0)
greenFill.Position = UDim2.new(0, 0, 1, 0)
greenFill.AnchorPoint = Vector2.new(0, 1)
greenFill.BackgroundColor3 = Color3.fromRGB(40, 220, 60) -- Authentic bright green
greenFill.BorderSizePixel = 0
greenFill.Parent = trackBar

local greenCorner = Instance.new("UICorner")
greenCorner.CornerRadius = UDim.new(0, 4)
greenCorner.Parent = greenFill

-- 4 sectors divided by 3 split notch lines at 25%, 50%, 75%
local splitFractions = { 0.25, 0.50, 0.75 }
for idx, frac in ipairs(splitFractions) do
    local notch = Instance.new("Frame")
    notch.Name = "SectorNotch_" .. idx
    notch.Size = UDim2.new(0, 18, 0, 2)
    notch.Position = UDim2.new(0.5, -9, 1.0 - frac, -1)
    notch.BackgroundColor3 = Color3.fromRGB(240, 200, 40)
    notch.BorderSizePixel = 0
    notch.ZIndex = 3
    notch.Parent = trackBar
end

-- Red and white diamond marker (◆) indicating player vehicle position
local diamondMarker = Instance.new("Frame")
diamondMarker.Name = "DiamondMarker"
diamondMarker.Size = UDim2.new(0, 16, 0, 16)
diamondMarker.Position = UDim2.new(0.5, 0, 1.0, 0)
diamondMarker.AnchorPoint = Vector2.new(0.5, 0.5)
diamondMarker.BackgroundColor3 = Color3.fromRGB(235, 30, 30) -- Red diamond
diamondMarker.Rotation = 45 -- Rotate square 45 deg into diamond
diamondMarker.BorderSizePixel = 0
diamondMarker.ZIndex = 5
diamondMarker.Parent = trackBar

local diamondStroke = Instance.new("UIStroke")
diamondStroke.Color = Color3.fromRGB(255, 255, 255) -- White border
diamondStroke.Thickness = 2.0
diamondStroke.Parent = diamondMarker

--------------------------------------------------------------------------------
-- 3. TOP-CENTER: Skewed Square Pacenote Badges with Color-Coded Borders
-- Red = 1 / Hairpin, Orange = 2, Yellow = 3, Green = 4-6, with modifier sub-badge ("Don't Cut")
--------------------------------------------------------------------------------
local pacenoteContainer = Instance.new("Frame")
pacenoteContainer.Name = "PacenoteContainer"
pacenoteContainer.Size = UDim2.new(0, 280, 0, 105)
pacenoteContainer.Position = UDim2.new(0.5, -140, 0, 20)
pacenoteContainer.BackgroundTransparency = 1.0
pacenoteContainer.Visible = false
pacenoteContainer.Parent = screenGui

-- Skewed square badge frame
local badgeSquare = Instance.new("Frame")
badgeSquare.Name = "BadgeSquare"
badgeSquare.Size = UDim2.new(0, 88, 0, 88)
badgeSquare.Position = UDim2.new(0, 10, 0, 8)
badgeSquare.BackgroundColor3 = Color3.fromRGB(18, 22, 28)
badgeSquare.BackgroundTransparency = 0.15
badgeSquare.BorderSizePixel = 0
badgeSquare.Rotation = -3 -- Authentic DiRT Rally skewed look
badgeSquare.Parent = pacenoteContainer

local badgeCorner = Instance.new("UICorner")
badgeCorner.CornerRadius = UDim.new(0, 8)
badgeCorner.Parent = badgeSquare

local badgeStroke = Instance.new("UIStroke")
badgeStroke.Name = "BadgeBorder"
badgeStroke.Color = Color3.fromRGB(240, 215, 30) -- Dynamically colored
badgeStroke.Thickness = 3.5
badgeStroke.Parent = badgeSquare

local badgeDirectionIcon = Instance.new("TextLabel")
badgeDirectionIcon.Name = "DirectionIcon"
badgeDirectionIcon.Size = UDim2.new(0, 48, 0, 44)
badgeDirectionIcon.Position = UDim2.new(0, 4, 0, 4)
badgeDirectionIcon.BackgroundTransparency = 1
badgeDirectionIcon.Font = Enum.Font.GothamBlack
badgeDirectionIcon.Text = "◀"
badgeDirectionIcon.TextColor3 = Color3.fromRGB(255, 255, 255)
badgeDirectionIcon.TextSize = 34
badgeDirectionIcon.Parent = badgeSquare

local badgeSeverityNum = Instance.new("TextLabel")
badgeSeverityNum.Name = "SeverityNum"
badgeSeverityNum.Size = UDim2.new(0, 44, 0, 44)
badgeSeverityNum.Position = UDim2.new(1, -46, 1, -46)
badgeSeverityNum.BackgroundTransparency = 1
badgeSeverityNum.Font = Enum.Font.GothamBlack
badgeSeverityNum.Text = "4"
badgeSeverityNum.TextColor3 = Color3.fromRGB(255, 255, 255)
badgeSeverityNum.TextSize = 36
badgeSeverityNum.Parent = badgeSquare

-- Modifier sub-badge (e.g. "DON'T CUT") positioned in bottom-right
local modifierBadge = Instance.new("Frame")
modifierBadge.Name = "ModifierBadge"
modifierBadge.Size = UDim2.new(0, 92, 0, 22)
modifierBadge.Position = UDim2.new(0, 108, 0, 52)
modifierBadge.BackgroundColor3 = Color3.fromRGB(210, 35, 35) -- Red modifier warning
modifierBadge.BorderSizePixel = 0
modifierBadge.Visible = false
modifierBadge.Parent = pacenoteContainer

local modCorner = Instance.new("UICorner")
modCorner.CornerRadius = UDim.new(0, 4)
modCorner.Parent = modifierBadge

local modifierText = Instance.new("TextLabel")
modifierText.Name = "ModifierText"
modifierText.Size = UDim2.new(1, 0, 1, 0)
modifierText.BackgroundTransparency = 1
modifierText.Font = Enum.Font.GothamBold
modifierText.Text = "DON'T CUT"
modifierText.TextColor3 = Color3.fromRGB(255, 255, 255)
modifierText.TextSize = 10
modifierText.Parent = modifierBadge

-- Description label and distance chaining (> 50)
local callDesc = Instance.new("TextLabel")
callDesc.Name = "CallDescription"
callDesc.Size = UDim2.new(0, 160, 0, 26)
callDesc.Position = UDim2.new(0, 108, 0, 14)
callDesc.BackgroundTransparency = 1
callDesc.Font = Enum.Font.GothamBlack
callDesc.Text = "RIGHT 4"
callDesc.TextColor3 = Color3.fromRGB(255, 255, 255)
callDesc.TextSize = 20
callDesc.TextXAlignment = Enum.TextXAlignment.Left
callDesc.Parent = pacenoteContainer

local nextChainText = Instance.new("TextLabel")
nextChainText.Name = "NextChainText"
nextChainText.Size = UDim2.new(0, 300, 0, 34)
nextChainText.TextWrapped = true
nextChainText.Position = UDim2.new(0, 108, 0, 78)
nextChainText.BackgroundTransparency = 1
nextChainText.Font = Enum.Font.GothamMedium
nextChainText.Text = "> into Left 3"
nextChainText.TextColor3 = Color3.fromRGB(160, 180, 205)
nextChainText.TextSize = 12
nextChainText.TextXAlignment = Enum.TextXAlignment.Left
nextChainText.Parent = pacenoteContainer

--------------------------------------------------------------------------------
-- 4. BOTTOM-RIGHT: Circular Tachometer (0-8 RPM, Redline, Boost, Gear, Speed, Handbrake)
--------------------------------------------------------------------------------
local clusterContainer = Instance.new("Frame")
clusterContainer.Name = "ClusterContainer"
clusterContainer.Size = UDim2.new(0, 310, 0, 240)
clusterContainer.Position = UDim2.new(1, -330, 1, -260)
clusterContainer.BackgroundColor3 = Color3.fromRGB(14, 17, 23)
clusterContainer.BackgroundTransparency = 0.25
clusterContainer.BorderSizePixel = 0
clusterContainer.Parent = screenGui

local clusterCorner = Instance.new("UICorner")
clusterCorner.CornerRadius = UDim.new(0, 16)
clusterCorner.Parent = clusterContainer

local clusterStroke = Instance.new("UIStroke")
clusterStroke.Color = Color3.fromRGB(55, 68, 85)
clusterStroke.Thickness = 1.4
clusterStroke.Parent = clusterContainer

-- Circular tachometer dial ring image backdrop
local dialImg = Instance.new("ImageLabel")
dialImg.Name = "TachDial"
dialImg.Size = UDim2.new(0, 210, 0, 210)
dialImg.Position = UDim2.new(0.5, -105, 0, 10)
dialImg.BackgroundTransparency = 1
dialImg.Image = "rbxassetid://93204797140681" -- Circular RPM dial asset
dialImg.ImageTransparency = 0.2
dialImg.ScaleType = Enum.ScaleType.Fit
dialImg.Parent = clusterContainer

-- Inner Concentric Boost Gauge Arc (-1 to +3 bar)
local boostArc = Instance.new("Frame")
boostArc.Name = "BoostArc"
boostArc.Size = UDim2.new(0, 130, 0, 6)
boostArc.Position = UDim2.new(0.5, -65, 0, 165)
boostArc.BackgroundColor3 = Color3.fromRGB(30, 38, 50)
boostArc.BorderSizePixel = 0
boostArc.Parent = clusterContainer

local boostFill = Instance.new("Frame")
boostFill.Name = "BoostFill"
boostFill.Size = UDim2.new(0.35, 0, 1, 0)
boostFill.BackgroundColor3 = Color3.fromRGB(0, 210, 255)
boostFill.BorderSizePixel = 0
boostFill.Parent = boostArc

local boostText = Instance.new("TextLabel")
boostText.Name = "BoostText"
boostText.Size = UDim2.new(1, 0, 0, 14)
boostText.Position = UDim2.new(0, 0, 0, 8)
boostText.BackgroundTransparency = 1
boostText.Font = Enum.Font.RobotoMono
boostText.Text = "TURBO 1.4 BAR"
boostText.TextColor3 = Color3.fromRGB(130, 210, 255)
boostText.TextSize = 9
boostText.Parent = boostArc

-- Large italic gear display ON THE LEFT of tachometer
local gearLabel = Instance.new("TextLabel")
gearLabel.Name = "GearLabel"
gearLabel.Size = UDim2.new(0, 75, 0, 75)
gearLabel.Position = UDim2.new(0, 16, 0, 48)
gearLabel.BackgroundTransparency = 1
gearLabel.RichText = true
gearLabel.Font = Enum.Font.GothamBlack
gearLabel.Text = "<i><b>1</b></i>"
gearLabel.TextColor3 = Color3.fromRGB(255, 215, 30)
gearLabel.TextSize = 64
gearLabel.Parent = clusterContainer

-- Digital speed with dimmed leading zeros ON THE RIGHT of tachometer
local speedLabel = Instance.new("TextLabel")
speedLabel.Name = "DigitalSpeedLabel"
speedLabel.Size = UDim2.new(0, 115, 0, 42)
speedLabel.Position = UDim2.new(1, -125, 0, 60)
speedLabel.BackgroundTransparency = 1
speedLabel.RichText = true
speedLabel.Font = Enum.Font.GothamBold
speedLabel.Text = '<font color="#556070">00</font>0 <font size="14" color="#8fa0b5">KM/H</font>'
speedLabel.TextColor3 = Color3.fromRGB(255, 255, 255)
speedLabel.TextSize = 28
speedLabel.TextXAlignment = Enum.TextXAlignment.Right
speedLabel.Parent = clusterContainer

-- Handbrake Warning Light (!) Row
local handbrakeLight = Instance.new("Frame")
handbrakeLight.Name = "HandbrakeLight"
handbrakeLight.Size = UDim2.new(0, 36, 0, 22)
handbrakeLight.Position = UDim2.new(1, -55, 0, 18)
handbrakeLight.BackgroundColor3 = Color3.fromRGB(45, 18, 18) -- Dim when inactive
handbrakeLight.BorderSizePixel = 0
handbrakeLight.Parent = clusterContainer

local hbCorner = Instance.new("UICorner")
hbCorner.CornerRadius = UDim.new(0, 4)
hbCorner.Parent = handbrakeLight

local hbText = Instance.new("TextLabel")
hbText.Name = "HbText"
hbText.Size = UDim2.new(1, 0, 1, 0)
hbText.BackgroundTransparency = 1
hbText.Font = Enum.Font.GothamBlack
hbText.Text = "(!)"
hbText.TextColor3 = Color3.fromRGB(110, 40, 40)
hbText.TextSize = 12
hbText.Parent = handbrakeLight

-- RPM Readout and surface badge at bottom
local rpmSubtext = Instance.new("TextLabel")
rpmSubtext.Name = "RpmSubtext"
rpmSubtext.Size = UDim2.new(1, -30, 0, 16)
rpmSubtext.Position = UDim2.new(0, 15, 1, -28)
rpmSubtext.BackgroundTransparency = 1
rpmSubtext.Font = Enum.Font.RobotoMono
rpmSubtext.Text = "1000 RPM  •  GRAVEL  •  AUTO"
rpmSubtext.TextColor3 = Color3.fromRGB(140, 160, 185)
rpmSubtext.TextSize = 11
rpmSubtext.Parent = clusterContainer

--------------------------------------------------------------------------------
-- 5. Stage Events & Split Timings
--------------------------------------------------------------------------------
local stageStartTime: number? = nil
local stageRunning = false
local stageFinished = false

local startEvent = StageRemotes.GetEvent("StageStart")
local splitEvent = StageRemotes.GetEvent("SplitCrossed")
local finishEvent = StageRemotes.GetEvent("StageFinished")

startEvent.OnClientEvent:Connect(function(timestamp)
    stageStartTime = timestamp or os.clock()
    stageRunning = true
    stageFinished = false
end)

splitEvent.OnClientEvent:Connect(function(splitIdx, dist, timestamp)
    local delta = (math.random(-65, 45)) / 100
    local isFaster = delta <= 0
    splitDeltaLabel.TextColor3 = isFaster and Color3.fromRGB(60, 240, 100) or Color3.fromRGB(245, 50, 50)
    splitDeltaLabel.Text = string.format("<i>SPLIT %d: %s%02d:%05.2f</i>", splitIdx, isFaster and "-" or "+", math.abs(delta) / 60, math.abs(delta) % 60)
    
    task.delay(4.5, function()
        if splitDeltaLabel.Text:find("SPLIT " .. splitIdx) then
            splitDeltaLabel.Text = ""
        end
    end)
end)

finishEvent.OnClientEvent:Connect(function()
    stageFinished = true
    stageRunning = false
    splitDeltaLabel.TextColor3 = Color3.fromRGB(255, 215, 0)
    splitDeltaLabel.Text = "<i><b>STAGE FINISHED!</b></i>"
end)

--------------------------------------------------------------------------------
-- 6. 60 FPS Render Stepped Loop
--------------------------------------------------------------------------------
local BORDER_COLORS = {
    [1] = Color3.fromRGB(235, 40, 40),   -- Red = 1
    [2] = Color3.fromRGB(255, 130, 25),  -- Orange = 2
    [3] = Color3.fromRGB(250, 215, 35),  -- Yellow = 3
    [4] = Color3.fromRGB(50, 210, 80),   -- Green = 4
    [5] = Color3.fromRGB(50, 210, 80),   -- Green = 5
    [6] = Color3.fromRGB(50, 210, 80),   -- Green = 6
    [7] = Color3.fromRGB(235, 40, 40),   -- Red = Hairpin
    [8] = Color3.fromRGB(255, 130, 25),  -- Orange = Square
    [9] = Color3.fromRGB(50, 210, 80),   -- Green = Flat
}

RunService.RenderStepped:Connect(function()
    local telemetry = VehicleController.GetTelemetry()
    local coDriver = CoDriverClient.GetActiveCall()
    local upcoming = CoDriverClient.GetUpcomingNote()
    
    -- A. Update Timer (Bold white italic MM:SS.mmm)
    if stageRunning and stageStartTime and not stageFinished then
        local elapsed = os.clock() - stageStartTime
        local mins = math.floor(elapsed / 60)
        local secs = elapsed % 60
        stageTimerLabel.Text = string.format("<i><b>%02d:%06.3f</b></i>", mins, secs)
    elseif not stageRunning and not stageFinished then
        stageTimerLabel.Text = "<i><b>00:00.000</b></i>"
    end
    
    -- B. Update Pacenote Badge (Top-Center)
    if coDriver.IsActive then
        pacenoteContainer.Visible = true
        local sev = coDriver.Severity
        local borderCol = BORDER_COLORS[sev] or Color3.fromRGB(250, 215, 35)
        badgeStroke.Color = borderCol
        
        if coDriver.Direction == "Left" then
            badgeDirectionIcon.Text = "◀"
        elseif coDriver.Direction == "Right" then
            badgeDirectionIcon.Text = "▶"
        else
            badgeDirectionIcon.Text = "▲"
        end
        badgeDirectionIcon.TextColor3 = borderCol
        
        local sevStr = (sev == 7 and "HP") or (sev == 8 and "SQ") or (sev == 9 and "FL") or tostring(sev)
        badgeSeverityNum.Text = sevStr
        callDesc.Text = coDriver.Description:upper()
        
        -- Modifier badge ("Don't Cut" etc)
        local mod = coDriver.Modifier
        if mod and #mod > 0 then
            modifierBadge.Visible = true
            modifierText.Text = mod:upper()
            if mod:find("Cut") then
                modifierBadge.BackgroundColor3 = Color3.fromRGB(210, 35, 35) -- Red for Don't Cut
            else
                modifierBadge.BackgroundColor3 = Color3.fromRGB(40, 50, 65)
            end
        else
            modifierBadge.Visible = false
        end
        
        if upcoming and #upcoming > 0 then
            nextChainText.Text = string.format("%d m · %s", math.floor(coDriver.DistanceRemaining * 0.28 + 0.5), upcoming)
            nextChainText.Visible = true
        else
            nextChainText.Text = string.format("%d m", math.floor(coDriver.DistanceRemaining * 0.28 + 0.5))
            nextChainText.Visible = true
        end
    else
        pacenoteContainer.Visible = false
    end
    
    -- C. Update Circular Tachometer & Controls
    local gearChar = telemetry.GearString or "1"
    gearLabel.Text = string.format("<i><b>%s</b></i>", gearChar)
    
    -- Digital speed with dimmed leading zeros (e.g. 54 -> <font color="#556070">0</font>54)
    local spd = math.floor(math.abs(telemetry.SpeedKmh))
    local spdStr = ""
    if spd < 10 then
        spdStr = string.format('<font color="#556070">00</font>%d', spd)
    elseif spd < 100 then
        spdStr = string.format('<font color="#556070">0</font>%d', spd)
    else
        spdStr = tostring(spd)
    end
    speedLabel.Text = string.format('%s <font size="14" color="#8fa0b5">KM/H</font>', spdStr)
    
    -- Boost Gauge fill
    local boostNorm = math.clamp((telemetry.RPM - 3000) / 4500, 0, 1)
    local boostBar = -0.5 + boostNorm * 2.5
    boostFill.Size = UDim2.new(boostNorm, 0, 1, 0)
    boostText.Text = string.format("TURBO %.1f BAR", boostBar)
    
    -- Handbrake indicator light
    if telemetry.Handbrake then
        handbrakeLight.BackgroundColor3 = Color3.fromRGB(235, 30, 30)
        hbText.TextColor3 = Color3.fromRGB(255, 255, 255)
    else
        handbrakeLight.BackgroundColor3 = Color3.fromRGB(45, 18, 18)
        hbText.TextColor3 = Color3.fromRGB(110, 40, 40)
    end
    
    rpmSubtext.Text = string.format("%d RPM  •  %s  •  %s", math.floor(telemetry.RPM), (telemetry.SurfaceName or "GRAVEL"):upper(), telemetry.TransmissionMode or "AUTO")
    
    -- D. Update Vertical Progress Bar & Red/White Diamond Marker
    local vehicle = VehicleController.GetActiveVehicle()
    if vehicle and vehicle.PrimaryPart then
        local stageData = ReplicatedStorage:FindFirstChild("ActiveStageData")
        local totalDistVal = stageData and stageData:FindFirstChild("TotalDistance") :: NumberValue?
        if totalDistVal and totalDistVal.Value > 0 then
            local progressRatio = math.clamp(CoDriverClient.GetProgress() / totalDistVal.Value, 0, 1)
            greenFill.Size = UDim2.new(1, 0, progressRatio, 0)
            diamondMarker.Position = UDim2.new(0.5, 0, 1.0 - progressRatio, 0)
        end
    end
end)

--------------------------------------------------------------------------------
-- 7. Top-Right Quick Action Pills (Stage Switcher, Replay, Cars, Settings)
--------------------------------------------------------------------------------
local quickBar = Instance.new("Frame")
quickBar.Name = "QuickActionBar"
quickBar.Size = UDim2.new(0, 480, 0, 32)
quickBar.Position = UDim2.new(1, -500, 0, 20)
quickBar.BackgroundTransparency = 1
quickBar.Parent = screenGui

local qLayout = Instance.new("UIListLayout")
qLayout.FillDirection = Enum.FillDirection.Horizontal
qLayout.HorizontalAlignment = Enum.HorizontalAlignment.Right
qLayout.VerticalAlignment = Enum.VerticalAlignment.Center
qLayout.Padding = UDim.new(0, 8)
qLayout.Parent = quickBar

local function makeQuickPill(name: string, text: string, color: Color3, onClick: () -> ()): TextButton
    local btn = Instance.new("TextButton")
    btn.Name = name
    btn.Size = UDim2.new(0, 110, 0, 28)
    btn.BackgroundColor3 = Color3.fromRGB(20, 25, 34)
    btn.Font = Enum.Font.GothamBold
    btn.Text = text
    btn.TextColor3 = color
    btn.TextSize = 11
    btn.BorderSizePixel = 0
    btn.Parent = quickBar

    local c = Instance.new("UICorner")
    c.CornerRadius = UDim.new(0, 6)
    c.Parent = btn

    local s = Instance.new("UIStroke")
    s.Color = color
    s.Transparency = 0.5
    s.Thickness = 1.0
    s.Parent = btn

    btn.MouseButton1Click:Connect(onClick)
    return btn
end

local stageToggleFunc = StageRemotes.GetFunction("ToggleStageMode")
local stageBtn = makeQuickPill("StageBtn", "STAGE: PROCEDURAL", Color3.fromRGB(80, 210, 120), function()
    local newMode = stageToggleFunc:InvokeServer()
    if newMode == "PineForest" then
        stageBtn.Text = "STAGE: PINE FOREST"
        stageBtn.TextColor3 = Color3.fromRGB(255, 180, 40)
    else
        stageBtn.Text = "STAGE: PROCEDURAL"
        stageBtn.TextColor3 = Color3.fromRGB(80, 210, 120)
    end
end)

makeQuickPill("ReplayBtn", "REPLAY [R]", Color3.fromRGB(0, 195, 255), function()
    local replayGui = playerGui:FindFirstChild("ReplayGui") :: ScreenGui?
    if replayGui then
        replayGui.Enabled = not replayGui.Enabled
    end
end)

makeQuickPill("CarsBtn", "CARS [V]", Color3.fromRGB(255, 215, 30), function()
    local selectorGui = playerGui:FindFirstChild("VehicleSelectorGui") :: ScreenGui?
    if selectorGui then
        selectorGui.Enabled = not selectorGui.Enabled
    end
end)

makeQuickPill("SettingsBtn", "SETTINGS [P]", Color3.fromRGB(190, 200, 215), function()
    local settingsGui = playerGui:FindFirstChild("SettingsMenuGui") :: ScreenGui?
    if settingsGui then
        settingsGui.Enabled = not settingsGui.Enabled
    end
end)

print("[RallyGui] Authentic DiRT Rally 2.0 HUD initialized successfully.")
