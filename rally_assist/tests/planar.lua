-- Independent bicycle model with steering/actuator lag and a lateral grip cap.
-- It does not model Roblox suspension, collisions, reverse gears or networking.
return function(Route,Driver,stages,reels)
    local reports={}
    local cases={}
    cases[#cases+1]={id='PineForest',hz=60}
    cases[#cases+1]={id='RiverbendCanyon',hz=60}
    cases[#cases+1]={id="PineForest",hz=30}
    cases[#cases+1]={id="PineForest",hz=120}
    for _,case in ipairs(cases)do
        local id,stage=case.id,stages[case.id]
        local base=Route.fromStage(stage)
        local line=Route.fromShowcase(reels[id].samples,{source="showcase"})
        line=Route.constrain(line,base,stage.Width,2.8,stage.features)
        local start=line.points[1]
        local yaw=math.atan2(start.fx,-start.fz)
        local state={x=start.x,y=start.y,z=start.z,vx=0,vz=0,fx=math.sin(yaw),fz=-math.cos(yaw),yawRate=0,
            grounded=4,upY=1,wheelbase=case.id=='RiverbendCanyon'and 8.3 or 7.5,halfWidth=2.8,halfLength=5.15,cgHeight=2.2,gravity=75,grip=42,braking=39,maxAngle=32,runState="Running"}
        local cfg={maxKmh=180,pace=1,margin=1.2,brake=1.5,roadAssist=true}
        local driver=Driver.new()
        local speed,steer,maxCross,minBodyClearance=0,0,0,math.huge
        local complete,duration,hint=false,0,nil
        local dt=1/case.hz
        for tick=1,700*case.hz do
            local time=tick*dt
            state.maxAngle=math.clamp(math.deg(math.atan(state.grip*state.wheelbase/math.max(speed*speed,25)))*1.05+6,4.5,32)
            local c=Driver.step(driver,line,base,stage,state,cfg,dt,time)
            for _,key in ipairs({"Throttle","Brake","Steer","targetSpeed"})do
                assert(c[key]==c[key]and math.abs(c[key])<1000,"Non-finite command")
            end
            assert(c.Throttle>=0 and c.Throttle<=1 and c.Brake>=0 and c.Brake<=1 and math.abs(c.Steer)<=1)
            local rate=(c.Steer==0 or math.sign(steer)~=math.sign(c.Steer))and 7 or 4.8
            steer=steer+math.clamp(c.Steer-steer,-rate*dt,rate*dt)
            local desired=speed/state.wheelbase*math.tan(steer*math.rad(state.maxAngle))
            desired=math.clamp(desired,-state.grip/math.max(speed,1),state.grip/math.max(speed,1))
            state.yawRate=state.yawRate+(desired-state.yawRate)*(1-math.exp(-8*dt))
            yaw=Driver.wrap(yaw+state.yawRate*dt)
            speed=math.max(0,speed+(42*c.Throttle-39*c.Brake-.018*speed)*dt)
            state.fx=math.sin(yaw);state.fz=-math.cos(yaw)
            state.vx=state.fx*speed;state.vz=state.fz*speed
            state.x=state.x+state.vx*dt;state.z=state.z+state.vz*dt
            local road=base:nearest(state,hint);hint=road.index
            state.y=road.y+1.95
            maxCross=math.max(maxCross,math.abs(road.lateral))
            local tangent=base:at(road.s)
            local aligned=state.fx*tangent.fx+state.fz*tangent.fz
            local sideways=state.fx*(-tangent.fz)+state.fz*tangent.fx
            local halfFootprint=math.abs(aligned)*state.halfWidth+math.abs(sideways)*state.halfLength
            local width=stage.Width
            for _,f in ipairs(stage.features or {})do
                if(f.Kind=='Bridge'or f.Kind=='Narrow')and f.Width and road.s>=f.From and road.s<=f.To then width=math.min(width,f.Width)end
            end
            minBodyClearance=math.min(minBodyClearance,width*.5-math.abs(road.lateral)-halfFootprint)
            if road.s>=stage.FinishAt-2 then complete=true;duration=time;break end
            if c.mode=="Align car with the stage road"then duration=time;break end
        end
        assert(complete,id.." model did not reach the finish at "..case.hz.." Hz")
        assert(minBodyClearance>0,id.." model car footprint departed the road")
        reports[#reports+1]={stage=id,hz=case.hz,seconds=duration,max_center_deviation=maxCross,min_body_edge_clearance=minBodyClearance,complete=complete}
    end
    return reports
end
