-- Quantized CSV pages, never executable replay content. New condition frames
-- have 35 fields; earlier 11/14-field recordings remain readable.
local R={}
local NO_POSE=99999999999
local function round(n)return math.floor(n+.5)end
local function lerp(a,b,f)return a+(b-a)*f end
function R.frame(t,s,flags,input)
 input=input or {}
 local f={round(t*1000),round(s.x*20),round(s.z*20),round(s.yaw*10000),round(s.v*10),round(s.steer*1000),round(s.damage*10),flags or 0,round((input.throttle or 0)*1000),round((input.brake or 0)*1000),input.handbrake and 1 or 0}
 f[12]=s.bodyY and round(s.bodyY*1000)or NO_POSE;f[13]=round((s.pitch or 0)*10000);f[14]=round((s.roll or 0)*10000)
 local mask=0
 for i=1,4 do
  local tyre=s.tyres and s.tyres[i]
  f[14+i]=round((tyre and tyre.pressure or 1)*1000)
  f[18+i]=round((tyre and tyre.wear or 0)*10000)
  if tyre and tyre.punctured then mask+=2^(i-1)end
 end
 f[23]=mask;f[24]=s.gear or 1;f[25]=round(s.rpm or 850)
 local health=s.health or {}
 for i,key in ipairs({'engine','brakes','suspension','steering'})do f[25+i]=round((health[key]or 1)*1000)end
 f[30]=s.impactId or s.crashes or 0;f[31]=round((s.impactSpeed or 0)*10);f[32]=round((s.impactSide or 0)*1000)
 f[33]=(s.terminal and 2048 or 0)+round(math.clamp(s.impact or 0,0,1)*1000)
 f[34]=round((s.tyreTemperature or 20)*10);f[35]=round((s.brakeTemperature or 20)*10)
 return f
end
function R.encode(frames)
 assert(#frames<=500,'Oversized replay page')
 local rows={};for i,f in ipairs(frames)do rows[i]=table.concat(f,',')end
 local text=table.concat(rows,'\n');assert(#text<=100000,'Oversized replay page');return text
end
function R.decode(text)
 assert(type(text)=='string'and #text<=100000,'Invalid replay page')
 local frames={};local previous=-1
 for line in text:gmatch('[^\n]+')do
  assert(not line:find(',,',1,true)and line:sub(1,1)~=','and line:sub(-1)~=',','Missing replay field')
  local f={}
  for value in line:gmatch('[^,]+')do
   local n=tonumber(value);assert(n and n==n and math.abs(n)<1e12 and n==math.floor(n),'Invalid replay number');f[#f+1]=n
  end
  assert(#f==11 or #f==14 or #f==35,'Invalid replay frame')
  assert(f[1]>=previous and f[8]>=0 and f[8]<=1,'Invalid replay chronology')
  assert(math.abs(f[9])<=1000 and f[10]>=0 and f[10]<=1000 and (f[11]==0 or f[11]==1),'Invalid recorded controls')
  if #f==35 then
   for i=15,18 do assert(f[i]>=0 and f[i]<=2000,'Invalid tyre pressure')end
   for i=19,22 do assert(f[i]>=0 and f[i]<=10000,'Invalid tyre wear')end
   assert(f[23]>=0 and f[23]<=15 and f[24]>=0 and f[24]<=20 and f[25]>=0 and f[25]<=50000,'Invalid tyre mask or drivetrain')
   for i=26,29 do assert(f[i]>=0 and f[i]<=1000,'Invalid component health')end
   assert(f[30]>=0 and f[30]<=1e9 and f[31]>=0 and f[31]<=100000 and math.abs(f[32])<=1000,'Invalid crash record')
   assert(f[33]>=0 and f[33]<4096 and f[33]%2048<=1000,'Invalid crash flags')
   assert(f[34]>=-1000 and f[34]<=3000 and f[35]>=-1000 and f[35]<=15000,'Invalid recorded temperature')
  end
  previous=f[1];frames[#frames+1]=f;assert(#frames<=500,'Oversized replay page')
 end
 return frames
end
function R.state(f)
 local s={x=f[2]/20,z=f[3]/20,yaw=f[4]/10000,v=f[5]/10,steer=f[6]/1000,damage=f[7]/10,lateralV=0,distance=0,crashes=0,impact=0,impactId=0,impactSpeed=0,impactSide=0,terminal=false,throttle=f[9]/1000,brake=f[10]/1000,handbrake=f[11]==1}
 if f[12]and f[12]~=NO_POSE then s.bodyY=f[12]/1000;s.pitch=f[13]/10000;s.roll=f[14]/10000 end
 local modern=#f==35
 s.tyres={};s.tyreTemperature=modern and f[34]/10 or 20;s.brakeTemperature=modern and f[35]/10 or 20
 for i=1,4 do
  local pressure=modern and f[14+i]/1000 or 1
  s.tyres[i]={pressure=pressure,targetPressure=pressure,wear=modern and f[18+i]/10000 or 0,punctured=modern and math.floor(f[23]/2^(i-1))%2==1 or false,temperature=s.tyreTemperature,load=0,slip=0,grip=1,compression=0}
 end
 s.health={};for i,key in ipairs({'engine','brakes','suspension','steering'})do s.health[key]=modern and f[25+i]/1000 or 1 end
 s.gear=modern and f[24]or 1;s.rpm=modern and f[25]or 850;s.engineHealth=s.health.engine
 if modern then s.impactId=f[30];s.crashes=f[30];s.impactSpeed=f[31]/10;s.impactSide=f[32]/1000;s.terminal=f[33]>=2048;s.impact=f[33]%2048/1000 end
 return s
end
function R.sample(frames,t)
 if #frames==0 then return nil end
 local ms=t*1000;local lo,hi=1,#frames
 while lo<hi do local mid=math.floor((lo+hi+1)/2);if frames[mid][1]<=ms then lo=mid else hi=mid-1 end end
 local a,b=frames[lo],frames[math.min(lo+1,#frames)]
 if b[8]==1 and ms<b[1]then return R.state(a)end
 local f=math.clamp((ms-a[1])/math.max(1,b[1]-a[1]),0,1)
 local s=R.state(a);local nextState=R.state(b)
 for _,k in ipairs({'x','z','v','steer'})do s[k]=lerp(s[k],nextState[k],f)end
 -- Crash damage arrives with the recorded impact; it cannot dent the car early.
 local sameImpact=s.impactId==nextState.impactId
 if sameImpact or #a<35 or #b<35 then
  s.damage=lerp(s.damage,nextState.damage,f)
  for key,value in pairs(s.health)do s.health[key]=lerp(value,nextState.health[key],f)end
 end
 s.engineHealth=s.health.engine
 for _,k in ipairs({'bodyY','pitch','roll'})do if s[k]and nextState[k]then s[k]=lerp(s[k],nextState[k],f)end end
 for _,k in ipairs({'rpm','tyreTemperature','brakeTemperature'})do s[k]=lerp(s[k],nextState[k],f)end
 for i,tyre in ipairs(s.tyres)do
  local following=nextState.tyres[i]
  -- Puncture/repair is discrete; hold all wheel conditions until that frame.
  if tyre.punctured==following.punctured then
   tyre.pressure=lerp(tyre.pressure,following.pressure,f);tyre.wear=lerp(tyre.wear,following.wear,f)
  end
  tyre.temperature=s.tyreTemperature
 end
 if sameImpact then s.impact=lerp(s.impact,nextState.impact,f)end
 local delta=(nextState.yaw-s.yaw+math.pi)%(2*math.pi)-math.pi;s.yaw+=delta*f
 return s
end
return R
