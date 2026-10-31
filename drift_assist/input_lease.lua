-- Own only the game's input override we installed. Do not erase another controller's input.
local InputLease = {}
InputLease.__index = InputLease
function InputLease.new(player) return setmetatable({player = player, last = nil}, InputLease) end
function InputLease:write(command)
    local current = self.player:GetAttribute("DebugInput")
    if current ~= nil and current ~= self.last then return false, "DebugInput is in use by another controller" end
    local value = string.format("%.4f,%.4f,%.4f,%d", math.clamp(command.throttle or 0,0,1),
        math.clamp(command.brake or 0,0,1), math.clamp(command.steer or 0,-1,1), if command.handbrake then 1 else 0)
    self.player:SetAttribute("DebugInput", value)
    self.last = value
    return true
end
function InputLease:release()
    if self.last and self.player:GetAttribute("DebugInput") == self.last then self.player:SetAttribute("DebugInput", nil) end
    self.last = nil
end
return InputLease
