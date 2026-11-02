-- Shared deterministic rally model, in studs and seconds (.28 metres/stud).
-- Fixed four-contact approximation: no unbounded tyre raycasts or client forces.
-- Profiles supply each car's engine, mass, axle balance, geometry and suspension.
local D={}
-- Edit this table for every car, or override individual keys in car.simulation.
D.Tuning={DamageEnergy=700,PunctureImpact=.24,PressureLeak=.11,LoadSensitivity=.12,
 WearRate=1,TyreHeatRate=.09,ThrottleResponse=7,CorneringScale=48,BodyFrequency=9}
local function tune(car,key)return car and car.simulation and car.simulation[key]or D.Tuning[key]end
local G=9.81/.28
local function wrap(a)return (a+math.pi)%(2*math.pi)-math.pi end
local function approach(a,b,rate,dt)return a+(b-a)*(1-math.exp(-rate*dt))end
local function finite(n)return type(n)=='number'and n==n and math.abs(n)<1e8 end
local function deepCopy(value)
 if type(value)~='table'then return value end
 local out={};for k,v in pairs(value)do out[k]=deepCopy(v)end;return out
end
local function equip(s,car,ambient)
 if not s.health then s.health={engine=1,brakes=1,suspension=1,steering=1}end
 if not s.tyres then
  s.tyres={}
  for i=1,4 do s.tyres[i]={pressure=1,targetPressure=1,temperature=ambient or 20,wear=0,punctured=false,load=0,slip=0,grip=1,compression=0}end
 end
 s.settings=s.settings or {damage=true,punctures=true,abs=true,tractionControl=true,steeringAssist=.65,stabilityAssist=.5}
 s.engineTemperature=s.engineTemperature or 75;s.brakeTemperature=s.brakeTemperature or 25
 s.engineHealth=s.health.engine
end
function D.new(route)
 local p=route:point(0)
 local s={x=p.x,z=0,v=0,lateralV=0,yaw=p.heading,steer=0,damage=0,distance=0,crashes=0,impact=0,impactSpeed=0,impactSide=0,throttle=0,brake=0}
 equip(s,nil,route:conditions(0).temperature);return s
end
function D.copy(s)return deepCopy(s)end
-- Only known handling switches are accepted; presentation options live on client.
function D.configure(s,settings)
 equip(s);settings=settings or {}
 if type(settings.assists)=='boolean'then s.settings.abs=settings.assists;s.settings.tractionControl=settings.assists;s.settings.steeringAssist=settings.assists and .65 or 0;s.settings.stabilityAssist=settings.assists and .5 or 0 end
 if finite(settings.tyrePressure)then D.setPressure(s,'all',settings.tyrePressure)end
 for _,key in ipairs({'damage','punctures','abs','tractionControl'})do if type(settings[key])=='boolean'then s.settings[key]=settings[key]end end
 for _,key in ipairs({'steeringAssist','stabilityAssist'})do if finite(settings[key])then s.settings[key]=math.clamp(settings[key],0,1)end end
end
-- Pressure is relative to a car's nominal cold pressure (1 = 100%, not PSI).
function D.setPressure(s,wheel,pressure,car)
 equip(s,car)
 if not finite(pressure)then return false end
 pressure=math.clamp(pressure,.55,1.4)
 local first,last=1,4
 if type(wheel)=='number'and wheel%1==0 and wheel>=1 and wheel<=4 then first=wheel;last=wheel
 elseif wheel=='front'then last=2 elseif wheel=='rear'then first=3 elseif wheel~='all'then return false end
 for i=first,last do local tyre=s.tyres[i];tyre.targetPressure=pressure;if not tyre.punctured then tyre.pressure=pressure end end
 return true
end
function D.puncture(s,wheel,car)
 equip(s,car)
 if not s.settings.damage or not s.settings.punctures or type(wheel)~='number'or wheel%1~=0 or wheel<1 or wheel>4 then return false end
 local t=s.tyres[wheel];local fresh=not t.punctured;t.punctured=true;t.wear=math.max(t.wear,.5);return fresh
end
-- Impact speed is the relative component into an obstacle, not vehicle speed.
-- Side -1/+1 selects left/right damage; zero is a frontal impact.
function D.impact(s,speed,side,car,severity)
 equip(s,car)
 if not finite(speed)or speed<5 then return 0 end
 side=finite(side)and math.clamp(side,-1,1)or 0
 severity=finite(severity)and math.clamp(severity,.1,3)or 1
 local energy=math.clamp(((speed*.28)^2-1.9)/tune(car,'DamageEnergy')*severity,0,.95)
 s.crashes=(s.crashes or 0)+1;s.impactId=(s.impactId or 0)+1;s.impact=1;s.impactSpeed=speed;s.impactSide=side
 if not s.settings.damage then return 0 end
 s.damage=math.clamp((s.damage or 0)+energy*62,0,100)
 local h=s.health
 h.engine=math.max(.08,h.engine-energy*(math.abs(side)<.3 and .75 or .28))
 h.brakes=math.max(.3,h.brakes-energy*.28);h.suspension=math.max(.18,h.suspension-energy*.7)
 h.steering=math.max(.25,h.steering-energy*.55);s.alignment=math.clamp((s.alignment or 0)+side*energy*.12,-.2,.2)
 s.engineHealth=h.engine
 if energy>tune(car,'PunctureImpact')and s.settings.punctures then D.puncture(s,side<0 and 1 or side>0 and 2 or (s.crashes%2==0 and 1 or 2),car)end
 s.terminal=energy>.82 or h.engine<=.1
 return energy
end
function D.repair(s,mode,car)
 equip(s,car)
 if mode=='tyres'or mode=='all'or mode=='service'then
  for _,t in ipairs(s.tyres)do t.punctured=false;t.pressure=t.targetPressure;t.wear=0 end
 end
 if mode=='all'or mode=='service'then
  s.health={engine=1,brakes=1,suspension=1,steering=1};s.damage=0;s.alignment=0;s.terminal=false;s.engineHealth=1
 end
 s.impact=0;s.impactSpeed=0
end
local function tyreGrip(t,ambient,wetness,off,surface)
 -- Underinflation trades small loose-surface compliance against heat and damage.
 local target=surface=='tarmac'and 1 or .94
 local pressureGrip=math.clamp(1-math.abs(t.pressure-target)*.32,.65,1)
 if t.punctured then pressureGrip=math.max(.22,t.pressure*.68)end
 local optimum=surface=='tarmac'and 65 or 48
 local thermal=math.clamp(1-math.abs(t.temperature-optimum)*.0022,.72,1)
 local water=math.clamp(1-wetness*math.max(0,.95-t.pressure)*.45,.7,1)
 return pressureGrip*thermal*water*(1-t.wear*.28)
end
function D.step(s,input,route,car,dt)
 dt=math.clamp(dt,0,1/30);if dt==0 then return s end
 local p=route:point(s.z);local climate=route:conditions(s.z);equip(s,car,climate.temperature)
 local _,offset=route:ground(s.x,s.z);local off=math.abs(offset)>p.width/2+1
 local mass=car.mass or 1000;local balance=car.rearShare or .5;local wb=car.wheelbase or 7.6
 local cg=car.centreOfGravityHeight or 1.8;local track=car.track or 5.6
 local transfer=math.clamp((s.acceleration or 0)*cg/(G*wb),-.18,.18)
 local frontLoad=math.clamp(1-balance-transfer,.15,.85)
 local lateralTransfer=math.clamp((s.yawRate or 0)*s.v*cg/(G*track),-.25,.25)
 local frontGrip,rearGrip=0,0;local averageGrip=0;local flatDrag,pull=0,0
 for i,t in ipairs(s.tyres)do
  local front=i<=2;local right=i%2==0;local share=(front and frontLoad or 1-frontLoad)*.5
  local wheelShare=math.clamp(share+(right and lateralTransfer or -lateralTransfer)*.5,.025,.65)
  t.load=wheelShare*mass*9.81
  local staticShare=(front and 1-balance or balance)*.5
  local loadSensitivity=math.clamp((wheelShare/staticShare)^(-tune(car,'LoadSensitivity')),.82,1.14)
  if t.punctured then t.pressure=math.max(.1,t.pressure-dt*tune(car,'PressureLeak'))else t.pressure=approach(t.pressure,t.targetPressure*(273+t.temperature)/(273+climate.temperature),.2,dt)end
  t.grip=tyreGrip(t,climate.temperature,climate.wetness,off,p.surface)*loadSensitivity
  averageGrip+=t.grip*wheelShare
  if front then frontGrip+=t.grip*.5 else rearGrip+=t.grip*.5 end
  if t.punctured then flatDrag+=(1-t.pressure)*1.4;pull+=(right and 1 or -1)*(1-t.pressure)*.022 end
 end
 local grip=averageGrip*climate.friction*car.grip*(p.surface=='tarmac'and 1.22 or 1)*(off and .63 or 1)
 s.grip=grip;s.frontLoad=frontLoad;s.rearLoad=1-frontLoad
 local steering=car.steering or {};local request=math.clamp(input.steer or 0,-1,1)
 local steerRate=(request==0 and (steering.ReturnRate or 10)or (steering.Rate or 9))*(s.settings.damage and (.55+.45*s.health.steering)or 1)
 s.steer=approach(s.steer,request,steerRate,dt)
 local throttle=math.clamp(input.throttle or 0,-1,1);local brake=math.clamp(input.brake or 0,0,1)
 -- Digital throttle ramps over a fraction of a second, making keyboard exits controllable.
 s.pedal=approach(s.pedal or 0,throttle,throttle==0 and 14 or tune(car,'ThrottleResponse'),dt)
 local effectiveThrottle=s.terminal and 0 or s.pedal
 local engineFactor=s.settings.damage and (.35+.65*s.health.engine)or 1
 local accel=effectiveThrottle*car.accel*engineFactor*(1-.35*math.min(math.abs(s.v)/car.top,.94))
 local longitudinal=car.tyres and car.tyres.LongitudinalGrip or .8
 local tractionCap=grip*G*math.clamp(longitudinal/ .68,.75,1.3)
 local wheelspin=0;s.tcsActive=false
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
  local driveFront=car.driveFront or 0
  local weight=driveFront*frontLoad+(1-driveFront)*(1-frontLoad)
  local drivenGrip=driveFront*frontGrip+(1-driveFront)*rearGrip
  local maximum=mass*9.81*weight*1.2*climate.friction*drivenGrip
  wheelspin=math.max(0,math.abs(effectiveThrottle)*force/math.max(maximum,1)-1)
  s.tcsActive=s.settings.tractionControl and wheelspin>.05
  force=math.min(force,maximum)*(s.tcsActive and 1 or 1-math.min(wheelspin,.7)*.15)
  accel=effectiveThrottle*force/mass/.28*engineFactor
 end
 if throttle<0 and s.v>2 then accel=-58 end
 if throttle>0 and s.v< -2 then accel=45 end
 local drag=(.72+.0011*(car.drag and car.drag.Air/.00024 or 1)*s.v*s.v+(off and 8 or 0)+flatDrag)*(s.v<0 and -1 or 1)
 if math.abs(s.v)<.3 and throttle==0 then s.v=0;drag=0 end
 s.throttle=throttle;s.brake=brake;s.handbrake=input.handbrake==true
 local brakeHealth=s.settings.damage and (.4+.6*s.health.brakes)or 1
 local fade=math.clamp(1-math.max(0,s.brakeTemperature-430)/700,.45,1)
 local brakeForce=(car.brakes and car.brakes.Force or 66)*brakeHealth*fade
 s.absActive=s.settings.abs and brake*brakeForce>tractionCap
 local locked=not s.settings.abs and brake*brakeForce>tractionCap*1.05 and math.abs(s.v)>8
 local braking=brake*math.min(brakeForce,tractionCap)*(s.v<0 and -1 or 1)
 local nextV=s.v+(accel-drag-braking-p.dy*20)*dt
 if brake>0 and (math.abs(s.v)<1.5 or s.v*nextV<0)then nextV=0 end
 s.acceleration=(nextV-s.v)/dt
 s.v=math.clamp(nextV,-23,car.top*(off and .68 or 1))
 local steerAngle=(s.steer+(s.settings.damage and (s.alignment or 0)or 0)+pull)*math.rad(steering.MaxAngle or 31)/(1+math.abs(s.v)/95)
 local response=math.clamp(frontLoad/(1-balance),.7,1.25)*math.clamp(frontGrip/math.max(rearGrip,.2),.65,1.25)
 if locked then response*=.48 end
 local yawRate=s.v/wb*math.tan(steerAngle)*response
 local demand=math.clamp(math.abs(accel-braking)/(grip*tune(car,'CorneringScale')),0,.95)
 local limit=grip*tune(car,'CorneringScale')*math.sqrt(1-demand*demand)/math.max(math.abs(s.v),10)
 local excess=yawRate-math.clamp(yawRate,-limit,limit)
 yawRate=math.clamp(yawRate,-limit,limit)+excess*.12
 local stability=s.settings.stabilityAssist
 local slideRate=input.handbrake and 2.1 or (4+2*stability)*grip
 local slideTarget=excess*math.abs(s.v)*.22*(1.25-.5*stability)
 s.lateralV=approach(s.lateralV,slideTarget,slideRate,dt)
 s.lateralV+=climate.wind*.002*dt
 if input.handbrake then yawRate*=1.2;s.v*=math.exp(-.65*dt)end
 -- Countersteer assist damps a developing slide without steering along the route.
 local assist=s.settings.steeringAssist
 yawRate+=math.clamp(s.lateralV/math.max(math.abs(s.v),10),-.2,.2)*assist*.12
 s.yawRate=yawRate;s.yaw=wrap(s.yaw-yawRate*dt)
 local forwardX,forwardZ=math.sin(s.yaw),math.cos(s.yaw)
 s.x+=(forwardX*s.v+forwardZ*s.lateralV)*dt
 local advance=(forwardZ*s.v-forwardX*s.lateralV)*dt
 if route.original then
  advance/=math.clamp(1-p.curvature*s.x,.5,1.5)
  s.yaw=wrap(s.yaw-p.curvature*advance)
 end
 s.z+=advance
 local _,lateral,newPoint=route:ground(s.x,s.z)
 s.impact=math.max(0,(s.impact or 0)-dt*2)
 local barrier=newPoint.bridge or newPoint.tunnel;local bound=newPoint.width/2-3.1
 if barrier and math.abs(lateral)>bound then
  local sign=lateral<0 and -1 or 1
  s.x=newPoint.x+sign*bound*math.sqrt(1+newPoint.dx*newPoint.dx)
  local relative=wrap(s.yaw-newPoint.heading)
  local hit=math.abs(math.sin(relative)*s.v)+math.abs(s.lateralV)
  if hit>5 and s.impact<=0 then D.impact(s,hit,sign,car)end
  s.yaw=approach(s.yaw,newPoint.heading,.8,dt);s.lateralV=0;s.v*=math.exp(-2*dt)
 elseif math.abs(lateral)>newPoint.width/2+14 then s.v*=math.exp(-1.8*dt)end
 local ty,pt,rl=D.contactPose(s,route,car)
 local suspension=car.suspension or {};local travel=suspension.Travel or 1.2
 local springHealth=s.settings.damage and s.health.suspension or 1
 local omega=tune(car,'BodyFrequency')/(1+travel*.3)*(.8+.2*springHealth)
 local bump=suspension.Bump or .4;local rebound=suspension.Rebound or .55
 s.bodyY=s.bodyY or ty;s.bodyV=s.bodyV or 0
 local compression=ty-s.bodyY
 local damping=math.clamp((compression>0 and bump or rebound)*1.7,.35,1.3)
 local stop=math.max(0,compression-travel*(suspension.BumpStopFrom or .88))*(suspension.BumpStopRate or 6)
 s.bodyV+=(omega*omega*compression+stop-2*damping*omega*s.bodyV)*dt
 s.bodyY=math.clamp(s.bodyY+s.bodyV*dt,ty-travel*.4,ty+travel*.65)
 s.pitch=approach(s.pitch or pt,pt+math.clamp((accel-braking)*.0006,-.06,.06),omega,dt)
 local antiroll=suspension.AntiRoll or {};local rollSupport=((antiroll.Front or .5)+(antiroll.Rear or .5))*.5
 s.roll=approach(s.roll or rl,rl+math.clamp(yawRate*s.v*.0007*(1.25-rollSupport*.5),-.09,.09),omega,dt)
 local tyreTemp=0;local speed=math.abs(s.v)
 for i,t in ipairs(s.tyres)do
  local drive=i<=2 and (car.driveFront or 0)or 1-(car.driveFront or 0)
  t.slip=math.abs(excess)*speed*.06+wheelspin*drive+(locked and brake or 0)+(input.handbrake and i>2 and .6 or 0)
  local heat=climate.temperature+speed*.28+t.slip*35+(1-t.pressure)*speed*.8
  t.temperature=approach(t.temperature,math.min(180,heat),tune(car,'TyreHeatRate')+(climate.wetness or 0)*.1,dt)
  t.compression=math.clamp(.5+compression/math.max(travel,.1),0,1)
  if s.settings.damage then
   t.wear=math.clamp(t.wear+dt*tune(car,'WearRate')*(speed*.0000015+t.slip*.00015)*(1+math.max(0,t.temperature-100)*.02),0,1)
   -- Repeated fast rough-shoulder abuse and worn tyres cause deterministic leaks.
   t.stress=(t.stress or 0)+dt*(off and speed>55 and (speed-55)*.003*(1.5-t.pressure)or -.3)
   t.stress=math.max(0,t.stress)
   if s.settings.punctures and (t.stress>7+i*.4 or t.wear>.985)then D.puncture(s,i,car)end
  end
  tyreTemp+=t.temperature*.25
 end
 s.tyreTemperature=tyreTemp;s.brakeTemperature=approach(s.brakeTemperature,climate.temperature+brake*speed*6,.08,dt)
 s.engineTemperature=approach(s.engineTemperature,78+math.abs(effectiveThrottle)*20+math.max(0,1-s.health.engine)*35,.035,dt)
 s.distance+=speed*dt
 return s
end
function D.telemetry(s)
 equip(s)
 local flats=0;local minPressure=2;local wear=0
 for _,t in ipairs(s.tyres)do if t.punctured then flats+=1 end;minPressure=math.min(minPressure,t.pressure);wear=math.max(wear,t.wear)end
 return {punctures=flats,pressure=minPressure,wear=wear,temperature=s.tyreTemperature or 20,engine=s.health.engine,brakes=s.health.brakes,suspension=s.health.suspension,steering=s.health.steering,terminal=s.terminal==true,grip=s.grip or 1}
end
function D.contactPose(s,route,car)
 local wb=car and car.wheelbase or 7.6;local rearShare=car and car.rearShare or .5
 local fX,fZ=math.sin(s.yaw),math.cos(s.yaw)
 local frontArm=wb*rearShare;local backArm=wb*(1-rearShare)
 local front=route:ground(s.x+fX*frontArm,s.z+fZ*frontArm)
 local back=route:ground(s.x-fX*backArm,s.z-fZ*backArm)
 local track=car and car.track or 5.6
 local left=route:ground(s.x+fZ*track*.5,s.z-fX*track*.5)
 local right=route:ground(s.x-fZ*track*.5,s.z+fX*track*.5)
 if s.tyres then
  local radius=(car and car.radius or 1.2)*.42
  local a=math.max(0,1-s.tyres[1].pressure)*radius;local b=math.max(0,1-s.tyres[2].pressure)*radius
  local c=math.max(0,1-s.tyres[3].pressure)*radius;local d=math.max(0,1-s.tyres[4].pressure)*radius
  front-=(a+b)*.5;back-=(c+d)*.5;left-=(a+c)*.5;right-=(b+d)*.5
 end
 return front*(1-rearShare)+back*rearShare+(car and car.rideHeight or 2.2),math.atan2(front-back,wb),math.atan2(right-left,track)
end
function D.pose(s,route,car)
 if s.bodyY then return s.bodyY,s.pitch or 0,s.roll or 0 end
 return D.contactPose(s,route,car)
end
function D.reset(s,route,z)
 local p=route:point(z);s.x=p.x;s.z=z;s.yaw=p.heading;s.v=0;s.lateralV=0;s.steer=0;s.impact=0;s.bodyY=nil;s.bodyV=0;s.pitch=nil;s.roll=nil;s.acceleration=0;s.yawRate=0;s.pedal=0
end
return D
