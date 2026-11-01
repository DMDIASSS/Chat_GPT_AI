-- Portable wheel-plane solver. All probes stay near the expected road elevation.
local Surface={}
local function vec(x,y,z) return {x=x,y=y,z=z} end
local function add(a,b) return vec(a.x+b.x,a.y+b.y,a.z+b.z) end
local function sub(a,b) return vec(a.x-b.x,a.y-b.y,a.z-b.z) end
local function mul(a,k) return vec(a.x*k,a.y*k,a.z*k) end
local function dot(a,b) return a.x*b.x+a.y*b.y+a.z*b.z end
local function cross(a,b) return vec(a.y*b.z-a.z*b.y,a.z*b.x-a.x*b.z,a.x*b.y-a.y*b.x) end
local function unit(a)
    local length=math.sqrt(dot(a,a))
    return if length>1e-6 then mul(a,1/length) else vec(0,1,0)
end
local function basis(heading,beta,up)
    local flat=vec(-math.sin(heading),0,-math.cos(heading))
    local travel=unit(sub(flat,mul(up,dot(flat,up))))
    local forward=add(mul(travel,math.cos(beta)),mul(cross(up,travel),math.sin(beta)))
    return forward,unit(cross(forward,up)),travel
end
local function offset(wheel,right,up,forward)
    return add(add(mul(right,wheel.x),mul(up,wheel.y)),mul(forward,-wheel.z))
end
function Surface.expected(reference,x,z)
    local up=reference.up or vec(0,1,0)
    return reference.y-(up.x*(x-reference.x)+up.z*(z-reference.z))/math.max(up.y,.35)
end
function Surface.probe(query,x,z,expected)
    -- The first origin is BELOW a normal tunnel roof. Never scan down from the sky.
    for _,rise in ipairs({.65,1.8}) do
        local hit=query(x,expected+rise,z,6+rise)
        if hit and not hit.offroad and hit.up.y>=.35 and math.abs(hit.y-expected)<=2.4 then return hit end
    end
    return nil
end
function Surface.solve(point,heading,beta,wheels,reference,query)
    if #wheels~=4 then return nil,"Four wheel attachments are required" end
    local expected=if point.y then point.y else Surface.expected(reference,point.x,point.z)
    local center=Surface.probe(query,point.x,point.z,expected)
    if not center then return nil,"Road surface missing at expected elevation" end
    local up=unit(center.up)
    local hits,forward,right,travel
    for _=1,2 do
        forward,right,travel=basis(heading,beta,up)
        hits={}
        for i,w in ipairs(wheels) do
            local o=offset(w,right,up,forward)
            local x,z=point.x+o.x,point.z+o.z
            local guess=center.y-(up.x*(x-point.x)+up.z*(z-point.z))/math.max(up.y,.35)
            local hit=Surface.probe(query,x,z,guess)
            if not hit then return nil,"Road missing below "..w.name end
            hits[i]=hit
        end
        -- Fit pitch and bank from the four actual wheel contacts in chassis coordinates.
        local front=mul(add(hits[1],hits[2]),.5)
        local rear=mul(add(hits[3],hits[4]),.5)
        local left=mul(add(hits[1],hits[3]),.5)
        local rightPoint=mul(add(hits[2],hits[4]),.5)
        local fitted=unit(cross(sub(rightPoint,left),sub(front,rear)))
        if fitted.y<0 then fitted=mul(fitted,-1) end
        if fitted.y<.35 then return nil,"Wheel plane too steep" end
        up=fitted
    end
    forward,right,travel=basis(heading,beta,up)
    local lower,upper,sum=-math.huge,math.huge,0
    for i,w in ipairs(wheels) do
        local o=offset(w,right,up,forward)
        local plane=dot(up,hits[i])-up.x*point.x-up.z*point.z-dot(up,o)
        local reach=w.reach
        -- Keep every tyre within the original suspension's contact/compression range.
        lower=math.max(lower,(plane+math.max(.35,reach-.9))/up.y)
        upper=math.min(upper,(plane+reach-.035)/up.y)
        sum+=(plane+reach-.235)/up.y
    end
    if lower>upper then return nil,"Terrain cannot support all four tyres" end
    local position=vec(point.x,math.clamp(sum/4,lower,upper),point.z)
    local distances={}
    for i,w in ipairs(wheels) do
        distances[i]=dot(up,sub(add(position,offset(w,right,up,forward)),hits[i]))
    end
    return {position=position,up=up,forward=forward,right=right,travel=travel,
        contacts=4,distances=distances,reference={x=center.x,y=center.y,z=center.z,up=up}}
end
Surface.basis=basis
return Surface
