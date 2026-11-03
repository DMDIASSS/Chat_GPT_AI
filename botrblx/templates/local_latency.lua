-- Turbo Soccer already predicts server snapshots. Never add a full ping again.
local Latency={}
Latency.__index=Latency
local clamp,min,max=math.clamp,math.min,math.max
local function distance(a,b)return math.sqrt((a[1]-b[1])^2+(a[2]-b[2])^2+(a[3]-b[3])^2)end
function Latency.new(player)
    return setmetatable({player=player,enabled=true,pingAt=-math.huge,frame=1/120,input=0,
        rejected=0,horizon=0},Latency)
end
function Latency:sample(now,dt)
    if dt and dt>0 and dt<.25 then self.frame=self.frame*.9+dt*.1 end
    if now-self.pingAt<.5 then return end
    self.pingAt=now
    local ok,seconds=pcall(function()return self.player:GetNetworkPing()end)
    local source='GetNetworkPing'
    if not ok or type(seconds)~='number'or seconds~=seconds or seconds<0 or seconds>3 then
        ok,seconds=pcall(function()
            return game:GetService('Stats').Network.ServerStatsItem['Data Ping']:GetValue()/1000
        end)
        source='Stats Data Ping'
    end
    if ok and type(seconds)=='number'and seconds==seconds and seconds>=0 and seconds<=3 then
        self.jitter=self.ping and(self.jitter or 0)*.8+math.abs(seconds-self.ping)*.2 or 0
        self.ping=self.ping and self.ping*.8+seconds*.2 or seconds
        self.pingSource=source;self.pingSeen=now
    elseif self.pingSeen and now-self.pingSeen>3 then self.ping=nil;self.jitter=nil end
end
function Latency:budget()
    -- Preserve short frames; permit up to 3 ms on slower render loops.
    return clamp(self.frame*.18,.00075,.003)
end
function Latency:lead(packet,wall)
    if not self.enabled then self.horizon=0;return 0 end
    local cap=.16
    if(self.ping or 0)>.25 or(self.jitter or 0)>.04 then cap=.08 end
    local h=(wall or .035)+self.frame+clamp(packet.sample_dt or 0,0,.07)*.5+self.input
    self.horizon=clamp(h,0,cap)
    return self.horizon
end
local function advance(body,seconds,ground,gravity)
    local out=table.clone(body)
    out.position=table.clone(body.position);out.velocity=table.clone(body.velocity)
    out.forward=body.forward and table.clone(body.forward)or nil
    out.up=body.up and table.clone(body.up)or nil
    out.angular_velocity=table.clone(body.angular_velocity or {0,0,0})
    for i=1,3 do out.position[i]+=body.velocity[i]*seconds end
    if not ground then
        out.position[3]+=.5*gravity*seconds*seconds
        out.velocity[3]+=gravity*seconds
    end
    -- Small-angle orientation lead, renormalized to an orthogonal basis.
    if out.forward and out.up then
        local w=out.angular_velocity
        local function rotate(v)
            local a={v[1]+(w[2]*v[3]-w[3]*v[2])*seconds,
                v[2]+(w[3]*v[1]-w[1]*v[3])*seconds,v[3]+(w[1]*v[2]-w[2]*v[1])*seconds}
            local n=math.sqrt(a[1]^2+a[2]^2+a[3]^2)
            for i=1,3 do a[i]/=max(n,1e-9)end
            return a
        end
        out.forward=rotate(out.forward);out.up=rotate(out.up)
        local f,u=out.forward,out.up
        local dot=f[1]*u[1]+f[2]*u[2]+f[3]*u[3]
        for i=1,3 do u[i]-=dot*f[i]end
        local n=math.sqrt(u[1]^2+u[2]^2+u[3]^2)
        for i=1,3 do u[i]/=max(n,1e-9)end
    end
    return out
end
function Latency:project(packet,physics,wall,checkpoint)
    local h=self:lead(packet,wall)
    if h==0 then return packet end
    local out=table.clone(packet)
    local radius=packet.ball_radius or physics.profile.physics.BALL_RADIUS
    local future=physics:predict(packet.ball,radius,h,1000,checkpoint)
    local last=future[#future]
    out.ball=table.clone(packet.ball);out.ball.position=last.position;out.ball.velocity=last.velocity
    out.car=advance(packet.car,h,packet.ground_estimate,physics.gravity)
    out.other_cars={}
    for _,car in ipairs(packet.other_cars or {})do
        out.other_cars[#out.other_cars+1]=advance(car,h,car.ground_estimate,physics.gravity)
    end
    return out
end
function Latency:fresh(job,packet,now,epoch)
    local m=job.metadata
    local age=now-m.at
    local limit=((self.jitter or 0)>.04 or(self.ping or 0)>.25)and .22 or .35
    local valid=m.epoch==epoch and m.team==packet.team and m.scene==packet.scene_token
        and age>=0 and age<=limit and m.ground==packet.ground_estimate
    -- Account for travel since the predicted target time before checking a correction.
    local dt=clamp(now-m.targetAt,-.2,.2)
    local function expected(body)
        return {body.position[1]+body.velocity[1]*dt,body.position[2]+body.velocity[2]*dt,body.position[3]+body.velocity[3]*dt}
    end
    valid=valid and distance(expected(m.car),packet.car.position)<260
        and distance(expected(m.ball),packet.ball.position)<350
    if not valid then self.rejected+=1 end
    return valid
end
function Latency:report()
    return {enabled=self.enabled,ping_ms=self.ping and self.ping*1000 or nil,ping_source=self.pingSource,
        jitter_ms=self.jitter and self.jitter*1000 or nil,frame_ms=self.frame*1000,
        lookahead_ms=self.horizon*1000,rejected_actions=self.rejected,
        network_lead_ms=0,reason='Game state is already client-predicted; lead only measured AI, sampling and input delay'}
end
return Latency
