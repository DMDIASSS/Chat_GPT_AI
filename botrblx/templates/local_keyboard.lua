-- Choose a keyboard API by observed Roblox state, not by successful pcall.
local Keyboard={}
Keyboard.__index=Keyboard
local names={"W","A","S","D","Q","E","SHIFT"}
local codes={W=Enum.KeyCode.W,A=Enum.KeyCode.A,S=Enum.KeyCode.S,D=Enum.KeyCode.D,
    Q=Enum.KeyCode.Q,E=Enum.KeyCode.E,SHIFT=Enum.KeyCode.LeftShift}
local vk={W=0x57,A=0x41,S=0x53,D=0x44,Q=0x51,E=0x45,SHIFT=0x10}
local scan={W=0x11,A=0x1E,S=0x1F,D=0x20,Q=0x10,E=0x12,SHIFT=0x2A}

function Keyboard.new(input)
    return setmetatable({input=input,candidates={},owned={},selected=nil,name="untested"},Keyboard)
end

function Keyboard:release()
    for backend,keys in pairs(self.owned)do
        for key in pairs(keys)do
            if pcall(backend.send,key,false)then keys[key]=nil end
        end
    end
end

function Keyboard:sendWith(backend,key,down)
    local keys=self.owned[backend]
    if not keys then keys={};self.owned[backend]=keys end
    if down then keys[key]=os.clock()end
    backend.send(key,down)
    if not down then keys[key]=nil end
end

function Keyboard:event(key,down)
    if self.selected then self:sendWith(self.selected,key,down);return end
    assert(not down,"Keyboard has not passed the input test")
    -- verify() may invalidate the selected backend while it still owns keys.
    for backend,keys in pairs(self.owned)do
        if keys[key]then self:sendWith(backend,key,false)end
    end
end

function Keyboard:observed()
    local observed={}
    for _,key in ipairs(names)do if self.input:IsKeyDown(codes[key])then observed[#observed+1]=key end end
    return table.concat(observed," ")
end

function Keyboard:verify()
    local keys=self.selected and self.owned[self.selected]
    for key,since in pairs(keys or {})do
        if os.clock()-since>.2 and not self.input:IsKeyDown(codes[key])then
            self.selected=nil;self.name="needs retest"
            return false,"Keyboard stopped reaching Roblox: "..key
        end
    end
    return true
end

function Keyboard:probe(cancelled,report)
    self:release();self.selected=nil
    self.candidates={}
    -- Ordinary API call only. If this runtime disallows it, the error is
    -- recorded and executor APIs are tested without changing thread identity.
    local ok,manager=pcall(function()return game:GetService("VirtualInputManager")end)
    if ok and manager then
        self.candidates[#self.candidates+1]={name="Roblox key events",send=function(key,down)
            manager:SendKeyEvent(down,codes[key],false,game)
        end}
    end
    if type(keypress)=="function"and type(keyrelease)=="function"then
        for _,spec in ipairs({{name="executor VK",map=vk},{name="executor scan",map=scan}})do
            local mapping=spec.map
            self.candidates[#self.candidates+1]={name=spec.name,send=function(key,down)
                (down and keypress or keyrelease)(mapping[key])
            end}
        end
    end
    local function waitState(key,wanted,limit)
        local untilTime=os.clock()+limit
        repeat
            if cancelled()then return false,"cancelled"end
            if self.input:IsKeyDown(codes[key])==wanted then return true end
            task.wait(.02)
        until os.clock()>=untilTime
        return false,wanted and "keydown was not observed"or "keyup was not observed"
    end
    for _,key in ipairs(names)do
        if self.input:IsKeyDown(codes[key])then return false,"Release your physical "..key.." key, then press F6 again"end
    end
    local failures={}
    for _,backend in ipairs(self.candidates)do
        if cancelled()then self:release();return false,"Keyboard test cancelled"end
        report("Testing "..backend.name..": W A S D Q E Shift. F8 cancels.")
        local passed,why=true,nil
        for _,key in ipairs(names)do
            if cancelled()then passed=false;why="cancelled";break end
            local sent,err=pcall(self.sendWith,self,backend,key,true)
            if not sent then passed=false;why=tostring(err):sub(1,130)
            else passed,why=waitState(key,true,.18)end
            -- Always issue the matching release, including a late/yielding press.
            local released,releaseError=pcall(self.sendWith,self,backend,key,false)
            if passed and not released then passed=false;why=tostring(releaseError):sub(1,130)end
            if passed then passed,why=waitState(key,false,.18)end
            if not passed then why=key..": "..tostring(why);break end
            task.wait(.02)
        end
        self:release()
        if cancelled()then return false,"Keyboard test cancelled"end
        if passed then
            self.selected=backend;self.name=backend.name
            return true
        end
        failures[#failures+1]=backend.name.." "..tostring(why)
        -- Do not proceed to another backend with a stuck key from this one.
        for _,key in ipairs(names)do
            if self.input:IsKeyDown(codes[key])then
                return false,"Key remained down after testing "..backend.name..": "..key..". Release it and retry."
            end
        end
    end
    self.name="unavailable"
    return false,"No keyboard method reached Roblox. "..table.concat(failures," | ")
end
return Keyboard
