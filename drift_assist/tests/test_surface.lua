local Surface=require("../surface")
local wheels={}
for _,row in ipairs({{"FL",-2.25,-3.32},{"FR",2.25,-3.32},{"RL",-2.25,3.32},{"RR",2.25,3.32}}) do
    table.insert(wheels,{name=row[1],x=row[2],y=-.3,z=row[3],reach=1.94})
end
local function queryPlane(a,b,height,roof)
    local norm=math.sqrt(a*a+b*b+1)
    local function query(x,origin,z,length)
        local floor=a*x+b*z+height
        if roof and origin>=floor+roof then
            return {x=x,y=floor+roof,z=z,up={x=-a/norm,y=1/norm,z=-b/norm}}
        end
        if origin<floor or origin-length>floor then return nil end
        return {x=x,y=floor,z=z,up={x=-a/norm,y=1/norm,z=-b/norm}}
    end
    return query,{x=0,y=height,z=0,up={x=-a/norm,y=1/norm,z=-b/norm}}
end
local cases=0
for _,a in ipairs({-.5,0,.4}) do
    for _,b in ipairs({-.45,0,.6}) do
        for _,beta in ipairs({-75,-60,0,35,60,75,120}) do
            local query,reference=queryPlane(a,b,12,3)
            local fit,why=Surface.solve({x=8,z=-4},.7,math.rad(beta),wheels,reference,query)
            assert(fit,why)
            assert(fit.contacts==4)
            for i,d in ipairs(fit.distances) do assert(d>0 and d<wheels[i].reach) end
            local up=fit.up
            assert(math.abs(up.x-reference.up.x)<1e-6 and math.abs(up.z-reference.up.z)<1e-6)
            local motion=fit.travel;local body=fit.forward;local right=fit.right
            local f=motion.x*body.x+motion.y*body.y+motion.z*body.z
            local r=motion.x*right.x+motion.y*right.y+motion.z*right.z
            local measured=math.deg(math.atan2(r,math.abs(f)))
            local expected=if beta==120 then 60 else beta
            assert(math.abs(measured-expected)<1e-5,measured.." vs "..expected)
            cases+=1
        end
    end
end
print("PASS "..cases.." wheel fits on grades/banks, both drift sides, 75 degrees and reversing")
local q,reference=queryPlane(0,0,0,3)
local fit=assert(Surface.solve({x=0,z=0},0,0,wheels,reference,q))
assert(fit.position.y<3)
print("PASS tunnel probes stay below roof and fit the floor")
local highest=0
local function missing(_,y,_,_) highest=math.max(highest,y);return nil end
local result,why=Surface.solve({x=0,z=0},0,0,wheels,reference,missing)
assert(not result and why and highest<=1.8)
print("PASS missing floor does not trigger a sky/mountain ray")
local function edge(x,y,z,length) if x>1 then return nil end;return q(x,y,z,length) end
assert(not Surface.solve({x=0,z=0},0,0,wheels,reference,edge))
print("PASS unsupported wheel rejects pose at road edge")
local function grass(x,y,z,length) local hit=q(x,y,z,length);if hit then hit.offroad=true end;return hit end
assert(not Surface.solve({x=0,z=0},0,0,wheels,reference,grass))
print("PASS grass/off-road hits are rejected")
