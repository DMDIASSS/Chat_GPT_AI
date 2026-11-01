-- Spatial lookup for the game's replicated 3D race-course elevations.
local Elevation={}
function Elevation.new(paths)
    local index={cells={},count=0}
    for _,path in ipairs(paths) do
        for i=1,#path.points-1 do
            local a,b=path.points[i],path.points[i+1]
            if not a.y or not b.y then continue end
            local dx,dz=b.x-a.x,b.z-a.z
            local length=dx*dx+dz*dz
            if length<.01 or length>2500 then continue end
            local segment={a=a,b=b,dx=dx,dz=dz,length=length}
            for x=math.floor(math.min(a.x,b.x)/16),math.floor(math.max(a.x,b.x)/16) do
                for z=math.floor(math.min(a.z,b.z)/16),math.floor(math.max(a.z,b.z)/16) do
                    local key=x..":"..z
                    index.cells[key]=index.cells[key] or {}
                    table.insert(index.cells[key],segment)
                end
            end
            index.count+=1
        end
    end
    return index
end
function Elevation.height(index,x,z,expected,maximumDelta)
    if not index then return nil end
    local best,score=nil,math.huge
    for ix=math.floor(x/16)-1,math.floor(x/16)+1 do
        for iz=math.floor(z/16)-1,math.floor(z/16)+1 do
            for _,s in ipairs(index.cells[ix..":"..iz] or {}) do
                local t=math.clamp(((x-s.a.x)*s.dx+(z-s.a.z)*s.dz)/s.length,0,1)
                local distance=(x-s.a.x-s.dx*t)^2+(z-s.a.z-s.dz*t)^2
                local y=s.a.y+(s.b.y-s.a.y)*t
                local delta=math.abs(y-expected)
                if distance<=144 and delta<=(maximumDelta or 6) then
                    local value=distance+delta*delta*(if maximumDelta==math.huge then .0001 else .5)
                    if value<score then score=value;best=y end
                end
            end
        end
    end
    return best
end
return Elevation
