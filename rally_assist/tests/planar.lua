-- Independent bicycle model with steering/actuator lag and a lateral grip cap.
-- It does not model Roblox suspension, collisions, reverse gears or networking.
return function(Route,Driver,stages,reels)
    local reports={}
    local cases={}
    for id in pairs(stages)do cases[#cases+1]={id=id,hz=60}end
    cases[#cases+1]={id="PineForest",hz=30}
    cases[#cases+1]={id="PineForest",hz=120}
    for _,case in ipairs(cases)do
        local id,stage=case.id,stages[case.id]
        local base=Route.fromStage(stage)
        local line=Route.fromShowcase(reels[id].samples,{source="showcase"})
        line=Route.constrain(line,base,stage.Width,2.5,stage.features)
        local start=line.points[1]
        local yaw=math.atan2(start.fx,-start.fz)
        local state={x=start.x,y=start.y,z=start.z,vx=0,vz=0,fx=math.sin(yaw),fz=-math.cos(yaw),yawRate=0,
            grounded=4,upY=1,wheelbase=7.5,halfWidth=2.5,grip=68,braking=44,maxAngle=34,runState="Running"}
        local cfg={maxKmh=180,pace=1}
        local driver=Driver.new()
        local speed,steer,maxCross=0,0,0
        local complete,duration,hint=false,0,nil
        local dt=1/case.hz
        for tick=1,500*case.hz do
            local time=tick*dt
            state.maxAngle=math.clamp(math.deg(math.atan(state.grip*state.wheelbase/math.max(speed*speed,100)))*1.15+7,4.5,34)
            local c=Driver.step(driver,line,base,stage,state,cfg,dt,time)
            for _,key in ipairs({"Throttle","Brake","Steer","targetSpeed"})do
                assert(c[key]==c[key]and math.abs(c[key])<1000,"Non-finite command")
            end
            assert(c.Throttle>=0 and c.Throttle<=1 and c.Brake>=0 and c.Brake<=1 and math.abs(c.Steer)<=1)
            steer=steer+(c.Steer-steer)*(1-math.exp(-4.2*dt))
            local desired=speed/7.5*math.tan(steer*math.rad(state.maxAngle))
            desired=math.clamp(desired,-state.grip/math.max(speed,1),state.grip/math.max(speed,1))
            state.yawRate=state.yawRate+(desired-state.yawRate)*(1-math.exp(-8*dt))
            yaw=Driver.wrap(yaw+state.yawRate*dt)
            speed=math.max(0,speed+(48*c.Throttle-44*c.Brake-.018*speed)*dt)
            state.fx=math.sin(yaw);state.fz=-math.cos(yaw)
            state.vx=state.fx*speed;state.vz=state.fz*speed
            state.x=state.x+state.vx*dt;state.z=state.z+state.vz*dt
            local road=base:nearest(state,hint);hint=road.index
            state.y=road.y+1.95
            maxCross=math.max(maxCross,math.abs(road.lateral))
            if road.s>=stage.FinishAt-2 then complete=true;duration=time;break end
            if c.mode=="Align car with the stage road"then duration=time;break end
        end
        assert(complete,id.." model did not reach the finish at "..case.hz.." Hz")
        assert(maxCross<stage.Width*.5+1,id.." model departed the road corridor")
        reports[#reports+1]={stage=id,hz=case.hz,seconds=duration,max_center_deviation=maxCross,complete=complete}
    end
    return reports
end
