-- User-marked goal geometry and passive motion recording. No game APIs.
local Calibration={}
Calibration.__index=Calibration
local abs,sqrt,min,max=math.abs,math.sqrt,math.min,math.max
local function copy(t)
    if type(t)~='table'then return t end
    local out={};for k,v in pairs(t)do out[k]=copy(v)end;return out
end
local function distance(a,b)return sqrt((a[1]-b[1])^2+(a[2]-b[2])^2+(a[3]-b[3])^2)end
local function dot(a,b)return a[1]*b[1]+a[2]*b[2]+a[3]*b[3]end
local function sub(a,b)return {a[1]-b[1],a[2]-b[2],a[3]-b[3]}end
local function median(t)
    if #t==0 then return nil end
    local a=table.clone(t);table.sort(a);return a[math.floor((#a+1)/2)]
end
local function vector(v)
    if type(v)~='table'or #v~=3 then return false end
    for _,x in ipairs(v)do if type(x)~='number'or x~=x or abs(x)>100000 then return false end end
    return true
end
Calibration.steps={
    {'center','Field centre','Place the centre of your car over the centre spot, upright on the floor.'},
    {'orange_a','Orange: first inner post','At the goal line, point your nose sideways into either INNER post face. Touch it and stop.'},
    {'orange_b','Orange: other inner post','Touch the OTHER inner post face with your nose at the goal line. Stop moving.'},
    {'orange_top','Orange: underside of crossbar','At the middle of the goal mouth, point the nose straight UP and touch the underside of the crossbar.'},
    {'orange_back','Orange: back of net','Inside the net, face away from midfield. Touch the REAR wall with your nose.'},
    {'blue_a','Blue: first inner post','Touch either INNER post face with your nose, sideways at the goal line.'},
    {'blue_b','Blue: other inner post','Touch the OTHER inner post face with your nose at the goal line.'},
    {'blue_top','Blue: underside of crossbar','At the middle of the goal mouth, point the nose UP and touch the underside of the crossbar.'},
    {'blue_back','Blue: back of net','Inside the blue net, face away from midfield and touch the REAR wall with your nose.'}}
function Calibration.new(profile)
    return setmetatable({profile=profile,points={},index=1,history={},reference='bumper',tab='geometry'},Calibration)
end
function Calibration:begin()self.history={};self.index=1;self.points={};self.candidate=nil end
function Calibration:observe(packet,now,keys,physics)
    if not packet then self.history={};return end
    self.latest=packet
    self.history[#self.history+1]={time=now,car=copy(packet.car),ground=packet.ground_estimate,on_ball=packet.ball_wheel_contacts or 0,preset=packet.car_preset or 'standard',verified=packet.car_size_verified,dimensions_verified=packet.car_dimensions_verified}
    while #self.history>1 and now-self.history[1].time>.6 do table.remove(self.history,1)end
    if self.recordingUntil and now<=self.recordingUntil and now-(self.motionAt or -math.huge)>=.09 then
        self.motionAt=now
        local row={time=now,car=copy(packet.car),ball=copy(packet.ball),ground=packet.ground_estimate,
            boost=packet.boost,keys=copy(keys or {}),radius=packet.ball_radius or self.profile.physics.BALL_RADIUS,
            radius_verified=packet.ball_size_verified,clear_flight=physics:clearFlight(packet,packet.ball_radius or self.profile.physics.BALL_RADIUS)}
        self.motion.samples[#self.motion.samples+1]=row
        if #self.motion.samples>=250 then self.recordingUntil=nil end
    end
    if self.recordingUntil and now>self.recordingUntil then self.recordingUntil=nil;self:summarizeMotion()end
end
function Calibration:probe(row,key)
    local car=row.car;local p=table.clone(car.position)
    if key~='center'and self.reference=='bumper'then
        local c=self.profile.car_presets[row.preset]or self.profile.car_presets.standard
        local f,u=car.forward,car.up
        local right={u[2]*f[3]-u[3]*f[2],u[3]*f[1]-u[1]*f[3],u[1]*f[2]-u[2]*f[1]}
        for i=1,3 do p[i]=p[i]+f[i]*(c.size[1]/2+c.offset[1])+right[i]*c.offset[2]+u[i]*c.offset[3]end
    end
    return {point=p,root=table.clone(car.position),forward=table.clone(car.forward),up=table.clone(car.up),
        preset=row.preset,reference=self.reference,hitbox_verified=row.verified==true,time=row.time}
end
function Calibration:corners(p)
    local cfg=self.profile.car_presets[p.preset]or self.profile.car_presets.standard
    local f,u=p.forward,p.up
    local right={u[2]*f[3]-u[3]*f[2],u[3]*f[1]-u[1]*f[3],u[1]*f[2]-u[2]*f[1]}
    local face={}
    for j=1,3 do face[j]=p.root[j]+f[j]*(cfg.offset[1]+cfg.size[1]/2)+right[j]*cfg.offset[2]+u[j]*cfg.offset[3]end
    local out={}
    for _,a in ipairs({-1,1})do for _,b in ipairs({-1,1})do for _,c in ipairs({-1,1})do
        local v={}
        for j=1,3 do v[j]=p.root[j]+f[j]*(cfg.offset[1]+a*cfg.size[1]/2)
            +right[j]*(cfg.offset[2]+b*cfg.size[2]/2)+u[j]*(cfg.offset[3]+c*cfg.size[3]/2)+p.point[j]-face[j]end
        out[#out+1]=v
    end end end
    return out
end
function Calibration:capture()
    assert(self.index<=#Calibration.steps,'All points captured; review and apply the result')
    assert(#self.history>=3,'Hold the car still for half a second first')
    local latest=self.history[#self.history]
    assert(latest.time-self.history[1].time>=.25,'Hold still a little longer')
    for _,r in ipairs(self.history)do
        assert(r.preset==latest.preset,'Car body changed; hold still and capture again')
        assert(distance(r.car.position,latest.car.position)<12,'Car moved during capture; stop and retry')
        assert(dot(r.car.velocity,r.car.velocity)<2500,'Car is still moving; stop and retry')
        assert(dot(r.car.angular_velocity or {0,0,0},r.car.angular_velocity or {0,0,0})<.08^2,'Car is rotating; hold still and retry')
    end
    local key=Calibration.steps[self.index][1]
    if key~='center'and self.reference=='bumper'then assert(latest.verified or latest.dimensions_verified,'Collision body dimensions are unknown; use a supported car or explicit centre-marker mode')end
    if key=='center'then assert(latest.ground and latest.car.up[3]>.9 and latest.on_ball==0 and abs(latest.car.position[3]-self.profile.physics.CAR_SPAWN_REST_Z)<30,'Centre point must be upright on the field floor, not on the ball')end
    local point=self:probe(latest,key);local probes={}
    for _,r in ipairs(self.history)do probes[#probes+1]=self:probe(r,key).point end
    for j=1,3 do local values={};for _,p in ipairs(probes)do values[#values+1]=p[j]end;point.point[j]=median(values)end
    point.samples=#probes;point.spread=0
    for _,p in ipairs(probes)do point.spread=max(point.spread,distance(p,point.point))end
    self.points[key]=point;self.index=self.index+1;self.candidate=nil
    if self.index>#Calibration.steps then self.candidate=self:fit()end
    return self.index
end
function Calibration:back()
    self.index=max(1,self.index-1);self.points[Calibration.steps[self.index][1]]=nil;self.candidate=nil
end
function Calibration:fit()
    for _,s in ipairs(Calibration.steps)do
        local p=self.points[s[1]]
        assert(type(p)=='table'and vector(p.point)and vector(p.root)and vector(p.forward)and vector(p.up),'Missing or invalid point: '..s[2])
        assert(abs(dot(p.forward,p.forward)-1)<.02 and abs(dot(p.up,p.up)-1)<.02 and abs(dot(p.forward,p.up))<.02,'Invalid car orientation at '..s[2])
        assert(p.reference=='bumper'or p.reference=='center','Unknown point reference')
    end
    local centre=self.points.center.point
    local floor=0 -- fixed vertical origin of the saved standard soccer arena
    local out={version=1,centre=table.clone(centre),floor=floor,goals={},
        note='Centre measures XY; floor zero comes from the saved standard arena. Front-face contacts use source hitbox offsets; rounded-corner correction uses the saved fillet. Marker mode uses the car root directly.'}
    for team,name in ipairs({'blue','orange'})do
        local a,b,top,back=self.points[name..'_a'],self.points[name..'_b'],self.points[name..'_top'],self.points[name..'_back']
        local dx,dy=b.point[1]-a.point[1],b.point[2]-a.point[2]
        local width=sqrt(dx*dx+dy*dy)
        assert(width>1000 and width<2400,name..': post spacing is implausible; capture the inner faces')
        local side={dx/width,dy/width,0}
        local normal={-side[2],side[1],0}
        local origin={(a.point[1]+b.point[1])/2,(a.point[2]+b.point[2])/2,floor}
        if dot(sub(origin,centre),normal)<0 then normal[1]=-normal[1];normal[2]=-normal[2]end
        local depth=dot(sub(origin,centre),normal)
        assert(depth>4000 and depth<7000,name..': goal is not at a plausible field end')
        assert(abs(depth-self.profile.arena.EXTENT_Y)<250,name..': capture the front goal line; large arena changes need a separate profile')
        assert(abs(dot(sub(origin,centre),side))<200,name..': goal centre is too far sideways from the centre spot')
        assert(abs(dot(sub(top.point,origin),normal))<180,name..': crossbar point must be at the goal mouth, not the ceiling/back wall')
        local height=top.point[3]-floor
        if top.reference=='bumper'then for _,v in ipairs(self:corners(top))do height=max(height,v[3]-floor)end end
        assert(height>350 and height<900,name..': crossbar height is implausible')
        local backDepth=dot(sub(back.point,origin),normal)
        assert(backDepth>300 and backDepth<1400,name..': touch the back of the net, not the field backwall')
        assert(abs(dot(sub(back.point,origin),side))<width*.4,name..': use the middle of the rear net wall')
        for _,p in ipairs({a,b})do
            assert(p.point[3]-floor>0 and p.point[3]-floor<height,name..': post contact must be below the crossbar')
            if p.reference=='bumper'then
                local sign=dot(sub(p.point,origin),side)>0 and 1 or -1
                assert(dot(p.forward,side)*sign>.9,name..': point the nose sideways into the inner post face')
            end
        end
        if top.reference=='bumper'then assert(top.forward[3]>.9,name..': point the nose up into the crossbar underside')end
        if back.reference=='bumper'then assert(dot(back.forward,normal)>.9,name..': point the nose into the rear net wall')end
        local r=self.profile.arena.MOUTH_FILLET
        local function rounded(z)
            local dz=max(0,r-min(z,height-z))
            return r-sqrt(max(0,r*r-dz*dz))
        end
        local function correction(p,sign)
            if p.reference=='center'then return rounded(p.point[3]-floor)end
            local face=dot(sub(p.point,origin),side)*sign
            local required=face
            for _,v in ipairs(self:corners(p))do
                local z=v[3]-floor
                if z>=0 and z<=height then required=max(required,dot(sub(v,origin),side)*sign+rounded(z))end
            end
            return required-face
        end
        local ca,cb=correction(a,-1),correction(b,1)
        width=width+ca+cb
        for i=1,2 do origin[i]=origin[i]+side[i]*(cb-ca)/2 end
        out.goals[team]={origin=origin,side=side,normal=normal,half_width=width/2,height=height,back_depth=backDepth,fillet=r}
    end
    local blue,orange=out.goals[1],out.goals[2]
    assert(dot(blue.normal,orange.normal)<-.97,'The two goals must face opposite field ends')
    assert(blue.normal[2]<-.95 and orange.normal[2]>.95,'Blue/orange ends appear swapped; this calibration targets the saved standard soccer orientation')
    assert(abs(blue.half_width-orange.half_width)<min(blue.half_width,orange.half_width)*.12,'Goal widths disagree; recapture the inner faces')
    assert(abs(blue.height-orange.height)<min(blue.height,orange.height)*.12,'Crossbar heights disagree')
    out.summary=string.format('Blue %.1f x %.1f studs | Orange %.1f x %.1f studs',blue.half_width*.2,blue.height*.1,orange.half_width*.2,orange.height*.1)
    return out
end
function Calibration:apply()self.candidate=self:fit();self.active=copy(self.candidate);return self.active end
function Calibration:goal(team)
    if self.active then return self.active.goals[team+1]end
    local a=self.profile.arena;local sign=team==0 and -1 or 1
    return {origin={0,sign*a.EXTENT_Y,0},side={1,0,0},normal={0,sign,0},half_width=a.MOUTH_HALF_WIDTH,
        height=a.MOUTH_HEIGHT,back_depth=a.GOAL_BACK_Y-a.EXTENT_Y,fillet=a.MOUTH_FILLET}
end
function Calibration:startMotion(now)self.motion={samples={},started_at=now};self.recordingUntil=now+20;self.motionAt=nil end
function Calibration:summarizeMotion()
    if not self.motion then return nil end
    local samples=self.motion.samples;local gravity,accel,brakes,radii={},{},{},{}
    for i,r in ipairs(samples)do
        if r.radius_verified then radii[#radii+1]=r.radius end
        local old=samples[i-1]
        if old then
            local dt=r.time-old.time
            if dt>.02 and dt<.3 and r.ground and old.ground and dot(r.car.forward,old.car.forward)>.995 and r.car.up[3]>.95 then
                local speed=dot(old.car.velocity,old.car.forward)
                local dv=(dot(r.car.velocity,r.car.forward)-speed)/dt
                if old.keys.W and not old.keys.S and not old.keys.LMB and speed>200 and speed<1000 and dv>0 and dv<3000 then accel[#accel+1]=dv end
                if old.keys.S and not old.keys.W and speed>400 and dv< -100 and dv> -6000 then brakes[#brakes+1]=-dv end
            end
        end
        local a,b=samples[i-4],samples[i-2]
        if a and b and a.clear_flight and b.clear_flight and r.clear_flight then
            local dt1,dt2=b.time-a.time,r.time-b.time
            if min(dt1,dt2)>.09 and max(dt1,dt2)<.4 then
                local g=2*((r.ball.position[3]-b.ball.position[3])/dt2-(b.ball.position[3]-a.ball.position[3])/dt1)/(dt1+dt2)
                local horizontal=0
                for j=1,2 do local n=2*((r.ball.position[j]-b.ball.position[j])/dt2-(b.ball.position[j]-a.ball.position[j])/dt1)/(dt1+dt2);horizontal=horizontal+n*n end
                g=g-math.log(1-self.profile.physics.BALL_DRAG)*r.ball.velocity[3]
                if g< -150 and g> -2000 and horizontal<250^2 then gravity[#gravity+1]=g end
            end
        end
    end
    local g=median(gravity);local deviations={}
    if g then for _,n in ipairs(gravity)do deviations[#deviations+1]=abs(n-g)end end
    self.motion.summary={samples=#samples,gravity_samples=#gravity,gravity=g,
        gravity_consistent=#gravity>=6 and median(deviations)<max(35,abs(g)*.08)or false,
        verified_ball_radius=median(radii),ground_acceleration_median=median(accel),braking_median=median(brakes),
        note='Acceleration/braking describe the sampled speeds and surface. Static landmarks and this recording do not identify masses or train the actor.'}
    return self.motion.summary
end
function Calibration:export()return {version=1,place=101880234193261,reference=self.reference,points=copy(self.points),motion=copy(self.motion)}end
function Calibration:load(data)
    assert(type(data)=='table'and data.version==1 and data.place==101880234193261,'Unsupported calibration file')
    assert(type(data.points)=='table','Calibration file has no points')
    local points={};local nextIndex=10
    for i,s in ipairs(Calibration.steps)do
        local p=data.points[s[1]]
        if p then
            assert(vector(p.point)and vector(p.root)and vector(p.forward)and vector(p.up),'Invalid saved landmark')
            assert(p.reference=='bumper'or p.reference=='center','Invalid saved reference')
            points[s[1]]=copy(p)
        else nextIndex=min(nextIndex,i)end
    end
    local old=self.points;self.points=points
    local ok,candidate=true,nil
    if nextIndex==10 then ok,candidate=pcall(function()return self:fit()end)end
    self.points=old
    if not ok then error(candidate)end
    local loadedMotion
    if data.motion then
        assert(type(data.motion.samples)=='table'and #data.motion.samples<=250,'Invalid motion recording')
        for _,r in ipairs(data.motion.samples)do
            assert(type(r.time)=='number'and r.time==r.time and abs(r.time)<1e9 and type(r.radius)=='number'and r.radius>0 and r.radius<1000,'Invalid motion sample')
            for _,body in ipairs({r.car,r.ball})do
                assert(type(body)=='table'and vector(body.position)and vector(body.velocity),'Invalid recorded pose')
            end
            assert(vector(r.car.forward)and vector(r.car.up)and type(r.keys)=='table','Invalid recorded controls')
        end
        local temporary=setmetatable({profile=self.profile,motion=copy(data.motion)},Calibration)
        temporary:summarizeMotion();loadedMotion=temporary.motion
    end
    self.points=points;self.candidate=candidate;self.index=nextIndex
    self.history={};self.recordingUntil=nil;self.motionAt=nil
    if loadedMotion then self.motion=loadedMotion end
    if data.reference=='bumper'or data.reference=='center'then self.reference=data.reference end
end
function Calibration:report()return {points=copy(self.points),candidate=copy(self.candidate),active=copy(self.active),motion=self.motion and copy(self.motion.summary)or nil}end
return Calibration
