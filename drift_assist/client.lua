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

local app = {version = "1.2.0", alive = true, enabled = true, connections = {},
    settings = Controller.settings({mode="road",style="farm",angle=35,cruiseKmh=85}), controller = Controller.new(), lease = InputLease.new(player),
    status = "Autodrive armed; sit in your own car", trace = {}, frames = 0,
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
    app.rail=nil
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
function app.nearestRoad()
    app.path, app.previousS, app.guide, app.guideAt = nil, nil, nil, nil
    app.direction, app.roadDirty = 1, true
    app.rail=nil
    app.loopAnchor,app.safeAnchor,app.surface=nil,nil,nil
end
function app.setStyle(style)
    app.settings.style=if style=="cool" then "cool" else "farm"
    if app.rail then app.rail.area=nil;app.rail.backwards=false end
end

local root, car, wheels = nil, nil, {}
local wheelGeometry={}
local function calibrateWheels()
    wheelGeometry={}
    for _,a in ipairs(wheels) do
        local front=a.Name:sub(1,1)=="F"
        local ride=car:GetAttribute(if front then "RideHeightF" else "RideHeightR") or 0
        local tire=car:GetAttribute(if front then "TireSize" else "TireSizeR") or car:GetAttribute("TireSize") or 100
        local scale=if tire==85 or tire==90 or tire==95 or tire==100 or tire==105 then tire/100 else 1
        local p=a.Position
        table.insert(wheelGeometry,{name=a.Name,x=p.X,y=p.Y,z=p.Z,reach=.84+ride+1.1*scale})
    end
    local width,length=0,0
    for _,w in ipairs(wheelGeometry) do width=math.max(width,math.abs(w.x));length=math.max(length,math.abs(w.z)) end
    app.settings.halfWidth=width+.8;app.settings.halfLength=length+1.5
end
local carCheckAt, roadCheckAt, traceAt, uiAt, obstacleAt = -math.huge, -math.huge, -math.huge, -math.huge, -math.huge
local groundParams, obstacleParams = RaycastParams.new(), RaycastParams.new()
groundParams.FilterType, obstacleParams.FilterType = Enum.RaycastFilterType.Exclude, Enum.RaycastFilterType.Exclude
groundParams.IgnoreWater, obstacleParams.IgnoreWater = true, true
groundParams.RespectCanCollide, obstacleParams.RespectCanCollide = true, true
local function findCar(now)
    local home=car and car:GetAttribute("HomeCF")
    local homeMoved=typeof(home)=="CFrame" and (
        (typeof(app.homeTransform)=="CFrame" and (home.Position-app.homeTransform.Position).Magnitude>500)
        or (app.homeInitialized and typeof(app.homeTransform)~="CFrame"))
    if now < carCheckAt and root and root.Parent and car and car.Parent and not homeMoved then return end
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
        app.loopAnchor,app.safeAnchor,app.surface=nil,nil,nil
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
    if homeMoved then app.nearestRoad() end
    app.homeTransform=car and car:GetAttribute("HomeCF")
    app.homeInitialized=car~=nil
    if root then calibrateWheels() end
    local filter = {}
    if cars then table.insert(filter, cars) end
    for _,p in ipairs(Players:GetPlayers()) do if p.Character then table.insert(filter,p.Character) end end
    groundParams.FilterDescendantsInstances = filter
    local obstacleFilter = {}
    if car then table.insert(obstacleFilter, car) end
    if player.Character then table.insert(obstacleFilter, player.Character) end
    obstacleParams.FilterDescendantsInstances = obstacleFilter
end

local minimapCache, watched = {}, {}
local raceName, raceText, racePath = nil, nil, nil
local courseCache={}
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
    -- Some maps expose road lines locally but are absent from the replicated minimap folder.
    for _,map in ipairs(World:GetChildren()) do
        if not map:IsA("Model") and not map:IsA("Folder") then continue end
        local value=map:FindFirstChild("MinimapLines") or map:FindFirstChild("MinimapPath")
        if value and value:IsA("StringValue") then
            seen[value]=true
            local cached=minimapCache[value]
            if not cached or cached.text~=value.Value then
                local data=value.Value
                if not data:find("|",1,true) then data="line|36|"..data end
                cached={text=value.Value,paths=Roads.parseMinimap(data,map.Name)}
                minimapCache[value]=cached
            end
            for _,path in ipairs(cached.paths) do if #paths<128 then table.insert(paths,path) end end
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
    local elevationChanged=false
    local coursePaths,courseSeen={},{}
    if courses then
        for _,folder in ipairs(courses:GetChildren()) do
            local pointsValue=folder:FindFirstChild("Points")
            if pointsValue and pointsValue:IsA("StringValue") then
                courseSeen[folder]=true
                local cached=courseCache[folder]
                if not cached or cached.text~=pointsValue.Value then
                    cached={text=pointsValue.Value,path=Roads.parseRace(pointsValue.Value,folder.Name,folder:GetAttribute("Width"))}
                    courseCache[folder]=cached;elevationChanged=true
                end
                if cached.path then table.insert(coursePaths,cached.path) end
            end
        end
    end
    for folder in pairs(courseCache) do if not courseSeen[folder] then courseCache[folder]=nil;elevationChanged=true end end
    if elevationChanged or not app.elevation then app.elevation=Elevation.new(coursePaths) end
    app.routes = paths
    app.racePath = racePath
    if app.path and not table.find(paths, app.path) and app.path ~= racePath then
        app.path, app.previousS, app.guide, app.guideAt = nil, nil, nil, nil
    end
    if app.loopAnchor and not table.find(paths,app.loopAnchor.path) and app.loopAnchor.path~=racePath then app.loopAnchor=nil end
    if app.safeAnchor and not table.find(paths,app.safeAnchor.path) and app.safeAnchor.path~=racePath then app.safeAnchor=nil end
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
    local floorX,floorY,floorZ,normalX,normalY,normalZ=0,0,0,0,0,0
    for _, attachment in ipairs(wheels) do
        local front = attachment.Name:sub(1,1) == "F"
        local ride = car:GetAttribute(if front then "RideHeightF" else "RideHeightR")
        local tire = car:GetAttribute(if front then "TireSize" else "TireSizeR")
        if not front and tire==nil then tire=car:GetAttribute("TireSize") end
        local scale = if tire==85 or tire==90 or tire==95 or tire==100 or tire==105 then tire/100 else 1
        -- Match the uploaded suspension rest + ride height + tyre radius, with 5 cm tolerance.
        local reach = 0.84 + (if Controller.finite(ride) then math.clamp(ride, -0.6, 1.5) else 0) + 1.1*scale + 0.05
        local hit = World:Raycast(attachment.WorldPosition, -cf.UpVector*reach, groundParams)
        if hit and hit.Normal.Y > 0.35 then
            count+=1;floorX+=hit.Position.X;floorY+=hit.Position.Y;floorZ+=hit.Position.Z
            normalX+=hit.Normal.X;normalY+=hit.Normal.Y;normalZ+=hit.Normal.Z
        end
    end
    return {x = root.Position.X, y = root.Position.Y, z = root.Position.Z,
        vx = velocity.X, vz = velocity.Z, vy = velocity.Y,
        yaw = math.atan2(-cf.LookVector.X, -cf.LookVector.Z), yawRate = angular.Y,
        grounded = count, upY = cf.UpVector.Y, mass = mass,
        forwardSpeed=velocity:Dot(cf.LookVector),sideSpeed=velocity:Dot(cf.RightVector),
        floor=if count>=3 then {x=floorX/count,y=floorY/count,z=floorZ/count,
            up={x=normalX/count,y=normalY/count,z=normalZ/count}} else nil}
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
local panel = make("Frame", {Name="Panel", Size=UDim2.fromOffset(364,520),
    Position=UDim2.new(1,-382,0,80), BackgroundColor3=palette.bg, BorderSizePixel=0}, gui)
corner(panel,12)
local scale = make("UIScale", {Scale=1}, panel)
local header = make("TextLabel", {Name="Header", Size=UDim2.new(1,-80,0,46), Position=UDim2.fromOffset(14,0),
    BackgroundTransparency=1, Text="DRIFT ASSIST  1.2.0", TextColor3=palette.ink,
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
    BackgroundTransparency=1, BorderSizePixel=0, ScrollBarThickness=3, CanvasSize=UDim2.fromOffset(0,535),
    ScrollingDirection=Enum.ScrollingDirection.Y}, panel)
button("Minimize", "_", UDim2.new(1,-69,0,9), UDim2.fromOffset(27,27), panel, function()
    minimized = not minimized
    body.Visible = not minimized
    panel.Size = UDim2.fromOffset(364, if minimized then 46 else 520)
end)
button("Close", "x", UDim2.new(1,-36,0,9), UDim2.fromOffset(27,27), panel, function() app.destroy() end)
local startButton = button("Start", "Start  [F6]", UDim2.fromOffset(0,0), UDim2.new(1,-6,0,38), body, function()
    if app.enabled then app.stop() else app.start() end
end)
local modeButton = button("Mode", "Farm mode", UDim2.fromOffset(0,46), UDim2.new(0.5,-4,0,34), body, function()
    app.setStyle(if app.settings.style=="farm" then "cool" else "farm")
end)
local travelButton=button("FarmTravel", "Farm: Loop", UDim2.new(.5,3,0,46), UDim2.new(.5,-9,0,34), body,function()
    app.settings.farmTravel=if app.settings.farmTravel=="loop" then "area" else "loop"
    if app.rail then app.rail.area=nil;app.rail.backwards=false end
end)
local sideButton = button("Side", "Reverse", UDim2.new(0.62,3,0,85), UDim2.new(0.38,-9,0,30), body, function()
    app.direction=-app.direction
    if app.rail then Rail.reverse(app.rail,app.settings.style=="farm" and app.settings.farmTravel=="area") end
    app.guideAt=nil
end)
button("Rejoin","Rejoin nearest road [F7]",UDim2.fromOffset(0,85),UDim2.new(.62,-4,0,30),body,app.nearestRoad)
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
        if not value:IsFocused() then
            value.Text = if key=="angle" and app.settings.style=="farm" then "60 auto" else string.format(if increment >= 1 then "%.0f%s" else "%.2f%s", app.settings[key], suffix)
        end
        value.TextEditable=key~="angle" or app.settings.style~="farm"
    end
    local function set(v)
        if key=="angle" and app.settings.style=="farm" then refresh();return end
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
slider("angle", "Cool maximum angle / Farm auto", 15,75,1," deg",125)
slider("cruiseKmh", "Speed (Farm: 25+ km/h)",20,500,1," km/h",183)
slider("farmRange", "Farm area length (studs)",20,300,1,"",241)
local status = make("TextLabel", {Name="Status", Position=UDim2.fromOffset(0,305), Size=UDim2.new(1,-8,0,61),
    BackgroundTransparency=1, Text=app.status, TextWrapped=true, TextYAlignment=Enum.TextYAlignment.Top,
    TextXAlignment=Enum.TextXAlignment.Left, Font=Enum.Font.Gotham, TextSize=13, TextColor3=palette.dim}, body)
local telemetry = make("TextLabel", {Name="Telemetry", Position=UDim2.fromOffset(0,370), Size=UDim2.new(1,-8,0,59),
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
        recoveries=app.recoveries or 0, last_surface_error=app.lastSurfaceError,last_surface_error_at=app.lastSurfaceErrorAt,
        surface=if app.surface then {position=app.surface.position,normal=app.surface.up,contacts=app.surface.contacts,
            wheel_distances=app.surface.distances} else nil,
        drift_pay=player:GetAttribute("DriftPay"),drift_pay_why=player:GetAttribute("DriftPayWhy"),
        elevation_segments=app.elevation and app.elevation.count,
        note="Farm/Cool kinematic autopilot. Farm uses the client angle bonus cap at 60 degrees. Server payouts and live contact are not guaranteed."}
end
button("Diagnostics", "Save diagnostics", UDim2.fromOffset(0,438), UDim2.new(1,-6,0,33), body, function()
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
make("TextLabel", {Name="Help", Position=UDim2.fromOffset(0,482), Size=UDim2.new(1,-8,0,57),
    BackgroundTransparency=1, Text="F6 Start/Stop | F7 Rejoin | S / Space Brake\nFarm: fixed 60 deg, Loop or Area reverse.\nCool: flowing lane line, automatic corner speed.",
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
    elseif input.KeyCode == Enum.KeyCode.F7 then app.nearestRoad()
    end
end)
connect(Input.WindowFocusReleased, function() app.focused=false; app.lease:release() end)
connect(Input.WindowFocused, function() app.focused=true end)
connect(player.CharacterRemoving, function() release(); carCheckAt=-math.huge end)

local function frame(dt)
    local now = os.clock()
    if now-uiAt > 0.1 then
        uiAt = now
        startButton.Text = if app.enabled then "Stop  [F6]" else "Start  [F6]"
        startButton.BackgroundColor3 = if app.enabled then palette.red else palette.accent
        modeButton.Text = if app.settings.style=="farm" then "Farm mode" else "Cool mode"
        travelButton.Text = if app.settings.farmTravel=="area" then "Farm: Area reverse" else "Farm: Loop"
        sideButton.Text = "Reverse"
        for _,refresh in pairs(sliderRefresh) do refresh() end
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
    if pause then app.lease:release(); app.status=pause; return end
    local input = readInput()
    refreshRoads(now)
    if not app.path then
        if app.racePath then app.path,app.direction=app.racePath,1
        else app.path,app.direction=Roads.nearest(app.routes,sample,sample.yaw) end
        app.direction=app.direction or 1
    end
    if not app.path then
        release();app.status="Waiting for road data; drive near a loaded road"
        return
    end
    local started=os.clock()
    if not app.rail or app.rail.path~=app.path then
        local projection=Roads.project(app.path,sample,nil,sample.yaw)
        if not projection then release();app.status="Waiting for a valid road";return end
        app.rail=Rail.new(app.path,projection,app.direction)
        app.recoveries=(app.recoveries or 0)+1
    end
    local function query(x,y,z,length)
        local hit=World:Raycast(Vector3.new(x,y,z),Vector3.new(0,-length,0),groundParams)
        if not hit then return nil end
        local offroad=hit.Material==Enum.Material.Grass or hit.Material==Enum.Material.LeafyGrass or hit.Material==Enum.Material.Mud
        return {x=hit.Position.X,y=hit.Position.Y,z=hit.Position.Z,
            up={x=hit.Normal.X,y=hit.Normal.Y,z=hit.Normal.Z},offroad=offroad}
    end
    local reference=if app.surface then app.surface.reference else sample.floor
    if not reference then
        reference={x=sample.x,y=sample.y-2,z=sample.z,up={x=0,y=1,z=0}}
    end
    if not app.loopAnchor then
        local home=car:GetAttribute("HomeCF")
        local homePosition=if typeof(home)=="CFrame" then home.Position else nil
        local anchorPath,anchorDirection,projection=app.path,app.direction,nil
        if homePosition and (homePosition-root.Position).Magnitude<5000 then
            anchorPath,anchorDirection,projection=Roads.nearest(app.routes,
                {x=homePosition.X,y=homePosition.Y-2,z=homePosition.Z},math.atan2(-home.LookVector.X,-home.LookVector.Z))
            if projection and projection.distance>30 then projection=nil end
        end
        if projection then
            app.loopAnchor={path=anchorPath,s=projection.s,direction=anchorDirection,
                reference={x=projection.x,y=homePosition.Y-2,z=projection.z,up={x=0,y=1,z=0}}}
        else
            app.loopAnchor={path=app.path,s=app.rail.s,direction=app.rail.direction,reference=reference}
        end
    end
    app.rail.anchor=app.loopAnchor
    app.settings.offroad=player:GetAttribute("DriftPayWhy")=="offroad"
    local oldPlan=table.clone(app.rail)
    local up=reference.up
    local _,planHeading=Roads.point(app.rail.path,app.rail.s)
    local slope=-(up.x*(-math.sin(planHeading))+up.z*(-math.cos(planHeading)))/math.max(up.y,.35)
    local travelScale=1/math.sqrt(1+slope*slope)
    local pose=Rail.step(app.rail,app.settings,dt,input.brake>.1 or input.handbrake,app.routes,travelScale)
    if pose.reference then reference=pose.reference end
    local expected=if pose.point.y then pose.point.y else Surface.expected(reference,pose.point.x,pose.point.z)
    local hint=Elevation.height(app.elevation,pose.point.x,pose.point.z,expected,if app.surface then 6 else math.huge)
    if hint and not pose.point.y and (not app.surface or math.abs(hint-expected)<1.25) then
        reference={x=pose.point.x,y=hint,z=pose.point.z,up=reference.up}
    end
    local surface,why=Surface.solve(pose.point,pose.heading,pose.beta,wheelGeometry,reference,query)
    if not surface then app.lastSurfaceError,app.lastSurfaceErrorAt=why,now end
    if not surface and app.settings.style=="cool" then
        -- A flowing line can approach a narrow verge. Retry the center before leaving the pavement.
        local center,h=Roads.point(app.rail.path,app.rail.s)
        if app.rail.direction<0 then h+=math.pi end
        local originalReference=if app.surface then app.surface.reference else reference
        surface,why=Surface.solve(center,h,pose.beta,wheelGeometry,originalReference,query)
        if surface then
            pose.point,pose.heading,pose.lateral=center,h,0
            app.rail.laneScale=math.min(app.rail.laneScale or 1,.25)
        end
    end
    if not surface and pose.joined then
        -- A geometric connection may lead into unloaded or unsupported terrain. Try another exit.
        Rail.rejectConnection(oldPlan,app.rail.path)
        app.rail.rejected=oldPlan.rejected
    end
    if not surface then
        app.surfaceBlockedSince=app.surfaceBlockedSince or now
    else app.surfaceBlockedSince=nil end
    local recover=app.settings.style=="farm" or pose.jumped or (app.surfaceBlockedSince and now-app.surfaceBlockedSince>.5)
    if not surface and recover and app.safeAnchor then
        -- Retry a validated part of this map instead of waiting at a broken segment forever.
        Rail.home(app.rail)
        local saved=app.rail.anchor
        app.rail.path,app.rail.s,app.rail.direction=app.safeAnchor.path,app.safeAnchor.s,app.safeAnchor.direction
        local p,h=Roads.point(app.rail.path,app.rail.s)
        if app.rail.direction<0 then h+=math.pi end
        pose.point,pose.heading,pose.jumped=p,h,true
        surface,why=Surface.solve(p,h,pose.beta,wheelGeometry,app.safeAnchor.reference,query)
        if app.settings.style=="cool" then app.rail.speed=0;pose.speed=0 end
        app.rail.anchor=saved
    end
    if not surface then
        app.rail=oldPlan
        app.lastSurfaceError=why
        app.lease:release()
        root.AssemblyLinearVelocity=Vector3.zero
        app.status="Waiting for road at its known height: "..tostring(why)
        return
    end
    app.surfaceBlockedSince=nil
    app.surface=surface
    app.path,app.direction=app.rail.path,app.rail.direction
    if not app.safeAnchor then
        app.safeAnchor={path=app.path,s=app.rail.s,direction=app.direction,reference=surface.reference}
    end
    if app.loopAnchor.path==app.path and math.abs(app.loopAnchor.s-app.rail.s)<6 then
        app.loopAnchor.reference=surface.reference
    end
    local p=surface.position
    local targetPosition=Vector3.new(p.x,p.y,p.z)
    local r,n,f=surface.right,surface.up,surface.forward
    local targetCF=CFrame.fromMatrix(targetPosition,Vector3.new(r.x,r.y,r.z),Vector3.new(n.x,n.y,n.z),Vector3.new(-f.x,-f.y,-f.z))
    local gap=(root.Position-targetPosition).Magnitude
    if gap>10 or sample.upY<.55 or pose.jumped then app.recoveries=(app.recoveries or 0)+1 end
    local ok,err=app.lease:write({throttle=if pose.speed>2 then .6 else 0,brake=0,steer=0,handbrake=false})
    if not ok then app.stop(err);return end
    car:PivotTo(targetCF*root.CFrame:Inverse()*car:GetPivot())
    local v=surface.travel
    root.AssemblyLinearVelocity=Vector3.new(v.x,v.y,v.z)*pose.speed
    root.AssemblyAngularVelocity=Vector3.zero
    app.physicsWrites+=1;app.inputWrites+=1;app.frames+=1
    app.status=(if app.settings.style=="cool" then "Cool line: " elseif app.settings.farmTravel=="area" then "Farm area: " else "Farm loop: ")..app.path.name
    app.lastCommand={targetAngle=pose.targetAngle,targetKmh=pose.speed*1.2,override=true,reason=app.status,
        lateral=pose.lateral,contacts=surface.contacts,backwards=pose.backwards,loops=app.rail.loops,connections=app.rail.links}
    local command=app.lastCommand
    local guide=nil
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
print("[HowToDrift Assist 1.2.0] Farm/Cool autopilot armed. F6 Stop/Start; F7 Rejoin. Farm Loop / Area reverse; speed up to 500 km/h.")
