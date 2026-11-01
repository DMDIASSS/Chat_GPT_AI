local Lease=require("../input_lease")
local p={attributes={}}
function p:GetAttribute(k) return self.attributes[k] end
function p:SetAttribute(k,v) self.attributes[k]=v end
local lease=Lease.new(p)
assert(lease:write({throttle=1,brake=0,steer=-0.4,handbrake=true}))
assert(p:GetAttribute("DebugInput")=="1.0000,0.0000,-0.4000,1")
lease:release();assert(p:GetAttribute("DebugInput")==nil)
print("PASS Input override serialization and cleanup")
p:SetAttribute("DebugInput","external")
assert(not lease:write({throttle=1}))
lease:release();assert(p:GetAttribute("DebugInput")=="external")
print("PASS Does not overwrite or erase an external controller")
p:SetAttribute("DebugInput",nil)
assert(lease:write({throttle=9,steer=-4,brake=-3}))
assert(p:GetAttribute("DebugInput")=="1.0000,0.0000,-1.0000,0")
p:SetAttribute("DebugInput","changed")
lease:release();assert(p:GetAttribute("DebugInput")=="changed")
print("PASS Clamps controls and leaves later external writes intact")
