--!strict
-- VehicleSelectorGui.luau
-- Interactive vehicle selection screen allowing players to browse and switch between all 5 rally cars.
-- Displays specifications (power, torque, mass, class, drivetrain) and fires SelectVehicle remote.

local Players = game:GetService("Players")
local UserInputService = game:GetService("UserInputService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local TweenService = game:GetService("TweenService")

local CarProfiles = require(ReplicatedStorage.RallyShared.Config.CarProfiles)
local StageRemotes = require(ReplicatedStorage.RallyShared.Remotes.StageRemotes)

local player = Players.LocalPlayer
local playerGui = player:WaitForChild("PlayerGui")

local selectVehicleEvent = StageRemotes.GetEvent("SelectVehicle")

-- Create ScreenGui
local screenGui = playerGui:FindFirstChild("VehicleSelectorGui") :: ScreenGui?
if not screenGui then
    screenGui = Instance.new("ScreenGui")
    screenGui.Name = "VehicleSelectorGui"
    screenGui.ResetOnSpawn = false
    screenGui.ZIndexBehavior = Enum.ZIndexBehavior.Sibling
    screenGui.Enabled = false
    screenGui.Parent = playerGui
end

local CAR_ROSTER = {
    {
        Id = "BrennerS1",
        Name = "Brenner S1 E2",
        Class = "Group B — Turbo 4WD",
        Drivetrain = "4WD",
        Power = "510 HP",
        Torque = "590 Nm",
        Weight = "1,090 kg",
        Color = Color3.fromRGB(240, 230, 210),
        Accent = Color3.fromRGB(240, 180, 20),
        Description = "Monstrous short-wheelbase Group B icon. Immense turbo boost and violent anti-lag crackle.",
    },
    {
        Id = "KazeRS",
        Name = "Kaze RS",
        Class = "Group A — Turbo 4WD",
        Drivetrain = "4WD",
        Power = "320 HP",
        Torque = "420 Nm",
        Weight = "1,230 kg",
        Color = Color3.fromRGB(20, 60, 180),
        Accent = Color3.fromRGB(255, 200, 30),
        Description = "Iconic 1990s Japanese rally champion. Legendary stability with active front & rear LSDs.",
    },
    {
        Id = "FalkeE3",
        Name = "Falke E3",
        Class = "Historic — NA RWD",
        Drivetrain = "RWD",
        Power = "285 HP",
        Torque = "310 Nm",
        Weight = "1,120 kg",
        Color = Color3.fromRGB(220, 220, 220),
        Accent = Color3.fromRGB(220, 30, 30),
        Description = "High-revving naturally aspirated classic rear-wheel-drive saloon. Unrivaled throttle-steer feel.",
    },
    {
        Id = "KumoR1",
        Name = "Kumo R1",
        Class = "Modern Rally1 — Hybrid 4WD",
        Drivetrain = "AWD + Hybrid",
        Power = "530 HP",
        Torque = "650 Nm",
        Weight = "1,260 kg",
        Color = Color3.fromRGB(25, 28, 35),
        Accent = Color3.fromRGB(0, 220, 255),
        Description = "State-of-the-art modern rally weapon. 100 kW electric hybrid motor providing explosive corner exits.",
    },
    {
        Id = "FrecciaHF",
        Name = "Freccia HF",
        Class = "Historic — Turbo FWD",
        Drivetrain = "FWD",
        Power = "145 HP",
        Torque = "185 Nm",
        Weight = "920 kg",
        Color = Color3.fromRGB(190, 25, 25),
        Accent = Color3.fromRGB(240, 240, 240),
        Description = "Featherweight Italian hot hatch. Highly agile lift-off oversteer characteristics for technical hairpins.",
    },
}

-- Background blur frame
local bgOverlay = Instance.new("Frame")
bgOverlay.Name = "BgOverlay"
bgOverlay.Size = UDim2.new(1, 0, 1, 0)
bgOverlay.BackgroundColor3 = Color3.fromRGB(10, 12, 16)
bgOverlay.BackgroundTransparency = 0.4
bgOverlay.BorderSizePixel = 0
bgOverlay.Parent = screenGui

-- Main Card Container
local mainFrame = Instance.new("Frame")
mainFrame.Name = "MainFrame"
mainFrame.Size = UDim2.new(0, 960, 0, 520)
mainFrame.Position = UDim2.new(0.5, -480, 0.5, -260)
mainFrame.BackgroundColor3 = Color3.fromRGB(16, 20, 26)
mainFrame.BorderSizePixel = 0
mainFrame.Parent = screenGui

local mainCorner = Instance.new("UICorner")
mainCorner.CornerRadius = UDim.new(0, 12)
mainCorner.Parent = mainFrame

local mainStroke = Instance.new("UIStroke")
mainStroke.Color = Color3.fromRGB(60, 75, 95)
mainStroke.Thickness = 1.5
mainStroke.Parent = mainFrame

-- Header
local title = Instance.new("TextLabel")
title.Name = "Title"
title.Size = UDim2.new(1, -60, 0, 40)
title.Position = UDim2.new(0, 30, 0, 20)
title.BackgroundTransparency = 1
title.Font = Enum.Font.GothamBlack
title.Text = "SELECT RALLY VEHICLE"
title.TextColor3 = Color3.fromRGB(255, 255, 255)
title.TextSize = 26
title.TextXAlignment = Enum.TextXAlignment.Left
title.Parent = mainFrame

local subtitle = Instance.new("TextLabel")
subtitle.Name = "Subtitle"
subtitle.Size = UDim2.new(1, -60, 0, 20)
subtitle.Position = UDim2.new(0, 30, 0, 55)
subtitle.BackgroundTransparency = 1
subtitle.Font = Enum.Font.GothamMedium
subtitle.Text = "Choose your vehicle class — Group B, Group A, Historic RWD, Rally1 Hybrid, or Historic FWD (Press 'V' to toggle)"
subtitle.TextColor3 = Color3.fromRGB(150, 165, 185)
subtitle.TextSize = 13
subtitle.TextXAlignment = Enum.TextXAlignment.Left
subtitle.Parent = mainFrame

-- Close Button
local closeBtn = Instance.new("TextButton")
closeBtn.Name = "CloseButton"
closeBtn.Size = UDim2.new(0, 32, 0, 32)
closeBtn.Position = UDim2.new(1, -45, 0, 20)
closeBtn.BackgroundColor3 = Color3.fromRGB(30, 36, 45)
closeBtn.Font = Enum.Font.GothamBold
closeBtn.Text = "✕"
closeBtn.TextColor3 = Color3.fromRGB(200, 200, 200)
closeBtn.TextSize = 16
closeBtn.Parent = mainFrame

local closeCorner = Instance.new("UICorner")
closeCorner.CornerRadius = UDim.new(0, 6)
closeCorner.Parent = closeBtn

closeBtn.MouseButton1Click:Connect(function()
    screenGui.Enabled = false
end)

-- Cards Container
local cardsContainer = Instance.new("Frame")
cardsContainer.Name = "CardsContainer"
cardsContainer.Size = UDim2.new(1, -40, 0, 400)
cardsContainer.Position = UDim2.new(0, 20, 0, 90)
cardsContainer.BackgroundTransparency = 1
cardsContainer.Parent = mainFrame

local listLayout = Instance.new("UIListLayout")
listLayout.FillDirection = Enum.FillDirection.Horizontal
listLayout.HorizontalAlignment = Enum.HorizontalAlignment.Center
listLayout.VerticalAlignment = Enum.VerticalAlignment.Center
listLayout.Padding = UDim.new(0, 14)
listLayout.Parent = cardsContainer

for idx, carInfo in ipairs(CAR_ROSTER) do
    local card = Instance.new("Frame")
    card.Name = "Card_" .. carInfo.Id
    card.Size = UDim2.new(0, 172, 0, 380)
    card.BackgroundColor3 = Color3.fromRGB(22, 27, 35)
    card.BorderSizePixel = 0
    card.Parent = cardsContainer
    
    local cardCorner = Instance.new("UICorner")
    cardCorner.CornerRadius = UDim.new(0, 8)
    cardCorner.Parent = card
    
    local cardStroke = Instance.new("UIStroke")
    cardStroke.Color = carInfo.Accent
    cardStroke.Thickness = 1.2
    cardStroke.Parent = card
    
    -- Accent bar top
    local bar = Instance.new("Frame")
    bar.Size = UDim2.new(1, 0, 0, 6)
    bar.BackgroundColor3 = carInfo.Accent
    bar.BorderSizePixel = 0
    bar.Parent = card
    
    -- Drivetrain Tag
    local driveTag = Instance.new("TextLabel")
    driveTag.Size = UDim2.new(0, 75, 0, 20)
    driveTag.Position = UDim2.new(0, 12, 0, 14)
    driveTag.BackgroundColor3 = Color3.fromRGB(35, 45, 60)
    driveTag.Font = Enum.Font.GothamBold
    driveTag.Text = carInfo.Drivetrain
    driveTag.TextColor3 = carInfo.Accent
    driveTag.TextSize = 10
    driveTag.Parent = card
    
    local tagCorner = Instance.new("UICorner")
    tagCorner.CornerRadius = UDim.new(0, 4)
    tagCorner.Parent = driveTag
    
    -- Car Name
    local carName = Instance.new("TextLabel")
    carName.Size = UDim2.new(1, -24, 0, 22)
    carName.Position = UDim2.new(0, 12, 0, 40)
    carName.BackgroundTransparency = 1
    carName.Font = Enum.Font.GothamBlack
    carName.Text = carInfo.Name
    carName.TextColor3 = Color3.fromRGB(255, 255, 255)
    carName.TextSize = 15
    carName.TextXAlignment = Enum.TextXAlignment.Left
    carName.Parent = card
    
    -- Car Class
    local carClass = Instance.new("TextLabel")
    carClass.Size = UDim2.new(1, -24, 0, 16)
    carClass.Position = UDim2.new(0, 12, 0, 64)
    carClass.BackgroundTransparency = 1
    carClass.Font = Enum.Font.GothamMedium
    carClass.Text = carInfo.Class
    carClass.TextColor3 = Color3.fromRGB(140, 155, 175)
    carClass.TextSize = 10
    carClass.TextXAlignment = Enum.TextXAlignment.Left
    carClass.Parent = card
    
    -- Visual Preview Box
    local previewBox = Instance.new("Frame")
    previewBox.Size = UDim2.new(1, -24, 0, 80)
    previewBox.Position = UDim2.new(0, 12, 0, 86)
    previewBox.BackgroundColor3 = Color3.fromRGB(14, 18, 24)
    previewBox.BorderSizePixel = 0
    previewBox.Parent = card
    
    local pCorner = Instance.new("UICorner")
    pCorner.CornerRadius = UDim.new(0, 6)
    pCorner.Parent = previewBox
    
    -- Silhouette representation
    local carSil = Instance.new("TextLabel")
    carSil.Size = UDim2.new(1, 0, 1, 0)
    carSil.BackgroundTransparency = 1
    carSil.Font = Enum.Font.GothamBlack
    carSil.Text = (carInfo.Id == "BrennerS1" and "🏎️ GROUP B") or
                   (carInfo.Id == "KazeRS" and "🚗 GROUP A") or
                   (carInfo.Id == "FalkeE3" and "🚘 RWD") or
                   (carInfo.Id == "KumoR1" and "⚡ HYBRID") or "🚙 FWD"
    carSil.TextColor3 = carInfo.Accent
    carSil.TextSize = 14
    carSil.Parent = previewBox
    
    -- Specs Table
    local specY = 175
    local function addSpec(label: string, val: string)
        local sLabel = Instance.new("TextLabel")
        sLabel.Size = UDim2.new(0, 60, 0, 16)
        sLabel.Position = UDim2.new(0, 12, 0, specY)
        sLabel.BackgroundTransparency = 1
        sLabel.Font = Enum.Font.GothamMedium
        sLabel.Text = label
        sLabel.TextColor3 = Color3.fromRGB(120, 135, 155)
        sLabel.TextSize = 11
        sLabel.TextXAlignment = Enum.TextXAlignment.Left
        sLabel.Parent = card
        
        local sVal = Instance.new("TextLabel")
        sVal.Size = UDim2.new(1, -80, 0, 16)
        sVal.Position = UDim2.new(0, 75, 0, specY)
        sVal.BackgroundTransparency = 1
        sVal.Font = Enum.Font.RobotoMono
        sVal.Text = val
        sVal.TextColor3 = Color3.fromRGB(240, 240, 240)
        sVal.TextSize = 11
        sVal.TextXAlignment = Enum.TextXAlignment.Right
        sVal.Parent = card
        
        specY += 20
    end
    
    addSpec("POWER", carInfo.Power)
    addSpec("TORQUE", carInfo.Torque)
    addSpec("WEIGHT", carInfo.Weight)
    
    -- Description snippet
    local descLabel = Instance.new("TextLabel")
    descLabel.Size = UDim2.new(1, -24, 0, 48)
    descLabel.Position = UDim2.new(0, 12, 0, 245)
    descLabel.BackgroundTransparency = 1
    descLabel.Font = Enum.Font.GothamMedium
    descLabel.Text = carInfo.Description
    descLabel.TextColor3 = Color3.fromRGB(130, 145, 165)
    descLabel.TextSize = 9
    descLabel.TextWrapped = true
    descLabel.TextYAlignment = Enum.TextYAlignment.Top
    descLabel.Parent = card
    
    -- Drive Button
    local driveBtn = Instance.new("TextButton")
    driveBtn.Name = "DriveButton"
    driveBtn.Size = UDim2.new(1, -24, 0, 36)
    driveBtn.Position = UDim2.new(0, 12, 1, -48)
    driveBtn.BackgroundColor3 = carInfo.Accent
    driveBtn.Font = Enum.Font.GothamBold
    driveBtn.Text = "DRIVE"
    driveBtn.TextColor3 = (carInfo.Id == "KumoR1" or carInfo.Id == "KazeRS") and Color3.fromRGB(20, 20, 20) or Color3.fromRGB(20, 20, 20)
    driveBtn.TextSize = 13
    driveBtn.Parent = card
    
    local btnCorner = Instance.new("UICorner")
    btnCorner.CornerRadius = UDim.new(0, 6)
    btnCorner.Parent = driveBtn
    
    driveBtn.MouseButton1Click:Connect(function()
        selectVehicleEvent:FireServer(carInfo.Id)
        screenGui.Enabled = false
    end)
end

-- Keybind toggle: 'V'
UserInputService.InputBegan:Connect(function(input, gameProcessed)
    if not gameProcessed and input.KeyCode == Enum.KeyCode.V then
        screenGui.Enabled = not screenGui.Enabled
    end
end)

-- On-screen Toggle Button (bottom-left)
local toggleBtn = Instance.new("TextButton")
toggleBtn.Name = "VehicleSelectToggle"
toggleBtn.Size = UDim2.new(0, 120, 0, 32)
toggleBtn.Position = UDim2.new(0, 30, 1, -45)
toggleBtn.BackgroundColor3 = Color3.fromRGB(20, 25, 34)
toggleBtn.BackgroundTransparency = 0.3
toggleBtn.Font = Enum.Font.GothamBold
toggleBtn.Text = "🚗 CARS (V)"
toggleBtn.TextColor3 = Color3.fromRGB(255, 215, 30)
toggleBtn.TextSize = 12
toggleBtn.BorderSizePixel = 0
toggleBtn.Parent = playerGui:WaitForChild("DirtRallyHud", 10) or screenGui

local tCorner = Instance.new("UICorner")
tCorner.CornerRadius = UDim.new(0, 6)
tCorner.Parent = toggleBtn

local tStroke = Instance.new("UIStroke")
tStroke.Color = Color3.fromRGB(60, 75, 95)
tStroke.Thickness = 1.0
tStroke.Parent = toggleBtn

toggleBtn.MouseButton1Click:Connect(function()
    screenGui.Enabled = not screenGui.Enabled
end)

print("[RallyGui] Vehicle Selector GUI initialized successfully.")
