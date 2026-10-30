local Roads=require("./roads")
local Rail={}
local function wrap(a) return (a+math.pi)%(2*math.pi)-math.pi end
function Rail.new(path,projection,direction,anchor)
    return {path=path,s=projection.s,direction=direction or 1,speed=0,beta=0,side=1,loops=0,
        anchor=anchor or {path=path,s=projection.s,direction=direction or 1},links=0}
end
function Rail.reference(state)
    return state.anchor.reference
end
function Rail.home(state)
    state.path,state.s,state.direction=state.anchor.path,state.anchor.s,state.anchor.direction
    state.connectionKey,state.connection=nil,nil
    state.loops+=1
    return state.anchor.reference
end
function Rail.reverse(state,backwards)
    state.direction=-state.direction
    state.side=-state.side
    state.beta=-state.beta
    state.backwards=if backwards then not state.backwards else false
    state.connectionKey,state.connection=nil,nil
end
function Rail.rejectConnection(state,target)
    local key=tostring(state.path)..":"..state.direction
    state.rejected=state.rejected or {}
    state.rejected[key]=state.rejected[key] or {}
    state.rejected[key][target]=true
    state.connectionKey,state.connection=nil,nil
end
function Rail.step(state,settings,dt,braking,paths,travelScale)
    dt=math.clamp(dt,1/240,.1)
    local farm=settings.style~="cool"
    local path=state.path
    local requested=math.clamp(settings.cruiseKmh,20,500)/1.2
    local area=farm and settings.farmTravel=="area"
    if area and not state.area then
        local span=math.min(math.clamp(settings.farmRange or 80,20,300),path.total)
        local low=math.clamp(state.s-span*.5,0,path.total-span)
        state.area={low=low,high=low+span}
    elseif not area and state.area then state.area=nil;state.backwards=false end
    local _,a=Roads.point(path,state.s-state.direction*8)
    local _,b=Roads.point(path,state.s+state.direction*8)
    local curve=wrap(b-a)*state.direction/16
    local speed=requested
    local connection
    local remaining=if path.closed then math.huge elseif state.direction>0 then path.total-state.s else state.s
    if remaining<100 and not path.closed and not area then
        local key=tostring(path)..":"..state.direction
        if state.connectionKey~=key then
            state.connectionKey=key
            state.connection=Roads.connection(paths or {},path,state.direction,state.rejected and state.rejected[key])
        end
        connection=state.connection
    end
    if not farm then
        speed=math.min(speed,math.sqrt(32/math.max(math.abs(curve),.0001)))
        if remaining<100 and not connection then speed=math.min(speed,math.sqrt(2*24*math.max(0,remaining-1))) end
        if braking then speed=0 end
        state.speed+=math.clamp(speed-state.speed,-30*dt,20*dt)
    else
        -- Farm mode has no corner, segment-end, or spawn-loop speed reduction.
        state.speed=if braking then 0 else requested
    end
    state.s+=state.direction*state.speed*dt*(travelScale or 1)
    local jumped,joined=false,false
    local overshoot=if state.direction>0 then state.s-path.total else -state.s
    if area then
        for _=1,16 do
            if state.s>state.area.high then
                state.s=state.area.high-(state.s-state.area.high)
                Rail.reverse(state,true)
            elseif state.s<state.area.low then
                state.s=state.area.low+(state.area.low-state.s)
                Rail.reverse(state,true)
            else break end
        end
    elseif path.closed then state.s%=path.total
    elseif overshoot>=0 or (not farm and not connection and remaining<1.1 and state.speed<.5 and not braking) then
        if connection then
            state.path,state.s,state.direction=connection.path,connection.s,connection.direction
            state.s+=state.direction*math.max(0,overshoot)
            state.s=if state.path.closed then state.s%state.path.total else math.clamp(state.s,0,state.path.total)
            state.links+=1;joined=true
        else
            Rail.home(state);jumped=true
            if not farm then state.speed=0 end
        end
        state.connectionKey,state.connection=nil,nil
    end
    local p,h=Roads.point(state.path,state.s)
    if state.direction<0 then h+=math.pi end
    if farm then
        -- Client scoring's angle multiplier reaches its maximum at 60 degrees.
        -- Keep one side: forced side switches would cross zero and interrupt a drift.
        state.beta=math.rad(60)*state.side
    else
        if math.abs(curve)>.004 then state.side=math.sign(curve) end
        local magnitude=math.min(math.clamp(settings.angle,15,75),math.clamp(math.abs(curve)*state.speed*45,0,75))
        magnitude*=math.clamp(state.speed/14,0,1)
        local target=math.rad(magnitude)*state.side
        state.beta+=math.clamp(target-state.beta,-math.rad(65)*dt,math.rad(65)*dt)
    end
    -- Cool mode follows a flowing lane line, constrained by the entire angled car footprint.
    -- Farm mode stays on the road's centerline for a stable constant-angle run.
    local lateral=0
    if not farm then
        state.weaveDistance=(state.weaveDistance or 0)+state.speed*dt*(travelScale or 1)
        local footprint=math.sqrt((settings.halfWidth or 3)^2+(settings.halfLength or 5)^2)
        local margin=math.max(0,state.path.width*.5-footprint-2)
        local amplitude=math.min(margin*.65,state.path.width*.14,8*55^2/math.max(state.speed,15)^2)
        state.laneScale=math.min(1,(state.laneScale or 1)+dt*.04)
        amplitude*=state.laneScale
        if settings.offroad then amplitude*=.25 end
        local phase=state.weaveDistance/55
        local wave=amplitude*math.sin(phase)
        local line=math.clamp(curve*60,-1,1)*math.min(margin*.25,2)
        lateral=math.clamp(wave+line,-margin,margin)
        p={x=p.x-math.cos(h)*lateral,y=p.y,z=p.z+math.sin(h)*lateral}
        h+=math.atan2(amplitude/55*math.cos(phase),math.max(.4,1-curve*lateral))
    end
    local orientationBeta=if state.backwards then math.sign(state.beta)*(math.pi-math.abs(state.beta)) else state.beta
    if not farm then
        local wanted=h+orientationBeta
        state.bodyYaw=if state.bodyYaw then state.bodyYaw+math.clamp(wrap(wanted-state.bodyYaw),-2.4*dt,2.4*dt) else wanted
        orientationBeta=wrap(state.bodyYaw-h)
    else state.bodyYaw=nil end
    return {point=p,heading=h,bodyHeading=h+orientationBeta,beta=orientationBeta,speed=state.speed,
        targetAngle=math.deg(state.beta),jumped=jumped,joined=joined,curvature=curve,
        lateral=lateral,backwards=state.backwards==true,reference=if jumped then state.anchor.reference else nil}
end
return Rail
