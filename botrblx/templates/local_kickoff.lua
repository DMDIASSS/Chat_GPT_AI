-- Bounded standard-stadium kickoff. No game modules or authoritative remotes.
local Kickoff={}
Kickoff.__index=Kickoff
local spawns={{-2048,-2560},{2048,-2560},{-256,-3840},{256,-3840},{0,-4608}}
local function speed(v)return math.sqrt(v[1]^2+v[2]^2+v[3]^2)end
local function length2(v)return math.sqrt(v[1]^2+v[2]^2)end
local function heading(car,delta)
    local f,u=car.forward,car.up
    local right={u[2]*f[3]-u[3]*f[2],u[3]*f[1]-u[1]*f[3],u[1]*f[2]-u[2]*f[1]}
    return math.atan2(delta[1]*right[1]+delta[2]*right[2],delta[1]*f[1]+delta[2]*f[2])
end
function Kickoff.new(profile)return setmetatable({profile=profile},Kickoff)end
function Kickoff:reset()
    self.state,self.stableAt,self.phase,self.moveAt,self.armedAt,self.latched,self.flipped=nil,nil,nil,nil,nil,nil,nil
end
function Kickoff:countdown(pg)
    local hud=pg:FindFirstChild("CarSoccerMatchHud")
    local call=hud and hud:FindFirstChild("Call",true)
    if not call or hud.Enabled==false then return false end
    local ancestor=call
    while ancestor and ancestor~=hud do
        if ancestor.Visible==false then return false end
        ancestor=ancestor.Parent
    end
    for _,label in ipairs(call:GetDescendants())do
        if label:IsA("TextLabel")and label.Visible~=false then
            local n=tonumber(label.Text)
            if n and n>=1 and n<=10 then return true end
        end
    end
    return false
end
function Kickoff:step(packet,now,pg)
    local car,ball=packet.car,packet.ball
    local p,b=car.position,ball.position
    local rest=self.profile.physics.BALL_REST_Z*(packet.ball_radius or self.profile.physics.BALL_RADIUS)/self.profile.physics.BALL_RADIUS
    local centered=length2(b)<25 and math.abs(b[3]-rest)<20 and speed(ball.velocity)<45
    if self.latched then
        if not centered then self.latched=false;self.stableAt=nil end
        return nil
    end
    if not self.state then
        local spawn=false
        local sign=packet.team==0 and 1 or -1
        for _,s in ipairs(spawns)do
            if (p[1]-sign*s[1])^2+(p[2]-sign*s[2])^2<100^2 then spawn=true;break end
        end
        local eligible=centered and spawn and packet.ground_estimate and math.abs(p[3]-17)<70 and car.up[3]>.65 and speed(car.velocity)<80
            and math.abs(heading(car,{-p[1],-p[2]}))<.35
        if not eligible then self.stableAt=nil;return nil end
        self.stableAt=self.stableAt or now
        if now-self.stableAt<.15 then return {0,0,0,0,0,0,0,0},"kickoff: detecting"end
        -- Respect a closer teammate and standard left-goes tie priority.
        for _,other in ipairs(packet.other_cars or {})do
            if other.team==packet.team then
                local d,own=length2(other.position),length2(p)
                if d<own-150 or(math.abs(d-own)<150 and other.position[1]*sign>p[1]*sign+100)then
                    self.latched=true;return nil
                end
            end
        end
        self.state="drive";self.armedAt=now;self.flipped=false;self.moveAt=nil
    end
    local dx,dy=b[1]-p[1],b[2]-p[2]
    local distance=math.sqrt(dx*dx+dy*dy)
    if not centered or distance<220 or now-self.armedAt>12 or(self.moveAt and now-self.moveAt>4.5)then
        self.state=nil;self.stableAt=nil;self.latched=true;return nil
    end
    if not self.moveAt and speed(car.velocity)>100 then self.moveAt=now end
    -- Dedicated countdown is only trusted after strict ball/spawn detection.
    if not self.moveAt and pg and self:countdown(pg)then
        return {0,0,0,0,0,0,0,0},"kickoff: countdown"
    end
    local error=heading(car,{dx,dy})
    local steer=error>.07 and 1 or(error<-.07 and -1 or 0)
    local action={1,steer,-1,steer,0,0,math.abs(error)<.45 and packet.boost>0 and 1 or 0,0}
    if self.state=="drive"and not self.flipped and self.moveAt and packet.ground_estimate
        and speed(car.velocity)>1050 and distance>1150 and distance<2650 and math.abs(error)<.12 then
        self.state="jump";self.phase=now;self.flipped=true
    end
    if self.state=="jump"then
        if now-self.phase>=.10 then self.state="release";self.phase=now
        else action[6]=1 end
    elseif self.state=="release"then
        if now-self.phase>=.10 then self.state="flip";self.phase=now;action[6]=1 end
    elseif self.state=="flip"then
        if now-self.phase>=.12 then self.state="recover";self.phase=now
        else action[6]=1 end
    elseif self.state=="recover"then
        -- Stop pitching after the dodge pulse; return to steering once grounded.
        action[3]=0;action[4]=0
        if now-self.phase>=.28 then self.state="drive"end
    end
    if self.state=="flip"or self.state=="jump"or self.state=="release"then
        action[2]=0;action[4]=0
    end
    if self.state=="recover"then action[3]=0;action[4]=0 end
    return action,"kickoff: "..self.state
end
return Kickoff
