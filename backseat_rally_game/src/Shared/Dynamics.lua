-- Shared deterministic driving model. The server owns progress and outcomes.
-- Four road contacts set chassis attitude; visual wheels have independent travel.
local D={}
local function wrap(a)return (a+math.pi)%(2*math.pi)-math.pi end
local function approach(a,b,rate,dt)return a+(b-a)*(1-math.exp(-rate*dt))end
function D.new(route)
 local p=route:point(0)
 return {x=p.x,z=0,v=0,lateralV=0,yaw=p.heading,steer=0,damage=0,distance=0,crashes=0,impact=0}
end
function D.copy(s)local out={};for k,v in pairs(s)do out[k]=v end;return out end
function D.step(s,input,route,car,dt)
 dt=math.clamp(dt,0,1/30);local p=route:point(s.z)
 local _,offset=route:ground(s.x,s.z);local off=math.abs(offset)>p.width/2+1
 local grip=car.grip*(p.surface=='tarmac'and 1.22 or 1)*(off and .63 or 1)
 s.steer=approach(s.steer,math.clamp(input.steer or 0,-1,1),9,dt)
 local throttle=math.clamp(input.throttle or 0,-1,1);local brake=math.clamp(input.brake or 0,0,1)
 local accel=throttle*car.accel*math.max(.72,1-s.damage*.003)*(1-.35*math.min(math.abs(s.v)/car.top,.94))
 if throttle<0 and s.v>2 then accel=-58 end
 if throttle>0 and s.v< -2 then accel=45 end
 local drag=(.72+.0011*s.v*s.v+(off and 8 or 0))*(s.v<0 and -1 or 1)
 if math.abs(s.v)<.3 and throttle==0 then s.v=0;drag=0 end
 s.throttle=throttle;s.brake=brake;s.handbrake=input.handbrake==true
 local braking=brake*66*(s.v<0 and -1 or 1)
 local nextV=s.v+(accel-drag-braking-p.dy*20)*dt
 if brake>0 and (math.abs(s.v)<1.5 or s.v*nextV<0)then nextV=0 end
 s.v=math.clamp(nextV,-23,car.top*(off and .68 or 1))
 local steerAngle=s.steer*math.rad(31)/(1+math.abs(s.v)/95)
 local yawRate=s.v/car.wheelbase*math.tan(steerAngle)
 local limit=grip*48/math.max(math.abs(s.v),10)
 local excess=yawRate-math.clamp(yawRate,-limit,limit)
 yawRate=math.clamp(yawRate,-limit,limit)+excess*.12
 s.lateralV=approach(s.lateralV,excess*math.abs(s.v)*.22,input.handbrake and 2.1 or 5*grip,dt)
 if input.handbrake then yawRate*=1.2;s.v*=math.exp(-.65*dt) end
 s.yaw=wrap(s.yaw-yawRate*dt)
 local forwardX,forwardZ=math.sin(s.yaw),math.cos(s.yaw)
 s.x+=(forwardX*s.v+forwardZ*s.lateralV)*dt
 s.z+=(forwardZ*s.v-forwardX*s.lateralV)*dt
 local _,lateral,newPoint=route:ground(s.x,s.z)
 s.impact=math.max(0,(s.impact or 0)-dt*2)
 local barrier=newPoint.bridge or newPoint.tunnel
 local bound=newPoint.width/2-3.1
 if barrier and math.abs(lateral)>bound then
  local sign=lateral<0 and -1 or 1
  s.x=newPoint.x+sign*bound*math.sqrt(1+newPoint.dx*newPoint.dx)
  local relative=wrap(s.yaw-newPoint.heading)
  local hit=math.abs(math.sin(relative)*s.v)+math.abs(s.lateralV)
  if hit>5 and s.impact<=0 then s.crashes+=1;s.damage=math.min(100,s.damage+hit*.2);s.impact=1 end
  s.yaw=approach(s.yaw,newPoint.heading,.8,dt);s.lateralV=0;s.v*=math.exp(-2*dt)
 elseif math.abs(lateral)>newPoint.width/2+14 then
  s.v*=math.exp(-1.8*dt)
 end
 s.distance+=math.abs(s.v)*dt
 return s
end
function D.pose(s,route)
 local y=route:ground(s.x,s.z);local fX,fZ=math.sin(s.yaw),math.cos(s.yaw)
 local front=route:ground(s.x+fX*3.8,s.z+fZ*3.8)
 local back=route:ground(s.x-fX*3.8,s.z-fZ*3.8)
 local left=route:ground(s.x+fZ*2.8,s.z-fX*2.8)
 local right=route:ground(s.x-fZ*2.8,s.z+fX*2.8)
 return y+2.2,math.atan2(front-back,7.6),math.atan2(right-left,5.6)
end
function D.reset(s,route,z)
 local p=route:point(z);s.x=p.x;s.z=z;s.yaw=p.heading;s.v=0;s.lateralV=0;s.steer=0;s.impact=0
end
return D
