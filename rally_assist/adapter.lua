-- Backseat Rally's seated driver/Body/Chassis contract, read from rendered state.
local Adapter={}
Adapter.__index=Adapter
local function child(root,...)
    for _,name in ipairs({...})do root=root and root:FindFirstChild(name)end
    return root
end
local function clone(t)
    if type(t)~="table"then return t end
    local out={};for k,v in pairs(t)do out[k]=type(v)=="table"and clone(v)or v end;return out
end
function Adapter.new(player,world,replicated,input)
    return setmetatable({player=player,world=world,replicated=replicated,input=input,
        lastProbe=-math.huge,groundParams=RaycastParams.new()},Adapter)
end
function Adapter:connectNative(now)
    if self.controller or now-self.lastProbe<5 then return end;self.lastProbe=now
    local playerScripts=self.player:FindFirstChild("PlayerScripts")
    local folder=child(playerScripts,"Client","Init","Car")
    if not folder then return end
    local controllerModule=folder:FindFirstChild("CarController")
    local inputModule=folder:FindFirstChild("CarInput")
    if controllerModule then
        local ok,value=pcall(require,controllerModule)
        if ok and type(value)=="table"and type(value.GetChassis)=="function"then self.controller=value end
    end
    if inputModule and not self.input.module then
        local ok,value=pcall(require,inputModule)
        if ok then self.input:attach(value)end
    end
    local core=child(self.replicated,"Shared","Core")
    for name,field in pairs({Route="nativeRoute",SpeedPlan="nativePlan"})do
        local module=core and core:FindFirstChild(name)
        if module then local ok,value=pcall(require,module);if ok and type(value)=="table"then self[field]=value end end
    end
end
function Adapter:find()
    local character=self.player.Character
    local humanoid=character and character:FindFirstChildOfClass("Humanoid")
    local seat=humanoid and humanoid.SeatPart
    if not seat or seat.Name~="Driver"or not seat.Parent or seat.Parent.Name~="Seats"then
        return nil,"Sit in the DRIVER seat"
    end
    local car=seat.Parent.Parent
    if not car or not car:IsA("Model")or not car.PrimaryPart then return nil,"Waiting for car Body"end
    local driver=car:GetAttribute("DriverUserId")
    if driver and driver~=0 and driver~=self.player.UserId then return nil,"Waiting for driver ownership"end
    self.car,self.root=car,car.PrimaryPart
    return car
end
function Adapter:restore()
    if self.chassis and self.chassis.Tune==self.applied then self.chassis.Tune=self.baseline end
    self.chassis,self.applied,self.baseline,self.signature=nil,nil,nil,nil
end
function Adapter:automatic(enabled)
    if enabled then
        if not self.gearLease then
            self.gearBase=self.player:GetAttribute("ManualGears");self.gearLease=true
            self.player:SetAttribute("ManualGears",false)
        end
    elseif self.gearLease then
        if self.player:GetAttribute("ManualGears")==false then self.player:SetAttribute("ManualGears",self.gearBase)end
        self.gearLease=false
    end
end
function Adapter:tune(cfg,enabled)
    self.cfg=cfg
    local chassis
    if self.controller then
        local ok,value=pcall(self.controller.GetChassis)
        if ok and value and value.Body==self.root then chassis=value end
    end
    if not enabled or not chassis then self:restore();return false end
    if chassis~=self.chassis then self:restore();self.chassis=chassis;self.baseline=chassis.Tune end
    if chassis.Tune~=self.applied and chassis.Tune~=self.baseline then self.baseline=chassis.Tune;self.signature=nil end
    local signature=string.format("%.3f/%.3f/%.3f",cfg.speed,cfg.turn,cfg.grip)
    if self.signature==signature and chassis.Tune==self.applied then return true end
    local base=self.baseline
    if type(base)~="table"or type(base.Engine)~="table"or type(base.Steering)~="table"or type(base.Tyres)~="table"then return false end
    local tune=clone(base)
    tune.Engine.Force=base.Engine.Force*cfg.speed^1.5
    if tune.Gears and tune.Gears.Ratios then
        for i,v in ipairs(base.Gears.Ratios)do tune.Gears.Ratios[i]=v/math.sqrt(cfg.speed)end
    end
    tune.Tyres.LateralGrip=base.Tyres.LateralGrip*cfg.grip
    tune.Tyres.LongitudinalGrip=base.Tyres.LongitudinalGrip*math.sqrt(cfg.grip)
    tune.Steering.Rate=(base.Steering.Rate or 4)*cfg.turn
    tune.Steering.ReturnRate=(base.Steering.ReturnRate or 6)*math.sqrt(cfg.turn)
    tune.Steering.MaxAngle=math.min(48,(base.Steering.MaxAngle or 34)*math.sqrt(cfg.turn))
    self.applied=tune;self.signature=signature;chassis.Tune=tune
    return true
end
function Adapter:measure()
    local root,car=self.root,self.car
    local cf,p,v,w=root.CFrame,root.Position,root.AssemblyLinearVelocity,root.AssemblyAngularVelocity
    local wheels={};local grounded=0;local wheelbase,halfWidth=7.5,2.5
    local native=self.chassis and self.chassis.Body==root and self.chassis or nil
    local cfg=native and native.Tune
    if native and native.State then grounded=native.State.Grounded or 0 end
    local params=self.groundParams
    params.FilterType=Enum.RaycastFilterType.Exclude
    params.FilterDescendantsInstances={car,self.player.Character}
    params.IgnoreWater=true;params.RespectCanCollide=true
    for _,name in ipairs({"FL","FR","RL","RR"})do
        local mount=root:FindFirstChild("Wheel"..name)
        if mount and mount:IsA("Attachment")then
            wheels[name]=mount.Position
            halfWidth=math.max(halfWidth,math.abs(mount.Position.X))
            if not native then
                local hit=self.world:Raycast(mount.WorldPosition,Vector3.new(0,-3.3,0),params)
                if hit and hit.Normal.Y>.3 then grounded=grounded+1 end
            end
        end
    end
    if wheels.FL and wheels.RL then wheelbase=math.abs(wheels.FL.Z-wheels.RL.Z)end
    local gravity=cfg and cfg.Gravity or 75
    local grip=cfg and cfg.Tyres and cfg.Tyres.LateralGrip*gravity or 42
    local surface=native and native.State and native.State.Surface
    local material=cfg and cfg.Surfaces and cfg.Surfaces[surface]
    if material then grip=grip*(material.Lateral or 1)end
    local wetness=native and native.State and native.State.Wetness or 0
    if cfg and cfg.WetGrip then
        grip=grip*(1+((cfg.WetGrip[surface]or cfg.WetGrip.Default or 1)-1)*wetness)
    end
    local stage=car:GetAttribute("StageId")or self.world:GetAttribute("StageHere")or "PineForest"
    if stage~=self.nativeStage then self.nativeHint=nil;self.nativeStage=stage end
    local preview
    if native and self.nativeRoute and self.nativePlan and self.cfg then
        local ok,value=pcall(function()
            local route=self.nativeRoute.Get(stage)
            local index,s=route:Nearest(p,self.nativeHint,30,60);self.nativeHint=index
            return self.nativePlan.Target(route,s,native,{MaxSpeed=self.cfg.maxKmh/1.008,
                GripUse=.8,Braking=math.min(26,(cfg.Brakes and cfg.Brakes.Force or 26)*.82),PlanAhead=300},true)
        end)
        if ok and type(value)=="number"and value==value and value>=0 and value<1000 then preview=value end
    end
    return {x=p.X,y=p.Y,z=p.Z,vx=v.X,vz=v.Z,vy=v.Y,fx=cf.LookVector.X,fz=cf.LookVector.Z,
        yawRate=-w.Y,upY=cf.UpVector.Y,grounded=grounded,wheelbase=wheelbase,halfWidth=halfWidth,
        maxAngle=native and native.MaxAngleNow or(cfg and cfg.Steering and cfg.Steering.MaxAngle or 28),
        grip=grip,braking=cfg and cfg.Brakes and cfg.Brakes.Force or 26,
        runState=car:GetAttribute("RunState")or "Idle",stage=stage,nativePreview=preview,
        carId=car:GetAttribute("CarId")or "Hatch",surface=surface or "Gravel"}
end
function Adapter:obstacle(state)
    local root=self.root
    local distance=math.clamp(math.sqrt(state.vx^2+state.vz^2)*.6+10,10,70)
    local direction=Vector3.new(state.fx,0,state.fz)*distance
    local hit=self.world:Raycast(root.Position+Vector3.new(0,.6,0),direction,self.groundParams)
    if hit and hit.Normal.Y<.65 then return hit.Distance end
end
function Adapter:boost(state,cfg,command,dt)
    if self.applied or state.grounded<3 or state.upY<.65 or self.root.Anchored then return end
    local root=self.root
    local mass=root.AssemblyMass
    if mass<=0 or mass>=1e7 then return end
    local cf=root.CFrame;local v=root.AssemblyLinearVelocity
    local forward=v:Dot(cf.LookVector);local side=v:Dot(cf.RightVector)
    local throttle=command.Throttle or 0;local steer=command.Steer or 0
    local acceleration=math.max(0,cfg.speed-1)*24*throttle
    if forward>cfg.maxKmh/1.008 or(command.Brake or 0)>.1 then acceleration=0 end
    local damping=math.clamp(-side*(cfg.grip-1)*1.8,-45,45)
    local force=(cf.LookVector*acceleration+cf.RightVector*damping)*mass*dt
    root:ApplyImpulse(force)
    if cfg.turn>1 and math.abs(steer)>.02 and math.abs(forward)>3 then
        local extra=-steer*math.min(math.abs(forward)/12,5)*(cfg.turn-1)
        local inertia=mass*(state.wheelbase^2+(state.halfWidth*2)^2)/12
        root:ApplyAngularImpulse(Vector3.new(0,extra*inertia*dt,0))
    end
end
function Adapter:destroy()self:restore();self:automatic(false)end
return Adapter
