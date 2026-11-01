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
 local climate=route:conditions(s.z)
 local thermal=math.clamp(1-math.abs((s.tyreTemperature or climate.temperature)-55)*.0015,.8,1)
 local grip=thermal*climate.friction*car.grip*(p.surface=='tarmac'and 1.22 or 1)*(off and .63 or 1)
 s.steer=approach(s.steer,math.clamp(input.steer or 0,-1,1),car.steering and car.steering.Rate or 9,dt)
 local throttle=math.clamp(input.throttle or 0,-1,1);local brake=math.clamp(input.brake or 0,0,1)
 local accel=throttle*car.accel*math.max(.72,1-s.damage*.003)*(1-.35*math.min(math.abs(s.v)/car.top,.94))
 if car.mass and car.torque then
  local ms=math.abs(s.v)*.28;local radius=(car.radius or 1.2)*.28
  local gear=math.clamp(s.gear or 1,1,#car.ratios)
  local rpm=ms/radius*car.ratios[gear]*60/(2*math.pi)
  if rpm>(car.shiftRpm or 6000)and gear<#car.ratios then gear+=1
  elseif rpm<2200 and gear>1 then gear-=1 end
  rpm=math.max(850,ms/radius*car.ratios[gear]*60/(2*math.pi));s.gear=gear;s.rpm=rpm
  local fraction=1
  if car.curve then
   fraction=car.curve[1][2]
   for i=2,#car.curve do local a,b=car.curve[i-1],car.curve[i]
    if rpm>=a[1]then fraction=a[2]+(b[2]-a[2])*math.clamp((rpm-a[1])/(b[1]-a[1]),0,1)end
   end
  end
  local force=car.torque*fraction*car.ratios[gear]*.88/radius
  force=math.min(force,car.power*745.7*.88/math.max(ms,3))
  local weight=(car.driveFront or 0)*(1-(car.rearShare or .5))+(1-(car.driveFront or 0))*(car.rearShare or .5)
  force=math.min(force,car.mass*9.81*weight*1.2*climate.friction*thermal)
  accel=throttle*force/car.mass/.28*math.max(.72,1-s.damage*.003)
 end
 if throttle<0 and s.v>2 then accel=-58 end
 if throttle>0 and s.v< -2 then accel=45 end
 local drag=(.72+.0011*(car.drag and car.drag.Air/.00024 or 1)*s.v*s.v+(off and 8 or 0))*(s.v<0 and -1 or 1)
 if math.abs(s.v)<.3 and throttle==0 then s.v=0;drag=0 end
 s.throttle=throttle;s.brake=brake;s.handbrake=input.handbrake==true
 local braking=brake*math.min(car.brakes and car.brakes.Force or 66,grip*9.81/.28)*(s.v<0 and -1 or 1)
 local nextV=s.v+(accel-drag-braking-p.dy*20)*dt
 if brake>0 and (math.abs(s.v)<1.5 or s.v*nextV<0)then nextV=0 end
 s.v=math.clamp(nextV,-23,car.top*(off and .68 or 1))
 local steerAngle=s.steer*math.rad(car.steering and car.steering.MaxAngle or 31)/(1+math.abs(s.v)/95)
 local balance=car.rearShare or .5
 local transfer=math.clamp((accel-braking)*.28*.55/(9.81*car.wheelbase*.28),-.12,.12)
 local frontLoad=math.clamp(1-balance-transfer,.2,.8)
 local response=math.clamp(frontLoad/(1-balance),.7,1.25)
 local yawRate=s.v/car.wheelbase*math.tan(steerAngle)*response
 local demand=math.clamp(math.abs(accel-braking)/(grip*48),0,.95)
 local limit=grip*48*math.sqrt(1-demand*demand)/math.max(math.abs(s.v),10)
 local excess=yawRate-math.clamp(yawRate,-limit,limit)
 yawRate=math.clamp(yawRate,-limit,limit)+excess*.12
 s.lateralV=approach(s.lateralV,excess*math.abs(s.v)*.22,input.handbrake and 2.1 or 5*grip,dt)
 s.lateralV+=climate.wind*.002*dt
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
 local ty,pt,rl=D.contactPose(s,route,car)
 local suspension=car.suspension or {};local travel=suspension.Travel or 1.2
 local omega=9/(1+travel*.3);local damping=math.clamp(((suspension.Bump or .4)+(suspension.Rebound or .55))*.8,.4,1)
 s.bodyY=s.bodyY or ty;s.bodyV=s.bodyV or 0
 s.bodyV+=(omega*omega*(ty-s.bodyY)-2*damping*omega*s.bodyV)*dt
 s.bodyY=math.clamp(s.bodyY+s.bodyV*dt,ty-travel*.4,ty+travel*.65)
 s.pitch=approach(s.pitch or pt,pt+math.clamp((accel-braking)*.0006,-.06,.06),omega,dt)
 s.roll=approach(s.roll or rl,rl+math.clamp(yawRate*s.v*.0007,-.07,.07),omega,dt)
 s.tyreTemperature=approach(s.tyreTemperature or climate.temperature,climate.temperature+math.abs(s.v)*.3+math.abs(excess)*8,.08,dt)
 s.distance+=math.abs(s.v)*dt
 return s
end
function D.contactPose(s,route,car)
 local wb=car and car.wheelbase or 7.6;local rearShare=car and car.rearShare or .5
 local fX,fZ=math.sin(s.yaw),math.cos(s.yaw)
 local frontArm=wb*rearShare;local backArm=wb*(1-rearShare)
 local front=route:ground(s.x+fX*frontArm,s.z+fZ*frontArm)
 local back=route:ground(s.x-fX*backArm,s.z-fZ*backArm)
 local left=route:ground(s.x+fZ*2.8,s.z-fX*2.8)
 local right=route:ground(s.x-fZ*2.8,s.z+fX*2.8)
 return front*(1-rearShare)+back*rearShare+2.2,math.atan2(front-back,wb),math.atan2(right-left,5.6)
end
function D.pose(s,route,car)
 if s.bodyY then return s.bodyY,s.pitch or 0,s.roll or 0 end
 return D.contactPose(s,route,car)
end
function D.reset(s,route,z)
 local p=route:point(z);s.x=p.x;s.z=z;s.yaw=p.heading;s.v=0;s.lateralV=0;s.steer=0;s.impact=0;s.bodyY=nil;s.bodyV=0;s.pitch=nil;s.roll=nil
end
return D
