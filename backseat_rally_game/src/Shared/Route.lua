-- Continuous, forward-monotone roads: no self-crossings, jumps, or blocked lanes.
local Route={};Route.__index=Route
local sin,cos,sqrt=math.sin,math.cos,math.sqrt
local function hash(seed,index)
 local value=(seed+(index+19)*104729)%2147483647
 for _=1,3 do value=(value*48271)%2147483647 end
 return value
end
function Route.random(seed,index)return hash(seed,index)/2147483647 end
function Route.new(seed,length,config)
 seed=math.floor(tonumber(seed)or 1)%1000000000
 local self=setmetatable({seed=seed,length=length or 0,config=config},Route)
 self.p1=Route.random(seed,1)*math.pi*2;self.p2=Route.random(seed,2)*math.pi*2
 self.p3=Route.random(seed,3)*math.pi*2
 self.a=90+Route.random(seed,5)*30;self.b=18+Route.random(seed,7)*8
 self.f=1/(220+Route.random(seed,8)*80);self.g=1/(62+Route.random(seed,9)*22)
 self.x0=self.a*sin(self.p1)+self.b*sin(self.p2)
 self.y0=11*sin(self.p3)
 return self
end
function Route:point(z)
 local c=self.config;local a,b,f,g=self.a,self.b,self.f,self.g
 -- Fade elevation into a flat starting apron, with zero derivative at z=0.
 local fade=math.clamp(z/160,0,1);local ease=fade*fade*(3-2*fade)
 local dease=(z>0 and z<160)and 6*fade*(1-fade)/160 or 0
 local rough=.35*sin(z/14+self.p1)+.2*sin(z/23+self.p2)
 local roughSlope=.35/14*cos(z/14+self.p1)+.2/23*cos(z/23+self.p2)
 local raw=rough+11*sin(z/280+self.p3)-self.y0+5*sin(z/510)
 local dy=(roughSlope+11/280*cos(z/280+self.p3)+5/510*cos(z/510))*ease+raw*dease
 local x=a*sin(f*z+self.p1)+b*sin(g*z+self.p2)-self.x0
 local dx=a*f*cos(f*z+self.p1)+b*g*cos(g*z+self.p2)
 local ddx=-a*f*f*sin(f*z+self.p1)-b*g*g*sin(g*z+self.p2)
 local chunk=math.floor(math.max(0,z)/c.Chunk)
 local biome=(math.floor(chunk/8)+self.seed%4)%4+1
 local bridge=chunk%17==10;local tunnel=chunk%19==14
 local bank=math.clamp(-ddx*6,-.055,.055)
 return {x=x,y=8+raw*ease,z=z,dx=dx,dy=dy,heading=math.atan2(dx,1),
  curvature=ddx/(1+dx*dx)^1.5,bank=bank,width=c.RoadWidth,biome=biome,
  bridge=bridge,tunnel=tunnel,chunk=chunk,surface=(biome==4 or tunnel)and 'tarmac'or 'gravel'}
end
function Route:ground(x,z)
 local p=self:point(z);local lateral=(x-p.x)/sqrt(1+p.dx*p.dx)
 local shoulder=math.max(0,math.abs(lateral)-p.width/2)
 return p.y+lateral*math.tan(p.bank)-math.min(shoulder*.13,3),lateral,p
end
function Route:conditions(z)
 local biome=self:point(z).biome
 local cfg=self.config.Climate or {dryWetness=.08,rainWetness=.45,wetGripLoss=.24,windSpeed=3}
 local wet=self.seed%3==0 and cfg.rainWetness or cfg.dryWetness
 return {temperature=biome==2 and -3 or(biome==3 and 32 or 18),wetness=wet,
  wind=math.sin(self.p1+z/1800)*cfg.windSpeed,friction=(biome==2 and .82 or 1)*(1-wet*cfg.wetGripLoss)}
end
function Route:call(z,speed)
 local lead=math.max(55,math.abs(speed or 0)*2.5)
 local at=z+lead;local p=self:point(at)
 local direction=math.abs(p.curvature)<.0013 and '↑'or(p.curvature>0 and '←'or '→')
 return direction..'  '..self:note(at-100)..string.format(' · %d m',math.floor(lead*.28+.5))
end
function Route:note(z)
 local p=self:point(z+100);local k=p.curvature
 if p.tunnel then return 'TUNNEL · keep the line' end
 if p.bridge then return 'BRIDGE · stay tidy' end
 if math.abs(k)<.0013 then return 'STRAIGHT · opens' end
 local severity=math.abs(k)>.004 and '3' or '5'
 return (k>0 and 'LEFT 'or 'RIGHT ')..severity..' · '..(math.abs(k)>.004 and 'tightens'or 'flow')
end
function Route:key(mode,car)return table.concat({self.config.Generation,mode,self.seed,self.length,car},':')end
return Route
