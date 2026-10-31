local E=require("../elevation")
local paths={{points={{x=0,y=0,z=0},{x=0,y=10,z=-50}}},{points={{x=0,y=40,z=0},{x=0,y=50,z=-50}}}}
local index=E.new(paths)
assert(index.count==2)
assert(math.abs(E.height(index,0,-25,4)-5)<1e-8)
assert(math.abs(E.height(index,0,-25,44)-45)<1e-8)
assert(not E.height(index,0,-25,100))
assert(not E.height(index,100,-25,5))
print("PASS 3D elevation lookup separates stacked roads and interpolates slopes")
