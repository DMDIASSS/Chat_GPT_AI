-- Roblox client adapter and dashboard. No require(), admin calls, or remote downloads.
local Players = game:GetService("Players")
local RunService = game:GetService("RunService")
local ReplicatedStorage = game:GetService("ReplicatedStorage")
local Input = game:GetService("UserInputService")
local GuiService = game:GetService("GuiService")
local HttpService = game:GetService("HttpService")
local World = game:GetService("Workspace")
local player = Players.LocalPlayer
assert(player, "HowToDrift Assist must run on the client")
local playerGui = player:FindFirstChildOfClass("PlayerGui") or player:WaitForChild("PlayerGui", 10)
assert(playerGui, "PlayerGui not ready; join the game first")
local env = if type(getgenv) == "function" then getgenv() else _G
local old = rawget(env, "__HowToDriftAssist")
if type(old) == "table" and type(old.destroy) == "function" then pcall(old.destroy) end

local app = {version = "1.0.0", alive = true, enabled = false, connections = {},
    settings = Controller.settings(), controller = Controller.new(), lease = InputLease.new(player),
    status = "Enter your car, choose Manual or Road auto, then Start", trace = {}, frames = 0,
    physicsWrites = 0, inputWrites = 0, peakControllerMs = 0, lastControllerMs = 0,
    peakUpdateMs = 0, lastUpdateMs = 0, routes = {},
    direction = 1, roadDirty = true, focused = true, keys = {}, lastError = nil}
env.__HowToDriftAssist = app
local function connect(event, fn)
    local c = event:Connect(fn)
    table.insert(app.connections, c)
    return c
end
local function finiteOrNil(v) return if Controller.finite(v) then v else nil end
local function primitive(value)
    local t = typeof(value)
    return if t == "string" or t == "boolean" or (t == "number" and Controller.finite(value)) then value else tostring(value)
end
local function release()
    app.lease:release()
    app.controller = Controller.new()
    app.lastCommand = nil
end
function app.stop(reason)
    app.enabled = false
    release()
    app.status = reason or "Stopped; normal car controls restored"
end
function app.start()
    release()
    app.enabled = true
    app.lastError = nil
    app.previousS, app.guide, app.guideAt = nil, nil, nil
    app.status = "Waiting for your seated, network-owned car"
end
function app.setMode(mode)
    release()
    app.settings.mode = if mode == "road" then "road" else "manual"
    app.previousS, app.guide, app.guideAt = nil, nil, nil
end
function app.cycleSide()
    app.settings.side = if app.settings.side == "auto" then "left" elseif app.settings.side == "left" then "right" else "auto"
end
function app.nearestRoad()
    app.path, app.previousS, app.guide, app.guideAt = nil, nil, nil, nil
    app.direction, app.roadDirty = 1, true
end

local root, car, wheels = nil, nil, {}
local carCheckAt, roadCheckAt, traceAt, uiAt, obstacleAt = -math.huge, -math.huge, -math.huge, -math.huge, -math.huge
local groundParams, obstacleParams = RaycastParams.new(), RaycastParams.new()
groundParams.FilterType, obstacleParams.FilterType = Enum.RaycastFilterType.Exclude, Enum.RaycastFilterType.Exclude
groundParams.IgnoreWater, obstacleParams.IgnoreWater = true, true
groundParams.RespectCanCollide, obstacleParams.RespectCanCollide = true, true
local function findCar(now)
    if now < carCheckAt and root and root.Parent and car and car.Parent then return end
    carCheckAt = now + 0.5
    local found
    local cars = World:FindFirstChild("Cars")
    if cars then
        for _, model in ipairs(cars:GetChildren()) do
            if model:IsA("Model") and model:GetAttribute("OwnerUserId") == player.UserId then found = model; break end
        end
    end
    if found ~= car or (found and (not root or not root.Parent)) then
        release()
        car, root, wheels = found, nil, {}
        app.previousS, app.guide, app.guideAt, app.path = nil, nil, nil, nil
        if found then
            local chassis = found:FindFirstChild("Chassis")
            if chassis and chassis:IsA("BasePart") then
                root = chassis
                for _, name in ipairs({"FL", "FR", "RL", "RR"}) do
                    local attachment = root:FindFirstChild(name)
                    if attachment and attachment:IsA("Attachment") then table.insert(wheels, attachment) end
                end
            end
        end
    end
    local filter = {}
    if cars then table.insert(filter, cars) end
    if player.Character then table.insert(filter, player.Character) end
    groundParams.FilterDescendantsInstances = filter
    local obstacleFilter = {}
    if car then table.insert(obstacleFilter, car) end
    if player.Character then table.insert(obstacleFilter, player.Character) end
    obstacleParams.FilterDescendantsInstances = obstacleFilter
end

local minimapCache, watched = {}, {}
local raceName, raceText, racePath = nil, nil, nil
local function refreshRoads(now)
    local currentRace = player:GetAttribute("RaceCourse")
    if now < roadCheckAt and not app.roadDirty and currentRace == raceName then return end
    roadCheckAt, app.roadDirty = now + 2, false
    local paths, seen = {}, {}
    local minimap = ReplicatedStorage:FindFirstChild("Minimap")
    if minimap then
        for _, value in ipairs(minimap:GetChildren()) do
            if not value:IsA("StringValue") then continue end
            seen[value] = true
            local cached = minimapCache[value]
            if not cached or cached.text ~= value.Value then
                cached = {text = value.Value, paths = Roads.parseMinimap(value.Value, value.Name)}
                minimapCache[value] = cached
                if not watched[value] then
                    watched[value] = true
                    connect(value:GetPropertyChangedSignal("Value"), function() app.roadDirty = true end)
                end
            end
            for _, path in ipairs(cached.paths) do if #paths < 128 then table.insert(paths, path) end end
        end
    end
    for value in pairs(minimapCache) do if not seen[value] then minimapCache[value] = nil end end
    local courses = ReplicatedStorage:FindFirstChild("RaceCourses")
    local course = if type(currentRace) == "string" and courses then courses:FindFirstChild(currentRace) else nil
    local points = course and course:FindFirstChild("Points")
    local text = if points and points:IsA("StringValue") then points.Value else nil
    if currentRace ~= raceName or text ~= raceText then
        raceName, raceText = currentRace, text
        racePath = if text then Roads.parseRace(text, "Race "..currentRace, course:GetAttribute("Width")) else nil
        if racePath then
            local startS, length = course:GetAttribute("StartD"), course:GetAttribute("Length")
            if Controller.finite(startS) and Controller.finite(length) then
                racePath.finishS = math.clamp(startS + length, 0, racePath.total)
            end
        end
        if app.settings.mode == "road" then
            app.path, app.previousS, app.guide, app.guideAt = nil, nil, nil, nil
        end
    end
    app.routes = paths
    app.racePath = racePath
    if app.path and not table.find(paths, app.path) and app.path ~= racePath then
        app.path, app.previousS, app.guide, app.guideAt = nil, nil, nil, nil
    end
end

local function readInput()
    local function down(a, b)
        return Input:IsKeyDown(Enum.KeyCode[a]) or (b ~= nil and Input:IsKeyDown(Enum.KeyCode[b]))
    end
    local throttle, brake = if down("W", "Up") then 1 else 0, if down("S", "Down") then 1 else 0
    local steer = (if down("D", "Right") then 1 else 0) - (if down("A", "Left") then 1 else 0)
    local handbrake = down("Space")
    if Input.GamepadEnabled then
        local ok, state = pcall(Input.GetGamepadState, Input, Enum.UserInputType.Gamepad1)
        if ok then
            for _, key in ipairs(state) do
                if key.KeyCode == Enum.KeyCode.Thumbstick1 and math.abs(key.Position.X) > 0.15 then steer = key.Position.X end
                if key.KeyCode == Enum.KeyCode.ButtonR2 then throttle = math.max(throttle, key.Position.Z) end
                if key.KeyCode == Enum.KeyCode.ButtonL2 then brake = math.max(brake, key.Position.Z) end
                if key.KeyCode == Enum.KeyCode.ButtonA and key.UserInputState == Enum.UserInputState.Begin then handbrake = true end
            end
        end
    end
    return {throttle = throttle, brake = brake, steer = steer, handbrake = handbrake,
        boost = down("LeftShift", "RightShift")}
end

local function sampleCar()
    if not root or not car then return nil, "Spawn / enter your own car" end
    if car:GetAttribute("OwnerUserId")~=player.UserId then return nil, "Waiting for your own car" end
    local humanoid = player.Character and player.Character:FindFirstChildOfClass("Humanoid")
    if not humanoid or not humanoid.SeatPart or not humanoid.SeatPart:IsDescendantOf(car) then return nil, "Sit in your own car" end
    if car:GetAttribute("NetOwner") ~= player.UserId then return nil, "Waiting for your car's network ownership" end
    if root.Anchored then return nil, "Car is anchored / parked" end
    local cf, velocity, angular = root.CFrame, root.AssemblyLinearVelocity, root.AssemblyAngularVelocity
    local mass = root.AssemblyMass
    if not Controller.finite(mass) or mass <= 0 then return nil, "Invalid car mass" end
    local count = 0
    for _, attachment in ipairs(wheels) do
        local front = attachment.Name:sub(1,1) == "F"
        local ride = car:GetAttribute(if front then "RideHeightF" else "RideHeightR")
        local tire = car:GetAttribute(if front then "TireSize" else "TireSizeR")
        if not front and tire==nil then tire=car:GetAttribute("TireSize") end
        local scale = if tire==85 or tire==90 or tire==95 or tire==100 or tire==105 then tire/100 else 1
        -- Match the uploaded suspension rest + ride height + tyre radius, with 5 cm tolerance.
        local reach = 0.84 + (if Controller.finite(ride) then math.clamp(ride, -0.6, 1.5) else 0) + 1.1*scale + 0.05
        local hit = World:Raycast(attachment.WorldPosition, -cf.UpVector*reach, groundParams)
        if hit and hit.Normal.Y > 0.35 then count += 1 end
    end
    return {x = root.Position.X, y = root.Position.Y, z = root.Position.Z,
        vx = velocity.X, vz = velocity.Z, vy = velocity.Y,
        yaw = math.atan2(-cf.LookVector.X, -cf.LookVector.Z), yawRate = angular.Y,
        grounded = count, upY = cf.UpVector.Y, mass = mass}
end

local function obstacle(sample, guide, now)
    if now < obstacleAt then return app.obstruction end
    obstacleAt = now + 0.1
    app.obstruction = nil
    local speed = math.sqrt(sample.vx^2+sample.vz^2)
    local heading = if speed > 3 then math.atan2(-sample.vx, -sample.vz) else sample.yaw
    local direction = Vector3.new(-math.sin(heading), 0, -math.cos(heading))
    local right = Vector3.new(math.cos(heading), 0, -math.sin(heading))
    local reach = math.clamp(speed*0.35 + speed*speed/80 + 8, 10, 180)
    for _, side in ipairs({-0.8, 0, 0.8}) do
        local origin = root.Position + right*(root.Size.X*0.5*side) + Vector3.new(0,0.25,0)
        local hit = World:Raycast(origin, direction*reach, obstacleParams)
        if hit and math.abs(hit.Normal.Y) < 0.65 then
            app.obstruction = "Obstacle ahead; braking"
            app.lastObstacle = {name = hit.Instance.Name, distance = finiteOrNil(hit.Distance)}
            return app.obstruction
        end
    end
    -- A path can continue into unloaded geometry. Wait instead of accelerating into empty space.
    if guide and guide.target then
        local p = guide.target
        local y = p.y or sample.y
        local ground = World:Raycast(Vector3.new(p.x,y+25,p.z),Vector3.new(0,-65,0),groundParams)
        if not ground then app.obstruction = "Road ahead is not loaded / no ground; braking" end
    end
    return app.obstruction
end

local palette = {bg = Color3.fromRGB(17,21,29), panel = Color3.fromRGB(27,33,45),
    ink = Color3.fromRGB(235,241,250), dim = Color3.fromRGB(153,170,190),
    accent = Color3.fromRGB(61,196,177), red = Color3.fromRGB(177,65,80)}
local function make(class, props, parent)
    local o = Instance.new(class)
    for k, v in pairs(props) do o[k] = v end
    o.Parent = parent
    return o
end
local function corner(parent, radius) make("UICorner", {CornerRadius=UDim.new(0,radius or 8)}, parent) end
local gui = make("ScreenGui", {Name="HowToDriftAssist", ResetOnSpawn=false, IgnoreGuiInset=true,
    DisplayOrder=95, ZIndexBehavior=Enum.ZIndexBehavior.Sibling}, playerGui)
app.gui = gui
local panel = make("Frame", {Name="Panel", Size=UDim2.fromOffset(364,610),
    Position=UDim2.new(1,-382,0,80), BackgroundColor3=palette.bg, BorderSizePixel=0}, gui)
corner(panel,12)
local scale = make("UIScale", {Scale=1}, panel)
local header = make("TextLabel", {Name="Header", Size=UDim2.new(1,-80,0,46), Position=UDim2.fromOffset(14,0),
    BackgroundTransparency=1, Text="DRIFT ASSIST  1.0.0", TextColor3=palette.ink,
    TextSize=17, Font=Enum.Font.GothamBold, TextXAlignment=Enum.TextXAlignment.Left, Active=true}, panel)
local function button(name, text, position, size, parent, callback)
    local b = make("TextButton", {Name=name, Text=text, Position=position, Size=size, BackgroundColor3=palette.panel,
        BorderSizePixel=0, TextColor3=palette.ink, TextSize=13, Font=Enum.Font.GothamBold, AutoButtonColor=true}, parent)
    corner(b,7)
    connect(b.Activated, callback)
    return b
end
local minimized = false
local body = make("ScrollingFrame", {Name="Body", Position=UDim2.fromOffset(12,48), Size=UDim2.new(1,-24,1,-60),
    BackgroundTransparency=1, BorderSizePixel=0, ScrollBarThickness=3, CanvasSize=UDim2.fromOffset(0,650),
    ScrollingDirection=Enum.ScrollingDirection.Y}, panel)
button("Minimize", "_", UDim2.new(1,-69,0,9), UDim2.fromOffset(27,27), panel, function()
    minimized = not minimized
    body.Visible = not minimized
    panel.Size = UDim2.fromOffset(364, if minimized then 46 else 610)
end)
button("Close", "x", UDim2.new(1,-36,0,9), UDim2.fromOffset(27,27), panel, function() app.destroy() end)
local startButton = button("Start", "Start  [F6]", UDim2.fromOffset(0,0), UDim2.new(1,-6,0,38), body, function()
    if app.enabled then app.stop() else app.start() end
end)
local modeButton = button("Mode", "Manual + angle hold", UDim2.fromOffset(0,46), UDim2.new(0.56,-4,0,34), body, function()
    app.setMode(if app.settings.mode == "manual" then "road" else "manual")
end)
local sideButton = button("Side", "Side: Auto", UDim2.new(0.56,3,0,46), UDim2.new(0.44,-9,0,34), body, app.cycleSide)
local sliderRefresh = {}
local draggingSlider, draggingPanel
local function slider(key, label, low, high, increment, suffix, y)
    local row = make("Frame", {Name=key, BackgroundTransparency=1, Position=UDim2.fromOffset(0,y), Size=UDim2.new(1,-6,0,58)}, body)
    make("TextLabel", {BackgroundTransparency=1, Size=UDim2.new(1,-92,0,24), Text=label,
        TextColor3=palette.dim, TextSize=13, Font=Enum.Font.Gotham, TextXAlignment=Enum.TextXAlignment.Left}, row)
    local value = make("TextBox", {Name="Value", Position=UDim2.new(1,-89,0,0), Size=UDim2.fromOffset(87,25),
        BackgroundColor3=palette.panel, BorderSizePixel=0, TextColor3=palette.ink, TextSize=13,
        Font=Enum.Font.GothamBold, ClearTextOnFocus=false}, row)
    corner(value,5)
    local track = make("TextButton", {Name="Track", Position=UDim2.fromOffset(0,36), Size=UDim2.new(1,-4,0,7),
        Text="", BackgroundColor3=palette.panel, BorderSizePixel=0, AutoButtonColor=false}, row)
    corner(track,4)
    local fill = make("Frame", {Size=UDim2.fromScale(0,1), BackgroundColor3=palette.accent, BorderSizePixel=0}, track)
    corner(fill,4)
    local knob = make("Frame", {Size=UDim2.fromOffset(13,13), AnchorPoint=Vector2.new(0.5,0.5),
        Position=UDim2.fromScale(0,0.5), BackgroundColor3=palette.ink, BorderSizePixel=0}, track)
    corner(knob,7)
    local function refresh()
        local fraction = (app.settings[key]-low)/(high-low)
        fill.Size, knob.Position = UDim2.fromScale(fraction,1), UDim2.fromScale(fraction,0.5)
        value.Text = string.format(if increment >= 1 then "%.0f%s" else "%.2f%s", app.settings[key], suffix)
    end
    local function set(v)
        if Controller.finite(v) then
            app.settings[key] = math.clamp(math.floor(v/increment+0.5)*increment, low, high)
        end
        refresh()
    end
    local function drag(x)
        local fraction = math.clamp((x-track.AbsolutePosition.X)/math.max(track.AbsoluteSize.X,1),0,1)
        set(low+(high-low)*fraction)
    end
    connect(track.InputBegan, function(input)
        if input.UserInputType == Enum.UserInputType.MouseButton1 or input.UserInputType == Enum.UserInputType.Touch then
            draggingSlider = {input=input, drag=drag}
            drag(input.Position.X)
        end
    end)
    connect(value.FocusLost, function() set(tonumber(value.Text:match("[%-%d%.]+"))) end)
    sliderRefresh[key] = refresh
    refresh()
end
slider("angle", "Drift angle", 15,50,1," deg",93)
slider("cruiseKmh", "Speed target / manual cap",20,180,1," km/h",151)
slider("power", "Power assistance",0.5,4,0.05,"x",209)
slider("speedMultiplier", "Speed multiplier",0.5,2.5,0.05,"x",267)
slider("strength", "Angle lock strength",0,1,0.05,"",325)
button("NearestRoad", "Nearest road", UDim2.fromOffset(0,387), UDim2.new(0.53,-4,0,32), body, app.nearestRoad)
button("ReverseRoad", "Reverse route", UDim2.new(0.53,3,0,387), UDim2.new(0.47,-9,0,32), body, function()
    app.stop("Route reversed. Align the car, then Start")
    app.direction = -app.direction
    app.previousS, app.guide, app.guideAt = nil, nil, nil
end)
local status = make("TextLabel", {Name="Status", Position=UDim2.fromOffset(0,429), Size=UDim2.new(1,-8,0,61),
    BackgroundTransparency=1, Text=app.status, TextWrapped=true, TextYAlignment=Enum.TextYAlignment.Top,
    TextXAlignment=Enum.TextXAlignment.Left, Font=Enum.Font.Gotham, TextSize=13, TextColor3=palette.dim}, body)
local telemetry = make("TextLabel", {Name="Telemetry", Position=UDim2.fromOffset(0,494), Size=UDim2.new(1,-8,0,49),
    BackgroundTransparency=1, Text="No car telemetry", TextWrapped=true, TextYAlignment=Enum.TextYAlignment.Top,
    TextXAlignment=Enum.TextXAlignment.Left, Font=Enum.Font.Code, TextSize=12, TextColor3=palette.ink}, body)

function app.report()
    local attributes = {}
    if car then
        for _, name in ipairs({"OwnerUserId","NetOwner","CarId","EngineStage","Turbo","WeightStage","TyreStage",
            "DriftAssist","Drivetrain","RideHeightF","RideHeightR","SteerLock","TireSize","TireSizeR"}) do
            local value = car:GetAttribute(name)
            if value ~= nil then attributes[name] = primitive(value) end
        end
    end
    local settings = Controller.settings(app.settings)
    return {version=app.version, place_id=game.PlaceId, enabled=app.enabled, status=app.status,
        settings=settings, car=if car then car.Name else nil, attributes=attributes,
        admin_granted=player:GetAttribute("Admin")==true, route=if app.path then app.path.name else nil,
        route_count=#app.routes, direction=app.direction, last_sample=app.lastSample, last_command=app.lastCommand,
        last_obstacle=app.lastObstacle, last_error=app.lastError, controller_frames=app.frames,
        physics_writes=app.physicsWrites, input_writes=app.inputWrites, last_controller_ms=app.lastControllerMs,
        peak_controller_ms=app.peakControllerMs, last_update_ms=app.lastUpdateMs, peak_update_ms=app.peakUpdateMs, trace=app.trace,
        note="Client physics assistance. No server/admin access; no drift reward submission. Offline tests do not prove live compatibility."}
end
button("Diagnostics", "Save diagnostics", UDim2.fromOffset(0,548), UDim2.new(1,-6,0,33), body, function()
    local ok, text = pcall(function() return HttpService:JSONEncode(app.report()) end)
    if not ok then app.status = "Diagnostics encode failed: "..tostring(text); return end
    if type(writefile) == "function" then
        local saved, err = pcall(writefile, "HowToDrift_Diagnostics.json", text)
        app.status = if saved then "Saved HowToDrift_Diagnostics.json in executor workspace" else "Save failed: "..tostring(err)
    elseif type(setclipboard) == "function" then
        local copied = pcall(setclipboard, text)
        app.status = if copied then "Diagnostics copied to clipboard" else "Clipboard unavailable"
    else
        print(text)
        app.status = "File writing unavailable; diagnostics printed in F9 console"
    end
end)
make("TextLabel", {Name="Help", Position=UDim2.fromOffset(0,591), Size=UDim2.new(1,-8,0,57),
    BackgroundTransparency=1, Text="F6 Start/Stop  |  F7 Mode  |  F8 Drift side\nW/S/A/D or arrows; hold Shift for boost.\nS / Space overrides Road auto. Use the game's Auto gearbox.",
    TextWrapped=true, TextYAlignment=Enum.TextYAlignment.Top, TextXAlignment=Enum.TextXAlignment.Left,
    Font=Enum.Font.Gotham, TextSize=11, TextColor3=palette.dim}, body)

connect(header.InputBegan, function(input)
    if input.UserInputType == Enum.UserInputType.MouseButton1 or input.UserInputType == Enum.UserInputType.Touch then
        draggingPanel = {input=input, position=input.Position, origin=panel.Position}
    end
end)
connect(Input.InputChanged, function(input)
    if draggingSlider and (input == draggingSlider.input or input.UserInputType == Enum.UserInputType.MouseMovement) then
        draggingSlider.drag(input.Position.X)
    elseif draggingPanel and (input == draggingPanel.input or input.UserInputType == Enum.UserInputType.MouseMovement) then
        local delta = input.Position-draggingPanel.position
        local origin = draggingPanel.origin
        panel.Position = UDim2.new(origin.X.Scale,origin.X.Offset+delta.X,origin.Y.Scale,origin.Y.Offset+delta.Y)
    end
end)
connect(Input.InputEnded, function(input)
    if input.UserInputType == Enum.UserInputType.MouseButton1 or input.UserInputType == Enum.UserInputType.Touch then
        if draggingSlider and (input == draggingSlider.input or input.UserInputType == Enum.UserInputType.MouseButton1) then draggingSlider = nil end
        if draggingPanel and (input == draggingPanel.input or input.UserInputType == Enum.UserInputType.MouseButton1) then draggingPanel = nil end
    end
end)
connect(Input.InputBegan, function(input, processed)
    if processed or Input:GetFocusedTextBox() then return end
    if input.KeyCode == Enum.KeyCode.F6 then if app.enabled then app.stop() else app.start() end
    elseif input.KeyCode == Enum.KeyCode.F7 then app.setMode(if app.settings.mode=="manual" then "road" else "manual")
    elseif input.KeyCode == Enum.KeyCode.F8 then app.cycleSide() end
end)
connect(Input.WindowFocusReleased, function() app.focused=false; release() end)
connect(Input.WindowFocused, function() app.focused=true end)
connect(player.CharacterRemoving, function() release(); carCheckAt=-math.huge end)

local function frame(dt)
    local now = os.clock()
    if now-uiAt > 0.1 then
        uiAt = now
        startButton.Text = if app.enabled then "Stop  [F6]" else "Start  [F6]"
        startButton.BackgroundColor3 = if app.enabled then palette.red else palette.accent
        modeButton.Text = if app.settings.mode=="road" then "Road auto  [F7]" else "Manual + angle hold"
        sideButton.Text = "Side: "..app.settings.side
        status.Text = app.status
        local s, cmd = app.lastSample, app.lastCommand
        if s then
            local m = Controller.measure(s)
            telemetry.Text = if m then string.format("%.1f km/h | angle %+.1f / %+.1f deg\nRoad: %s\nGround %d/4 | controller %.2f ms",m.speed*1.2,
                math.deg(m.beta),cmd and cmd.targetAngle or 0,app.path and app.path.name or "none",s.grounded,app.lastControllerMs) else "Invalid telemetry"
        else telemetry.Text="No seated car telemetry" end
        local camera = World.CurrentCamera
        if camera then scale.Scale=math.clamp(math.min(camera.ViewportSize.Y/720,camera.ViewportSize.X/600),0.5,1) end
    end
    if not app.enabled then return end
    findCar(now)
    local sample, reason = sampleCar()
    if not sample then release(); app.status=reason; app.lastSample=nil; return end
    app.lastSample = sample
    local pause
    if not app.focused then pause="Paused while game is unfocused"
    elseif Input:GetFocusedTextBox() then pause="Paused while typing"
    elseif GuiService.MenuIsOpen then pause="Paused in Roblox menu"
    elseif player:GetAttribute("InGarage") then pause="Paused in garage"
    elseif player:GetAttribute("Replaying") or player:GetAttribute("Spectating") then pause="Paused during replay / spectating"
    elseif dt > 0.2 then pause="Paused after a long frame" end
    local goAt=player:GetAttribute("RaceGoAt")
    if Controller.finite(goAt) and World:GetServerTimeNow()<goAt then pause="Waiting for race countdown" end
    local externalInput=player:GetAttribute("DebugInput")
    if externalInput~=nil and externalInput~=app.lease.last then
        app.stop("Another controller owns DebugInput; stop it before starting this one")
        return
    end
    if pause then release(); app.status=pause; return end
    local input = readInput()
    local guide
    if app.settings.mode=="road" then
        refreshRoads(now)
        local speed=math.sqrt(sample.vx^2+sample.vz^2)
        if not app.path then
            if app.racePath then app.path,app.direction=app.racePath,1
            else app.path,app.direction=Roads.nearest(app.routes,sample,sample.yaw) end
            app.direction=app.direction or 1
        end
        if app.path then
            if not app.guideAt or now-app.guideAt >= 0.075 then
                app.guide=Roads.guide(app.path,app.direction,sample,speed,sample.yaw,app.previousS)
                app.guideAt=now
                if app.guide then
                    app.previousS=app.guide.s
                    if app.path.finishS and app.direction>0 then app.guide.remaining=math.max(0,app.path.finishS-app.guide.s) end
                end
            end
            guide=app.guide
            if guide then guide.blocked=obstacle(sample,guide,now) end
        end
    end
    local started=os.clock()
    local command=Controller.step(app.controller,app.settings,sample,input,guide,dt)
    app.frames+=1
    app.status=command.reason
    if command.override then
        local ok, err=app.lease:write(command)
        if not ok then app.stop(err); return end
        app.inputWrites+=1
    else app.lease:release() end
    local controllable = sample.grounded>=3 and sample.upY>=0.55
    if controllable and (command.ax~=0 or command.az~=0) then
        local stepDt=math.clamp(dt,1/240,0.05)
        root:ApplyImpulse(Vector3.new(command.ax,0,command.az)*sample.mass*stepDt)
        app.physicsWrites+=1
    end
    if controllable and command.yawRate then
        local current=root.AssemblyAngularVelocity
        root.AssemblyAngularVelocity=Vector3.new(current.X,command.yawRate,current.Z)
        app.physicsWrites+=1
    end
    app.lastCommand={throttle=command.throttle,brake=command.brake,steer=command.steer,handbrake=command.handbrake,
        ax=command.ax,az=command.az,yawRate=command.yawRate,targetAngle=command.targetAngle,targetKmh=command.targetKmh,
        override=command.override,reason=command.reason,crossTrack=guide and finiteOrNil(guide.crossTrack)}
    app.lastControllerMs=(os.clock()-started)*1000
    app.peakControllerMs=math.max(app.peakControllerMs,app.lastControllerMs)
    if now-traceAt>=0.5 then
        traceAt=now
        local m=Controller.measure(sample)
        table.insert(app.trace,{at=now,speed_kmh=m and m.speed*1.2,angle=m and math.deg(m.beta),target_angle=command.targetAngle,
            grounded=sample.grounded,status=app.status,cross_track=guide and finiteOrNil(guide.crossTrack)})
        if #app.trace>240 then table.remove(app.trace,1) end
    end
end

function app.destroy()
    if not app.alive then return end
    app.stop()
    app.alive=false
    for _, c in ipairs(app.connections) do pcall(function() c:Disconnect() end) end
    gui:Destroy()
    if rawget(env,"__HowToDriftAssist")==app then env.__HowToDriftAssist=nil end
end
connect(gui.AncestryChanged,function(_,parent) if not parent then app.destroy() end end)
connect(RunService.PreSimulation,function(dt)
    if not app.alive then return end
    local started=os.clock()
    local ok,err=xpcall(function() frame(dt) end,function(message) return tostring(message) end)
    app.lastUpdateMs=(os.clock()-started)*1000
    app.peakUpdateMs=math.max(app.peakUpdateMs,app.lastUpdateMs)
    if not ok then
        app.lastError=tostring(err)
        app.stop("Stopped after error: "..tostring(err))
        warn("[HowToDrift Assist] "..tostring(err))
    end
end)
print("[HowToDrift Assist 1.0.0] Ready. F6 Start/Stop; F7 mode; F8 side. Start at 65 km/h, 30 degrees.")
