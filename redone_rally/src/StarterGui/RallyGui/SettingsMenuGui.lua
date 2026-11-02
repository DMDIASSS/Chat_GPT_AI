--!strict
-- SettingsMenuGui.luau
-- Interactive configuration UI adjusting camera shake, graphics presets, and audio volumes in real time.

local Players = game:GetService("Players")
local UserInputService = game:GetService("UserInputService")
local Lighting = game:GetService("Lighting")
local SoundService = game:GetService("SoundService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")

local CameraController = require(ReplicatedStorage.RallyClient.CameraController)
local VehicleController = require(ReplicatedStorage.RallyClient.VehicleController)
local CoDriverClient = require(ReplicatedStorage.RallyClient.CoDriverClient)

local player = Players.LocalPlayer
local playerGui = player:WaitForChild("PlayerGui")

-- Create ScreenGui
local screenGui = playerGui:FindFirstChild("SettingsMenuGui") :: ScreenGui?
if not screenGui then
    screenGui = Instance.new("ScreenGui")
    screenGui.Name = "SettingsMenuGui"
    screenGui.ResetOnSpawn = false
    screenGui.ZIndexBehavior = Enum.ZIndexBehavior.Sibling
    screenGui.Enabled = false
    screenGui.Parent = playerGui
end

-- Settings State
local currentShake = 1.0
local currentMasterVol = 1.0
local currentEngineVol = 0.8
local currentCodriverVol = 0.85
local currentSurfaceVol = 0.75
local currentGraphicsPreset = "High"

-- Main Dialog Container
local mainDialog = Instance.new("Frame")
mainDialog.Name = "SettingsDialog"
mainDialog.Size = UDim2.new(0, 560, 0, 480)
mainDialog.Position = UDim2.new(0.5, -280, 0.5, -240)
mainDialog.BackgroundColor3 = Color3.fromRGB(16, 20, 26)
mainDialog.BorderSizePixel = 0
mainDialog.Parent = screenGui

local dCorner = Instance.new("UICorner")
dCorner.CornerRadius = UDim.new(0, 10)
dCorner.Parent = mainDialog

local dStroke = Instance.new("UIStroke")
dStroke.Color = Color3.fromRGB(60, 75, 95)
dStroke.Thickness = 1.4
dStroke.Parent = mainDialog

-- Header
local title = Instance.new("TextLabel")
title.Name = "Title"
title.Size = UDim2.new(1, -60, 0, 36)
title.Position = UDim2.new(0, 25, 0, 15)
title.BackgroundTransparency = 1
title.Font = Enum.Font.GothamBlack
title.Text = "GAMEPLAY & AUDIO SETTINGS"
title.TextColor3 = Color3.fromRGB(255, 255, 255)
title.TextSize = 20
title.TextXAlignment = Enum.TextXAlignment.Left
title.Parent = mainDialog

local closeBtn = Instance.new("TextButton")
closeBtn.Size = UDim2.new(0, 28, 0, 28)
closeBtn.Position = UDim2.new(1, -40, 0, 15)
closeBtn.BackgroundColor3 = Color3.fromRGB(30, 36, 45)
closeBtn.Font = Enum.Font.GothamBold
closeBtn.Text = "✕"
closeBtn.TextColor3 = Color3.fromRGB(220, 220, 220)
closeBtn.TextSize = 14
closeBtn.BorderSizePixel = 0
closeBtn.Parent = mainDialog

local cCorner = Instance.new("UICorner")
cCorner.CornerRadius = UDim.new(0, 4)
cCorner.Parent = closeBtn

closeBtn.MouseButton1Click:Connect(function()
    screenGui.Enabled = false
end)

-- Layout list
local content = Instance.new("ScrollingFrame")
content.Name = "Content"
content.Size = UDim2.new(1, -50, 1, -70)
content.Position = UDim2.new(0, 25, 0, 55)
content.BackgroundTransparency = 1
content.BorderSizePixel = 0
content.ScrollBarThickness = 4
content.AutomaticCanvasSize = Enum.AutomaticSize.Y
content.CanvasSize = UDim2.fromOffset(0, 0)
content.Parent = mainDialog

local listLayout = Instance.new("UIListLayout")
listLayout.FillDirection = Enum.FillDirection.Vertical
listLayout.Padding = UDim.new(0, 14)
listLayout.Parent = content

-- Helper: Slider builder
local function makeSlider(label: string, initialVal: number, minVal: number, maxVal: number, onUpdate: (number) -> (), formatValue: ((number) -> string)?): Frame
    local row = Instance.new("Frame")
    row.Size = UDim2.new(1, 0, 0, 42)
    row.BackgroundTransparency = 1
    row.Parent = content
    
    local nameLbl = Instance.new("TextLabel")
    nameLbl.Size = UDim2.new(0, 180, 0, 18)
    nameLbl.Position = UDim2.new(0, 0, 0, 0)
    nameLbl.BackgroundTransparency = 1
    nameLbl.Font = Enum.Font.GothamMedium
    nameLbl.Text = label
    nameLbl.TextColor3 = Color3.fromRGB(200, 210, 225)
    nameLbl.TextSize = 12
    nameLbl.TextXAlignment = Enum.TextXAlignment.Left
    nameLbl.Parent = row
    
    local valLbl = Instance.new("TextLabel")
    valLbl.Size = UDim2.new(0, 60, 0, 18)
    valLbl.Position = UDim2.new(1, -60, 0, 0)
    valLbl.BackgroundTransparency = 1
    valLbl.Font = Enum.Font.RobotoMono
    local format = formatValue or function(value: number): string return string.format("%d%%", math.floor(value * 100)) end
    valLbl.Text = format(initialVal)
    valLbl.TextColor3 = Color3.fromRGB(255, 215, 30)
    valLbl.TextSize = 12
    valLbl.TextXAlignment = Enum.TextXAlignment.Right
    valLbl.Parent = row
    
    local track = Instance.new("TextButton")
    track.Name = "Track"
    track.Size = UDim2.new(1, 0, 0, 8)
    track.Position = UDim2.new(0, 0, 0, 24)
    track.BackgroundColor3 = Color3.fromRGB(35, 42, 54)
    track.BorderSizePixel = 0
    track.Text = ""
    track.Parent = row
    
    local tCorner = Instance.new("UICorner")
    tCorner.CornerRadius = UDim.new(0, 4)
    tCorner.Parent = track
    
    local normInit = (initialVal - minVal) / (maxVal - minVal)
    local fill = Instance.new("Frame")
    fill.Size = UDim2.new(normInit, 0, 1, 0)
    fill.BackgroundColor3 = Color3.fromRGB(255, 215, 30)
    fill.BorderSizePixel = 0
    fill.Parent = track
    
    local fCorner = Instance.new("UICorner")
    fCorner.CornerRadius = UDim.new(0, 4)
    fCorner.Parent = fill
    
    local isDragging = false
    track.MouseButton1Down:Connect(function()
        isDragging = true
    end)
    
    UserInputService.InputEnded:Connect(function(input)
        if input.UserInputType == Enum.UserInputType.MouseButton1 then
            isDragging = false
        end
    end)
    
    UserInputService.InputChanged:Connect(function(input)
        if isDragging and input.UserInputType == Enum.UserInputType.MouseMovement then
            local relX = math.clamp(input.Position.X - track.AbsolutePosition.X, 0, track.AbsoluteSize.X)
            local norm = relX / track.AbsoluteSize.X
            local val = minVal + norm * (maxVal - minVal)
            fill.Size = UDim2.new(norm, 0, 1, 0)
            valLbl.Text = format(val)
            onUpdate(val)
        end
    end)
    
    return row
end

-- 1. Camera Shake Slider (0% to 150%)
makeSlider("Camera Shake Intensity", 1.0, 0.0, 1.5, function(val)
    currentShake = val
    CameraController.SetShakeMultiplier(val)
end)

-- The rack rate scale changes every car through the same steering solver.
makeSlider("Wheel turn rate", 1.0, 0.5, 1.5, function(value)
    VehicleController.SetSteeringRateScale(value)
end)
makeSlider("Co-driver lead (seconds)", 3.0, 1.5, 5.0, function(value)
    CoDriverClient.SetLeadTime(value)
end, function(value) return string.format("%.1f s", value) end)
local voiceEnabled = true
local voiceButton = Instance.new("TextButton")
voiceButton.Size = UDim2.new(1, 0, 0, 30)
voiceButton.BackgroundColor3 = Color3.fromRGB(28, 34, 44)
voiceButton.TextColor3 = Color3.fromRGB(230, 235, 240)
voiceButton.Font = Enum.Font.GothamMedium
voiceButton.TextSize = 12
voiceButton.Text = "Co-driver speech: ON"
voiceButton.Parent = content
voiceButton.MouseButton1Click:Connect(function()
    voiceEnabled = not voiceEnabled
    CoDriverClient.SetVoiceEnabled(voiceEnabled)
    voiceButton.Text = "Co-driver speech: " .. (voiceEnabled and "ON" or "OFF")
end)

-- 2. Graphics Presets
local gfxRow = Instance.new("Frame")
gfxRow.Size = UDim2.new(1, 0, 0, 52)
gfxRow.BackgroundTransparency = 1
gfxRow.Parent = content

local gfxLbl = Instance.new("TextLabel")
gfxLbl.Size = UDim2.new(1, 0, 0, 18)
gfxLbl.BackgroundTransparency = 1
gfxLbl.Font = Enum.Font.GothamMedium
gfxLbl.Text = "Graphics Quality Preset"
gfxLbl.TextColor3 = Color3.fromRGB(200, 210, 225)
gfxLbl.TextSize = 12
gfxLbl.TextXAlignment = Enum.TextXAlignment.Left
gfxLbl.Parent = gfxRow

local presetBtnsFrame = Instance.new("Frame")
presetBtnsFrame.Size = UDim2.new(1, 0, 0, 28)
presetBtnsFrame.Position = UDim2.new(0, 0, 0, 22)
presetBtnsFrame.BackgroundTransparency = 1
presetBtnsFrame.Parent = gfxRow

local pLayout = Instance.new("UIListLayout")
pLayout.FillDirection = Enum.FillDirection.Horizontal
pLayout.Padding = UDim.new(0, 10)
pLayout.Parent = presetBtnsFrame

local presetButtons = {}
local presets = { "Low", "Medium", "High", "Ultra" }

local function applyGraphicsPreset(pName: string)
    currentGraphicsPreset = pName
    for name, btn in pairs(presetButtons) do
        local isSel = (name == pName)
        btn.BackgroundColor3 = isSel and Color3.fromRGB(255, 215, 30) or Color3.fromRGB(28, 34, 44)
        btn.TextColor3 = isSel and Color3.fromRGB(20, 20, 20) or Color3.fromRGB(200, 210, 225)
    end
    
    -- Real-time lighting adjustments
    pcall(function()
        if pName == "Low" then
            Lighting.GlobalShadows = false
            Lighting.Technology = Enum.Technology.ShadowMap
        elseif pName == "Medium" then
            Lighting.GlobalShadows = true
            Lighting.Technology = Enum.Technology.ShadowMap
        elseif pName == "High" then
            Lighting.GlobalShadows = true
            Lighting.Technology = Enum.Technology.Future
        elseif pName == "Ultra" then
            Lighting.GlobalShadows = true
            Lighting.Technology = Enum.Technology.Future
        end
    end)
end

for _, pName in ipairs(presets) do
    local pBtn = Instance.new("TextButton")
    pBtn.Size = UDim2.new(0, 115, 0, 26)
    pBtn.BackgroundColor3 = (pName == "High") and Color3.fromRGB(255, 215, 30) or Color3.fromRGB(28, 34, 44)
    pBtn.Font = Enum.Font.GothamBold
    pBtn.Text = pName:upper()
    pBtn.TextColor3 = (pName == "High") and Color3.fromRGB(20, 20, 20) or Color3.fromRGB(200, 210, 225)
    pBtn.TextSize = 11
    pBtn.BorderSizePixel = 0
    pBtn.Parent = presetBtnsFrame
    
    local c = Instance.new("UICorner")
    c.CornerRadius = UDim.new(0, 4)
    c.Parent = pBtn
    
    presetButtons[pName] = pBtn
    pBtn.MouseButton1Click:Connect(function()
        applyGraphicsPreset(pName)
    end)
end

-- 3. Audio Volume Sliders
makeSlider("Master Volume", 1.0, 0.0, 1.0, function(val)
    currentMasterVol = val
    local masterGrp = SoundService:FindFirstChild("Master") :: SoundGroup?
    if not masterGrp then
        masterGrp = Instance.new("SoundGroup")
        masterGrp.Name = "Master"
        masterGrp.Parent = SoundService
    end
    masterGrp.Volume = val
end)

makeSlider("Engine Volume", 0.8, 0.0, 1.0, function(val)
    currentEngineVol = val
    local vehicle = VehicleController.GetActiveVehicle()
    if vehicle and vehicle.PrimaryPart then
        local sndFolder = vehicle.PrimaryPart:FindFirstChild("VehicleSounds")
        if sndFolder then
            for _, s in ipairs(sndFolder:GetChildren()) do
                if s:IsA("Sound") and (s.Name:find("Engine") or s.Name:find("Turbo")) then
                    s.Volume = val * currentMasterVol
                end
            end
        end
    end
end)

makeSlider("Co-Driver Volume", 0.85, 0.0, 1.0, function(val)
    currentCodriverVol = val
    CoDriverClient.SetVolume(val * currentMasterVol)
end)

makeSlider("Surface & Tire Skid Volume", 0.75, 0.0, 1.0, function(val)
    currentSurfaceVol = val
    local vehicle = VehicleController.GetActiveVehicle()
    if vehicle and vehicle.PrimaryPart then
        local sndFolder = vehicle.PrimaryPart:FindFirstChild("VehicleSounds")
        if sndFolder then
            for _, s in ipairs(sndFolder:GetChildren()) do
                if s:IsA("Sound") and (s.Name:find("Skid") or s.Name:find("Tire")) then
                    s.Volume = val * currentMasterVol
                end
            end
        end
    end
end)

-- Keybind toggle: 'O'
UserInputService.InputBegan:Connect(function(input, processed)
    if not processed and input.KeyCode == Enum.KeyCode.O then
        screenGui.Enabled = not screenGui.Enabled
    end
end)

print("[RallyGui] Settings Menu GUI initialized successfully.")
