-- Independent route maths. X/Z are Roblox horizontal axes, Y is height.
local Route={}
Route.__index=Route
local sqrt,abs,min,max=math.sqrt,math.abs,math.min,math.max
local function lerp(a,b,t)return a+(b-a)*t end
local function distance(a,b)return sqrt((a.x-b.x)^2+(a.z-b.z)^2)end
local function copy(p)return {x=p.x,y=p.y,z=p.z,speed=p.speed,steer=p.steer,t=p.t,surface=p.surface,width=p.width}end
function Route.new(points,meta)
    assert(#points>=2,"A route needs at least two positions")
    local self=setmetatable({points={},meta=meta or {},length=0},Route)
    for _,p in ipairs(points)do
        if #self.points==0 or distance(p,self.points[#self.points])>.15 then
            local q=copy(p)
            if #self.points>0 then self.length=self.length+distance(q,self.points[#self.points])end
            q.s=self.length;self.points[#self.points+1]=q
        end
    end
    assert(#self.points>=2,"The route has no travel")
    self.grid={}
    for i,p in ipairs(self.points)do
        local a,b=self.points[max(1,i-2)],self.points[min(#self.points,i+2)]
        local dx,dz=b.x-a.x,b.z-a.z
        local len=sqrt(dx*dx+dz*dz)
        p.fx,p.fz=dx/max(len,1e-8),dz/max(len,1e-8)
        local aa,bb,cc=distance(a,p),distance(p,b),distance(a,b)
        p.k=aa*bb*cc>1e-8 and 2*((p.x-a.x)*(b.z-a.z)-(p.z-a.z)*(b.x-a.x))/(aa*bb*cc)or 0
        local key=math.floor(p.x/40)..":"..math.floor(p.z/40)
        self.grid[key]=self.grid[key]or {};table.insert(self.grid[key],i)
    end
    return self
end
function Route.fromShowcase(rows,meta)
    local points={}
    for _,r in ipairs(rows)do points[#points+1]={t=r[1],x=r[2],y=r[3],z=r[4],speed=abs(r[5]),steer=r[6]}end
    return Route.new(points,meta)
end
function Route.fromStage(stage)
    local x,y,z=unpack(stage.Origin)
    local heading=math.rad(stage.Heading or 0)
    local points={{x=x,y=y,z=z,width=stage.Width,surface=stage.Surface}}
    for _,segment in ipairs(stage.segments)do
        local curvature=segment.Straight and 0 or(segment.Turn=="Right"and 1 or -1)/segment.Radius
        local length=segment.Straight or segment.Radius*math.rad(segment.Angle)
        local steps=max(1,math.ceil(length))
        local step=length/steps;local baseY=y
        for i=1,steps do
            heading=heading+curvature*step
            x=x+math.sin(heading)*step;z=z-math.cos(heading)*step
            local t=i/steps
            y=baseY+(segment.Rise or 0)*t*t*(3-2*t)
            if i%4==0 or i==steps then
                points[#points+1]={x=x,y=y,z=z,width=stage.Width,surface=segment.Surface or stage.Surface}
            end
        end
    end
    return Route.new(points,{source="stage",stage=stage.Id})
end
function Route.constrain(line,base,width,halfWidth,features)
    local points={};local hint
    for _,point in ipairs(line.points)do
        local n=base:nearest(point,hint);hint=n.index
        local p=copy(point)
        local localWidth=width
        for _,f in ipairs(features or {})do
            if(f.Kind=="Bridge"or f.Kind=="Narrow")and f.From and f.To and f.Width
                and n.s>=f.From-6 and n.s<=f.To+6 then localWidth=min(localWidth,f.Width)end
        end
        local margin=max(1,localWidth*.5-halfWidth-1.25)
        if abs(n.lateral)>margin then
            local road=base:at(n.s);local side=math.clamp(n.lateral,-margin,margin)
            p.x=road.x-road.fz*side;p.z=road.z+road.fx*side
        end
        points[#points+1]=p
    end
    return Route.new(points,line.meta)
end
function Route:indexAt(s)
    local lo,hi=1,#self.points
    while lo<hi do
        local middle=math.floor((lo+hi+1)/2)
        if self.points[middle].s<=s then lo=middle else hi=middle-1 end
    end
    return min(lo,#self.points-1)
end
function Route:at(s)
    s=math.clamp(s,0,self.length)
    local i=self:indexAt(s);local a,b=self.points[i],self.points[i+1]
    local t=math.clamp((s-a.s)/max(b.s-a.s,1e-8),0,1)
    return {x=lerp(a.x,b.x,t),y=lerp(a.y,b.y,t),z=lerp(a.z,b.z,t),s=s,
        fx=lerp(a.fx,b.fx,t),fz=lerp(a.fz,b.fz,t),k=lerp(a.k,b.k,t),
        speed=a.speed and b.speed and lerp(a.speed,b.speed,t)or nil,
        steer=a.steer and b.steer and lerp(a.steer,b.steer,t)or 0,
        surface=a.surface or b.surface,width=a.width or b.width}
end
function Route:nearest(position,hint)
    local best,bestCost=nil,math.huge
    local tested={}
    local function test(i)
        i=math.clamp(i,1,#self.points-1)
        if tested[i]then return end;tested[i]=true
        local a,b=self.points[i],self.points[i+1]
        local dx,dz=b.x-a.x,b.z-a.z
        local t=math.clamp(((position.x-a.x)*dx+(position.z-a.z)*dz)/max(dx*dx+dz*dz,1e-8),0,1)
        local x,y,z=lerp(a.x,b.x,t),lerp(a.y,b.y,t),lerp(a.z,b.z,t)
        local cost=(position.x-x)^2+(position.z-z)^2+(position.y-y)^2*.7
        if hint and abs(i-hint)>100 then cost=cost+30 end
        if cost<bestCost then
            bestCost=cost;best={index=i,s=lerp(a.s,b.s,t),x=x,y=y,z=z,
                lateral=((position.x-x)*(-a.fz)+(position.z-z)*a.fx),height=position.y-y}
        end
    end
    if hint then for i=hint-12,hint+55 do test(i)end end
    if not best or bestCost>30^2 then
        local gx,gz=math.floor(position.x/40),math.floor(position.z/40)
        for x=gx-2,gx+2 do for z=gz-2,gz+2 do
            for _,i in ipairs(self.grid[x..":"..z]or {})do test(i-1);test(i)end
        end end
    end
    if not best or bestCost>300^2 then for i=1,#self.points-1 do test(i)end end
    best.distance=sqrt((position.x-best.x)^2+(position.z-best.z)^2)
    return best
end
function Route:targetSpeed(s,cap,grip,braking,pace)
    local desired=cap
    local horizon=min(self.length,s+max(160,cap*2.2))
    for ahead=s,horizon,6 do
        local p=self:at(ahead)
        local corner=sqrt(max(grip,5)/max(abs(p.k),.00001))
        local reference=p.speed and max(8,p.speed)*(pace or 1)or cap
        local limit=min(cap,corner,reference)
        desired=min(desired,sqrt(limit^2+2*braking*max(ahead-s-5,0)))
    end
    return desired
end
return Route
