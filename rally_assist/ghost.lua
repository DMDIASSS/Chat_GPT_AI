-- Observe a ghost already delivered to this client. No requests or score writes.
local Ghost={}
Ghost.__index=Ghost
function Ghost.new()return setmetatable({tracks={},capture=nil},Ghost)end
local function finite(v)return type(v)=="number"and v==v and math.abs(v)<1e7 end
function Ghost.base64(text)
    assert(type(text)=="string"and #text<=1000000 and #text%4==0,"Invalid ghost data length")
    assert(not text:find("[^A-Za-z0-9+/=]"),"Invalid ghost encoding")
    local alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
    local codes={};for i=1,64 do codes[alphabet:byte(i)]=i-1 end;codes[61]=0
    local padding=text:sub(-2)=="=="and 2 or(text:sub(-1)=="="and 1 or 0)
    local out=buffer.create(#text/4*3-padding);local offset=0
    for i=1,#text,4 do
        local a,b,c,d=text:byte(i,i+3)
        local value=codes[a]*262144+codes[b]*4096+codes[c]*64+codes[d]
        for _,shift in ipairs({16,8,0})do
            if offset<buffer.len(out)then buffer.writeu8(out,offset,math.floor(value/2^shift)%256);offset=offset+1 end
        end
    end
    return out
end
function Ghost.decode(payload)
    assert(type(payload)=="table"and type(payload.Count)=="number"and payload.Count%1==0
        and payload.Count>=2 and payload.Count<=12000,"Invalid ghost sample count")
    assert(type(payload.Rate)=="number"and payload.Rate>=1 and payload.Rate<=120,"Invalid ghost rate")
    local raw=Ghost.base64(payload.Data)
    assert(buffer.len(raw)==payload.Count*30,"Unsupported ghost format")
    local rows={}
    for i=0,payload.Count-1 do
        local off=i*30
        local x,y,z=buffer.readf32(raw,off),buffer.readf32(raw,off+4),buffer.readf32(raw,off+8)
        assert(finite(x)and finite(y)and finite(z),"Non-finite ghost position")
        assert(bit32.band(buffer.readu8(raw,off+25),64)==0,"Ghost contains a reset; use the stage line")
        rows[#rows+1]={i/payload.Rate,x,y,z,math.abs(buffer.readi16(raw,off+20)/50),buffer.readi16(raw,off+22)/10000}
    end
    return rows
end
function Ghost:receive(stage,carId,payload)
    local ok,rows=pcall(Ghost.decode,payload)
    if not ok then self.reason=tostring(rows);return false,self.reason end
    self.tracks[stage.."/"..carId]={samples=rows,duration=rows[#rows][1],source="personal ghost"}
    self.reason=nil;return true
end
function Ghost:sample(stage,carId,state,point,now)
    local key=stage.."/"..carId
    if state=="Running"then
        local c=self.capture
        if not c or c.key~=key then
            c={key=key,at=now,rows={},lastAt=-math.huge,invalid=point.elapsed and point.elapsed>2 or false};self.capture=c
        end
        if now-c.lastAt<.08 then return end;c.lastAt=now
        local previous=c.rows[#c.rows]
        local measured=0
        if previous then
            local travel=(point.x-previous[2])^2+(point.y-previous[3])^2+(point.z-previous[4])^2
            if travel>80^2 then c.invalid=true end
            measured=math.sqrt((point.x-previous[2])^2+(point.z-previous[4])^2)/math.max(now-c.at-previous[1],.01)
        end
        local speed=point.speed and point.speed>1 and point.speed or measured
        if #c.rows<7500 then c.rows[#c.rows+1]={now-c.at,point.x,point.y,point.z,speed,0}else c.invalid=true end
    elseif self.capture then
        local c=self.capture;self.capture=nil
        if state=="Finished"and c.key==key and not c.invalid and #c.rows>30 then
            local duration=c.rows[#c.rows][1]
            local previous=self.tracks[key]
            if not previous or(previous.source~="personal ghost"and duration<previous.duration)then
                self.tracks[key]={samples=c.rows,duration=duration,source="learned ghost"}
            end
        end
    end
end
return Ghost
