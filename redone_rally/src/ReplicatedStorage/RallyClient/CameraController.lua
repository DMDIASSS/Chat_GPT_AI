--!strict
-- CameraController.luau
-- Dynamic rally camera supporting:
-- 1. DynamicChase (speed FOV kick, drift angle framing, Perlin terrain shake)
-- 2. Chase (clean high-stability 3rd-person)
-- 3. Cockpit (interior 1st-person with head inertia & steer lookahead)
-- 4. TracksideDirector (cinematic TV cameras stationed along the stage panning with car)

local RunService = game:GetService("RunService")
local UserInputService = game:GetService("UserInputService")
local Workspace = game:GetService("Workspace")
local Players = game:GetService("Players")

local VehicleController = require(script.Parent.VehicleController)

export type CameraMode = "DynamicChase" | "Chase" | "Cockpit" | "TracksideDirector"

local CameraController = {}

local currentCamera = Workspace.CurrentCamera
local currentMode: CameraMode = "Cockpit"
local replayTarget: Model? = nil
local replaySteer = 0
local streamRequestActive = false
local lastStreamPosition: Vector3? = nil
local lastStreamClock = -math.huge

-- Camera tuning parameters
local BASE_FOV = 70
local MAX_FOV = 90
local CHASE_DISTANCE = 18.0
local CHASE_HEIGHT = 5.5
local CHASE_DAMPING = 8.0

local currentFOV = BASE_FOV
local smoothedCamPos = Vector3.zero
local smoothedLookAt = Vector3.zero
local shakeTime = 0
local shakeMultiplier = 1.0 -- Controlled via Settings Menu

-- Trackside TV Director camera state
local activeDirectorPoint: Vector3? = nil
local activeDirectorIndex = 0

-- On-screen camera mode notification badge
local modeBadge: TextLabel? = nil
local badgeFadeTween: any = nil

local function showModeBadge(modeName: string)
    local player = Players.LocalPlayer
    local pGui = player and player:FindFirstChild("PlayerGui")
    local hud = pGui and pGui:FindFirstChild("DirtRallyHud")
    if not hud then return end
    
    if not modeBadge or not modeBadge.Parent then
        modeBadge = Instance.new("TextLabel")
        modeBadge.Name = "CameraModeBadge"
        modeBadge.Size = UDim2.new(0, 240, 0, 26)
        modeBadge.Position = UDim2.new(0.5, -120, 0, 135)
        modeBadge.BackgroundColor3 = Color3.fromRGB(15, 18, 24)
        modeBadge.BackgroundTransparency = 0.3
        modeBadge.Font = Enum.Font.GothamBold
        modeBadge.TextColor3 = Color3.fromRGB(255, 215, 30)
        modeBadge.TextSize = 12
        modeBadge.BorderSizePixel = 0
        
        local corner = Instance.new("UICorner")
        corner.CornerRadius = UDim.new(0, 4)
        corner.Parent = modeBadge
        
        modeBadge.Parent = hud
    end
    
    modeBadge.Text = "CAMERA: " .. modeName:upper()
    modeBadge.Visible = true
    task.delay(1.8, function()
        if modeBadge and modeBadge.Text == "CAMERA: " .. modeName:upper() then
            modeBadge.Visible = false
        end
    end)
end

-- Keybind to cycle camera modes: 'C'
UserInputService.InputBegan:Connect(function(input, processed)
    if processed then return end
    if input.KeyCode == Enum.KeyCode.C then
        CameraController.CycleMode()
    end
end)

function CameraController.CycleMode(): CameraMode
    if currentMode == "DynamicChase" then
        CameraController.SetMode("Chase")
    elseif currentMode == "Chase" then
        CameraController.SetMode("Cockpit")
    elseif currentMode == "Cockpit" then
        CameraController.SetMode("TracksideDirector")
    else
        CameraController.SetMode("DynamicChase")
    end
    return currentMode
end

function CameraController.SetMode(mode: CameraMode)
    currentMode = replayTarget and mode or "Cockpit"
    showModeBadge(currentMode)
end

function CameraController.SetReplayTarget(target: Model?)
    replayTarget = target
    smoothedCamPos, smoothedLookAt = Vector3.zero, Vector3.zero
    activeDirectorPoint = nil
    lastStreamPosition = nil
    if not target then CameraController.SetMode("Cockpit") end
end
function CameraController.SetReplaySteer(value: number) replaySteer = value end

function CameraController.GetMode(): CameraMode
    return currentMode
end

function CameraController.SetShakeMultiplier(mult: number)
    shakeMultiplier = math.clamp(mult, 0.0, 2.0)
end

-- Helper: Find nearest trackside camera viewpoint for TV Director mode
local function getTracksideViewpoint(carPos: Vector3): Vector3
    local stageFolder = Workspace:FindFirstChild("RallyStage")
    local roadFolder = stageFolder and stageFolder:FindFirstChild("Roadbed")
    if not roadFolder then
        return carPos + Vector3.new(25, 12, 25)
    end
    
    local children = roadFolder:GetChildren()
    if #children == 0 then return carPos + Vector3.new(25, 12, 25) end
    
    -- Pick camera stations placed every ~16 slices
    local bestStation: Vector3? = nil
    local bestDist = 999999
    
    for i = 1, #children, 16 do
        local slice = children[i]
        if slice:IsA("BasePart") then
            -- Station is offset 28 studs laterally and 10 studs high
            local stationPos = slice.CFrame * Vector3.new(28, 10, 0)
            local d = (stationPos - carPos).Magnitude
            if d < bestDist and d > 20 then
                bestDist = d
                bestStation = stationPos
            end
        end
    end
    
    return bestStation or (carPos + Vector3.new(28, 12, 28))
end

local hiddenCharacter: Model? = nil
local hiddenParts: { [BasePart]: number } = {}
local function maskDriver(character: Model?)
    if character == hiddenCharacter then return end
    for part, value in pairs(hiddenParts) do if part.Parent then part.LocalTransparencyModifier = value end end
    hiddenParts = {}
    hiddenCharacter = character
    if character then
        for _,part in ipairs(character:GetDescendants()) do
            if part:IsA("BasePart") then hiddenParts[part] = part.LocalTransparencyModifier; part.LocalTransparencyModifier = 1 end
        end
    end
end

RunService.RenderStepped:Connect(function(dt)
    currentCamera = Workspace.CurrentCamera
    if not currentCamera then return end
    local vehicle = replayTarget or VehicleController.GetActiveVehicle()
    if not vehicle or not vehicle.Parent or not vehicle.PrimaryPart then
        maskDriver(nil)
        if currentCamera.CameraType == Enum.CameraType.Scriptable then
            currentCamera.CameraType = Enum.CameraType.Custom
        end
        return
    end
    
    maskDriver(currentMode == "Cockpit" and Players.LocalPlayer.Character or nil)
    currentCamera.CameraType = Enum.CameraType.Scriptable
    local primaryPart = vehicle.PrimaryPart
    local carCF = primaryPart.CFrame
    local linVel = primaryPart.AssemblyLinearVelocity
    local speed = linVel.Magnitude
    currentCamera.Focus = carCF
    if replayTarget and Workspace.StreamingEnabled and not streamRequestActive
        and os.clock()-lastStreamClock >= 1
        and (not lastStreamPosition or (carCF.Position-lastStreamPosition).Magnitude >= 96) then
        streamRequestActive = true
        lastStreamPosition,lastStreamClock = carCF.Position,os.clock()
        local position = carCF.Position
        task.spawn(function()
            pcall(function() Players.LocalPlayer:RequestStreamAroundAsync(position, 2) end)
            streamRequestActive = false
        end)
    end
    local telemetry = VehicleController.GetTelemetry()
    
    shakeTime += dt
    
    if currentMode == "Cockpit" then
        -- 1. Cockpit View: Located at left-hand driver cabin head height (-Z is forward!)
        local eye = primaryPart:FindFirstChild("DriverEye") :: Attachment?
        local headOffset = eye and eye.Position or Vector3.new(-1.35, 2.2, 1)
        local headWorld = carCF:PointToWorldSpace(headOffset)
        
        -- Look ahead along -Z into turn
        local steerYaw = -(replayTarget and replaySteer or telemetry.Steer) * 0.16
        local lookTarget = (carCF * CFrame.Angles(0, steerYaw, 0) * CFrame.new(headOffset.X, headOffset.Y, -25)).Position
        
        -- G-Force head bob
        local accelShake = Vector3.new(
            math.sin(shakeTime * 25) * (speed / 150) * 0.05 * shakeMultiplier,
            math.cos(shakeTime * 30) * (speed / 150) * 0.06 * shakeMultiplier,
            0
        )
        
        currentCamera.CFrame = CFrame.lookAt(headWorld + accelShake, lookTarget)
        currentCamera.FieldOfView = BASE_FOV + (speed / 140) * 10
        
    elseif currentMode == "TracksideDirector" then
        -- 2. TV Director Camera: Stationary elevated trackside cameras with telephoto tracking
        local carPos = carCF.Position
        if not activeDirectorPoint or (activeDirectorPoint - carPos).Magnitude > 160 then
            activeDirectorPoint = getTracksideViewpoint(carPos)
        end
        
        local lookAtTarget = carPos + (linVel * 0.15) + Vector3.new(0, 1.5, 0)
        local dToCar = (activeDirectorPoint - carPos).Magnitude
        
        -- Telephoto zoom based on distance
        local telephotoFOV = math.clamp(32 + (dToCar / 160) * 28, 30, 60)
        currentCamera.FieldOfView = telephotoFOV
        currentCamera.CFrame = CFrame.lookAt(activeDirectorPoint, lookAtTarget)
        
    elseif currentMode == "DynamicChase" or currentMode == "Chase" then
        -- 3. Dynamic / Standard Chase Camera
        local speedRatio = math.clamp(speed / 140.0, 0, 1)
        
        -- Speed FOV Kick: transitions from 70 to 90 deg
        local targetFOV = (currentMode == "DynamicChase") and (BASE_FOV + (MAX_FOV - BASE_FOV) * (speedRatio ^ 1.4)) or BASE_FOV
        currentFOV = currentFOV + (targetFOV - currentFOV) * math.clamp(dt * 5, 0, 1)
        currentCamera.FieldOfView = currentFOV
        
        -- Drift Angle Framing: camera swings outwards during oversteer slides
        local driftOffset = Vector3.zero
        if currentMode == "DynamicChase" then
            local slip = telemetry.SlipAngleDeg
            if math.abs(slip) > 4 then
                local driftAngleRad = math.rad(math.clamp(slip * 0.45, -35, 35))
                driftOffset = carCF.RightVector * (math.sin(driftAngleRad) * 4.5)
            end
        end
        
        -- Perlin Noise Camera Shake on rough terrain and high speed
        local shakeOffset = Vector3.zero
        if currentMode == "DynamicChase" and speed > 10 and shakeMultiplier > 0.01 then
            local shakeFreq = 18.0
            local shakeIntensity = (speedRatio ^ 1.8) * 0.35 * shakeMultiplier
            local noiseX = (math.noise(shakeTime * shakeFreq, 0, 0)) * shakeIntensity
            local noiseY = (math.noise(0, shakeTime * shakeFreq, 0)) * shakeIntensity
            shakeOffset = Vector3.new(noiseX, noiseY, 0)
        end
        
        -- Target Chase Position behind vehicle
        local targetPos = carCF.Position - (carCF.LookVector * CHASE_DISTANCE) + (Vector3.new(0, 1, 0) * CHASE_HEIGHT) + driftOffset
        local targetLookAt = carCF.Position + (carCF.LookVector * 10) + Vector3.new(0, 1.5, 0)
        
        if smoothedCamPos == Vector3.zero then
            smoothedCamPos = targetPos
            smoothedLookAt = targetLookAt
        else
            smoothedCamPos = smoothedCamPos:Lerp(targetPos, math.clamp(dt * CHASE_DAMPING, 0, 1))
            smoothedLookAt = smoothedLookAt:Lerp(targetLookAt, math.clamp(dt * (CHASE_DAMPING * 1.5), 0, 1))
        end
        
        currentCamera.CFrame = CFrame.lookAt(smoothedCamPos + shakeOffset, smoothedLookAt)
    end
end)

return CameraController
