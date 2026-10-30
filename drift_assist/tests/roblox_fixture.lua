-- Minimal Roblox doubles for standalone lifecycle tests and optional planar source checks.
local now, env, created, warnings, savedFiles = 0, {}, {}, {}, {}
local function event()
    local e={listeners={}}
    function e:Connect(fn)
        local c={active=true};function c:Disconnect() self.active=false end
        table.insert(self.listeners,{c,fn});return c
    end
    function e:Fire(...)
        for _,r in ipairs(table.clone(self.listeners)) do if r[1].active then r[2](...) end end
    end
    return e
end
local vectorMT={}
local Vector3,Vector2={},{ }
function Vector3.new(x,y,z) return setmetatable({X=x or 0,Y=y or 0,Z=z or 0},vectorMT) end
function Vector2.new(x,y) return Vector3.new(x,y,0) end
function vectorMT.__add(a,b) return Vector3.new(a.X+b.X,a.Y+b.Y,a.Z+b.Z) end
function vectorMT.__sub(a,b) return Vector3.new(a.X-b.X,a.Y-b.Y,a.Z-b.Z) end
function vectorMT.__unm(a) return Vector3.new(-a.X,-a.Y,-a.Z) end
function vectorMT.__mul(a,b)
    if type(a)=="number" then return Vector3.new(a*b.X,a*b.Y,a*b.Z) end
    if type(b)=="number" then return Vector3.new(a.X*b,a.Y*b,a.Z*b) end
    return Vector3.new(a.X*b.X,a.Y*b.Y,a.Z*b.Z)
end
function vectorMT.__div(a,b) return Vector3.new(a.X/b,a.Y/b,a.Z/b) end
function vectorMT:Dot(b) return self.X*b.X+self.Y*b.Y+self.Z*b.Z end
function vectorMT:Cross(b) return Vector3.new(self.Y*b.Z-self.Z*b.Y,self.Z*b.X-self.X*b.Z,self.X*b.Y-self.Y*b.X) end
function vectorMT:Lerp(b,t) return self+(b-self)*t end
function vectorMT.__index(v,k)
    if k=="Magnitude" then return math.sqrt(v.X*v.X+v.Y*v.Y+v.Z*v.Z) end
    if k=="Unit" then return v/math.max(v.Magnitude,1e-12) end
    return vectorMT[k]
end
Vector3.zero=Vector3.new();Vector2.zero=Vector2.new()
local function enumGroup()
    return setmetatable({},{__index=function(t,k) local v={Name=k,Value=k};rawset(t,k,v);return v end})
end
local Enum=setmetatable({},{__index=function(t,k) local v=enumGroup();rawset(t,k,v);return v end})
local function dimension(s,o) return {Scale=s or 0,Offset=o or 0} end
local UDim={new=dimension}
local UDim2={new=function(xs,xo,ys,yo) return {X=dimension(xs,xo),Y=dimension(ys,yo)} end}
function UDim2.fromOffset(x,y) return UDim2.new(0,x,0,y) end
function UDim2.fromScale(x,y) return UDim2.new(x,0,y,0) end
local Color3={fromRGB=function(...) return {...} end,fromHSV=function(...) return {...} end,new=function(...) return {...} end}
local RaycastParams={new=function() return {} end}
local function cf(yaw,position)
    local value={__cframe=true,yaw=yaw,LookVector=Vector3.new(-math.sin(yaw),0,-math.cos(yaw)),RightVector=Vector3.new(math.cos(yaw),0,-math.sin(yaw)),
        UpVector=Vector3.new(0,1,0),Position=position or Vector3.zero}
    function value:Inverse() return {inverse=true,original=self} end
    return setmetatable(value,{__mul=function(a,b)
        if b.inverse then return setmetatable({target=a},{__mul=function(transform,_) return transform.target end}) end
        error('Unexpected CFrame fixture multiplication')
    end})
end
local nativeTypeof=typeof
local function typeof(value) return if type(value)=="table" and value.__cframe then "CFrame" else nativeTypeof(value) end
local CFrame={lookAt=function(p,target) local d=target-p;return cf(math.atan2(-d.X,-d.Z),p) end}
function CFrame.fromMatrix(position,right,up,back)
    local value=cf(math.atan2(back.X,back.Z),position)
    value.RightVector,value.UpVector,value.LookVector=right,up,-back
    return value
end
local methods={}
local function object(class,parent,name)
    local p={ClassName=class,Name=name or class,Parent=parent,attrs={},events={},children={},
        AbsolutePosition=Vector2.new(0,0),AbsoluteSize=Vector2.new(300,7)}
    local obj
    obj=setmetatable({props=p},{__index=function(_,k)
        if methods[k] then return methods[k] end
        if k=="Activated" or k=="AncestryChanged" or k=="InputBegan" or k=="InputEnded" or k=="FocusLost" then
            p.events[k]=p.events[k] or event();return p.events[k]
        end
        if k=="WorldPosition" and p.localPosition and p.Parent then
            local r=p.Parent;local o=p.localPosition
            return r.Position+r.CFrame.RightVector*o.X+r.CFrame.UpVector*o.Y-r.CFrame.LookVector*o.Z
        end
        if k=="Position" and p.ClassName=="Attachment" then return p.localPosition end
        return p[k]
    end,__newindex=function(_,k,v)
        local previous=p[k];p[k]=v
        if k=="Parent" and previous~=v then
            if v then table.insert(v.props.children,obj) end
            if p.events.AncestryChanged then p.events.AncestryChanged:Fire(obj,v) end
        end
        if p.events[k] then p.events[k]:Fire() end
    end})
    if parent then table.insert(parent.props.children,obj) end
    table.insert(created,obj)
    return obj
end
function methods:GetChildren()
    local children={}
    for _,c in ipairs(self.children) do if c.Parent==self then table.insert(children,c) end end
    return children
end
function methods:FindFirstChild(name)
    for _,c in ipairs(self:GetChildren()) do if c.Name==name then return c end end
    return nil
end
function methods:FindFirstChildOfClass(name)
    for _,c in ipairs(self:GetChildren()) do if c:IsA(name) then return c end end
    return nil
end
function methods:WaitForChild(name) return self:FindFirstChild(name) end
function methods:IsA(name) return self.ClassName==name or (name=="BasePart" and (self.ClassName=="Part" or self.ClassName=="Seat")) end
function methods:IsDescendantOf(parent)
    local p=self.Parent
    while p do if p==parent then return true end;p=p.Parent end
    return false
end
function methods:GetAttribute(k) return self.attrs[k] end
function methods:IsFocused() return self.focused==true end
function methods:SetAttribute(k,v) self.attrs[k]=v end
function methods:GetPropertyChangedSignal(k) self.events[k]=self.events[k] or event();return self.events[k] end
function methods:Destroy()
    if self.destroyed then return end
    self.destroyed=true
    for _,c in ipairs(self:GetChildren()) do c:Destroy() end
    self.Parent=nil
end
function methods:ApplyImpulse(v) self.AssemblyLinearVelocity+=v/self.AssemblyMass end
function methods:ApplyAngularImpulse(v) self.AssemblyAngularVelocity+=v/(self.inertia or self.AssemblyMass) end
function methods:ApplyImpulseAtPosition(v,position)
    self:ApplyImpulse(v)
    local angular=(position-self.Position):Cross(v)/(self.inertia or self.AssemblyMass)
    self.AssemblyAngularVelocity+=Vector3.new(0,angular.Y,0)
end
function methods:GetVelocityAtPosition(position) return self.AssemblyLinearVelocity+self.AssemblyAngularVelocity:Cross(position-self.Position) end
function methods:GetPivot() return self.PrimaryPart.CFrame end
function methods:PivotTo(cframe)
    self.PrimaryPart.CFrame=cframe;self.PrimaryPart.Position=cframe.Position
    self.PrimaryPart.pivots=(self.PrimaryPart.pivots or 0)+1
end
local Instance={new=object}
local services={Players={LocalPlayer=object("Player")},Workspace=object("Workspace"),ReplicatedStorage=object("ReplicatedStorage"),
    RunService={PreSimulation=event()},GuiService={MenuIsOpen=false},HttpService={}}
local input={InputBegan=event(),InputChanged=event(),InputEnded=event(),WindowFocused=event(),WindowFocusReleased=event(),
    held={},GamepadEnabled=false}
services.UserInputService=input
function input:IsKeyDown(key) return self.held[key.Name] or false end
function input:GetFocusedTextBox() return self.focus end
function input:GetGamepadState() return {} end
local player=services.Players.LocalPlayer
player.UserId=12345
player.CharacterRemoving=event()
local playerGui=object("PlayerGui",player)
local character=object("Model",nil,"Character")
player.Character=character
local humanoid=object("Humanoid",character)
local World=services.Workspace
World.Gravity=196.2
World.CurrentCamera={ViewportSize=Vector2.new(1920,1080)}
function World:GetServerTimeNow() return now+(self.clockOffset or 0) end
local floorPart=object("Part",World,"RoadSurface")
function World:Raycast(origin,direction,_params)
    if self.raycastOverride then return self.raycastOverride(origin,direction,_params) end
    if direction.Y>=0 then return nil end
    local t=-origin.Y/direction.Y
    if t<0 or t>1 then return nil end
    return {Position=origin+direction*t,Normal=Vector3.new(0,1,0),Distance=direction.Magnitude*t,
        Material=Enum.Material.Asphalt,Instance=floorPart}
end
function services.Players:GetPlayers() return {player} end
function services.HttpService:JSONEncode(value)
    self.lastEncoded=value
    local function inspect(v)
        if type(v)=="number" then assert(v==v and math.abs(v)<math.huge,"Invalid JSON number")
        elseif type(v)=="table" then for _,x in pairs(v) do inspect(x) end
        else assert(type(v)=="string" or type(v)=="boolean" or v==nil,"Non-JSON telemetry") end
    end
    inspect(value)
    return "{\"fixture\":true}"
end
local game={PlaceId=91374382281493,GetService=function(_,name) return assert(services[name],name) end}
local workspace=World
local originalOs=os
local os={clock=function() return now end,time=function() return 1793318400 end}
local getgenv=function() return env end
local warn=function(message) table.insert(warnings,message) end
local writefile=function(name,body) savedFiles[name]=body end
local function step(dt)
    now+=dt or 1/60
    services.RunService.PreSimulation:Fire(dt or 1/60)
end
local function findCreated(name)
    for i=#created,1,-1 do if created[i].Name==name and not created[i].destroyed then return created[i] end end
end
local function spawnCar(options)
    options=options or {}
    local cars=World:FindFirstChild("Cars") or object("Folder",World,"Cars")
    local car=object("Model",cars,"FixtureCar")
    car:SetAttribute("OwnerUserId",options.owner or player.UserId)
    car:SetAttribute("NetOwner",options.netOwner or player.UserId)
    car:SetAttribute("CarId","S13")
    local chassis=object("Part",car,"Chassis")
    chassis.Position=Vector3.new(0,2,0);chassis.CFrame=cf(0,chassis.Position)
    chassis.Size=Vector3.new(4.5,1,6.64)
    chassis.AssemblyMass=1000;chassis.AssemblyLinearVelocity=Vector3.new(0,0,-30);chassis.AssemblyAngularVelocity=Vector3.zero
    chassis.inertia=chassis.AssemblyMass*(chassis.Size.X^2+chassis.Size.Z^2)/12
    chassis.Anchored=false;car.PrimaryPart=chassis
    local seat=object("Seat",car,"DriverSeat")
    for _,name in ipairs({"FL","FR","RL","RR"}) do
        local attachment=object("Attachment",chassis,name)
        attachment.localPosition=Vector3.new(if name:sub(2,2)=="L" then -2.25 else 2.25,-0.3,if name:sub(1,1)=="F" then -3.32 else 3.32)
    end
    for _,name in ipairs({"AntiGravity","SpringFL","SpringFR","SpringRL","SpringRR"}) do object("VectorForce",chassis,name) end
    if options.seated~=false then humanoid.SeatPart=seat end
    return car,chassis,seat
end
