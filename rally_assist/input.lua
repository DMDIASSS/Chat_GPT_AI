-- Prefer the existing client's analog input table. Ordinary require may be
-- unavailable in an executor, so a verified keyboard backend is also supported.
local Input={}
Input.__index=Input
local codes={W=Enum.KeyCode.W,A=Enum.KeyCode.A,S=Enum.KeyCode.S,D=Enum.KeyCode.D,SPACE=Enum.KeyCode.Space}
local order={"W","A","S","D","SPACE"}
local vk={W=0x57,A=0x41,S=0x53,D=0x44,SPACE=0x20}
local scan={W=0x11,A=0x1E,S=0x1F,D=0x20,SPACE=0x39}
function Input.new(service)
    return setmetatable({service=service,held={},heldAt={},owned={},name="waiting",steerAccumulator=0,pedals={W=0,S=0}},Input)
end
function Input:attach(module)
    if type(module)~="table"or type(module.Read)~="function"then return false end
    local original=module.Read
    local wrapper=function(...)
        local manual=original(...)
        self.lastRead=os.clock();self.reads=(self.reads or 0)+1
        self.manual=manual
        if not self.claimed then return manual end
        local command=self.command
        if not command or os.clock()-self.commandAt>.2 then
            return {Throttle=0,Brake=1,Steer=0,Handbrake=false,Analog=true,Manual=false}
        end
        return {Throttle=command.Throttle,Brake=command.Brake,Steer=command.Steer,
            Handbrake=command.Handbrake==true,Analog=true,Manual=false,ShiftUp=false,ShiftDown=false,Hold=false}
    end
    local ok=pcall(function()module.Read=wrapper end)
    if ok and module.Read==wrapper then
        self:releaseKeys()
        self.module,self.original,self.wrapper=module,original,wrapper;self.name="analog";return true
    end
    return false
end
function Input:releaseKeys()
    for _,entry in ipairs(self.owned)do
        for key in pairs(entry.keys)do if pcall(entry.backend.send,key,false)then entry.keys[key]=nil end end
    end
    self.held={};self.heldAt={};self.steerAccumulator=0;self.pedals={W=0,S=0};self.keySteer=0;self.steerAt=nil
    self.steerError=0;self.steerDt=nil;self.lastSign=nil
end
function Input:estimateSteer()
    local now=os.clock();local dt=self.steerAt and math.clamp(now-self.steerAt,0,.15)or 0;self.steerAt=now
    if dt>.001 then self.steerDt=dt end
    local target=(self.held.D and 1 or 0)-(self.held.A and 1 or 0)
    local value=self.keySteer or 0
    local rate=(target==0 or math.sign(target)~=math.sign(value))and(self.returnRate or 6.5)or(self.steerRate or 4.2)
    self.keySteer=value+math.clamp(target-value,-rate*dt,rate*dt)
    return self.keySteer
end
function Input:release()
    self.epoch=(self.epoch or 0)+1
    self.claimed=false;self.command=nil;self:releaseKeys()
end
function Input:destroy()
    self:release()
    if self.module and self.module.Read==self.wrapper then self.module.Read=self.original end
    self.module=nil;self.wrapper=nil
end
function Input:manualState()
    if self.manual and self.module and self.module.Read==self.wrapper then return self.manual end
    local down=function(key)return self.service:IsKeyDown(codes[key])end
    return {Throttle=down("W")and 1 or 0,Brake=down("S")and 1 or 0,
        Steer=(down("D")and 1 or 0)-(down("A")and 1 or 0),Handbrake=down("SPACE")}
end
function Input:probe(cancelled,progress)
    if self.module and self.module.Read==self.wrapper then
        if not self.lastRead then task.wait(.2)end
        if cancelled()then return false,"Input test cancelled"end
        if self.lastRead and os.clock()-self.lastRead<.3 then return true end
        self:destroy();self.name="waiting"
    end
    self:releaseKeys();self.backend=nil
    local candidates={}
    local ok,manager=pcall(function()return game:GetService("VirtualInputManager")end)
    if ok and manager then candidates[#candidates+1]={name="Roblox keys",send=function(key,pressed)
        manager:SendKeyEvent(pressed,codes[key],false,game)
    end}end
    if type(keypress)=="function"and type(keyrelease)=="function"then
        for _,spec in ipairs({{name="executor VK",mapping=vk},{name="executor scan",mapping=scan}})do
            candidates[#candidates+1]={name=spec.name,send=function(key,pressed)
                (pressed and keypress or keyrelease)(spec.mapping[key])
            end}
        end
    end
    for _,key in ipairs(order)do
        if self.service:IsKeyDown(codes[key])then return false,"Release movement keys before starting autodrive"end
    end
    for _,backend in ipairs(candidates)do
        local entry={backend=backend,keys={}};self.owned[#self.owned+1]=entry
        local passed=true
        progress("Checking "..backend.name)
        for _,key in ipairs(order)do
            if cancelled()then self:releaseKeys();return false,"Input test cancelled"end
            entry.keys[key]=true
            local sent=pcall(backend.send,key,true)
            task.wait(.04)
            local observed=sent and self.service:IsKeyDown(codes[key])
            local released=pcall(backend.send,key,false)
            task.wait(.04)
            if released then entry.keys[key]=nil end
            if cancelled()then self:releaseKeys();return false,"Input test cancelled"end
            if not observed or not released or self.service:IsKeyDown(codes[key])then passed=false;break end
        end
        self:releaseKeys()
        if passed then self.backend=backend;self.backendEntry=entry;self.name=backend.name;return true end
    end
    return false,"No input method reached Roblox; assists remain available in manual mode"
end
function Input:write(command)
    local epoch=self.epoch or 0
    self.command=command;self.commandAt=os.clock()
    if self.module and self.module.Read==self.wrapper then
        if not self.lastRead or os.clock()-self.lastRead>.3 then return false,"Analog input stopped updating; restart autodrive"end
        self.claimed=true;return true
    end
    if not self.backend then return false,"Keyboard needs verification"end
    for key,since in pairs(self.heldAt)do
        if os.clock()-since>.25 and not self.service:IsKeyDown(codes[key])then
            self.backend=nil;self.name="needs input test"
            return false,"Input stopped reaching Roblox: "..key.."; restart autodrive"
        end
    end
    local wanted={}
    for key,value in pairs({W=command.Throttle,S=command.Brake})do
        if value<=0 then self.pedals[key]=0;wanted[key]=false else
            self.pedals[key]=self.pedals[key]+math.clamp(value,0,1)
            wanted[key]=self.pedals[key]>=1
            if wanted[key]then self.pedals[key]=self.pedals[key]-1 end
        end
    end
    -- Match the game's digital rise/return ramps. A naive duty cycle cancels
    -- small steering inputs because returning to center is faster than turning.
    local value=math.clamp(command.Steer,-1,1)
    local estimate=self:estimateSteer()
    local dt=math.clamp(self.steerDt or 1/60,1/240,.1)
    if self.lastSign~=math.sign(value)then self.steerError=0 end;self.lastSign=math.sign(value)
    self.steerError=math.clamp((self.steerError or 0)+(value-estimate)*dt,-.04,.04)
    local function errorAfter(target)
        local rate=(target==0 or math.sign(target)~=math.sign(estimate))and(self.returnRate or 6.5)or(self.steerRate or 4.2)
        local nextValue=estimate+math.clamp(target-estimate,-rate*dt,rate*dt)
        return math.abs(self.steerError+(value-nextValue)*dt)
    end
    local releaseError=errorAfter(0)
    wanted.A=value<-.001 and errorAfter(-1)<releaseError
    wanted.D=value>.001 and errorAfter(1)<releaseError
    wanted.SPACE=command.Handbrake==true
    for _,key in ipairs(order)do
        if self.held[key]and not wanted[key]then
            self.backend.send(key,false);self.held[key]=nil;self.heldAt[key]=nil;self.backendEntry.keys[key]=nil
        end
    end
    for _,key in ipairs(order)do
        if wanted[key]and not self.held[key]then
            self.held[key]=true;self.heldAt[key]=os.clock();self.backendEntry.keys[key]=true;self.backend.send(key,true)
            if epoch~=(self.epoch or 0)then
                self.backendEntry.keys[key]=true;self:releaseKeys();return false,"Autodrive stopped"
            end
        end
    end
    return true
end
return Input
