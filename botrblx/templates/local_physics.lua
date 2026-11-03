-- Independent ball/world predictor. All coordinates use the numeric arena
-- profile, not rendered mesh bounds. Future car touches are deliberately absent.
local Physics={}
Physics.__index=Physics
local abs,min,max,sqrt=math.abs,math.min,math.max,math.sqrt
local function dot(a,b)return a[1]*b[1]+a[2]*b[2]+a[3]*b[3]end
local function cross(a,b)return {a[2]*b[3]-a[3]*b[2],a[3]*b[1]-a[1]*b[3],a[1]*b[2]-a[2]*b[1]}end
local function length(v)return sqrt(dot(v,v))end
local function distance(a,b)return sqrt((a[1]-b[1])^2+(a[2]-b[2])^2+(a[3]-b[3])^2)end
local function limit(v,cap)
    local speed=length(v)
    if speed>cap then for i=1,3 do v[i]=v[i]*cap/speed end end
end
local function copy(ball)
    local body={position=table.clone(ball.position),velocity=table.clone(ball.velocity),
        angular_velocity=table.clone(ball.angular_velocity or {0,0,0}),slow=ball.slow or 0}
    if ball.forward then body.forward=table.clone(ball.forward)end
    if ball.up then body.up=table.clone(ball.up)end
    return body
end
local function median(values)
    local sorted=table.clone(values);table.sort(sorted)
    return sorted[math.ceil(#sorted/2)]
end

function Physics.new(profile,arena)
    return setmetatable({profile=profile,arena=arena,gravity=profile.physics.GRAVITY_Z,
        history={},gravitySamples={},errors={},trace={},events={},status="saved profile",resets=0,
        totalFlightErrors=0},Physics)
end

function Physics:mark(kind,now,reason)
    self.events[#self.events+1]={kind=kind,time=now,reason=reason}
    if #self.events>40 then table.remove(self.events,1)end
end

-- One stationary-world sphere contact has a closed-form normal/friction impulse.
-- The sphere's contact inertia gives tangent effective mass m/3.5. Restitution
-- uses pre-force velocity; split penetration correction never adds bounce energy.
function Physics:step(ball,radius,dt)
    local cfg=self.profile.physics
    local p,v,w=ball.position,ball.velocity,ball.angular_velocity
    if length(v)==0 and length(w)==0 then return false end -- simulator sleep state
    local drag=(1-cfg.BALL_DRAG)^dt
    for i=1,3 do v[i]=v[i]*drag end
    local old={v[1],v[2],v[3]}
    v[3]=v[3]+self.gravity*dt
    local worldRadius=radius*cfg.BALL_WORLD_RADIUS/cfg.BALL_RADIUS
    local d=self.arena:distance(p)
    local touched,obstructed=false,false
    if d-worldRadius<cfg.CONTACT_BREAKING_THRESHOLD then
        local _,n=self.arena:query(p)
        local flat=abs(n[3])>.9999 or(abs(n[3])<.0001 and(abs(n[1])>.9999 or abs(n[2])>.9999))
        if d-worldRadius<(flat and cfg.BALL_WORLD_CONTACT_FLAT or cfg.CONTACT_BREAKING_THRESHOLD)then
            touched=true
            obstructed=n[3]<.9
            local incoming=dot(old,n)
            local bounce=abs(incoming)>=cfg.RESTITUTION_VEL_THRESHOLD and max(-incoming*cfg.BALLWORLD_RESTITUTION,0)or 0
            local impulse=max(0,bounce-dot(v,n))
            local spin=cross(w,n)
            local slip={v[1]-radius*spin[1],v[2]-radius*spin[2],v[3]-radius*spin[3]}
            local normalSlip=dot(slip,n)
            for i=1,3 do slip[i]=slip[i]-normalSlip*n[i]end
            local speed=length(slip)
            local friction=0
            if speed>1e-8 then
                for i=1,3 do slip[i]=slip[i]/speed end
                friction=-min(speed/3.5,cfg.BALLWORLD_FRICTION*impulse)
            end
            local torque=cross(n,slip)
            local push=cfg.SOLVER_ERP2*max(radius-d,0)
            for i=1,3 do
                v[i]=v[i]+n[i]*impulse+slip[i]*friction
                w[i]=w[i]-torque[i]*2.5/radius*friction
                p[i]=p[i]+n[i]*push
            end
        end
    end
    -- The saved solver integrates before its final speed limits.
    for i=1,3 do p[i]=p[i]+v[i]*dt end
    limit(v,cfg.BALL_MAX_SPEED);limit(w,cfg.BALL_MAX_ANG_SPEED)
    if length(v)<cfg.BALL_SLEEP_LIN_SPEED and length(w)<cfg.BALL_SLEEP_ANG_SPEED then
        ball.slow=(ball.slow or 0)+dt
        if ball.slow>cfg.BALL_SLEEP_TIME then
            ball.velocity={0,0,0};ball.angular_velocity={0,0,0}
        end
    else ball.slow=0 end
    return touched,obstructed
end

function Physics:predict(ball,radius,seconds,stride,checkpoint)
    radius=radius or self.profile.physics.BALL_RADIUS
    local state=copy(ball)
    local result={{time=0,position=table.clone(state.position),velocity=table.clone(state.velocity),bounces=0,obstructions=0}}
    local dt=1/self.profile.physics.TICK_RATE
    local steps=math.floor(math.clamp(seconds or 2.5,0,3)*self.profile.physics.TICK_RATE+.5)
    local bounces,obstructions=0,0
    for tick=1,steps do
        local touched,blocked=self:step(state,radius,dt)
        if touched then bounces=bounces+1 end
        if blocked then obstructions=obstructions+1 end
        if tick%(stride or 4)==0 or tick==steps then
            result[#result+1]={time=tick*dt,position=table.clone(state.position),
                velocity=table.clone(state.velocity),bounces=bounces,obstructions=obstructions}
        end
        if checkpoint and tick%2==0 then checkpoint()end
    end
    return result
end

function Physics:reset()
    self.history={};self.forecast=nil;self.lastAt=nil;self.lastBall=nil
    self.errors={};self.error=nil;self.mismatch=false
    self.resets=self.resets+1
end

function Physics:clearFlight(packet,radius)
    local ball=packet.ball
    if ball.position[3]<radius+180 or self.arena:distance(ball.position)<radius+100 then return false end
    local function close(car)
        return distance(car.position,ball.position)<radius+250+min(length(ball.velocity)*.12,500)
    end
    if close(packet.car)then return false end
    for _,car in ipairs(packet.other_cars or {})do if close(car)then return false end end
    return true
end

-- Passive calibration uses only isolated airborne positions. Finite-difference
-- velocities from rendered frames are averages, so fitting their acceleration
-- directly would mistake interpolation and touches for gravity.
function Physics:observe(packet,now,cheap)
    if not packet then if self.lastAt then self:reset()end;return end
    local radius=packet.ball_radius or self.profile.physics.BALL_RADIUS
    local p=packet.ball.position
    if self.lastAt then
        local dt=now-self.lastAt
        if dt<=0 or dt>.15 or abs(radius-self.radius)>1 or self.team~=packet.team
            or distance(p,self.lastBall)>self.profile.physics.BALL_MAX_SPEED*dt+100 then self:reset()end
    end
    self.lastAt,self.lastBall,self.radius,self.team=now,table.clone(p),radius,packet.team
    local clear=not cheap and self:clearFlight(packet,radius)
    if not clear then self.history={};self.forecast=nil else
        local h=self.history
        h[#h+1]={at=now,p=table.clone(p)}
        while #h>1 and now-h[1].at>.6 do table.remove(h,1)end
        if #h>=7 and now-(self.lastFit or -math.huge)>=.1 then
            local a,b,c=h[1],h[math.floor((#h+1)/2)],h[#h]
            local dt1,dt2=b.at-a.at,c.at-b.at
            if min(dt1,dt2)>=.09 then
                local acceleration={}
                for i=1,3 do acceleration[i]=2*((c.p[i]-b.p[i])/dt2-(b.p[i]-a.p[i])/dt1)/(dt1+dt2)end
                local gravity=acceleration[3]+(-math.log(1-self.profile.physics.BALL_DRAG))*packet.ball.velocity[3]
                if sqrt(acceleration[1]^2+acceleration[2]^2)<250 and gravity< -150 and gravity> -3000 then
                    local samples=self.gravitySamples
                    samples[#samples+1]=gravity;if #samples>15 then table.remove(samples,1)end
                    if #samples>=6 then
                        local middle=median(samples)
                        local deviations={};for i,g in ipairs(samples)do deviations[i]=abs(g-middle)end
                        if median(deviations)<max(35,abs(middle)*.08)then
                            self.gravity=middle;self.observedGravity=middle
                            self.status=abs(middle-self.profile.physics.GRAVITY_Z)>100 and "live gravity adapted"or "flight checked"
                        end
                    end
                end
                self.lastFit=now
            end
        end
        if self.forecast and now-self.forecast.at>=.2 then
            local future=self:predict(self.forecast.ball,radius,now-self.forecast.at,1000)
            local error=distance(p,future[#future].position)
            self.errors[#self.errors+1]=error;if #self.errors>20 then table.remove(self.errors,1)end
            self.error=median(self.errors)
            self.lastFlightError=self.error;self.lastFlightAt=now
            self.totalFlightErrors=self.totalFlightErrors+1
            self.forecast=nil
        end
        if not self.forecast then self.forecast={at=now,ball=copy(packet.ball)}end
    end
    -- A gross coordinate/arena mismatch cannot safely use this ground planner.
    self.mismatch=self.arena:distance(p)<-radius*2 or(self.error or 0)>radius*2
    if now-(self.traceAt or -math.huge)>=.2 then
        self.traceAt=now
        local others={}
        for _,car in ipairs(packet.other_cars or {})do
            local body=copy(car)
            body.team=car.team;body.boost_estimate=car.boost_estimate
            body.ground_estimate=car.ground_estimate;body.flip_estimate=car.flip_estimate
            others[#others+1]=body
        end
        local sample={time=now,car=copy(packet.car),ball=copy(packet.ball),
            other_cars=others,boost_pads=packet.boost_pads,
            team=packet.team,ground=packet.ground_estimate,radius=radius,boost=packet.boost,
            radius_verified=packet.ball_size_verified==true,car_preset=packet.car_preset,
            car_verified=packet.car_size_verified==true,wheel_contacts=packet.wheel_contacts,
            pads_known=packet.boost_known,pads_total=packet.boost_total,pad_folder_found=packet.pad_folder_found,
            hitbox_probe=packet.hitbox_probe,sample_dt=packet.sample_dt,
            decision=self.decision,decision_age=self.decision and self.decision.time and now-self.decision.time or nil,
            runtime=self.runtime,physics_status=self.status,gravity=self.gravity,
            flight_error=self.error,plan=self.plan}
        self.latestPose=sample
        if not self.runtime or self.runtime.enabled then
            self.trace[#self.trace+1]=sample
            if #self.trace>150 then table.remove(self.trace,1)end
        end
    end
end

function Physics:report()
    return {version="local-6.8",profile=self.profile.name,units="simulation units; seconds",
        studs_per_unit=self.profile.roblox_studs_per_sim_unit,arena=self.profile.arena,
        saved_physics=self.profile.physics,gravity_used=self.gravity,observed_gravity=self.observedGravity,
        gravity_samples=#self.gravitySamples,flight_position_error_median=self.error,
        flight_error_samples=#self.errors,status=self.status,profile_mismatch=self.mismatch==true,
        last_valid_flight_error=self.lastFlightError,last_valid_flight_time=self.lastFlightAt,
        total_flight_error_samples=self.totalFlightErrors,resets=self.resets,trace=self.trace,latest_pose=self.latestPose,
        trace_collection="Active-run poses; paused sampling does not replace the driving trace",
        runtime=self.runtime,events=self.events,last_error=self.lastError,
        limitations="Ball/world forecast only; future car touches and exact curved goal-frame contact are uncertain. Ground reach is an estimate."}
end

return Physics
