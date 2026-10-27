-- Minimal scheduler/UI doubles for lifecycle tests of the standalone script.
local now, env, created, scheduled = 0, {}, {}, {}
local function event()
    local e = {listeners = {}}
    function e:Connect(fn)
        local c = {active = true}; function c:Disconnect() self.active = false end
        table.insert(self.listeners, {c,fn}); return c
    end
    function e:Fire(...)
        for _, row in ipairs(self.listeners) do if row[1].active then row[2](...) end end
    end
    return e
end
local function object(class)
    local o = {ClassName = class, Activated = event(), AncestryChanged = event(), children = {}}
    function o:Clone() return object(self.ClassName) end
    function o:Destroy() self.destroyed = true; self.AncestryChanged:Fire(self,nil) end
    function o:IsA(wanted) return self.ClassName == wanted end
    function o:FindFirstChild(name) return self.children[name] end
    function o:WaitForChild(name) return assert(self.children[name]) end
    table.insert(created,o)
    return o
end
local input = {InputBegan = event()}
local services = {Players = {LocalPlayer = object("Player")}, CoreGui = object("CoreGui"), UserInputService = input,
    RunService = {Heartbeat = event()}, ReplicatedStorage = object("ReplicatedStorage")}
local game = {GetService = function(_, name) return assert(services[name]) end}
local Instance = {new = object}
local UDim2 = {new = function(...) return {...} end,fromOffset = function(...) return {...} end}
local UDim = {new = function(...) return {...} end}
local Color3 = {fromRGB = function(...) return {...} end}
local Enum = {Font = {Gotham = 1,GothamBold = 2}, ZIndexBehavior = {Sibling = 1},TextXAlignment = {Left = 1},KeyCode = {F6 = 6}}
local os = {clock = function() return now end}
local getgenv = function() return env end
local warnings = {}
local warn = function(message) table.insert(warnings,message) end
local cachedMain
local require = function(_) return assert(cachedMain, "No live RoWorld module in this fixture") end
local task = {}
function task.spawn(fn) table.insert(scheduled,coroutine.create(fn)) end
function task.wait(dt) coroutine.yield(dt) end
local function step()
    now += .55
    for _, co in ipairs(scheduled) do
        if coroutine.status(co) ~= "dead" then
            local ok, err = coroutine.resume(co); assert(ok,err)
        end
    end
end
