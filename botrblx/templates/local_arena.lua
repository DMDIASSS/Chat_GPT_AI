-- Analytic collision volume, in simulation units. Visual Roblox parts have
-- CanQuery=false; Workspace raycasts or decorative mesh bounds are not physics.
local Arena={}
Arena.__index=Arena
local abs,min,max,sqrt=math.abs,math.min,math.max,math.sqrt
local function length(v)return sqrt(v[1]^2+v[2]^2+v[3]^2)end
local function dot(a,b)return a[1]*b[1]+a[2]*b[2]+a[3]*b[3]end
local function cross(a,b)return {a[2]*b[3]-a[3]*b[2],a[3]*b[1]-a[1]*b[3],a[1]*b[2]-a[2]*b[1]}end
local function addScaled(p,v,k)return {p[1]+v[1]*k,p[2]+v[2]*k,p[3]+v[3]*k}end
local function sign(x)return x<0 and -1 or 1 end

function Arena.new(profile)
    local self=setmetatable({profile=profile,facets={},preset="standard",hitboxVerified=false},Arena)
    for i=1,#profile.ramp_facets_degrees-1 do
        local lo,hi=math.rad(profile.ramp_facets_degrees[i]),math.rad(profile.ramp_facets_degrees[i+1])
        self.facets[i]={math.cos((lo+hi)/2),math.sin((lo+hi)/2),math.cos((hi-lo)/2)}
    end
    local a=profile.arena
    self.sideCenter={a.EXTENT_X-a.SIDE_CORNER_RADIUS,0}
    self.sideCenter[2]=a.CORNER-self.sideCenter[1]-a.SIDE_CORNER_RADIUS*sqrt(2)
    self.backCenter={0,a.EXTENT_Y-a.BACK_CORNER_RADIUS}
    self.backCenter[1]=a.CORNER-self.backCenter[2]-a.BACK_CORNER_RADIUS*sqrt(2)
    self.tangent1={self.sideCenter[1]+a.SIDE_CORNER_RADIUS/sqrt(2),self.sideCenter[2]+a.SIDE_CORNER_RADIUS/sqrt(2)}
    self.tangent2={self.backCenter[1]+a.BACK_CORNER_RADIUS/sqrt(2),self.backCenter[2]+a.BACK_CORNER_RADIUS/sqrt(2)}
    local h=a.MOUTH_HEIGHT-132.496-256
    local dx=(.3185*h+sqrt(.10144225*h*h-1.10144225*(h*h-57600)))/1.10144225
    self.netCorner={640+dx,256+h-.3185*dx}
    return self
end

function Arena:corner(x,z,r)
    local dx,dz=max(r-x,0),max(r-z,0)
    if dx>0 and dz>0 then
        local best=math.huge
        for _,f in ipairs(self.facets)do best=min(best,r*f[3]-dx*f[1]-dz*f[2])end
        return best
    end
    return min(x,z)
end

function Arena:plan(x,y)
    local a=self.profile.arena
    local best,bx,by,ramp=math.huge,0,0,a.EDGE_RADIUS
    local function take(px,py,nx,ny,r)
        local distance=(x-px)^2+(y-py)^2
        if distance<best then best,bx,by,ramp=distance,nx,ny,r end
    end
    take(a.EXTENT_X,math.clamp(y,0,self.sideCenter[2]),1,0,a.EDGE_RADIUS)
    local theta=math.clamp(math.atan2(y-self.sideCenter[2],x-self.sideCenter[1]),0,math.pi/4)
    take(self.sideCenter[1]+a.SIDE_CORNER_RADIUS*math.cos(theta),self.sideCenter[2]+a.SIDE_CORNER_RADIUS*math.sin(theta),math.cos(theta),math.sin(theta),a.EDGE_RADIUS)
    local dx,dy=self.tangent2[1]-self.tangent1[1],self.tangent2[2]-self.tangent1[2]
    local t=math.clamp(((x-self.tangent1[1])*dx+(y-self.tangent1[2])*dy)/(dx*dx+dy*dy),0,1)
    take(self.tangent1[1]+t*dx,self.tangent1[2]+t*dy,1/sqrt(2),1/sqrt(2),a.EDGE_RADIUS)
    theta=math.clamp(math.atan2(y-self.backCenter[2],x-self.backCenter[1]),math.pi/4,math.pi/2)
    local blend=math.clamp((math.pi/2-theta)/(math.pi/4),0,1)
    local r=a.BACK_RAMP_RADIUS+(a.EDGE_RADIUS-a.BACK_RAMP_RADIUS)*(blend+.3*blend*(1-blend))
    take(self.backCenter[1]+a.BACK_CORNER_RADIUS*math.cos(theta),self.backCenter[2]+a.BACK_CORNER_RADIUS*math.sin(theta),math.cos(theta),math.sin(theta),r)
    take(math.clamp(x,0,self.backCenter[1]),a.EXTENT_Y,0,1,a.BACK_RAMP_RADIUS)
    local inside=x<=a.EXTENT_X and y<=a.EXTENT_Y and x+y<=a.CORNER
    if inside and x>self.sideCenter[1]then
        theta=math.atan2(y-self.sideCenter[2],x-self.sideCenter[1])
        if theta>=0 and theta<=math.pi/4 and(x-self.sideCenter[1])^2+(y-self.sideCenter[2])^2>a.SIDE_CORNER_RADIUS^2 then inside=false end
    end
    if inside and y>self.backCenter[2]then
        theta=math.atan2(y-self.backCenter[2],x-self.backCenter[1])
        if theta>=math.pi/4 and theta<=math.pi/2 and(x-self.backCenter[1])^2+(y-self.backCenter[2])^2>a.BACK_CORNER_RADIUS^2 then inside=false end
    end
    return (inside and 1 or -1)*sqrt(best),bx,by,ramp
end

local function roundUnion(a,b,r)
    a,b=a-r,b-r
    if a>0 and b>0 then return -min(a,b)-r end
    return sqrt(min(a,0)^2+min(b,0)^2)-r
end

function Arena:netProfile(depth,z)
    local a=self.profile.arena
    local floorHeight=depth<=234 and 0 or(min(depth,640)-234)*16/406
    local floorDistance=(z-floorHeight)*(depth<=234 and 1 or .9992243739289178)
    local roof=(depth<=224 and a.MOUTH_HEIGHT or a.MOUTH_HEIGHT-(depth-224)*.3185)-z
    roof=roof*(depth<=224 and 1 or .9528381434926312)
    local back=240-sqrt(max(depth-640,0)^2+(z-256)^2)
    if depth>640 then back=self:corner(240-(depth-640),240-abs(z-256),240)end
    return min(floorDistance,roof,max(640-depth,back,min(self.netCorner[1]-depth,z-self.netCorner[2])))
end

function Arena:distance(p)
    local a=self.profile.arena
    local x,y,z=abs(p[1]),abs(p[2]),p[3]
    if y>4000 and x<a.GOAL_HALF_WIDTH+700 then
        -- Rounded mouth, front lip, sloped roof/floor and faceted rear cavity.
        local radius=a.MOUTH_FILLET
        local dx,dz=x-(a.MOUTH_HALF_WIDTH-radius),abs(z-a.MOUTH_HEIGHT/2)-(a.MOUTH_HEIGHT/2-radius)
        local mouth=sqrt(max(dx,0)^2+max(dz,0)^2)+min(max(dx,dz),0)-radius
        local blend=math.clamp((x-950)/400,0,1)
        local ramp=96+(a.BACK_RAMP_RADIUS-96)*blend*blend*(3-2*blend)
        local wall=-min(self:corner(a.EXTENT_Y-y,z,ramp),self:corner(a.EXTENT_Y-y,a.HEIGHT-z,a.CEILING_RADIUS))
        local free=roundUnion(mouth,wall,a.MOUTH_LIP)
        local depth=y-a.EXTENT_Y
        if depth>0 and free>0 then
            local w,h=a.MOUTH_HALF_WIDTH-x,self:netProfile(depth,z)
            local netFree=radius-sqrt(max(radius-w,0)^2+max(radius-h,0)^2)-min(max(radius-w,radius-h),0)
            free=min(free,netFree+max(a.MOUTH_LIP-depth,0))
        end
        return min(z,a.HEIGHT-z,free)
    end
    local side,_,_,ramp=self:plan(x,y)
    return min(self:corner(side,z,ramp),self:corner(side,a.HEIGHT-z,a.CEILING_RADIUS))
end

function Arena:query(p)
    local d=self:distance(p)
    local normal={}
    for i=1,3 do
        local plus,minus=table.clone(p),table.clone(p);plus[i]=plus[i]+.5;minus[i]=minus[i]-.5
        normal[i]=self:distance(plus)-self:distance(minus)
    end
    local magnitude=length(normal)
    if magnitude<1e-9 then return d,{0,0,1}end
    for i=1,3 do normal[i]=normal[i]/magnitude end
    return d,normal
end

function Arena:ray(p,direction,limit)
    local t=0
    for _=1,48 do
        local gap=self:distance(addScaled(p,direction,t))
        if gap<.01 then return t end
        t=t+gap;if t>limit then return nil end
    end
end

local function sphereRay(p,dir,center,radius,limit)
    local delta={p[1]-center[1],p[2]-center[2],p[3]-center[3]}
    local b=dot(delta,dir)
    local discriminant=b*b-dot(delta,delta)+radius*radius
    if discriminant<0 then return nil end
    local root=sqrt(discriminant)
    local near,far=-b-root,-b+root
    if near>=0 and near<=limit then return near end
    if far>=0 and far<=limit then return far end
end

function Arena:ground(car,ball,ballRadius)
    local config=self.profile.car_presets[self.preset]
    local right=cross(car.up,car.forward)
    local down={-car.up[1],-car.up[2],-car.up[3]}
    local contacts,ballContacts=0,0
    for _,wheel in ipairs({config.front,config.back})do
        for _,side in ipairs({-1,1})do
            local point=addScaled(addScaled(addScaled(car.position,car.forward,wheel.offset[1]),right,side*wheel.offset[2]),car.up,wheel.offset[3])
            local limit=wheel.rest_length+wheel.radius
            -- Match the simulator's minimum wheel-ray distance filter.
            local minimum=self.profile.physics.WHEEL_RAY_MIN_HIT_DIST
            local hit=self:ray(point,down,limit)
            if hit and hit<minimum then hit=self:ray(addScaled(point,down,minimum),down,limit-minimum)end
            if ball and ballRadius then
                local ballHit=sphereRay(point,down,ball.position,ballRadius,limit)
                if ballHit and(not hit or ballHit<hit)then hit=ballHit;ballContacts=ballContacts+1 end
            end
            if hit then contacts=contacts+1 end
        end
    end
    return contacts>=3,contacts,ballContacts
end

function Arena:measureCar(model,root)
    self.lastMeasure=os.clock()
    for _,part in ipairs(model:GetDescendants())do
        if part:IsA("BasePart")and part~=root then
            local box=part:FindFirstChildOfClass("SelectionBox")
            if box and box.Adornee==part then
                local k=1/self.profile.roblox_studs_per_sim_unit
                local measured={part.Size.Z*k,part.Size.X*k,part.Size.Y*k}
                local localOffset=root.CFrame:ToObjectSpace(part.CFrame).Position
                local offset={-localOffset.Z*k,localOffset.X*k,localOffset.Y*k}
                for name,config in pairs(self.profile.car_presets)do
                    local error=0
                    for i=1,3 do error=error+abs(measured[i]-config.size[i])+abs(offset[i]-config.offset[i])end
                    if error<1 then self.preset=name;self.hitboxVerified=true;return end
                end
            end
        end
    end
    self.preset="standard";self.hitboxVerified=false
end

function Arena:ballRadius(root)
    local trail=root:FindFirstChild("TrailBodyA")
    if trail and trail:IsA("Attachment")then
        local radius=abs(trail.Position.X)/(.6*self.profile.roblox_studs_per_sim_unit)
        if radius>=self.profile.physics.BALL_RADIUS*.25 and radius<=self.profile.physics.BALL_RADIUS*4 then
            return radius,true
        end
    end
    return self.profile.physics.BALL_RADIUS,false
end

function Arena:recovery(packet,previous,now)
    local cfg=self.profile.recovery
    if not cfg.enabled then return nil end
    local p=packet.car.position
    if self.escapeUntil and now<self.escapeUntil then
        if packet.ground_estimate then return {-1,self.escapeSteer,0,self.escapeSteer,0,0,0,1},"reverse/turn"end
        return nil
    end
    if not self.windowAt then self.windowAt=now;self.windowPosition=table.clone(p)end
    local moved=length({p[1]-self.windowPosition[1],p[2]-self.windowPosition[2],p[3]-self.windowPosition[3]})
    local inverted=p[3]<100 and packet.car.up[3]<-.5 and length(packet.car.velocity)<100
    if moved>cfg.minimum_travel or(abs(previous[1])<.5 and not inverted)then self.windowAt=now;self.windowPosition=table.clone(p);return nil end
    if now-self.windowAt<cfg.stuck_seconds or now<(self.cooldownUntil or 0)then return nil end
    self.windowAt=now;self.windowPosition=table.clone(p)
    local ballDistance=length({p[1]-packet.ball.position[1],p[2]-packet.ball.position[2],p[3]-packet.ball.position[3]})
    if ballDistance<(packet.ball_radius or 91.25)+250 then return nil end
    local gap,normal=self:query(p)
    if packet.ground_estimate and(abs(normal[3])<.8 or abs(p[2])>self.profile.arena.EXTENT_Y-300)and gap<120 then
        self.escapeSteer=dot(cross(packet.car.up,packet.car.forward),normal)>=0 and -1 or 1
        self.escapeUntil=now+cfg.escape_seconds;self.cooldownUntil=now+cfg.cooldown_seconds
        return {-1,self.escapeSteer,0,self.escapeSteer,0,0,0,1},"reverse/turn"
    end
    if not packet.ground_estimate and inverted then
        self.cooldownUntil=now+cfg.cooldown_seconds
        return {0,0,0,0,1,1,0,0},"upright"
    end
end

function Arena:resetRecovery()
    self.windowAt=nil;self.windowPosition=nil;self.escapeUntil=nil;self.cooldownUntil=nil
end

return Arena
