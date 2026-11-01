-- Receding-horizon corridor search, with steering lag, slip and braking limits.
local Driver={}
local abs,min,max,sqrt=math.abs,math.min,math.max,math.sqrt
function Driver.wrap(a)return (a+math.pi)%(2*math.pi)-math.pi end
function Driver.new()return {steer=0,throttle=0,brake=0,model={accel=42,braking=26,yawGain=1},stuck=0}end
local function approach(a,b,rate,dt)return a+math.clamp(b-a,-rate*dt,rate*dt)end
function Driver.width(stage,s)
    local width=stage.Width or 18
    for _,f in ipairs(stage.features or {})do
        if(f.Kind=='Bridge'or f.Kind=='Narrow')and f.From and f.To and f.Width and s>=f.From-5 and s<=f.To+5 then width=min(width,f.Width)end
    end
    return width
end
function Driver.envelope(state,tangent,margin)
    local f=state.fx*tangent.fx+state.fz*tangent.fz
    local side=state.fx*(-tangent.fz)+state.fz*tangent.fx
    return abs(f)*(state.halfWidth or 2.5)+abs(side)*(state.halfLength or(state.wheelbase or 7.5)/2+1)+(margin or 1.2)
end
local function traction(state)
    local roll=(state.gravity or 75)*(state.halfWidth or 2.5)/max(state.cgHeight or 2.2,1)*.6
    return max(8,min((state.grip or 42)*.76,roll))
end
function Driver.steerLimit(state,speed,angle)
    return min(1,math.atan(traction(state)*(state.wheelbase or 7.5)/max(speed^2,25))/max(angle,.01))
end
local function availableAngle(state,speed)
    return math.clamp(math.deg(math.atan((state.grip or 42)*(state.wheelbase or 7.5)/max(speed^2,25)))*1.05+6,4.5,32)
end
local function observe(self,state,dt)
    local speed=state.vx*state.fx+state.vz*state.fz
    local old=self.observation
    if old and dt>.002 and dt<.16 and state.grounded>=3 and state.upY>.9 then
        local a=(speed-old.speed)/dt
        if old.throttle>.85 and old.brake<.1 and a>2 and a<140 then self.model.accel=self.model.accel*.97+a*.03 end
        if old.brake>.65 and speed>5 and a< -4 and a> -120 then self.model.braking=self.model.braking*.96-a*.04 end
        if abs(self.steer)>.15 and abs(self.steer-old.steer)<.025 and speed>12 then
            local expected=speed/(state.wheelbase or 7.5)*math.tan(self.steer*math.rad(state.maxAngle or 20))
            local gain=abs(expected)>.1 and state.yawRate/expected or 0
            if gain>.35 and gain<2 then self.model.yawGain=self.model.yawGain*.985+gain*.015 end
        end
    end
    self.observation={speed=speed,throttle=self.throttle,brake=self.brake,steer=self.steer}
end
local function window(base,stage,state,road,cfg,braking)
    local speed=sqrt(state.vx^2+state.vz^2)
    local stop=speed^2/(2*braking)+speed*.4+65
    local step=5
    local first=max(0,road.s-20)
    local last=min(base.length,road.s+math.clamp(stop+100,180,650))
    local points={}
    local grip=traction(state)
    for s=first,last,step do
        local p=base:at(s);p.width=Driver.width(stage,s)
        p.limit=min(cfg.maxKmh/1.008,sqrt(grip/max(abs(p.k),.00001)))
        if s>stage.FinishAt then p.limit=min(p.limit,sqrt(max(0,(stage.StopAt or base.length)-s)*2*braking))end
        points[#points+1]=p
    end
    for i=#points-1,1,-1 do points[i].limit=min(points[i].limit,sqrt(points[i+1].limit^2+2*braking*step))end
    return {points=points,first=first,step=step}
end
local function at(w,s)
    return w.points[math.clamp(math.floor((s-w.first)/w.step+.5)+1,1,#w.points)]
end
local function locate(w,x,z,hint)
    local best,dist=nil,math.huge
    local index=math.clamp(math.floor(((hint or w.first)-w.first)/w.step)+1,1,#w.points-1)
    for i=max(1,index-3),min(#w.points-1,index+12)do
        local a,b=w.points[i],w.points[i+1]
        local dx,dz=b.x-a.x,b.z-a.z
        local t=math.clamp(((x-a.x)*dx+(z-a.z)*dz)/max(dx*dx+dz*dz,.00001),0,1)
        local px,pz=a.x+dx*t,a.z+dz*t
        local d=(x-px)^2+(z-pz)^2
        if d<dist then dist=d;best={s=a.s+w.step*t,lateral=(x-px)*(-a.fz)+(z-pz)*a.fx,p=a}end
    end
    return best
end
local function collision(q,obstacles,state)
    local fx,fz=math.sin(q.yaw),-math.cos(q.yaw)
    for _,o in ipairs(obstacles or {})do
        local dx,dz=o.x-q.x,o.z-q.z
        if abs(dx*fx+dz*fz)<(state.halfLength or 5)+(o.radius or .8)+.6
            and abs(dx*(-fz)+dz*fx)<(state.halfWidth or 2.5)+(o.radius or .8)+.6 then return true end
    end
    return false
end
local function rollout(self,w,state,cfg,road,offsetA,offsetB,power,braking,grip)
    local q={x=state.x,z=state.z,yaw=math.atan2(state.fx,-state.fz),vx=state.vx,vz=state.vz,
        rate=state.yawRate or 0,steer=state.steerInput or self.steer,command=self.steer,s=road.s}
    local cost=0;local violation=0;local first;local trace={}
    local dt=.09
    local initialSpeed=sqrt(state.vx^2+state.vz^2)
    local angleScale=math.clamp((state.maxAngle or 20)/availableAngle(state,initialSpeed),.65,1.6)
    for tick=1,18 do
        local n=locate(w,q.x,q.z,q.s);q.s=n.s
        local v=sqrt(q.vx^2+q.vz^2)
        local look=math.clamp(12+v*.42,12,48)
        local target=at(w,q.s+look)
        local offset=tick<9 and offsetA or offsetB
        local usable=max(0,target.width*.5-(state.halfWidth or 2.5)-(cfg.margin or 1.2))
        local lateral=offset*usable
        local tx,tz=target.x-target.fz*lateral,target.z+target.fx*lateral
        local fx,fz=math.sin(q.yaw),-math.cos(q.yaw)
        local dx,dz=tx-q.x,tz-q.z
        local heading=math.atan2(dx*(-fz)+dz*fx,dx*fx+dz*fz)
        local angle=math.atan2(2*(state.wheelbase or 7.5)*math.sin(heading),max(sqrt(dx*dx+dz*dz),4))
        local maxAngle=math.rad(max(4,availableAngle(state,v)*angleScale))
        local steering=math.clamp((angle-q.rate*.045)/maxAngle,-1,1)
        if abs(heading)>1.15 then steering=math.sign(heading)end
        local steerLimit=Driver.steerLimit(state,v,maxAngle)
        steering=math.clamp(steering,-steerLimit,steerLimit)
        local throttle=power==1 and 1 or(power==2 and .25 or 0)
        local brake=power==3 and .7 or(power==4 and 1 or 0)
        local limit=n.p.limit
        if state.nativePreview then limit=min(limit,state.nativePreview)end
        if v>limit+1 then throttle=0;brake=max(brake,math.clamp((v-limit)/10,0,1))end
        if not first then first={Throttle=throttle,Brake=brake,Steer=steering,Handbrake=false,Analog=true}end
        q.command=approach(q.command,steering,3,dt)
        if state.inputAnalog then q.steer=q.steer+(q.command-q.steer)*(1-math.exp(-18*dt))else
            local rate=(abs(q.command)<.015 or math.sign(q.command)~=math.sign(q.steer))and(state.returnRate or 6.5)or(state.steerRate or 4.2)
            q.steer=approach(q.steer,q.command,rate,dt)
        end
        local rate=v/(state.wheelbase or 7.5)*math.tan(q.steer*maxAngle)*self.model.yawGain
        local physicalGrip=max(8,(state.grip or 42)*.9)
        rate=math.clamp(rate,-physicalGrip/max(v,4),physicalGrip/max(v,4))
        q.rate=q.rate+(rate-q.rate)*(1-math.exp(-7*dt));q.yaw=Driver.wrap(q.yaw+q.rate*dt)
        fx,fz=math.sin(q.yaw),-math.cos(q.yaw)
        local longitudinal=q.vx*fx+q.vz*fz
        local side=q.vx*(-fz)+q.vz*fx
        local sideAccel=math.clamp(-side*9,-physicalGrip,physicalGrip)
        local acc=self.model.accel*throttle-braking*brake-.025*v
        longitudinal=max(0,longitudinal+acc*dt);side=side+sideAccel*dt
        q.vx=fx*longitudinal-fz*side;q.vz=fz*longitudinal+fx*side
        q.x=q.x+q.vx*dt;q.z=q.z+q.vz*dt
        local nn=locate(w,q.x,q.z,q.s);q.s=nn.s
        local shape={fx=fx,fz=fz,halfWidth=state.halfWidth,halfLength=state.halfLength,wheelbase=state.wheelbase}
        local clearance=nn.p.width*.5-Driver.envelope(shape,nn.p,cfg.margin)
        local excess=max(0,abs(nn.lateral)-clearance)
        violation=max(violation,excess)
        local rollExcess=max(0,abs(q.rate)*v-grip)/grip
        violation=max(violation,rollExcess*2)
        cost=cost+rollExcess^2*10000
        cost=cost+excess^2*1000+max(0,abs(nn.lateral)-max(0,clearance)*.7)^2*.25
        cost=cost+max(0,v-limit)^2*.2+heading^2*.2+abs(steering-self.steer)*.03
        if collision(q,state.obstacles,state)then violation=max(violation,20);cost=cost+400000 end
        cost=cost-(q.s-road.s)*.1-throttle*.03
        if tick%3==0 then trace[#trace+1]={x=q.x,y=state.y,z=q.z,s=q.s,lateral=nn.lateral,clearance=clearance}end
    end
    cost=cost-(q.s-road.s)*4+abs(offsetA-offsetB)*.5+(offsetA-(self.preference or 0))^2*(cfg.pace or 1)*.3
    return first,cost,violation,trace
end
function Driver.assist(base,stage,state,cfg)
    local road=base:nearest(state)
    local p=base:at(road.s)
    local speed=sqrt(state.vx^2+state.vz^2)
    local clearance=Driver.width(stage,road.s)*.5-Driver.envelope(state,p,cfg.margin)
    local lateralVelocity=state.vx*(-p.fz)+state.vz*p.fx
    local predicted=road.lateral+lateralVelocity*.45
    local excess=max(0,abs(predicted)-max(0,clearance-1))
    local lateralAccel=excess>0 and math.clamp((-math.sign(predicted)*min(excess*5,18)-lateralVelocity)*6,-90,90)or 0
    local heading=math.atan2(p.fx*(-state.fz)+p.fz*state.fx,p.fx*state.fx+p.fz*state.fz)
    local yawAccel=excess>0 and math.clamp((heading*2-(state.yawRate or 0))*5,-5,5)or 0
    if road.distance>25 or abs(road.height)>10 then
        lateralAccel=0;yawAccel=0;excess=0
    end
    local brake=0
    if excess>0 and speed>12 then brake=math.clamp(excess*.2,0,1)end
    if(state.upright or state.upY)<.8 and speed>8 then brake=max(brake,.65)end
    local cornerOver=max(0,abs(state.yawRate or 0)*speed/traction(state)-.9)
    if cornerOver>0 then
        brake=max(brake,min(1,cornerOver))
        local limit=traction(state)/max(speed,4)
        yawAccel=yawAccel+math.clamp((math.sign(state.yawRate)*limit-state.yawRate)*5,-4,4)
    end
    return {road=road,clearance=clearance,predictedLateral=predicted,lateralAccel=lateralAccel,
        rightX=-p.fz,rightZ=p.fx,yawAccel=yawAccel,Brake=brake,risk=excess>0 or(state.upright or state.upY)<.8 or cornerOver>0}
end
function Driver.step(self,route,base,stage,state,cfg,dt,now)
    dt=math.clamp(dt,1/240,.15);observe(self,state,dt)
    if self.brakeSetting~=(cfg.brake or 1)then
        self.brakeSetting=cfg.brake or 1;self.model.braking=max(8,(state.braking or 26)*.82)
    end
    local road=base:nearest(state,self.baseHint);self.baseHint=road.index
    local function stop(mode)
        self.throttle=0;self.brake=1
        return {Throttle=0,Brake=1,Steer=0,Handbrake=false,Analog=true,mode=mode,progress=road.s,targetSpeed=0,lateral=road.lateral,remaining=base.length-road.s}
    end
    if state.runState=='Countdown'then return stop('Countdown')end
    if state.runState=='Finished'or road.s>=(stage.StopAt or base.length)-2 then return stop('Stage complete')end
    if abs(road.height)>18 or(road.distance>(stage.Width or 18)*.5+18 and road.s>stage.StartAt)then return stop('Align car with the stage road')end
    if state.grounded<2 or(state.upright or state.upY)<.45 then
        local c=stop('Stabilizing car');c.Brake=state.grounded>=2 and 1 or 0
        self.steer=approach(self.steer,0,3,dt);c.Steer=self.steer;return c
    end
    local braking=max(8,min(self.model.braking,state.braking or 26))
    local speed=sqrt(state.vx^2+state.vz^2)
    local emergency=state.obstacle and state.obstacle<(state.halfLength or 5)+speed*.12+2
    if emergency then return stop('Obstacle: emergency braking')end
    if road.s<stage.StartAt and road.distance>(stage.Width or 18)*.6 then
        local p=base:at(stage.StartAt)
        local dx,dz=p.x-state.x,p.z-state.z
        local heading=math.atan2(dx*(-state.fz)+dz*state.fx,dx*state.fx+dz*state.fz)
        local c=stop('Approaching stage start')
        c.Steer=math.clamp(heading/math.rad(25),-1,1)
        c.Throttle=speed<12 and .3 or 0;c.Brake=speed>14 and .5 or 0
        return c
    end
    if not self.plannedAt or now-self.plannedAt>=.1 or not self.plan then
        local began=os.clock()
        local w=window(base,stage,state,road,cfg,braking)
        self.preference=0
        if route~=base then
            local n=route:nearest(state,self.routeHint);self.routeHint=n.index
            local preferred=route:at(n.s+max(15,speed*.8))
            local r=base:nearest(preferred,road.index)
            local usable=max(1,Driver.width(stage,r.s)*.5-(state.halfWidth or 2.5)-(cfg.margin or 1.2))
            self.preference=math.clamp(r.lateral/usable,-.7,.7)
        end
        local best,bestCost,bestViolation,bestTrace
        for _,a in ipairs({-.7,0,.7})do for _,b in ipairs({-.7,0,.7})do for power=1,4 do
            local c,cost,violation,trace=rollout(self,w,state,cfg,road,a,b,power,braking,traction(state))
            if not bestCost or cost<bestCost then best,bestCost,bestViolation,bestTrace=c,cost,violation,trace end
        end end end
        self.plan=best;self.plannedAt=now;self.prediction=bestTrace;self.violation=bestViolation
        self.speedLimit=at(w,road.s).limit
        self.planMs=(os.clock()-began)*1000
        -- If no rollout fits, prioritize braking and the least harmful escape.
        if bestViolation>.2 then self.plan.Throttle=0;self.plan.Brake=1 end
    end
    local c=self.plan
    self.steer=approach(self.steer,c.Steer,3,dt)
    self.brake=approach(self.brake,c.Brake,8,dt)
    self.throttle=self.brake>.1 and 0 or approach(self.throttle,c.Throttle,6,dt)
    return {Throttle=self.throttle,Brake=self.brake,Steer=self.steer,Handbrake=false,Analog=true,
        mode=(self.violation or 0)>.2 and 'Braking: predicted corridor exit'or 'Predictive corridor driving',
        progress=road.s,targetSpeed=self.speedLimit or speed,lateral=road.lateral,remaining=base.length-road.s,
        prediction=self.prediction,predictedViolation=self.violation,reference='road corridor',model=self.model,planMilliseconds=self.planMs}
end
return Driver
