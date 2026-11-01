-- Quantized, paged CSV data; no executable replay content. ~25 KB / 50 s page.
local R={}
local function round(n)return math.floor(n+.5)end
function R.frame(t,s,flags,input)
 input=input or {}
 local f={round(t*1000),round(s.x*20),round(s.z*20),round(s.yaw*10000),round(s.v*10),round(s.steer*1000),round(s.damage*10),flags or 0,round((input.throttle or 0)*1000),round((input.brake or 0)*1000),input.handbrake and 1 or 0}
 if s.bodyY then f[12]=round(s.bodyY*1000);f[13]=round((s.pitch or 0)*10000);f[14]=round((s.roll or 0)*10000)end
 return f
end
function R.encode(frames)
 local rows={}
 for i,f in ipairs(frames)do rows[i]=table.concat(f,',')end
 return table.concat(rows,'\n')
end
function R.decode(text)
 assert(type(text)=='string'and #text<=100000,'Invalid replay page')
 local frames={};local previous=-1
 for line in text:gmatch('[^\n]+')do
  local f={};for value in line:gmatch('[^,]+')do f[#f+1]=tonumber(value)end
  assert(#f==11 or #f==14,'Invalid replay frame')
  for _,n in ipairs(f)do assert(n==n and math.abs(n)<1e12 and n==math.floor(n),'Invalid replay number')end
  assert(f[1]>=previous and f[8]>=0 and f[8]<=1,'Invalid replay chronology')
  assert(math.abs(f[9])<=1000 and f[10]>=0 and f[10]<=1000 and (f[11]==0 or f[11]==1),'Invalid recorded controls')
  previous=f[1];frames[#frames+1]=f;assert(#frames<=500,'Oversized replay page')
 end
 return frames
end
function R.state(f)
 local s={x=f[2]/20,z=f[3]/20,yaw=f[4]/10000,v=f[5]/10,steer=f[6]/1000,damage=f[7]/10,lateralV=0,distance=0,crashes=0,impact=0,throttle=f[9]/1000,brake=f[10]/1000,handbrake=f[11]==1}
 if f[12]then s.bodyY=f[12]/1000;s.pitch=f[13]/10000;s.roll=f[14]/10000 end
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
 for _,k in ipairs({'x','z','v','steer','damage'})do s[k]+=(nextState[k]-s[k])*f end
 for _,k in ipairs({'bodyY','pitch','roll'})do if s[k]and nextState[k]then s[k]+=(nextState[k]-s[k])*f end end
 local delta=(nextState.yaw-s.yaw+math.pi)%(2*math.pi)-math.pi;s.yaw+=delta*f
 return s
end
return R
