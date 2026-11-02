--!strict
-- CompanionTabletGui.luau
-- 2nd-player co-driver companion tablet interface.
-- Provides live 2D stage route map, real-time vehicle GPS dot, and interactive tulip-style pace note route book.

local Players = game:GetService("Players")
local UserInputService = game:GetService("UserInputService")
local RunService = game:GetService("RunService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Workspace = game:GetService("Workspace")

local VehicleController = require(ReplicatedStorage.RallyClient.VehicleController)
local CoDriverClient = require(ReplicatedStorage.RallyClient.CoDriverClient)
local StageRemotes = require(ReplicatedStorage.RallyShared.Remotes.StageRemotes)

local player = Players.LocalPlayer
local playerGui = player:WaitForChild("PlayerGui")

local companionEvent = StageRemotes.GetEvent("CompanionSync")

-- Create ScreenGui
local screenGui = playerGui:FindFirstChild("CompanionTabletGui") :: ScreenGui?
if not screenGui then
    screenGui = Instance.new("ScreenGui")
    screenGui.Name = "CompanionTabletGui"
    screenGui.ResetOnSpawn = false
    screenGui.ZIndexBehavior = Enum.ZIndexBehavior.Sibling
    screenGui.Enabled = false
    screenGui.Parent = playerGui
end

-- Tablet Shell (Rugged Carbon / Rubber Bumpers)
local tabletFrame = Instance.new("Frame")
tabletFrame.Name = "TabletFrame"
tabletFrame.Size = UDim2.new(0, 840, 0, 500)
tabletFrame.Position = UDim2.new(0.5, -420, 0.5, -250)
tabletFrame.BackgroundColor3 = Color3.fromRGB(18, 22, 28)
tabletFrame.BorderSizePixel = 0
tabletFrame.Parent = screenGui

local tCorner = Instance.new("UICorner")
tCorner.CornerRadius = UDim.new(0, 16)
tCorner.Parent = tabletFrame

local tStroke = Instance.new("UIStroke")
tStroke.Color = Color3.fromRGB(70, 85, 105)
tStroke.Thickness = 3.0
tStroke.Parent = tabletFrame

-- Tablet Bezel Header
local header = Instance.new("Frame")
header.Name = "Header"
header.Size = UDim2.new(1, -30, 0, 36)
header.Position = UDim2.new(0, 15, 0, 10)
header.BackgroundTransparency = 1
header.Parent = tabletFrame

local headerTitle = Instance.new("TextLabel")
headerTitle.Size = UDim2.new(0, 300, 1, 0)
headerTitle.BackgroundTransparency = 1
headerTitle.Font = Enum.Font.GothamBlack
headerTitle.Text = "CO-DRIVER COMPANION TABLET"
headerTitle.TextColor3 = Color3.fromRGB(255, 255, 255)
headerTitle.TextSize = 16
headerTitle.TextXAlignment = Enum.TextXAlignment.Left
headerTitle.Parent = header

local gpsStatus = Instance.new("TextLabel")
gpsStatus.Size = UDim2.new(0, 160, 1, 0)
gpsStatus.Position = UDim2.new(0, 320, 0, 0)
gpsStatus.BackgroundTransparency = 1
gpsStatus.Font = Enum.Font.RobotoMono
gpsStatus.Text = "● GPS LIVE (10 Hz)"
gpsStatus.TextColor3 = Color3.fromRGB(70, 240, 110)
gpsStatus.TextSize = 12
gpsStatus.TextXAlignment = Enum.TextXAlignment.Left
gpsStatus.Parent = header

-- Close Button
local closeBtn = Instance.new("TextButton")
closeBtn.Size = UDim2.new(0, 28, 0, 28)
closeBtn.Position = UDim2.new(1, -28, 0, 4)
closeBtn.BackgroundColor3 = Color3.fromRGB(35, 42, 52)
closeBtn.Font = Enum.Font.GothamBold
closeBtn.Text = "✕"
closeBtn.TextColor3 = Color3.fromRGB(220, 220, 220)
closeBtn.TextSize = 14
closeBtn.BorderSizePixel = 0
closeBtn.Parent = header

local cCorner = Instance.new("UICorner")
cCorner.CornerRadius = UDim.new(0, 4)
cCorner.Parent = closeBtn

closeBtn.MouseButton1Click:Connect(function()
    screenGui.Enabled = false
end)

--------------------------------------------------------------------------------
-- LEFT: 2D Stage GPS Vector Map Canvas
--------------------------------------------------------------------------------
local mapFrame = Instance.new("Frame")
mapFrame.Name = "MapCanvas"
mapFrame.Size = UDim2.new(0, 430, 0, 420)
mapFrame.Position = UDim2.new(0, 15, 0, 55)
mapFrame.BackgroundColor3 = Color3.fromRGB(12, 15, 20)
mapFrame.BorderSizePixel = 0
mapFrame.ClipsDescendants = true
mapFrame.Parent = tabletFrame

local mCorner = Instance.new("UICorner")
mCorner.CornerRadius = UDim.new(0, 8)
mCorner.Parent = mapFrame

local mStroke = Instance.new("UIStroke")
mStroke.Color = Color3.fromRGB(45, 55, 70)
mStroke.Thickness = 1.2
mStroke.Parent = mapFrame

-- Map Grid lines
for gx = 1, 6 do
    local gLine = Instance.new("Frame")
    gLine.Size = UDim2.new(0, 1, 1, 0)
    gLine.Position = UDim2.new(gx / 7, 0, 0, 0)
    gLine.BackgroundColor3 = Color3.fromRGB(25, 32, 42)
    gLine.BorderSizePixel = 0
    gLine.Parent = mapFrame
end
for gy = 1, 6 do
    local gLine = Instance.new("Frame")
    gLine.Size = UDim2.new(1, 0, 0, 1)
    gLine.Position = UDim2.new(0, 0, gy / 7, 0)
    gLine.BackgroundColor3 = Color3.fromRGB(25, 32, 42)
    gLine.BorderSizePixel = 0
    gLine.Parent = mapFrame
end

-- Map Road Line Container
local roadContainer = Instance.new("Frame")
roadContainer.Name = "RoadContainer"
roadContainer.Size = UDim2.new(1, 0, 1, 0)
roadContainer.BackgroundTransparency = 1
roadContainer.Parent = mapFrame

-- Player GPS Dot
local playerBlip = Instance.new("Frame")
playerBlip.Name = "PlayerBlip"
playerBlip.Size = UDim2.new(0, 14, 0, 14)
playerBlip.Position = UDim2.new(0.5, -7, 0.5, -7)
playerBlip.BackgroundColor3 = Color3.fromRGB(255, 60, 50)
playerBlip.BorderSizePixel = 0
playerBlip.ZIndex = 5
playerBlip.Parent = mapFrame

local bCorner = Instance.new("UICorner")
bCorner.CornerRadius = UDim.new(1, 0)
bCorner.Parent = playerBlip

local bStroke = Instance.new("UIStroke")
bStroke.Color = Color3.fromRGB(255, 255, 255)
bStroke.Thickness = 2.0
bStroke.Parent = playerBlip

local headingArrow = Instance.new("Frame")
headingArrow.Name = "HeadingArrow"
headingArrow.Size = UDim2.new(0, 2, 0, 12)
headingArrow.Position = UDim2.new(0.5, -1, 0, -8)
headingArrow.BackgroundColor3 = Color3.fromRGB(255, 255, 255)
headingArrow.BorderSizePixel = 0
headingArrow.Parent = playerBlip

--------------------------------------------------------------------------------
-- RIGHT: Scrolling Pace Notes Route Book
--------------------------------------------------------------------------------
local routeBookFrame = Instance.new("Frame")
routeBookFrame.Name = "RouteBook"
routeBookFrame.Size = UDim2.new(0, 360, 0, 420)
routeBookFrame.Position = UDim2.new(1, -375, 0, 55)
routeBookFrame.BackgroundColor3 = Color3.fromRGB(12, 15, 20)
routeBookFrame.BorderSizePixel = 0
routeBookFrame.Parent = tabletFrame

local rCorner = Instance.new("UICorner")
rCorner.CornerRadius = UDim.new(0, 8)
rCorner.Parent = routeBookFrame

local rStroke = Instance.new("UIStroke")
rStroke.Color = Color3.fromRGB(45, 55, 70)
rStroke.Thickness = 1.2
rStroke.Parent = routeBookFrame

local bookTitle = Instance.new("TextLabel")
bookTitle.Size = UDim2.new(1, -20, 0, 24)
bookTitle.Position = UDim2.new(0, 10, 0, 8)
bookTitle.BackgroundTransparency = 1
bookTitle.Font = Enum.Font.GothamBold
bookTitle.Text = "PACE NOTES ROUTE BOOK"
bookTitle.TextColor3 = Color3.fromRGB(255, 215, 30)
bookTitle.TextSize = 12
bookTitle.TextXAlignment = Enum.TextXAlignment.Left
bookTitle.Parent = routeBookFrame

local scrollList = Instance.new("ScrollingFrame")
scrollList.Name = "NotesScroll"
scrollList.Size = UDim2.new(1, -20, 1, -45)
scrollList.Position = UDim2.new(0, 10, 0, 36)
scrollList.BackgroundTransparency = 1
scrollList.BorderSizePixel = 0
scrollList.ScrollBarThickness = 4
scrollList.ScrollBarImageColor3 = Color3.fromRGB(60, 75, 95)
scrollList.Parent = routeBookFrame

local sLayout = Instance.new("UIListLayout")
sLayout.FillDirection = Enum.FillDirection.Vertical
sLayout.Padding = UDim.new(0, 6)
sLayout.Parent = scrollList

local noteCardInstances = {}
local mapBounds = { minX = -400, maxX = 400, minZ = 0, maxZ = 3500 }

local function renderStagePolyline()
    roadContainer:ClearAllChildren()
    local stageFolder = Workspace:FindFirstChild("RallyStage")
    local roadFolder = stageFolder and stageFolder:FindFirstChild("Roadbed")
    if not roadFolder then return end
    
    local pts: { Vector3 } = {}
    local minX, maxX = 999999, -999999
    local minZ, maxZ = 999999, -999999
    
    for _, ch in ipairs(roadFolder:GetChildren()) do
        if ch:IsA("BasePart") and ch.Name:find("^Road_") then
            local p = ch.Position
            table.insert(pts, p)
            if p.X < minX then minX = p.X end
            if p.X > maxX then maxX = p.X end
            if p.Z < minZ then minZ = p.Z end
            if p.Z > maxZ then maxZ = p.Z end
        end
    end
    
    if #pts == 0 then return end
    local padX = math.max(80, (maxX - minX) * 0.12)
    local padZ = math.max(80, (maxZ - minZ) * 0.10)
    mapBounds = {
        minX = minX - padX,
        maxX = maxX + padX,
        minZ = minZ - padZ,
        maxZ = maxZ + padZ,
    }
    
    local spanX = math.max(100, mapBounds.maxX - mapBounds.minX)
    local spanZ = math.max(100, mapBounds.maxZ - mapBounds.minZ)
    
    for i = 1, #pts, 2 do
        local p = pts[i]
        local nx = (p.X - mapBounds.minX) / spanX
        local ny = 1.0 - ((p.Z - mapBounds.minZ) / spanZ)
        local dot = Instance.new("Frame")
        dot.Size = UDim2.new(0, 4, 0, 4)
        dot.Position = UDim2.new(nx, -2, ny, -2)
        dot.BackgroundColor3 = Color3.fromRGB(90, 175, 250)
        dot.BorderSizePixel = 0
        dot.Parent = roadContainer
        local dc = Instance.new("UICorner")
        dc.CornerRadius = UDim.new(1, 0)
        dc.Parent = dot
    end
end

-- Populate route notes from ActiveStageData
local function refreshRouteBook()
    renderStagePolyline()
    for _, ch in ipairs(scrollList:GetChildren()) do
        if ch:IsA("Frame") then ch:Destroy() end
    end
    noteCardInstances = {}
    
    local stageData = ReplicatedStorage:FindFirstChild("ActiveStageData")
    local notesFolder = stageData and stageData:FindFirstChild("PaceNotes")
    if not notesFolder then return end
    
    local notes = notesFolder:GetChildren()
    table.sort(notes, function(a, b)
        return (a:GetAttribute("Distance") or 0) < (b:GetAttribute("Distance") or 0)
    end)
    
    for _, n in ipairs(notes) do
        local idx = n:GetAttribute("Index") or 1
        local dist = n:GetAttribute("Distance") or 0
        local sev = n:GetAttribute("Severity") or 4
        local dir = n:GetAttribute("Direction") or "Straight"
        local desc = n:GetAttribute("Description") or ""
        
        local card = Instance.new("Frame")
        card.Name = "NoteItem_" .. idx
        card.Size = UDim2.new(1, -8, 0, 36)
        card.BackgroundColor3 = Color3.fromRGB(20, 25, 34)
        card.BorderSizePixel = 0
        card.Parent = scrollList
        
        local cCorner = Instance.new("UICorner")
        cCorner.CornerRadius = UDim.new(0, 4)
        cCorner.Parent = card
        
        local cStroke = Instance.new("UIStroke")
        cStroke.Color = Color3.fromRGB(50, 60, 75)
        cStroke.Thickness = 1.0
        cStroke.Parent = card
        
        -- Dist indicator
        local dLbl = Instance.new("TextLabel")
        dLbl.Size = UDim2.new(0, 65, 1, 0)
        dLbl.Position = UDim2.new(0, 8, 0, 0)
        dLbl.BackgroundTransparency = 1
        dLbl.Font = Enum.Font.RobotoMono
        dLbl.Text = string.format("%04d m", math.floor(dist * 0.28))
        dLbl.TextColor3 = Color3.fromRGB(150, 165, 180)
        dLbl.TextSize = 11
        dLbl.TextXAlignment = Enum.TextXAlignment.Left
        dLbl.Parent = card
        
        -- Icon
        local iLbl = Instance.new("TextLabel")
        iLbl.Size = UDim2.new(0, 30, 1, 0)
        iLbl.Position = UDim2.new(0, 80, 0, 0)
        iLbl.BackgroundTransparency = 1
        iLbl.Font = Enum.Font.GothamBlack
        iLbl.Text = (dir == "Left" and "◀") or (dir == "Right" and "▶") or "▲"
        iLbl.TextColor3 = Color3.fromRGB(255, 215, 30)
        iLbl.TextSize = 16
        iLbl.Parent = card
        
        -- Desc
        local descLbl = Instance.new("TextLabel")
        descLbl.Size = UDim2.new(1, -190, 1, 0)
        descLbl.Position = UDim2.new(0, 115, 0, 0)
        descLbl.BackgroundTransparency = 1
        descLbl.Font = Enum.Font.GothamBold
        descLbl.Text = desc:upper()
        descLbl.TextColor3 = Color3.fromRGB(240, 240, 240)
        descLbl.TextSize = 12
        descLbl.TextXAlignment = Enum.TextXAlignment.Left
        descLbl.Parent = card
        
        -- Call Now Button for co-driver player
        local callBtn = Instance.new("TextButton")
        callBtn.Size = UDim2.new(0, 65, 0, 24)
        callBtn.Position = UDim2.new(1, -72, 0.5, -12)
        callBtn.BackgroundColor3 = Color3.fromRGB(35, 45, 60)
        callBtn.Font = Enum.Font.GothamBold
        callBtn.Text = "CALL"
        callBtn.TextColor3 = Color3.fromRGB(255, 215, 30)
        callBtn.TextSize = 10
        callBtn.BorderSizePixel = 0
        callBtn.Parent = card
        
        local cbCorner = Instance.new("UICorner")
        cbCorner.CornerRadius = UDim.new(0, 4)
        cbCorner.Parent = callBtn
        
        callBtn.MouseButton1Click:Connect(function()
            companionEvent:FireServer(idx, desc, sev, dir)
        end)
        
        noteCardInstances[idx] = { Card = card, Stroke = cStroke }
    end
    
    scrollList.CanvasSize = UDim2.new(0, 0, 0, #notes * 42)
end

-- Keybind toggle: 'M'
UserInputService.InputBegan:Connect(function(input, processed)
    if not processed and input.KeyCode == Enum.KeyCode.M then
        screenGui.Enabled = not screenGui.Enabled
        if screenGui.Enabled then
            refreshRouteBook()
        end
    end
end)

-- 10 Hz Map & Highlight Update
local mapTimer = 0
RunService.RenderStepped:Connect(function(dt)
    if not screenGui.Enabled then return end
    
    mapTimer += dt
    if mapTimer < 0.05 then return end
    mapTimer = 0
    
    local vehicle = VehicleController.GetActiveVehicle()
    if not vehicle or not vehicle.PrimaryPart then return end
    
    local carPos = vehicle.PrimaryPart.Position
    local spanX = math.max(100, mapBounds.maxX - mapBounds.minX)
    local spanZ = math.max(100, mapBounds.maxZ - mapBounds.minZ)
    
    -- Map bounding box normalization
    local normX = math.clamp((carPos.X - mapBounds.minX) / spanX, 0.05, 0.95)
    local normY = math.clamp((carPos.Z - mapBounds.minZ) / spanZ, 0.05, 0.95)
    
    playerBlip.Position = UDim2.new(normX, -7, 1.0 - normY, -7)
    
    -- Orient heading arrow
    local look = vehicle.PrimaryPart.CFrame.LookVector
    local headingAngle = math.deg(math.atan2(look.X, look.Z))
    headingArrow.Rotation = headingAngle
    
    -- Highlight active note in Route Book
    local activeCall = CoDriverClient.GetActiveCall()
    if activeCall and activeCall.IsActive then
        for idx, item in pairs(noteCardInstances) do
            if idx == activeCall.Index then
                item.Card.BackgroundColor3 = Color3.fromRGB(50, 42, 20)
                item.Stroke.Color = Color3.fromRGB(255, 215, 30)
                item.Stroke.Thickness = 2.0
            else
                item.Card.BackgroundColor3 = Color3.fromRGB(20, 25, 34)
                item.Stroke.Color = Color3.fromRGB(50, 60, 75)
                item.Stroke.Thickness = 1.0
            end
        end
    end
end)

print("[RallyGui] Companion Tablet GUI initialized successfully.")
