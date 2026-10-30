-- Continuous road autopilot: scalar planning, with poses applied by the client adapter.
local Roads=require("./roads")
local Rail={}
local function wrap(a) return (a+math.pi)%(2*math.pi)-math.pi end
function Rail.new(path,projection,direction)
    return {path=path,s=projection.s,direction=direction or 1,speed=0,beta=0,side=1}
end
function Rail.step(state,settings,dt,braking)
    dt=math.clamp(dt,1/240,0.05)
    local path=state.path
    local speed=math.clamp(settings.cruiseKmh,20,180)/1.2
    local _,a=Roads.point(path,state.s-state.direction*8)
    local _,b=Roads.point(path,state.s+state.direction*8)
    local curve=wrap(b-a)*state.direction/16
    if math.abs(curve)>.003 then state.side=math.sign(curve) end
    speed=math.min(speed,math.sqrt(70/math.max(math.abs(curve),.0001)))
    if braking then speed=0 end
    state.speed+=math.clamp(speed-state.speed,-80*dt,55*dt)
    state.s+=state.direction*state.speed*dt
    local reversed=false
    if path.closed then state.s%=path.total
    elseif (state.direction>0 and state.s>=path.total) or (state.direction<0 and state.s<=0) then
        -- Open roads continue in the other direction; no restart or manual alignment.
        state.s=math.clamp(state.s,0,path.total)
        state.direction=-state.direction
        state.speed=math.min(state.speed,12)
        reversed=true
    end
    local p,h=Roads.point(path,state.s)
    if state.direction<0 then h+=math.pi end
    local angle=math.rad(math.clamp(settings.angle,15,75))*state.side
    state.beta+=math.clamp(angle-state.beta,-math.rad(110)*dt,math.rad(110)*dt)
    return {point=p,heading=h,bodyHeading=h+state.beta,speed=state.speed,
        targetAngle=math.deg(state.beta),reversed=reversed}
end
return Rail
