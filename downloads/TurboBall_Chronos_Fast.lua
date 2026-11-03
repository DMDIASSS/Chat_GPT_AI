-- Chronos V2.1 by KingJake: https://github.com/KingJake3113/Chronos
-- Pinned release: 4f8fdd27e4802d977b33b9ade4759ff6aeaca5aa
-- Actual SHARED_HEAD.lt and POLICY.lt weights; no Nexto model is embedded.
-- Model pair digest: 0fe5bbe1318632b1934076230fc7426ae07db797e75b46f8d667b633f4e3a16f
-- Roblox adapter derived from botrblx local v6.8. See CHRONOS_NOTICE.md.
-- Frame-budgeted local inference, latency compensation, reversible light graphics.
-- Rocket League rankings do not establish playing strength in Turbo Soccer.
-- Generated LOCAL model + telemetry + controls. Weights stay on this PC.
local Policy=(function()
-- Chronos V2.1: full float32 weights; no network calls during inference.
local Policy={}
function Policy.decode(encoded,count)
    assert(type(buffer)=="table"and type(buffer.readf32)=="function",
        "This runtime needs Roblox buffer.readf32/writeu8")
    local alphabet="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
    local values={};for i=1,64 do values[string.byte(alphabet,i)]=i-1 end
    values[61]=0 -- '=' padding
    local out=buffer.create(count*4)
    local offset=0
    for i=1,#encoded,4 do
        local a,b,c,d=string.byte(encoded,i,i+3)
        local n=assert(values[a])*262144+assert(values[b])*4096+assert(values[c])*64+assert(values[d])
        if offset<count*4 then buffer.writeu8(out,offset,math.floor(n/65536));offset=offset+1 end
        if offset<count*4 then buffer.writeu8(out,offset,math.floor(n/256)%256);offset=offset+1 end
        if offset<count*4 then buffer.writeu8(out,offset,n%256);offset=offset+1 end
    end
    assert(offset==count*4,"Incomplete embedded model")
    -- Decode once: inner matrix loops use indexed numbers, not per-MAC buffer calls.
    local numbers=table.create(count)
    for i=1,count do numbers[i]=buffer.readf32(out,(i-1)*4)end
    return numbers
end

function Policy.actions()
    local actions={}
    for throttle=-1,1 do for steer=-1,1 do for boost=0,1 do for brake=0,1 do
        if boost==0 or throttle==1 then
            actions[#actions+1]={throttle~=0 and throttle or boost,steer,0,steer,0,0,boost,brake}
        end
    end end end end
    for pitch=-1,1 do for yaw=-1,1 do for roll=-1,1 do for jump=0,1 do for boost=0,1 do
        if not(jump==1 and yaw~=0)and not(pitch==0 and roll==0 and jump==0)then
            local brake=jump==1 and(pitch~=0 or yaw~=0 or roll~=0)and 1 or 0
            actions[#actions+1]={boost,yaw,pitch,yaw,roll,jump,boost,brake}
        end
    end end end end end
    assert(#actions==90)
    return actions
end

function Policy.keys(action,ground)
    -- Wheel-ray contact can remain true near takeoff/landing. Jump direction
    -- must retain the actor's pitch/yaw even when that estimate says grounded.
    local air=not ground or action[6]~=0
    local t=air and -action[3]or action[1]
    local s=air and action[4]or action[2]
    local keys={}
    if t>.5 then keys.W=true elseif t<-.5 then keys.S=true end
    if s>.5 then keys.D=true elseif s<-.5 then keys.A=true end
    if action[5]>.5 then keys.E=true elseif action[5]<-.5 then keys.Q=true end
    if action[6]~=0 then keys.RMB=true end
    if action[7]~=0 then keys.LMB=true end
    if action[8]~=0 and not air then keys.SHIFT=true end
    t=(keys.W and 1 or 0)-(keys.S and 1 or 0)
    s=(keys.D and 1 or 0)-(keys.A and 1 or 0)
    local r=(keys.E and 1 or 0)-(keys.Q and 1 or 0)
    local y=(r~=0 or not keys.SHIFT)and s or 0
    if r==0 and keys.SHIFT then r=s end
    return keys,{t,s,-t,y,r,keys.RMB and 1 or 0,keys.LMB and 1 or 0,keys.SHIFT and 1 or 0}
end

local PADS=
{{0.0,-4240.0,70.0},{-1792.0,-4184.0,70.0},{1792.0,-4184.0,70.0},{-3072.0,-4096.0,73.0},{3072.0,-4096.0,73.0},{-940.0,-3308.0,70.0},{940.0,-3308.0,70.0},{0.0,-2816.0,70.0},{-3584.0,-2484.0,70.0},{3584.0,-2484.0,70.0},{-1788.0,-2300.0,70.0},{1788.0,-2300.0,70.0},{-2048.0,-1036.0,70.0},{0.0,-1024.0,70.0},{2048.0,-1036.0,70.0},{-3584.0,0.0,73.0},{-1024.0,0.0,70.0},{1024.0,0.0,70.0},{3584.0,0.0,73.0},{-2048.0,1036.0,70.0},{0.0,1024.0,70.0},{2048.0,1036.0,70.0},{-1788.0,2300.0,70.0},{1788.0,2300.0,70.0},{-3584.0,2484.0,70.0},{3584.0,2484.0,70.0},{0.0,2816.0,70.0},{-940.0,3310.0,70.0},{940.0,3308.0,70.0},{-3072.0,4096.0,73.0},{3072.0,4096.0,73.0},{-1792.0,4184.0,70.0},{1792.0,4184.0,70.0},{0.0,4240.0,70.0}}
local MIRROR_PADS=
{1,3,2,5,4,7,6,8,10,9,12,11,15,14,13,19,18,17,16,22,21,20,24,23,26,25,27,29,28,31,30,33,32,34}
local ACTIONS=Policy.actions()
local max,sqrt,abs=math.max,math.sqrt,math.abs

local function dense(layer,x,checkpoint)
    local w,b,width,rows=layer.w,layer.b,layer.width,layer.rows
    local out=layer.out
    local bulk=width-width%4
    local last=rows-rows%4
    local base=0
    for r=1,last,4 do
        local a0,a1,a2,a3=b[r],b[r+1],b[r+2],b[r+3]
        local b1,b2,b3=base+width,base+width*2,base+width*3
        for c=1,bulk,4 do
            local x0,x1,x2,x3=x[c],x[c+1],x[c+2],x[c+3]
            a0=a0+w[base+c]*x0+w[base+c+1]*x1+w[base+c+2]*x2+w[base+c+3]*x3
            a1=a1+w[b1+c]*x0+w[b1+c+1]*x1+w[b1+c+2]*x2+w[b1+c+3]*x3
            a2=a2+w[b2+c]*x0+w[b2+c+1]*x1+w[b2+c+2]*x2+w[b2+c+3]*x3
            a3=a3+w[b3+c]*x0+w[b3+c+1]*x1+w[b3+c+2]*x2+w[b3+c+3]*x3
        end
        for c=bulk+1,width do
            local v=x[c]
            a0=a0+w[base+c]*v;a1=a1+w[b1+c]*v
            a2=a2+w[b2+c]*v;a3=a3+w[b3+c]*v
        end
        out[r]=a0;out[r+1]=a1;out[r+2]=a2;out[r+3]=a3
        base=base+width*4
        if checkpoint then checkpoint()end
    end
    for r=last+1,rows do
        local value=b[r]
        for c=1,width do value=value+w[base+c]*x[c]end
        out[r]=value;base=base+width
    end
    return out
end

local function denseVector(l,x,checkpoint)
    local out,w,width=l.out,l.packed,l.width
    -- ReLU creates exact zeros. Omit their multiplications, preserving order
    -- and every model weight; no thresholding or weight pruning is involved.
    local cols,values=l.columns,l.values
    local count=0
    for c=1,width do
        if x[c]~=0 then count+=1;cols[count]=c;values[count]=x[c]end
    end
    local bulk=count-count%4
    local ng=math.ceil(l.rows/3)
    for group=1,ng,2 do
        local a0=l.biasV[group]
        local a1=l.biasV[group+1]or vector.zero
        local b0,b1=(group-1)*width,group*width
        if group<ng then
            for k=1,bulk,4 do
                local c0,c1,c2,c3=cols[k],cols[k+1],cols[k+2],cols[k+3]
                local x0,x1,x2,x3=values[k],values[k+1],values[k+2],values[k+3]
                a0=a0+w[b0+c0]*x0+w[b0+c1]*x1+w[b0+c2]*x2+w[b0+c3]*x3
                a1=a1+w[b1+c0]*x0+w[b1+c1]*x1+w[b1+c2]*x2+w[b1+c3]*x3
            end
            for k=bulk+1,count do local c,v=cols[k],values[k];a0=a0+w[b0+c]*v;a1=a1+w[b1+c]*v end
        else
            for k=1,count do a0=a0+w[b0+cols[k]]*values[k]end
        end
        local r=(group-1)*3+1
        out[r]=a0.x;if r+1<=l.rows then out[r+1]=a0.y end;if r+2<=l.rows then out[r+2]=a0.z end
        if group<ng then
            r+=3;out[r]=a1.x;if r+1<=l.rows then out[r+1]=a1.y end;if r+2<=l.rows then out[r+2]=a1.z end
        end
        if checkpoint then checkpoint()end
    end
    return out
end

-- Decode straight into a buffer: no multi-million-element flat number table.
function Policy.loadChunks(chunks,layout,count,yieldWork,progress)
    local alphabet='ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/'
    local values={};for i=1,64 do values[string.byte(alphabet,i)]=i-1 end;values[61]=0
    local data=buffer.create(count*4)
    local offset=0
    for chunkIndex,part in ipairs(chunks)do
        for i=1,#part,4 do
            local a,b,c,d=string.byte(part,i,i+3)
            local n=assert(values[a])*262144+assert(values[b])*4096+assert(values[c])*64+assert(values[d])
            if offset<count*4 then buffer.writeu8(data,offset,math.floor(n/65536));offset+=1 end
            if offset<count*4 then buffer.writeu8(data,offset,math.floor(n/256)%256);offset+=1 end
            if offset<count*4 then buffer.writeu8(data,offset,n%256);offset+=1 end
            if yieldWork and i%2048==1 then yieldWork()end
        end
        if progress then progress('Decoding embedded model',chunkIndex,#chunks)end
    end
    assert(offset==count*4,'Incomplete embedded Chronos model')
    return Policy.loadBuffer(data,layout,count)
end

function Policy.loadBuffer(data,layout,count)
    assert(buffer.len(data)==count*4,'Incomplete Chronos FP32 model')
    local tensors={}
    for name,spec in pairs(layout)do
        assert(spec[1]>=1 and spec[2]>=1 and spec[1]+spec[2]-1<=count,'Invalid Chronos tensor layout')
        tensors[name]={data=data,offset=(spec[1]-1)*4,count=spec[2]}
    end
    return tensors
end

local function normalizeRelu(x,w,b)
    local mean=0
    for i=1,#x do mean=mean+x[i]end
    mean=mean/#x
    local variance=0
    for i=1,#x do local d=x[i]-mean;variance=variance+d*d end
    local scale=1/sqrt(variance/#x+1e-5)
    for i=1,#x do x[i]=max(0,(x[i]-mean)*scale*w[i]+b[i])end
end

function Policy.new(tensors,options)
    options=options or {}
    local native=options.vector~=false and type(vector)=='table'and type(vector.create)=='function'
    local function size(v)return v.count or #v end
    local function get(v,index)
        if v.data then return buffer.readf32(v.data,v.offset+(index-1)*4)end
        return v[index]
    end
    local function numbers(v)
        if not v.data then return v end
        local out=table.create(v.count)
        for i=1,v.count do out[i]=get(v,i);if options.yieldWork and i%256==0 then options.yieldWork()end end
        return out
    end
    local layers={}
    local function layer(prefix,width,rows,norm)
        local stage='Preparing actor layer '..tostring(#layers+1)..'/7'
        if options.progress then options.progress(stage,0,rows)end
        local raw=assert(tensors[prefix..'.weight'])
        local l={b=numbers(assert(tensors[prefix..'.bias'])),width=width,rows=rows,out=table.create(rows)}
        assert(size(raw)==width*rows and #l.b==rows,'Chronos tensor shape mismatch')
        if norm then
            l.nw=numbers(assert(tensors[norm..'.weight']));l.nb=numbers(assert(tensors[norm..'.bias']))
            assert(#l.nw==rows and #l.nb==rows,'Chronos normalization shape mismatch')
        end
        if native then
            l.packed=table.create(math.ceil(rows/3)*width);l.biasV={}
            l.columns=table.create(width);l.values=table.create(width)
            local index=0
            for r=1,rows,3 do
                local base=(r-1)*width
                l.biasV[#l.biasV+1]=vector.create(l.b[r],l.b[r+1]or 0,l.b[r+2]or 0)
                for c=1,width do
                    index+=1
                    l.packed[index]=vector.create(get(raw,base+c),r+1<=rows and get(raw,base+width+c)or 0,
                        r+2<=rows and get(raw,base+width*2+c)or 0)
                end
                if options.yieldWork then options.yieldWork()end
                if options.progress then options.progress(stage,math.min(r+2,rows),rows)end
            end
        else l.w=numbers(raw)end
        layers[#layers+1]=l
        if options.progress then options.progress(stage,rows,rows)end
    end
    layer('shared.0',225,960,'shared.1')
    layer('shared.3',960,960,'shared.4')
    layer('policy.0',960,960,'policy.1')
    layer('policy.3',960,800,'policy.4')
    layer('policy.6',800,640,'policy.7')
    layer('policy.9',640,640,'policy.10')
    layer('policy.12',640,90)
    return function(obs,context,checkpoint)
        assert(#obs==225 and #context.mask==90,'Expected Chronos observation/action mask')
        local x=obs
        for _,l in ipairs(layers)do
            x=(native and denseVector or dense)(l,x,checkpoint)
            if l.nw then normalizeRelu(x,l.nw,l.nb)end
            if checkpoint then checkpoint()end
        end
        local best,peak=nil,-math.huge
        for i,v in ipairs(x)do
            assert(v==v and abs(v)<math.huge,'Non-finite Chronos output')
            if context.mask[i]and v>peak then best,peak=i,v end
        end
        assert(best,'Chronos action mask is empty')
        return best,table.clone(x)
    end,native and 'vector float32'or 'scalar'
end

function Policy.mask(ground,boost,flip,turtled)
    local mask=table.create(90,false)
    for i,a in ipairs(ACTIONS)do
        local enabled
        if ground then enabled=i<=24
        else enabled=(i>25 and a[6]==0)or(i<=24 and a[1]==a[7]and((a[4]~=0)==(a[8]~=0)))end
        if boost==0 and a[7]~=0 then enabled=false end
        -- Keep the upstream jump union after boost filtering.
        if(flip or turtled)and a[6]~=0 then enabled=true end
        mask[i]=enabled
    end
    return mask
end

function Policy.action(index,context)
    local a=table.clone(assert(ACTIONS[index]))
    if context.mirror then a[2]=-a[2];a[4]=-a[4];a[5]=-a[5]end
    return a
end

local function cross(a,b)return {a[2]*b[3]-a[3]*b[2],a[3]*b[1]-a[1]*b[3],a[1]*b[2]-a[2]*b[1]}end
local function dot(a,b)return a[1]*b[1]+a[2]*b[2]+a[3]*b[3]end
local function difference(a,b)return {a[1]-b[1],a[2]-b[2],a[3]-b[3]}end
local function add(out,v,coef)
    for i=1,3 do out[#out+1]=v[i]*(coef or 1)end
end

function Policy.padValues(packet)
    local values,assigned=table.create(34,0),{}
    for _,pad in ipairs(packet.boost_pads or {})do
        local best,distance=nil,256^2
        for i,p in ipairs(PADS)do
            if(p[3]>72)==pad.is_big then
                local d=(p[1]-pad.position[1])^2+(p[2]-pad.position[2])^2
                if d<=distance then best,distance=i,d end
            end
        end
        if best and not assigned[best]then
            assigned[best]=true
            if pad.active then values[best]=1
            else
                local duration=pad.is_big and 10 or 4
                local timer=math.clamp(pad.cooldown_remaining or duration,.01,duration)
                values[best]=1/(1+timer)
            end
        end
    end
    return values
end

function Policy.observe(packet,previous,hasFlip,randomIndex)
    local inv=packet.team==1
    local ix=inv and -1 or 1
    local mirror=packet.car.position[1]*ix>0
    local sx=mirror and -ix or ix
    local reflection=mirror and -1 or 1
    local function polar(v)return {v[1]*sx,v[2]*ix,v[3]}end
    local function axial(v)return {v[1]*ix,v[2]*ix*reflection,v[3]*reflection}end
    local ballPos,ballVel=polar(packet.ball.position),polar(packet.ball.velocity)
    local obs=table.create(225)
    add(obs,ballPos,1/5000);add(obs,ballVel,1/2300);add(obs,axial(packet.ball.angular_velocity),1/3)
    for i=1,8 do
        obs[#obs+1]=previous[i]*(mirror and(i==2 or i==4 or i==5)and -1 or 1)
    end
    local pads=Policy.padValues(packet)
    for i=1,34 do
        local index=mirror and MIRROR_PADS[i]or i
        if inv then index=35-index end
        obs[#obs+1]=pads[index]
    end
    local function row(body,boost,ground,flip,jumped,demoed)
        local pos,vel=polar(body.position),polar(body.velocity)
        local f,u=polar(body.forward),polar(body.up)
        local omega=axial(body.angular_velocity)
        local right=cross(u,f)
        local function localVector(v)return {dot(f,v),dot(right,v),dot(u,v)}end
        local out={}
        add(out,pos,1/5000);add(out,f);add(out,u);add(out,vel,1/2300)
        add(out,omega,1/3);add(out,localVector(omega),1/3)
        add(out,localVector(difference(ballPos,pos)),1/5000)
        add(out,localVector(difference(ballVel,vel)),1/2300)
        out[25]=boost/100;out[26]=ground and 1 or 0;out[27]=flip and 1 or 0
        out[28]=demoed and 1 or 0;out[29]=jumped and 1 or 0
        return out
    end
    local jumped=packet.has_jumped
    if jumped==nil then jumped=not packet.ground_estimate end
    for _,v in ipairs(row(packet.car,packet.boost,packet.ground_estimate,hasFlip,jumped,packet.is_demoed))do obs[#obs+1]=v end
    local teams={{},{}}
    for _,other in ipairs(packet.other_cars or {})do
        local side=other.team==packet.team and 1 or 2
        local g,flip,j=other.ground_estimate,other.flip_estimate,other.has_jumped
        if flip==nil then flip=g end
        if j==nil then j=not g end
        teams[side][#teams[side]+1]=row(other,other.boost_estimate or 50,g,flip,j,other.is_demoed)
    end
    for side,players in ipairs(teams)do
        local count=side==1 and 2 or 3
        assert(#players<=count,'Chronos supports at most three cars per team')
        while #players<count do players[#players+1]=table.create(29,0)end
        for i=#players,2,-1 do
            local j=(randomIndex or math.random)(i)
            players[i],players[j]=players[j],players[i]
        end
        for _,p in ipairs(players)do for _,v in ipairs(p)do obs[#obs+1]=v end end
    end
    assert(#obs==225,'Invalid Chronos observation size')
    for _,v in ipairs(obs)do assert(v==v and abs(v)<math.huge,'Non-finite Chronos observation')end
    return obs,{mirror=mirror,entity_count=2+#(packet.other_cars or {}),
        mask=Policy.mask(packet.ground_estimate,packet.boost,hasFlip,packet.turtled)}
end
return Policy

end)()
local Keyboard=(function()
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
function Keyboard:matches(wanted)
    for _,key in ipairs(names)do
        if self.input:IsKeyDown(codes[key])~=(wanted[key]==true)then return false,key end
    end
    return true
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

end)()
local Arena=(function()
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
    local probe={selection_boxes=0,best_error=nil,candidates={}}
    local sizeMatch,ambiguous=nil,false
    for _,part in ipairs(model:GetDescendants())do
        if part:IsA("BasePart")and part~=root then
            local box=part:FindFirstChildOfClass("SelectionBox")
            if box and box.Adornee==part then
                probe.selection_boxes=probe.selection_boxes+1
                local k=1/self.profile.roblox_studs_per_sim_unit
                local measured={part.Size.Z*k,part.Size.X*k,part.Size.Y*k}
                local localOffset=root.CFrame:ToObjectSpace(part.CFrame).Position
                local offset={-localOffset.Z*k,localOffset.X*k,localOffset.Y*k}
                if #probe.candidates<6 then probe.candidates[#probe.candidates+1]={size=measured,offset=offset}end
                for name,config in pairs(self.profile.car_presets)do
                    local sizeError=0
                    for i=1,3 do sizeError=sizeError+abs(measured[i]-config.size[i])end
                    if sizeError<.1 then
                        if sizeMatch and sizeMatch~=name then ambiguous=true end
                        sizeMatch=name
                    end
                    local error=0
                    for i=1,3 do error=error+abs(measured[i]-config.size[i])+abs(offset[i]-config.offset[i])end
                    if not probe.best_error or error<probe.best_error then
                        probe.best_error=error;probe.closest_preset=name
                    end
                    if error<1 then self.preset=name;self.sizeVerified=true;self.hitboxVerified=true;self.hitboxProbe=probe;return end
                end
            end
        end
    end
    self.sizeVerified=sizeMatch~=nil and not ambiguous
    self.preset=self.sizeVerified and sizeMatch or "standard";self.hitboxVerified=false
    probe.dimension_preset=self.sizeVerified and sizeMatch or nil
    probe.offset_verified=false
    self.hitboxProbe=probe
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
    local nearBoundary=abs(p[1])>self.profile.arena.EXTENT_X-180 or abs(p[2])>self.profile.arena.EXTENT_Y-300
    -- A neutral policy action can deadlock at a goal post just as a held
    -- throttle can. Only count idle time at a boundary, away from ball control.
    if moved>cfg.minimum_travel or(abs(previous[1])<.5 and not inverted and not nearBoundary)then
        self.windowAt=now;self.windowPosition=table.clone(p);return nil
    end
    if now-self.windowAt<cfg.stuck_seconds or now<(self.cooldownUntil or 0)then return nil end
    self.windowAt=now;self.windowPosition=table.clone(p)
    local ballDistance=length({p[1]-packet.ball.position[1],p[2]-packet.ball.position[2],p[3]-packet.ball.position[3]})
    if ballDistance<(packet.ball_radius or 91.25)+250 then return nil end
    local gap,normal=self:query(p)
    if packet.ground_estimate and(abs(normal[3])<.8 or nearBoundary)and gap<120 then
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

end)()
local Pads=(function()
-- Render cues verified against PadsView/PadLook: yellow rings mean active;
-- grey/dark rings mean cooldown. Position comes from each static PadHalo.
local Pads={}
Pads.__index=Pads
function Pads.new(profile)
    return setmetatable({profile=profile,entries={},lastIndex=-math.huge,lastRead=-math.huge,
        known=0,total=0},Pads)
end
local function horizontal(a,b)return (a.X-b.X)^2+(a.Z-b.Z)^2 end
function Pads:index(scene,now)
    -- Match play nests BoostPads under MatchView; freeplay may put it directly
    -- under the scene. The caller scopes discovery to the local car's view.
    local folder=scene:FindFirstChild("BoostPads",true)
    if folder==self.folder and now-self.lastIndex<2 then return end
    local previous={}
    if folder==self.folder then
        for _,entry in ipairs(self.entries)do previous[entry.halo]=entry end
    end
    self.folder=folder;self.lastIndex=now;self.entries={};self.known=0
    if not folder then self.total=0;return end
    local rings={}
    for _,part in ipairs(folder:GetDescendants())do
        if part:IsA("BasePart")then
            if part.Name=="PadHalo"then
                local entry=previous[part]or{halo=part}
                entry.rings={};self.entries[#self.entries+1]=entry
            elseif part.Name=="PadRing"then rings[#rings+1]=part end
        end
    end
    -- Assign each ring to its nearest halo, so similarly named decorations
    -- and nearby pad effects cannot be treated as extra boost pads.
    for _,ring in ipairs(rings)do
        local best,distance=nil,16^2
        for _,entry in ipairs(self.entries)do
            local d=horizontal(ring.Position,entry.halo.Position)
            if d<distance then best,distance=entry,d end
        end
        if best then best.rings[#best.rings+1]=ring end
    end
    self.total=#self.entries
    for _,entry in ipairs(self.entries)do
        local count=#entry.rings
        if count==16 then entry.big=true elseif count==10 then entry.big=false end
        local p=entry.halo.Position;local k=1/self.profile.roblox_studs_per_sim_unit
        if entry.big~=nil then
            entry.position={p.X*k,p.Z*k,entry.big and 73 or 70}
        end
    end
end
function Pads:read(scene,carPosition,now)
    self:index(scene,now)
    if now-self.lastRead>=.2 then
        self.lastRead=now;self.known=0
        for _,entry in ipairs(self.entries)do
            local wasActive=entry.active
            entry.active=nil
            if entry.big~=nil then
                local yellow,valid=0,true
                for _,ring in ipairs(entry.rings)do
                    if not ring:IsDescendantOf(self.folder)then valid=false;break end
                    local c=ring.Color
                    if type(ring.Transparency)~="number"or ring.Transparency>.25 or not c then valid=false;break end
                    if c.R>.8 and c.G>.6 and c.B<.65 then yellow=yellow+1
                    elseif c.B<c.R+.015 or c.B<c.G+.015 then
                        -- Other skins/tints are not a verified availability cue.
                        valid=false;break
                    end
                end
                if valid then
                    entry.active=yellow==#entry.rings;self.known=self.known+1
                    if entry.active then entry.emptyAt=nil
                    elseif wasActive==true then entry.emptyAt=now end
                else entry.emptyAt=nil end
            end
        end
    end
    local candidates={}
    for _,entry in ipairs(self.entries)do
        if entry.active~=nil and entry.position then
            local p=entry.position
            candidates[#candidates+1]={position=p,is_big=entry.big,active=entry.active,
                cooldown_remaining=entry.emptyAt and math.max(.01,(entry.big and 10 or 4)-(now-entry.emptyAt))or nil,
                distance=(p[1]-carPosition[1])^2+(p[2]-carPosition[2])^2}
        end
    end
    table.sort(candidates,function(a,b)return a.distance<b.distance end)
    local selected,picked={},{}
    local limit=self.profile.policy_boost_limit
    -- Keep large-pad information even when several small pads are closer.
    local reserve=math.min(2,math.floor(limit/3))
    for _,candidate in ipairs(candidates)do
        if candidate.is_big and #selected<reserve then selected[#selected+1]=candidate;picked[candidate]=true end
    end
    for _,candidate in ipairs(candidates)do
        if #selected>=limit then break end
        if not picked[candidate]then selected[#selected+1]=candidate end
    end
    table.sort(selected,function(a,b)return a.distance<b.distance end)
    return selected
end
return Pads

end)()
local Teams=(function()
-- Team identity from rendered match UI. No game modules or private tables loaded.
local Teams={}
Teams.__index=Teams
local function plain(value)
    return (tostring(value or ""):gsub("<[^>]*>",""):gsub("&amp;","&"):gsub("&lt;","<"):gsub("&gt;",">"):match("^%s*(.-)%s*$")):lower()
end
local function colorTeam(color,palette,dimmed)
    if not color then return nil end
    for team,base in ipairs(palette)do
        local scale=1
        if dimmed then
            scale=(color.R*base[1]+color.G*base[2]+color.B*base[3])/(base[1]^2+base[2]^2+base[3]^2)
        end
        if scale>=(dimmed and .95^8-.01 or .99)and scale<=1.01 then
            if math.max(math.abs(color.R-base[1]*scale),math.abs(color.G-base[2]*scale),math.abs(color.B-base[3]*scale))<.012 then return team-1 end
        end
    end
end
local function rgb(r,g,b)return {r/255,g/255,b/255}end
function Teams.plate(color)
    return colorTeam(color,{rgb(46,120,226),rgb(232,116,38)},true)
end
function Teams.relation(tag)
    -- MatchView.setNames: teammate Plate height=.74 plus Boost; opponent=1.
    local plate=tag and tag:FindFirstChild("Plate")
    local height=plate and plate.Size and plate.Size.Y and plate.Size.Y.Scale
    local holder=tag and tag:FindFirstChild("Boost")
    local fill=holder and holder:FindFirstChild("Fill")
    if type(height)~="number"then return nil end
    if math.abs(height-.74)<.001 and fill then return true end
    if math.abs(height-1)<.001 and not holder then return false end
end
local function edgeTeam(row)
    local face=row:FindFirstChild("Face")
    local edge=face and face:FindFirstChild("TeamEdge")
    if not edge then return nil end
    if edge.BackgroundTransparency==1 then
        for _,child in ipairs(edge:GetChildren())do
            if child:IsA("Frame")then edge=child;break end
        end
    end
    -- ScoreSheet's standard and cel layouts use these exact team-edge colors.
    local c=edge.BackgroundColor3
    return colorTeam(c,{rgb(30,155,240),rgb(252,122,2)},false)
        or colorTeam(c,{rgb(92,208,255),rgb(252,122,2)},false)
end
function Teams.new(player)
    return setmetatable({player=player,names={},source="waiting for match team",at=-math.huge},Teams)
end
function Teams:roster(pg)
    local names,counts={}, {[0]=0,[1]=0}
    local sheet=pg:FindFirstChild("CarSoccerMatchSheet")
    if sheet then
        for _,row in ipairs(sheet:GetDescendants())do
            if row:IsA("Frame")and row.Name:match("^Row%d+$")then
                local team=edgeTeam(row)
                if team~=nil then
                    counts[team]=counts[team]+1
                    for _,item in ipairs(row:GetDescendants())do
                        if item:IsA("TextLabel")then
                            local name=plain(item.Text)
                            if name~="" and not tonumber(name)then
                                if names[name]and names[name].row~=row then names[name]={ambiguous=true}
                                else names[name]={team=team,row=row}end
                            end
                        end
                    end
                end
            end
        end
    end
    self.names,self.counts=names,counts
    local own=names[plain(self.player.Name)]
    if not own and self.player.DisplayName then own=names[plain(self.player.DisplayName)]end
    if own and not own.ambiguous then return own.team end
end
function Teams:named(tag)
    local plate=tag and tag:FindFirstChild("Plate")
    local label=plate and plate:FindFirstChild("Name")
    local row=label and self.names[plain(label.Text)]
    if row and not row.ambiguous then return row.team end
end
function Teams:detect(pg,scene,ownRoot,now,manual)
    if now-self.at<.2 and manual==self.manual and scene==self.scene then return self.team,self.source end
    self.at,self.manual,self.scene=now,manual,scene
    local roster=self:roster(pg)
    local vote,conflict
    for _,tag in ipairs(scene:GetDescendants())do
        if tag.Name=="Nametag"and tag:IsA("BillboardGui")and tag.Enabled~=false and tag.Parent~=ownRoot then
            local root=tag.Parent
            local model=root and root.Parent
            if root and root:IsA("BasePart")and model and model:IsA("Model")and model.PrimaryPart==root then
                local relation=Teams.relation(tag)
                local plate=tag:FindFirstChild("Plate")
                local team=self:named(tag)or(plate and Teams.plate(plate.BackgroundColor3))
                if team~=nil and relation~=nil then
                    local inferred=relation and team or 1-team
                    if vote~=nil and vote~=inferred then conflict=true end
                    vote=inferred
                end
            end
        end
    end
    if manual~=nil then self.team,self.source=manual,"manual override"
    elseif conflict or(roster~=nil and vote~=nil and roster~=vote)then self.team,self.source=nil,"team UI updating; waiting"
    elseif roster~=nil then self.team,self.source=roster,"scoreboard: "..self.player.Name
    elseif vote~=nil then self.team,self.source=vote,"nameplate relationship"
    else
        local hud=pg:FindFirstChild("CarSoccerMatchHud")
        if hud and hud.Enabled then self.team,self.source=nil,"open scoreboard once to identify your team"
        else self.team,self.source=0,"freeplay blue (no active match HUD)"end
    end
    return self.team,self.source
end
return Teams

end)()
local Cars=(function()
-- Read remote cars from the game's team nameplates, never chassis paint.
local Cars={}
Cars.__index=Cars
local colors={{46/255,120/255,226/255},{232/255,116/255,38/255}}
function Cars.team(color)
    if not color then return nil end
    local c={color.R,color.G,color.B}
    if not c[1]or not c[2]or not c[3]then return nil end
    for i,base in ipairs(colors)do
        local scale=(c[1]*base[1]+c[2]*base[2]+c[3]*base[3])/(base[1]^2+base[2]^2+base[3]^2)
        if scale>=.95^8-.01 and scale<=1.01 then
            local error=0
            for j=1,3 do error=math.max(error,math.abs(c[j]-base[j]*scale))end
            if error<.025 then return i-1 end
        end
    end
end
function Cars.new(profile,arenaClass)
    return setmetatable({profile=profile,arenaClass=arenaClass,tracked={},scanAt=-math.huge},Cars)
end
function Cars:read(scene,ownRoot,ballRoot,now,pose,ball,ballRadius,ownTeam)
    if scene~=self.scene then self.scene=scene;self.tracked={};self.scanAt=-math.huge end
    if now-self.scanAt>=.5 then
        self.scanAt=now
        local found={}
        for _,tag in ipairs(scene:GetDescendants())do
            if tag.Name=="Nametag"and tag:IsA("BillboardGui")then
                local root=tag.Parent
                local model=root and root.Parent
                if root and root:IsA("BasePart")and model and model:IsA("Model")
                    and model.PrimaryPart==root and root~=ownRoot and root~=ballRoot then
                    local entry=self.tracked[root]or{arena=self.arenaClass.new(self.profile)}
                    entry.tag,entry.model,entry.root=tag,model,root
                    found[root]=entry
                end
            end
        end
        self.tracked=found
    end
    local rows={}
    self.opponents,self.teammates,self.unknown,self.boostUnknown=0,0,0,0
    for root,entry in pairs(self.tracked)do
        local plate=entry.tag:FindFirstChild("Plate")
        local relation=self.teams and Teams.relation(entry.tag)
        local team=self.teams and self.teams:named(entry.tag)
        local plateTeam=plate and Cars.team(plate.BackgroundColor3)
        if team==nil and relation~=nil then team=relation and ownTeam or 1-ownTeam end
        if team==nil then team=plateTeam end
        local visible=root~=ownRoot and root~=ballRoot and root:IsDescendantOf(scene)
            and entry.model.PrimaryPart==root and entry.tag:IsDescendantOf(root)and entry.tag.Enabled~=false
        if visible and team~=nil then
            local frame=root.CFrame
            local dt=entry.at and now-entry.at or 0
            if entry.frame and dt>0 and dt<=.3 then
                local body,distance=pose(frame,entry.frame,dt)
                if distance/dt<=350 then
                    if now-(entry.arena.lastMeasure or -math.huge)>2 then entry.arena:measureCar(entry.model,root)end
                    if not entry.groundAt or now-entry.groundAt>=.1 then
                        entry.ground=entry.arena:ground(body,ball,ballRadius);entry.groundAt=now
                    end
                    if entry.ground then entry.lastGround=now end
                    body.team=team
                    body.ground_estimate=entry.ground==true
                    body.flip_estimate=body.ground_estimate or(entry.lastGround~=nil and now-entry.lastGround<1.25)
                    local holder=entry.tag:FindFirstChild("Boost")
                    local fill=holder and holder:FindFirstChild("Fill")
                    -- Only teammates have a source-backed boost bar. Opponent
                    -- boost/flip are explicitly estimates, not hidden state.
                    body.boost_verified=team==ownTeam and fill~=nil and relation~=false
                    body.boost_estimate=body.boost_verified and math.clamp(fill.Size.X.Scale*100,0,100)or 50
                    rows[#rows+1]=body
                else entry.lastGround=nil;entry.groundAt=nil end
            else entry.lastGround=nil;entry.groundAt=nil end
            entry.frame,entry.at=frame,now
        else
            if visible then self.unknown=self.unknown+1 end
            entry.frame,entry.at,entry.lastGround=nil,nil,nil
        end
    end
    local p=ownRoot.Position
    local scale=1/self.profile.roblox_studs_per_sim_unit
    local function distance(body)
        local v=body.position
        return (v[1]-p.X*scale)^2+(v[2]-p.Z*scale)^2+(v[3]-p.Y*scale)^2
    end
    table.sort(rows,function(a,b)return distance(a)<distance(b)end)
    while #rows>5 do table.remove(rows)end
    for _,body in ipairs(rows)do
        if body.team==ownTeam then self.teammates=self.teammates+1 else self.opponents=self.opponents+1 end
        if not body.boost_verified then self.boostUnknown=self.boostUnknown+1 end
    end
    return rows
end
return Cars

end)()
local Kickoff=(function()
-- Bounded standard-stadium kickoff. No game modules or authoritative remotes.
local Kickoff={}
Kickoff.__index=Kickoff
local spawns={{-2048,-2560},{2048,-2560},{-256,-3840},{256,-3840},{0,-4608}}
local function speed(v)return math.sqrt(v[1]^2+v[2]^2+v[3]^2)end
local function length2(v)return math.sqrt(v[1]^2+v[2]^2)end
local function heading(car,delta)
    local f,u=car.forward,car.up
    local right={u[2]*f[3]-u[3]*f[2],u[3]*f[1]-u[1]*f[3],u[1]*f[2]-u[2]*f[1]}
    return math.atan2(delta[1]*right[1]+delta[2]*right[2],delta[1]*f[1]+delta[2]*f[2])
end
function Kickoff.new(profile)return setmetatable({profile=profile},Kickoff)end
function Kickoff:reset()
    self.state,self.stableAt,self.phase,self.moveAt,self.armedAt,self.latched,self.flipped=nil,nil,nil,nil,nil,nil,nil
end
function Kickoff:countdown(pg)
    local hud=pg:FindFirstChild("CarSoccerMatchHud")
    local call=hud and hud:FindFirstChild("Call",true)
    if not call or hud.Enabled==false then return false end
    local ancestor=call
    while ancestor and ancestor~=hud do
        if ancestor.Visible==false then return false end
        ancestor=ancestor.Parent
    end
    for _,label in ipairs(call:GetDescendants())do
        if label:IsA("TextLabel")and label.Visible~=false then
            local n=tonumber(label.Text)
            if n and n>=1 and n<=10 then return true end
        end
    end
    return false
end
function Kickoff:step(packet,now,pg)
    local car,ball=packet.car,packet.ball
    local p,b=car.position,ball.position
    local rest=self.profile.physics.BALL_REST_Z*(packet.ball_radius or self.profile.physics.BALL_RADIUS)/self.profile.physics.BALL_RADIUS
    local centered=length2(b)<25 and math.abs(b[3]-rest)<20 and speed(ball.velocity)<45
    if self.latched then
        if not centered then self.latched=false;self.stableAt=nil end
        return nil
    end
    if not self.state then
        local spawn=false
        local sign=packet.team==0 and 1 or -1
        for _,s in ipairs(spawns)do
            if (p[1]-sign*s[1])^2+(p[2]-sign*s[2])^2<100^2 then spawn=true;break end
        end
        local eligible=centered and spawn and packet.ground_estimate and math.abs(p[3]-17)<70 and car.up[3]>.65 and speed(car.velocity)<80
            and math.abs(heading(car,{-p[1],-p[2]}))<.35
        if not eligible then self.stableAt=nil;return nil end
        self.stableAt=self.stableAt or now
        if now-self.stableAt<.15 then return {0,0,0,0,0,0,0,0},"kickoff: detecting"end
        -- Respect a closer teammate and standard left-goes tie priority.
        for _,other in ipairs(packet.other_cars or {})do
            if other.team==packet.team then
                local d,own=length2(other.position),length2(p)
                if d<own-150 or(math.abs(d-own)<150 and other.position[1]*sign>p[1]*sign+100)then
                    self.latched=true;return nil
                end
            end
        end
        self.state="drive";self.armedAt=now;self.flipped=false;self.moveAt=nil
    end
    local dx,dy=b[1]-p[1],b[2]-p[2]
    local distance=math.sqrt(dx*dx+dy*dy)
    if not centered or distance<220 or now-self.armedAt>12 or(self.moveAt and now-self.moveAt>4.5)then
        self.state=nil;self.stableAt=nil;self.latched=true;return nil
    end
    if not self.moveAt and speed(car.velocity)>100 then self.moveAt=now end
    -- Dedicated countdown is only trusted after strict ball/spawn detection.
    if not self.moveAt and pg and self:countdown(pg)then
        return {0,0,0,0,0,0,0,0},"kickoff: countdown"
    end
    local error=heading(car,{dx,dy})
    local steer=error>.07 and 1 or(error<-.07 and -1 or 0)
    local action={1,steer,-1,steer,0,0,math.abs(error)<.45 and packet.boost>0 and 1 or 0,0}
    if self.state=="drive"and not self.flipped and self.moveAt and packet.ground_estimate
        and speed(car.velocity)>1050 and distance>1150 and distance<2650 and math.abs(error)<.12 then
        self.state="jump";self.phase=now;self.flipped=true
    end
    if self.state=="jump"then
        if now-self.phase>=.10 then self.state="release";self.phase=now
        else action[6]=1 end
    elseif self.state=="release"then
        if now-self.phase>=.10 then self.state="flip";self.phase=now;action[6]=1 end
    elseif self.state=="flip"then
        if now-self.phase>=.12 then self.state="recover";self.phase=now
        else action[6]=1 end
    elseif self.state=="recover"then
        -- Stop pitching after the dodge pulse; return to steering once grounded.
        action[3]=0;action[4]=0
        if now-self.phase>=.28 then self.state="drive"end
    end
    if self.state=="flip"or self.state=="jump"or self.state=="release"then
        action[2]=0;action[4]=0
    end
    if self.state=="recover"then action[3]=0;action[4]=0 end
    return action,"kickoff: "..self.state
end
return Kickoff

end)()
local Physics=(function()
-- Independent ball/world predictor. All coordinates use the numeric arena
-- profile, not rendered mesh bounds. Future car touches are deliberately absent.
local Physics={}
Physics.__index=Physics
local abs,min,max,sqrt=math.abs,math.min,math.max,math.sqrt
local function dot(a,b)return a[1]*b[1]+a[2]*b[2]+a[3]*b[3]end
local function cross(a,b)return {a[2]*b[3]-a[3]*b[2],a[3]*b[1]-a[1]*b[3],a[1]*b[2]-a[2]*b[1]}end
local function length(v)return sqrt(dot(v,v))end
local function distance(a,b)return sqrt((a[1]-b[1])^2+(a[2]-b[2])^2+(a[3]-b[3])^2)end
local function limit(v,cap)
    local speed=length(v)
    if speed>cap then for i=1,3 do v[i]=v[i]*cap/speed end end
end
local function copy(ball)
    local body={position=table.clone(ball.position),velocity=table.clone(ball.velocity),
        angular_velocity=table.clone(ball.angular_velocity or {0,0,0}),slow=ball.slow or 0}
    if ball.forward then body.forward=table.clone(ball.forward)end
    if ball.up then body.up=table.clone(ball.up)end
    return body
end
local function median(values)
    local sorted=table.clone(values);table.sort(sorted)
    return sorted[math.ceil(#sorted/2)]
end

function Physics.new(profile,arena)
    return setmetatable({profile=profile,arena=arena,gravity=profile.physics.GRAVITY_Z,
        history={},gravitySamples={},errors={},trace={},events={},status="saved profile",resets=0,
        totalFlightErrors=0},Physics)
end

function Physics:mark(kind,now,reason)
    self.events[#self.events+1]={kind=kind,time=now,reason=reason}
    if #self.events>40 then table.remove(self.events,1)end
end

-- One stationary-world sphere contact has a closed-form normal/friction impulse.
-- The sphere's contact inertia gives tangent effective mass m/3.5. Restitution
-- uses pre-force velocity; split penetration correction never adds bounce energy.
function Physics:step(ball,radius,dt)
    local cfg=self.profile.physics
    local p,v,w=ball.position,ball.velocity,ball.angular_velocity
    if length(v)==0 and length(w)==0 then return false end -- simulator sleep state
    local drag=(1-cfg.BALL_DRAG)^dt
    for i=1,3 do v[i]=v[i]*drag end
    local old={v[1],v[2],v[3]}
    v[3]=v[3]+self.gravity*dt
    local worldRadius=radius*cfg.BALL_WORLD_RADIUS/cfg.BALL_RADIUS
    local d=self.arena:distance(p)
    local touched,obstructed=false,false
    if d-worldRadius<cfg.CONTACT_BREAKING_THRESHOLD then
        local _,n=self.arena:query(p)
        local flat=abs(n[3])>.9999 or(abs(n[3])<.0001 and(abs(n[1])>.9999 or abs(n[2])>.9999))
        if d-worldRadius<(flat and cfg.BALL_WORLD_CONTACT_FLAT or cfg.CONTACT_BREAKING_THRESHOLD)then
            touched=true
            obstructed=n[3]<.9
            local incoming=dot(old,n)
            local bounce=abs(incoming)>=cfg.RESTITUTION_VEL_THRESHOLD and max(-incoming*cfg.BALLWORLD_RESTITUTION,0)or 0
            local impulse=max(0,bounce-dot(v,n))
            local spin=cross(w,n)
            local slip={v[1]-radius*spin[1],v[2]-radius*spin[2],v[3]-radius*spin[3]}
            local normalSlip=dot(slip,n)
            for i=1,3 do slip[i]=slip[i]-normalSlip*n[i]end
            local speed=length(slip)
            local friction=0
            if speed>1e-8 then
                for i=1,3 do slip[i]=slip[i]/speed end
                friction=-min(speed/3.5,cfg.BALLWORLD_FRICTION*impulse)
            end
            local torque=cross(n,slip)
            local push=cfg.SOLVER_ERP2*max(radius-d,0)
            for i=1,3 do
                v[i]=v[i]+n[i]*impulse+slip[i]*friction
                w[i]=w[i]-torque[i]*2.5/radius*friction
                p[i]=p[i]+n[i]*push
            end
        end
    end
    -- The saved solver integrates before its final speed limits.
    for i=1,3 do p[i]=p[i]+v[i]*dt end
    limit(v,cfg.BALL_MAX_SPEED);limit(w,cfg.BALL_MAX_ANG_SPEED)
    if length(v)<cfg.BALL_SLEEP_LIN_SPEED and length(w)<cfg.BALL_SLEEP_ANG_SPEED then
        ball.slow=(ball.slow or 0)+dt
        if ball.slow>cfg.BALL_SLEEP_TIME then
            ball.velocity={0,0,0};ball.angular_velocity={0,0,0}
        end
    else ball.slow=0 end
    return touched,obstructed
end

function Physics:predict(ball,radius,seconds,stride,checkpoint)
    radius=radius or self.profile.physics.BALL_RADIUS
    local state=copy(ball)
    local result={{time=0,position=table.clone(state.position),velocity=table.clone(state.velocity),bounces=0,obstructions=0}}
    local dt=1/self.profile.physics.TICK_RATE
    local steps=math.floor(math.clamp(seconds or 2.5,0,3)*self.profile.physics.TICK_RATE+.5)
    local bounces,obstructions=0,0
    for tick=1,steps do
        local touched,blocked=self:step(state,radius,dt)
        if touched then bounces=bounces+1 end
        if blocked then obstructions=obstructions+1 end
        if tick%(stride or 4)==0 or tick==steps then
            result[#result+1]={time=tick*dt,position=table.clone(state.position),
                velocity=table.clone(state.velocity),bounces=bounces,obstructions=obstructions}
        end
        if checkpoint and tick%2==0 then checkpoint()end
    end
    return result
end

function Physics:reset()
    self.history={};self.forecast=nil;self.lastAt=nil;self.lastBall=nil
    self.errors={};self.error=nil;self.mismatch=false
    self.resets=self.resets+1
end

function Physics:clearFlight(packet,radius)
    local ball=packet.ball
    if ball.position[3]<radius+180 or self.arena:distance(ball.position)<radius+100 then return false end
    local function close(car)
        return distance(car.position,ball.position)<radius+250+min(length(ball.velocity)*.12,500)
    end
    if close(packet.car)then return false end
    for _,car in ipairs(packet.other_cars or {})do if close(car)then return false end end
    return true
end

-- Passive calibration uses only isolated airborne positions. Finite-difference
-- velocities from rendered frames are averages, so fitting their acceleration
-- directly would mistake interpolation and touches for gravity.
function Physics:observe(packet,now,cheap)
    if not packet then if self.lastAt then self:reset()end;return end
    local radius=packet.ball_radius or self.profile.physics.BALL_RADIUS
    local p=packet.ball.position
    if self.lastAt then
        local dt=now-self.lastAt
        if dt<=0 or dt>.15 or abs(radius-self.radius)>1 or self.team~=packet.team
            or distance(p,self.lastBall)>self.profile.physics.BALL_MAX_SPEED*dt+100 then self:reset()end
    end
    self.lastAt,self.lastBall,self.radius,self.team=now,table.clone(p),radius,packet.team
    local clear=not cheap and self:clearFlight(packet,radius)
    if not clear then self.history={};self.forecast=nil else
        local h=self.history
        h[#h+1]={at=now,p=table.clone(p)}
        while #h>1 and now-h[1].at>.6 do table.remove(h,1)end
        if #h>=7 and now-(self.lastFit or -math.huge)>=.1 then
            local a,b,c=h[1],h[math.floor((#h+1)/2)],h[#h]
            local dt1,dt2=b.at-a.at,c.at-b.at
            if min(dt1,dt2)>=.09 then
                local acceleration={}
                for i=1,3 do acceleration[i]=2*((c.p[i]-b.p[i])/dt2-(b.p[i]-a.p[i])/dt1)/(dt1+dt2)end
                local gravity=acceleration[3]+(-math.log(1-self.profile.physics.BALL_DRAG))*packet.ball.velocity[3]
                if sqrt(acceleration[1]^2+acceleration[2]^2)<250 and gravity< -150 and gravity> -3000 then
                    local samples=self.gravitySamples
                    samples[#samples+1]=gravity;if #samples>15 then table.remove(samples,1)end
                    if #samples>=6 then
                        local middle=median(samples)
                        local deviations={};for i,g in ipairs(samples)do deviations[i]=abs(g-middle)end
                        if median(deviations)<max(35,abs(middle)*.08)then
                            self.gravity=middle;self.observedGravity=middle
                            self.status=abs(middle-self.profile.physics.GRAVITY_Z)>100 and "live gravity adapted"or "flight checked"
                        end
                    end
                end
                self.lastFit=now
            end
        end
        if self.forecast and now-self.forecast.at>=.2 then
            local future=self:predict(self.forecast.ball,radius,now-self.forecast.at,1000)
            local error=distance(p,future[#future].position)
            self.errors[#self.errors+1]=error;if #self.errors>20 then table.remove(self.errors,1)end
            self.error=median(self.errors)
            self.lastFlightError=self.error;self.lastFlightAt=now
            self.totalFlightErrors=self.totalFlightErrors+1
            self.forecast=nil
        end
        if not self.forecast then self.forecast={at=now,ball=copy(packet.ball)}end
    end
    -- A gross coordinate/arena mismatch cannot safely use this ground planner.
    self.mismatch=self.arena:distance(p)<-radius*2 or(self.error or 0)>radius*2
    if now-(self.traceAt or -math.huge)>=.2 then
        self.traceAt=now
        local others={}
        for _,car in ipairs(packet.other_cars or {})do
            local body=copy(car)
            body.team=car.team;body.boost_estimate=car.boost_estimate
            body.ground_estimate=car.ground_estimate;body.flip_estimate=car.flip_estimate
            others[#others+1]=body
        end
        local sample={time=now,car=copy(packet.car),ball=copy(packet.ball),
            other_cars=others,boost_pads=packet.boost_pads,
            team=packet.team,ground=packet.ground_estimate,radius=radius,boost=packet.boost,
            radius_verified=packet.ball_size_verified==true,car_preset=packet.car_preset,
            car_verified=packet.car_size_verified==true,wheel_contacts=packet.wheel_contacts,
            pads_known=packet.boost_known,pads_total=packet.boost_total,pad_folder_found=packet.pad_folder_found,
            hitbox_probe=packet.hitbox_probe,sample_dt=packet.sample_dt,
            decision=self.decision,decision_age=self.decision and self.decision.time and now-self.decision.time or nil,
            runtime=self.runtime,physics_status=self.status,gravity=self.gravity,
            flight_error=self.error,plan=self.plan}
        self.latestPose=sample
        if not self.runtime or self.runtime.enabled then
            self.trace[#self.trace+1]=sample
            if #self.trace>150 then table.remove(self.trace,1)end
        end
    end
end

function Physics:report()
    return {version="local-6.8",profile=self.profile.name,units="simulation units; seconds",
        studs_per_unit=self.profile.roblox_studs_per_sim_unit,arena=self.profile.arena,
        saved_physics=self.profile.physics,gravity_used=self.gravity,observed_gravity=self.observedGravity,
        gravity_samples=#self.gravitySamples,flight_position_error_median=self.error,
        flight_error_samples=#self.errors,status=self.status,profile_mismatch=self.mismatch==true,
        last_valid_flight_error=self.lastFlightError,last_valid_flight_time=self.lastFlightAt,
        total_flight_error_samples=self.totalFlightErrors,resets=self.resets,trace=self.trace,latest_pose=self.latestPose,
        trace_collection="Active-run poses; paused sampling does not replace the driving trace",
        runtime=self.runtime,events=self.events,last_error=self.lastError,
        limitations="Ball/world forecast only; future car touches and exact curved goal-frame contact are uncertain. Ground reach is an estimate."}
end

return Physics

end)()
local Intercept=(function()
-- Ground approach controller. The trained policy retains close touches, jumps,
-- aerials, wall play and recovery. This is a bounded reach estimate, not a car sim.
local Intercept={}
Intercept.__index=Intercept
local abs,min,max,sqrt=math.abs,math.min,math.max,math.sqrt
local function dot(a,b)return a[1]*b[1]+a[2]*b[2]+a[3]*b[3]end
local function distance(a,b)return sqrt((a[1]-b[1])^2+(a[2]-b[2])^2)end
local function unit(x,y)
    local d=sqrt(x*x+y*y);if d<1e-8 then return 0,1 end
    return x/d,y/d
end
local function sign(x)return x<0 and -1 or 1 end
local function curve(points,value)
    for i=2,#points do
        if value<=points[i][1]then
            local a,b=points[i-1],points[i]
            return a[2]+(b[2]-a[2])*math.clamp((value-a[1])/(b[1]-a[1]),0,1)
        end
    end
    return points[#points][2]
end
function Intercept.new(profile,arena,physics)
    return setmetatable({profile=profile,arena=arena,physics=physics,supportEnabled=false},Intercept)
end
function Intercept:reset()self.side=nil;self.last=nil;self.padTarget=nil;self.goalX=nil end
function Intercept:goal(team)
    if self.calibration then return self.calibration:goal(team)end
    local a=self.profile.arena;local sign=team==0 and -1 or 1
    return {origin={0,sign*a.EXTENT_Y,0},side={1,0,0},normal={0,sign,0},half_width=a.MOUTH_HALF_WIDTH,height=a.MOUTH_HEIGHT}
end

-- Rank ground-shot lanes against the observed defenders. Constant-velocity
-- projections are a short tactical estimate, not a prediction of their actions.
function Intercept:shotLane(packet,future,seconds)
    local goal=self:goal(1-packet.team)
    local lateral=(future[1]-goal.origin[1])*goal.side[1]+(future[2]-goal.origin[2])*goal.side[2]
    local carLateral=(packet.car.position[1]-goal.origin[1])*goal.side[1]+(packet.car.position[2]-goal.origin[2])*goal.side[2]
    local preferred=math.clamp(lateral*.25,-goal.half_width*.55,goal.half_width*.55)
    local half=goal.half_width-(packet.ball_radius or self.profile.physics.BALL_RADIUS)-120
    local function cost(x)
        local dx,dy=goal.origin[1]+goal.side[1]*x-future[1],goal.origin[2]+goal.side[2]*x-future[2]
        local length=max(1,sqrt(dx*dx+dy*dy))
        local score=abs(x-preferred)*.015+(x-carLateral)^2*.000001
        for _,other in ipairs(packet.other_cars or {})do
            if(other.team==0 or other.team==1)and other.team~=packet.team and other.position and other.position[3]<250 then
                local velocity=other.velocity or {0,0,0}
                local px,py=other.position[1],other.position[2]
                local u=math.clamp(((px-future[1])*dx+(py-future[2])*dy)/(length*length),0,1)
                local time=min(2.5,seconds+u*length/2400)
                px=px+velocity[1]*time;py=py+velocity[2]*time
                u=math.clamp(((px-future[1])*dx+(py-future[2])*dy)/(length*length),0,1)
                local gap=sqrt((px-future[1]-dx*u)^2+(py-future[2]-dy*u)^2)
                score=score+max(0,460-gap)
            end
        end
        return score
    end
    local best,bestCost=preferred,cost(preferred)
    for _,x in ipairs({-half,0,half})do
        local value=cost(x)
        if value<bestCost then best,bestCost=x,value end
    end
    if self.goalX and abs(self.goalX)<=half and cost(self.goalX)<=bestCost+25 then best=self.goalX end
    self.goalX=best
    return best
end

function Intercept:support(packet,future,danger)
    local attack=packet.team==0 and 1 or -1
    if not self.supportEnabled or danger or(future[2]*attack< -1800 and packet.ball.velocity[2]*attack< -250)then return nil end
    local function eta(body)
        local dx,dy=unit(future[1]-body.position[1],future[2]-body.position[2])
        local v=body.velocity or {0,0,0}
        local speed=math.clamp(v[1]*dx+v[2]*dy+650,650,1800)
        local heading=body.forward and abs(self:heading(body,future))or 0
        return distance(body.position,future)/speed+heading*.3
    end
    local own=eta(packet.car)
    local chosen,best=nil,own-.4
    for _,other in ipairs(packet.other_cars or {})do
        if other.team==packet.team and other.position and other.position[3]<150
            and other.ground_estimate==true and(other.position[2]-future[2])*attack< -120
            and distance(other.position,future)<1300 and other.forward and other.up and other.velocity then
            local dx,dy=unit(future[1]-other.position[1],future[2]-other.position[2])
            local closing=other.velocity[1]*dx+other.velocity[2]*dy
            local facing=other.forward[1]*dx+other.forward[2]*dy
            if closing>500 and facing>.85 then
                local arrival=eta(other)
                if arrival<best then chosen,best=other,arrival end
            end
        end
    end
    if not chosen then return nil end
    local side=sign(future[1]-chosen.position[1])
    if abs(future[1]-chosen.position[1])<100 then side=sign(packet.car.position[1]-future[1])end
    return {math.clamp(future[1]*.45+side*750,-self.profile.arena.EXTENT_X+700,self.profile.arena.EXTENT_X-700),
        math.clamp(future[2]-attack*1500,-self.profile.arena.EXTENT_Y+650,self.profile.arena.EXTENT_Y-650),17},best
end

function Intercept:heading(car,target)
    local x,y=target[1]-car.position[1],target[2]-car.position[2]
    -- Native car right = up x forward (the Roblox/simulation swap reflects axes).
    local right={car.up[2]*car.forward[3]-car.up[3]*car.forward[2],
        car.up[3]*car.forward[1]-car.up[1]*car.forward[3],
        car.up[1]*car.forward[2]-car.up[2]*car.forward[1]}
    return math.atan2(x*right[1]+y*right[2],x*car.forward[1]+y*car.forward[2])
end

-- A small 60 Hz longitudinal integration uses throttle taper, measured cap and
-- finite boost. Turning consumes time; reachable balls must also be low enough.
function Intercept:travel(car,boost,seconds)
    local speed=max(0,dot(car.velocity,car.forward))
    local travel={0}
    local cfg=self.profile.physics
    for i=1,math.floor(seconds*60)do
        local throttle=4*cfg.THROTTLE_TORQUE_AMOUNT/cfg.CAR_MASS*curve(cfg.DRIVE_SPEED_TORQUE_FACTOR,speed)
        local acceleration=throttle
        if boost>0 then
            acceleration=acceleration+cfg.BOOST_ACCEL_GROUND
            boost=boost-cfg.BOOST_USED_PER_SECOND/60
        end
        speed=min(cfg.CAR_MAX_SPEED,speed+acceleration/60)
        travel[i+1]=travel[i]+speed/60
    end
    return travel
end
function Intercept:reach(car,boost,seconds,angle,travel)
    local ticks=math.floor(max(0,seconds-min(abs(angle)/2.5,.9))*60)
    travel=travel or self:travel(car,boost,seconds)
    return travel[min(ticks+1,#travel)]
end

-- Use verified active pads on an existing approach, with a small detour budget.
-- A grounded override must not hide boost information that the actor receives.
function Intercept:routePad(packet,target,danger,behind,radius)
    if packet.boost>=20 or danger or behind> -radius*.5 then self.padTarget=nil;return end
    local car,ball=packet.car,packet.ball
    local attack=packet.team==0 and 1 or -1
    if distance(car.position,ball.position)<1500
        or(ball.position[2]*attack< -self.profile.arena.EXTENT_Y*.35 and ball.velocity[2]*attack< -250)then
        self.padTarget=nil;return
    end
    local direct=distance(car.position,target)
    local tx,ty=unit(target[1]-car.position[1],target[2]-car.position[2])
    local chosen,score=nil,math.huge
    for _,pad in ipairs(packet.boost_pads or {})do
        if pad.active==true then
            local d=distance(car.position,pad.position)
            local detour=d+distance(pad.position,target)-direct
            local ahead=(pad.position[1]-car.position[1])*tx+(pad.position[2]-car.position[2])*ty
            if d>80 and d<(pad.is_big and 1400 or 650)and ahead>d*.2 and detour<min(350,120+direct*.1)then
                local cost=d*.2+detour-(pad.is_big and 150 or 0)
                if self.padTarget and distance(self.padTarget,pad.position)<1 then cost=cost-80 end
                if cost<score then chosen,score=pad,cost end
            end
        end
    end
    self.padTarget=chosen and table.clone(chosen.position)or nil
    return chosen
end

function Intercept:step(packet,modelAction,now)
    local car,ball=packet.car,packet.ball
    local arena=self.profile.arena
    local radius=packet.ball_radius or self.profile.physics.BALL_RADIUS
    local ballDistance=distance(car.position,ball.position)
    if self.physics.mismatch then return nil,"physics mismatch: model"end
    if not packet.ground_estimate or car.up[3]<.85 or car.position[3]>130
        or abs(car.position[1])>arena.EXTENT_X-300 then return nil end
    -- Ground assistance only: never invent aerial/flip timing or interrupt the
    -- actor at contact. Goals and side switches reset the approach hysteresis.
    if ballDistance<radius+300 then return nil end
    -- Near the ball we need the actor's jump decision; far ground approaches
    -- can be planned without paying for a model result that would be replaced.
    if ballDistance<1000 then
        if not modelAction then return nil,nil,true end
        if modelAction[6]>0 then return nil end
    end
    local trajectory=self.physics:predict(ball,radius,2.5)
    local attack=packet.team==0 and 1 or -1
    local ownGoal=self:goal(packet.team)
    local danger=false
    for _,sample in ipairs(trajectory)do
        local p=sample.position
        local dx,dy=p[1]-ownGoal.origin[1],p[2]-ownGoal.origin[2]
        if dx*ownGoal.normal[1]+dy*ownGoal.normal[2]>-radius
            and abs(dx*ownGoal.side[1]+dy*ownGoal.side[2])<ownGoal.half_width-radius*.5
            and p[3]-ownGoal.origin[3]<ownGoal.height+radius then danger=true;break end
    end
    local chosen,bestGap=nil,math.huge
    local travel=self:travel(car,packet.boost,2.5)
    for _,sample in ipairs(trajectory)do
        local p=sample.position
        if sample.time>=.15 and p[3]<radius+150 and abs(p[2])<arena.EXTENT_Y+200 then
            local gap=distance(car.position,p)-self:reach(car,packet.boost,sample.time,self:heading(car,p),travel)-(radius+100)
            if gap<bestGap then bestGap=gap;chosen=sample end
            if gap<=0 then chosen=sample;break end
        end
    end
    if not chosen then return nil end -- keep learned high-ball/wall decisions
    local future=chosen.position
    local goalX=self:shotLane(packet,future,chosen.time)
    local goal=self:goal(1-packet.team)
    local goalPoint={goal.origin[1]+goal.side[1]*goalX,goal.origin[2]+goal.side[2]*goalX,17}
    local dx,dy=unit(goalPoint[1]-future[1],goalPoint[2]-future[2])
    local speed=sqrt(car.velocity[1]^2+car.velocity[2]^2)
    local preset=self.profile.car_presets[packet.car_preset or "standard"]or self.profile.car_presets.standard
    local front=preset.size[1]/2+preset.offset[1]
    local standOff=math.clamp(radius+front+100+speed*.06,220,440)
    local target={future[1]-dx*standOff,future[2]-dy*standOff,17}
    local behind=(car.position[1]-future[1])*dx+(car.position[2]-future[2])*dy
    local mode=danger and "defend intercept"or "ground intercept"
    if behind> -radius*.5 and not danger then
        -- Going directly through the ball from the wrong side makes own goals.
        -- Pick one side and hold it until we have reached the approach side.
        if not self.side then
            local side=(car.position[1]-future[1])*(-dy)+(car.position[2]-future[2])*dx
            self.side=sign(side)
        end
        local clearance=radius+front+260
        target[1]=target[1]-dy*clearance*self.side
        target[2]=target[2]+dx*clearance*self.side
        mode="circle behind ball"
    else
        self.side=nil
        local alignment=car.forward[1]*dx+car.forward[2]*dy
        local lateral=abs((car.position[1]-future[1])*(-dy)+(car.position[2]-future[2])*dx)
        if alignment>.9 and behind<0 and lateral<radius+70 then
            target={future[1]+dx*(radius+200),future[2]+dy*(radius+200),17}
        end
    end
    local supportTarget,teammateETA=self:support(packet,future,danger)
    if supportTarget then target=supportTarget;mode="support teammate";self.side=nil end
    target[1]=math.clamp(target[1],-arena.EXTENT_X+350,arena.EXTENT_X-350)
    target[2]=math.clamp(target[2],-arena.EXTENT_Y+180,arena.EXTENT_Y-180)
    -- Rounded corners have less driveable floor than a rectangular clamp.
    for _=1,4 do
        local gap,n=self.arena:query({target[1],target[2],70})
        if abs(n[3])>.7 or gap>=160 then break end
        target[1]=target[1]+n[1]*(160-gap);target[2]=target[2]+n[2]*(160-gap)
    end
    local pad=self:routePad(packet,target,danger or supportTarget~=nil,behind,radius)
    local driveTime=chosen.time
    if pad then
        target={pad.position[1],pad.position[2],17}
        mode="boost on approach"
        driveTime=max(.35,distance(car.position,target)/max(speed,1000))
    end
    local angle=self:heading(car,target)
    local remaining=distance(car.position,target)
    local headingError=angle-(car.angular_velocity and car.angular_velocity[3]or 0)*.16
    local steer=abs(headingError)>.055 and sign(headingError)or 0
    local forwardSpeed=dot(car.velocity,car.forward)
    local desired=min(self.profile.physics.CAR_MAX_SPEED,max(450,remaining/max(driveTime,.3)))
    if supportTarget then desired=min(desired,1100)end
    desired=min(desired,500+1700*max(math.cos(angle),0)^2)
    if abs(angle)>1.1 then desired=min(desired,650)end
    local throttle=1
    if forwardSpeed>desired+180 then throttle=-1 end -- actual braking, no boost
    if supportTarget and remaining<220 then throttle=forwardSpeed>180 and -1 or 0 end
    local boost=throttle==1 and abs(angle)<.12 and remaining>700
        and forwardSpeed<desired-150 and packet.boost>0 and 1 or 0
    local slide=abs(angle)>1.2 and speed>500 and speed<1400 and 1 or 0
    local action={throttle,steer,0,steer,0,0,boost,slide}
    self.last={mode=mode,target=target,ball=table.clone(future),time=chosen.time,
        reachable=bestGap<=0,danger=danger,heading=angle,desired_speed=desired,action=action,
        boost_pad=pad and {position=table.clone(pad.position),is_big=pad.is_big}or nil,
        goal_x=goalX,goal_target=goalPoint,support=supportTarget~=nil,teammate_eta=teammateETA}
    self.physics.plan=self.last
    return action,mode
end
return Intercept

end)()
local Timing=(function()
-- Deadline scheduling and bounded active-run measurements. No game APIs.
local Timing={}
Timing.__index=Timing
function Timing.due(now,deadline,period)
    if deadline and now+1e-6<deadline then return false,deadline,0 end
    local late=deadline and math.max(0,now-deadline)or 0
    local nextAt=deadline and deadline+(math.floor(late/period)+1)*period or now+period
    return true,nextAt,late
end
function Timing.new(target)
    return setmetatable({target=target,samples={},rate=0},Timing)
end
function Timing:record(sample)
    if not self.last or sample.time-self.last.time>.5 then self.windowAt=sample.time;self.count=0;self.rate=0 end
    self.count=self.count+1
    if sample.time-self.windowAt>=1 then
        self.rate=(self.count-1)/(sample.time-self.windowAt)
        self.count=1;self.windowAt=sample.time
    end
    self.last=sample
    self.samples[#self.samples+1]=sample
    if #self.samples>120 then table.remove(self.samples,1)end
end
function Timing:report()
    local out={target_hz=self.target,decision_hz=self.rate,samples=#self.samples,last=self.last,
        model_calls=0,fields={}}
    for _,key in ipairs({'pose_ms','observe_ms','model_ms','planning_ms','safety_ms','decision_ms','input_ms','schedule_late_ms','entities'})do
        local sum,peak=0,0
        for _,sample in ipairs(self.samples)do local n=sample[key]or 0;sum=sum+n;peak=math.max(peak,n)end
        out.fields[key]={mean=sum/math.max(1,#self.samples),max=peak}
    end
    for _,sample in ipairs(self.samples)do out.model_calls=out.model_calls+(sample.model_ran and 1 or 0)end
    return out
end
return Timing

end)()
local Calibration=(function()
-- User-marked goal geometry and passive motion recording. No game APIs.
local Calibration={}
Calibration.__index=Calibration
local abs,sqrt,min,max=math.abs,math.sqrt,math.min,math.max
local function copy(t)
    if type(t)~='table'then return t end
    local out={};for k,v in pairs(t)do out[k]=copy(v)end;return out
end
local function distance(a,b)return sqrt((a[1]-b[1])^2+(a[2]-b[2])^2+(a[3]-b[3])^2)end
local function dot(a,b)return a[1]*b[1]+a[2]*b[2]+a[3]*b[3]end
local function sub(a,b)return {a[1]-b[1],a[2]-b[2],a[3]-b[3]}end
local function median(t)
    if #t==0 then return nil end
    local a=table.clone(t);table.sort(a);return a[math.floor((#a+1)/2)]
end
local function vector(v)
    if type(v)~='table'or #v~=3 then return false end
    for _,x in ipairs(v)do if type(x)~='number'or x~=x or abs(x)>100000 then return false end end
    return true
end
Calibration.steps={
    {'center','Field centre','Place the centre of your car over the centre spot, upright on the floor.'},
    {'orange_a','Orange: first inner post','At the goal line, point your nose sideways into either INNER post face. A slope-induced tilt is OK; keep pointing outward and stop.'},
    {'orange_b','Orange: other inner post','Touch the OTHER inner post face at the goal line. Tilt on the rounded surface is OK. Stop moving.'},
    {'orange_top','Orange: underside of crossbar','At the middle of the goal mouth, Press F10 to arm, then fly nose-up into the UNDERSIDE at the middle of the mouth. Contact is captured automatically.'},
    {'orange_back','Orange: back of net','Inside the net, touch the REAR wall. Nose-out or nose-up on the curved wall is OK. Stop moving.'},
    {'blue_a','Blue: first inner post','Touch either INNER post face with your nose, sideways at the goal line.'},
    {'blue_b','Blue: other inner post','Touch the OTHER inner post face with your nose at the goal line.'},
    {'blue_top','Blue: underside of crossbar','At the middle of the goal mouth, Press F10 to arm, then fly nose-up into the UNDERSIDE at the middle of the mouth. Contact is captured automatically.'},
    {'blue_back','Blue: back of net','Inside the blue net, touch the REAR wall. Nose-out or nose-up on the curved wall is OK. Stop moving.'}}
function Calibration.new(profile)
    return setmetatable({profile=profile,baseline=copy(profile.goal_defaults),points={},index=1,history={},reference='bumper',tab='geometry'},Calibration)
end
function Calibration:begin()self.crossbar=nil;self.history={};self.index=1;self.points={};self.candidate=nil end
function Calibration:observe(packet,now,keys,physics)
    if not packet then self.history={};return end
    self.latest=packet
    self.history[#self.history+1]={time=now,car=copy(packet.car),ground=packet.ground_estimate,on_ball=packet.ball_wheel_contacts or 0,preset=packet.car_preset or 'standard',verified=packet.car_size_verified,dimensions_verified=packet.car_dimensions_verified}
    while #self.history>1 and now-self.history[1].time>.6 do table.remove(self.history,1)end
    if self.crossbar then self:observeCrossbar(now)end
    if self.recordingUntil and now<=self.recordingUntil and now-(self.motionAt or -math.huge)>=.09 then
        self.motionAt=now
        local row={time=now,car=copy(packet.car),ball=copy(packet.ball),ground=packet.ground_estimate,
            boost=packet.boost,keys=copy(keys or {}),radius=packet.ball_radius or self.profile.physics.BALL_RADIUS,
            radius_verified=packet.ball_size_verified,clear_flight=physics:clearFlight(packet,packet.ball_radius or self.profile.physics.BALL_RADIUS)}
        self.motion.samples[#self.motion.samples+1]=row
        if #self.motion.samples>=250 then self.recordingUntil=nil end
    end
    if self.recordingUntil and now>self.recordingUntil then self.recordingUntil=nil;self:summarizeMotion()end
end
function Calibration:probe(row,key)
    local car=row.car;local p=table.clone(car.position)
    if key~='center'and self.reference=='bumper'then
        local c=self.profile.car_presets[row.preset]or self.profile.car_presets.standard
        local f,u=car.forward,car.up
        local right={u[2]*f[3]-u[3]*f[2],u[3]*f[1]-u[1]*f[3],u[1]*f[2]-u[2]*f[1]}
        for i=1,3 do p[i]=p[i]+f[i]*(c.size[1]/2+c.offset[1])+right[i]*c.offset[2]+u[i]*c.offset[3]end
    end
    return {point=p,root=table.clone(car.position),forward=table.clone(car.forward),up=table.clone(car.up),
        preset=row.preset,reference=self.reference,hitbox_verified=row.verified==true,time=row.time}
end
function Calibration:corners(p)
    local cfg=self.profile.car_presets[p.preset]or self.profile.car_presets.standard
    local f,u=p.forward,p.up
    local right={u[2]*f[3]-u[3]*f[2],u[3]*f[1]-u[1]*f[3],u[1]*f[2]-u[2]*f[1]}
    local face={}
    for j=1,3 do face[j]=p.root[j]+f[j]*(cfg.offset[1]+cfg.size[1]/2)+right[j]*cfg.offset[2]+u[j]*cfg.offset[3]end
    local out={}
    for _,a in ipairs({-1,1})do for _,b in ipairs({-1,1})do for _,c in ipairs({-1,1})do
        local v={}
        for j=1,3 do v[j]=p.root[j]+f[j]*(cfg.offset[1]+a*cfg.size[1]/2)
            +right[j]*(cfg.offset[2]+b*cfg.size[2]/2)+u[j]*(cfg.offset[3]+c*cfg.size[3]/2)+p.point[j]-face[j]end
        out[#out+1]=v
    end end end
    return out
end
function Calibration:store(point)
    self.points[Calibration.steps[self.index][1]]=point
    self.index=self.index+1;self.candidate=nil;self.crossbar=nil
    if self.index>#Calibration.steps then self.candidate=self:fit()end
end
-- Arm before jumping. Record the highest box support around an abrupt vertical
-- stop, not an arbitrary midair pose or the average of a moving flight.
function Calibration:observeCrossbar(now)
    local sweep=self.crossbar
    if self.reference~='bumper'then self.crossbar=nil;self.message='Crossbar capture cancelled: reference changed';return end
    if sweep.contactAt and now-sweep.contactAt>=.2 then
        local point=sweep.best;point.capture_mode='flying_contact';point.samples=sweep.samples
        point.spread=sweep.high-sweep.low;point.contact_velocity_drop=sweep.drop
        self:store(point);self.message='Flying crossbar contact captured. Continue with the next landmark.';return
    end
    if now>sweep.untilTime then
        self.crossbar=nil;self.message='No clear crossbar impact detected. F10 to retry; fly upward into the underside, not over the bar.';return
    end
    local row=self.history[#self.history];if not row then return end
    local a,b=self.points[sweep.goal..'_a'],self.points[sweep.goal..'_b']
    local dx,dy=b.point[1]-a.point[1],b.point[2]-a.point[2];local width=sqrt(dx*dx+dy*dy)
    if width<1000 then self.crossbar=nil;self.message='Recapture both inner posts first';return end
    local x,y=row.car.position[1]-(a.point[1]+b.point[1])/2,row.car.position[2]-(a.point[2]+b.point[2])/2
    local point=self:probe(row,Calibration.steps[self.index][1]);local height=-math.huge
    for _,v in ipairs(self:corners(point))do height=max(height,v[3])end
    local valid=(row.verified or row.dimensions_verified)and row.car.forward[3]>.9
        and abs((x*dx+y*dy)/width)<200 and abs((-x*dy+y*dx)/width)<140
        and height>350 and height<900
    if not valid then sweep.previous=nil;return end
    local old=sweep.previous;local vz=row.car.velocity[3]
    if old and old.preset==row.preset then
        local dt=row.time-old.time;local drop=old.vz-vz
        if dt>0 and dt<.18 and old.vz>120 and drop>max(90,1800*dt)then
            sweep.contactAt=sweep.contactAt or now;sweep.drop=max(sweep.drop or 0,drop)
            if not sweep.best or old.height>sweep.high then sweep.best=old.point;sweep.high=old.height end
            sweep.low=min(sweep.low or old.height,old.height);sweep.samples=(sweep.samples or 0)+1
        end
    end
    if sweep.contactAt then
        if not sweep.best or height>sweep.high then sweep.best=point;sweep.high=height end
        sweep.low=min(sweep.low or height,height);sweep.samples=(sweep.samples or 0)+1
    end
    sweep.previous={time=row.time,vz=vz,height=height,point=point,preset=row.preset}
end
function Calibration:capture()
    assert(self.index<=#Calibration.steps,'All points captured; review and apply the result')
    local key=Calibration.steps[self.index][1]
    if key=='orange_top'or key=='blue_top'then
        if self.crossbar then self.crossbar=nil;self.message='Flying capture cancelled; F10 arms again';return self.index end
        assert(self.reference=='bumper','Use front bumper contact for flying crossbar capture')
        local goal=key=='orange_top'and 'orange'or 'blue'
        assert(self.points[goal..'_a']and self.points[goal..'_b'],'Capture both inner posts first')
        local row=self.history[#self.history];assert(row,'Wait for a valid car pose')
        self.crossbar={goal=goal,untilTime=row.time+8}
        self.message='ARMED for 8 seconds: fly nose-up into the crossbar UNDERSIDE. F10 cancels.'
        return self.index
    end
    assert(#self.history>=3,'Hold the car still for half a second first')
    local latest=self.history[#self.history]
    assert(latest.time-self.history[1].time>=.25,'Hold still a little longer')
    for _,r in ipairs(self.history)do
        assert(r.preset==latest.preset,'Car body changed; hold still and capture again')
        assert(distance(r.car.position,latest.car.position)<12,'Car moved during capture; stop and retry')
        assert(dot(r.car.velocity,r.car.velocity)<2500,'Car is still moving; stop and retry')
        assert(dot(r.car.angular_velocity or {0,0,0},r.car.angular_velocity or {0,0,0})<.08^2,'Car is rotating; hold still and retry')
    end
    if key~='center'and self.reference=='bumper'then assert(latest.verified or latest.dimensions_verified,'Collision body dimensions are unknown; use a supported car or explicit centre-marker mode')end
    if key=='center'then assert(latest.ground and latest.car.up[3]>.9 and latest.on_ball==0 and abs(latest.car.position[3]-self.profile.physics.CAR_SPAWN_REST_Z)<30,'Centre point must be upright on the field floor, not on the ball')end
    local point=self:probe(latest,key);local probes={}
    for _,r in ipairs(self.history)do probes[#probes+1]=self:probe(r,key).point end
    for j=1,3 do local values={};for _,p in ipairs(probes)do values[#values+1]=p[j]end;point.point[j]=median(values)end
    point.samples=#probes;point.spread=0
    for _,p in ipairs(probes)do point.spread=max(point.spread,distance(p,point.point))end
    self:store(point)
    return self.index
end
function Calibration:back()
    self.crossbar=nil
    self.index=max(1,self.index-1);self.points[Calibration.steps[self.index][1]]=nil;self.candidate=nil
end
function Calibration:fit()
    for _,s in ipairs(Calibration.steps)do
        local p=self.points[s[1]]
        assert(type(p)=='table'and vector(p.point)and vector(p.root)and vector(p.forward)and vector(p.up),'Missing or invalid point: '..s[2])
        assert(abs(dot(p.forward,p.forward)-1)<.02 and abs(dot(p.up,p.up)-1)<.02 and abs(dot(p.forward,p.up))<.02,'Invalid car orientation at '..s[2])
        assert(p.reference=='bumper'or p.reference=='center','Unknown point reference')
    end
    local centre=self.points.center.point
    local floor=0 -- fixed vertical origin of the saved standard soccer arena
    local out={version=1,centre=table.clone(centre),floor=floor,goals={},warnings={},
        note='Centre measures XY; floor zero comes from the saved standard arena. Front-face contacts use source hitbox offsets; rounded-corner correction uses the saved fillet. Marker mode uses the car root directly. Sloped post captures use the full rotated box. Rear body support is a layout check, not the curved wall surface.'}
    for team,name in ipairs({'blue','orange'})do
        local a,b,top,back=self.points[name..'_a'],self.points[name..'_b'],self.points[name..'_top'],self.points[name..'_back']
        local dx,dy=b.point[1]-a.point[1],b.point[2]-a.point[2]
        local width=sqrt(dx*dx+dy*dy)
        assert(width>1000 and width<2400,name..': post spacing is implausible; capture the inner faces')
        local side={dx/width,dy/width,0}
        local normal={-side[2],side[1],0}
        local origin={(a.point[1]+b.point[1])/2,(a.point[2]+b.point[2])/2,floor}
        if dot(sub(origin,centre),normal)<0 then normal[1]=-normal[1];normal[2]=-normal[2]end
        local depth=dot(sub(origin,centre),normal)
        assert(depth>4000 and depth<7000,name..': goal is not at a plausible field end')
        assert(abs(depth-self.profile.arena.EXTENT_Y)<250,name..': capture the front goal line; large arena changes need a separate profile')
        assert(abs(dot(sub(origin,centre),side))<200,name..': goal centre is too far sideways from the centre spot')
        assert(abs(dot(sub(top.point,origin),normal))<180,name..': crossbar point must be at the goal mouth, not the ceiling/back wall')
        local height=top.point[3]-floor
        if top.reference=='bumper'then for _,v in ipairs(self:corners(top))do height=max(height,v[3]-floor)end end
        assert(height>350 and height<900,name..': crossbar height is implausible')
        local backDepth=dot(sub(back.point,origin),normal)
        local backMethod='marker'
        if back.reference=='bumper'then
            backMethod='body_support'
            backDepth=-math.huge
            for _,v in ipairs(self:corners(back))do backDepth=max(backDepth,dot(sub(v,origin),normal))end
        end
        assert(backDepth>300 and backDepth<1400,name..': touch the back of the net, not the field backwall')
        assert(abs(dot(sub(back.point,origin),side))<width*.4,name..': use the middle of the rear net wall')
        for _,p in ipairs({a,b})do
            assert(p.point[3]-floor>0 and p.point[3]-floor<height,name..': post contact must be below the crossbar')
            if p.reference=='bumper'then
                local sign=dot(sub(p.point,origin),side)>0 and 1 or -1
                local horizontal=sqrt(p.forward[1]^2+p.forward[2]^2)
                assert(horizontal>.2 and dot(p.forward,side)*sign/horizontal>.9,name..': point the nose outward into the inner post face; slope tilt is OK')
            end
        end
        if top.reference=='bumper'then assert(top.forward[3]>.9,name..': point the nose up into the crossbar underside')end
        if back.reference=='bumper'then
            local horizontal=sqrt(back.forward[1]^2+back.forward[2]^2)
            local noseOut=horizontal>.2 and dot(back.forward,normal)/horizontal>.9
            local wallSupported=dot(back.up,normal)<-.85 and back.forward[3]>.8
            assert(noseOut or wallSupported,name..': touch the rear wall nose-out, or nose-up with wheels supported on its curve')
            if wallSupported then
                backMethod='wall_supported_body'
                out.warnings[#out.warnings+1]=name..': rear capture is wall-supported; body support depth is approximate, not the exact curved wall surface'
            end
        end
        local r=self.profile.arena.MOUTH_FILLET
        local function rounded(z)
            local dz=max(0,r-min(z,height-z))
            return r-sqrt(max(0,r*r-dz*dz))
        end
        local function correction(p,sign)
            if p.reference=='center'then return rounded(p.point[3]-floor)end
            local face=dot(sub(p.point,origin),side)*sign
            local required=face
            for _,v in ipairs(self:corners(p))do
                local z=v[3]-floor
                if z>=0 and z<=height then required=max(required,dot(sub(v,origin),side)*sign+rounded(z))end
            end
            return required-face
        end
        local ca,cb=correction(a,-1),correction(b,1)
        width=width+ca+cb
        for i=1,2 do origin[i]=origin[i]+side[i]*(cb-ca)/2 end
        out.goals[team]={origin=origin,side=side,normal=normal,half_width=width/2,height=height,back_depth=backDepth,fillet=r,back_reference=backMethod}
    end
    local blue,orange=out.goals[1],out.goals[2]
    assert(dot(blue.normal,orange.normal)<-.97,'The two goals must face opposite field ends')
    assert(blue.normal[2]<-.95 and orange.normal[2]>.95,'Blue/orange ends appear swapped; this calibration targets the saved standard soccer orientation')
    assert(abs(blue.half_width-orange.half_width)<min(blue.half_width,orange.half_width)*.12,'Goal widths disagree; recapture the inner faces')
    assert(abs(blue.height-orange.height)<min(blue.height,orange.height)*.12,'Crossbar heights disagree')
    out.summary=string.format('Blue %.1f x %.1f studs | Orange %.1f x %.1f studs',blue.half_width*.2,blue.height*.1,orange.half_width*.2,orange.height*.1)
    if #out.warnings>0 then out.summary=out.summary..' | rear-wall depth approximate'end
    return out
end
function Calibration:apply()self.candidate=self:fit();self.active=copy(self.candidate);return self.active end
function Calibration:goal(team)
    if self.active then return self.active.goals[team+1]end
    if self.baseline then return self.baseline.goals[team+1]end
    local a=self.profile.arena;local sign=team==0 and -1 or 1
    return {origin={0,sign*a.EXTENT_Y,0},side={1,0,0},normal={0,sign,0},half_width=a.MOUTH_HALF_WIDTH,
        height=a.MOUTH_HEIGHT,back_depth=a.GOAL_BACK_Y-a.EXTENT_Y,fillet=a.MOUTH_FILLET}
end
function Calibration:startMotion(now)self.motion={samples={},started_at=now};self.recordingUntil=now+20;self.motionAt=nil end
function Calibration:summarizeMotion()
    if not self.motion then return nil end
    local samples=self.motion.samples;local gravity,accel,brakes,radii={},{},{},{}
    for i,r in ipairs(samples)do
        if r.radius_verified then radii[#radii+1]=r.radius end
        local old=samples[i-1]
        if old then
            local dt=r.time-old.time
            if dt>.02 and dt<.3 and r.ground and old.ground and dot(r.car.forward,old.car.forward)>.995 and r.car.up[3]>.95 then
                local speed=dot(old.car.velocity,old.car.forward)
                local dv=(dot(r.car.velocity,r.car.forward)-speed)/dt
                if old.keys.W and not old.keys.S and not old.keys.LMB and speed>200 and speed<1000 and dv>0 and dv<3000 then accel[#accel+1]=dv end
                if old.keys.S and not old.keys.W and speed>400 and dv< -100 and dv> -6000 then brakes[#brakes+1]=-dv end
            end
        end
        local a,b=samples[i-4],samples[i-2]
        if a and b and a.clear_flight and b.clear_flight and r.clear_flight then
            local dt1,dt2=b.time-a.time,r.time-b.time
            if min(dt1,dt2)>.09 and max(dt1,dt2)<.4 then
                local g=2*((r.ball.position[3]-b.ball.position[3])/dt2-(b.ball.position[3]-a.ball.position[3])/dt1)/(dt1+dt2)
                local horizontal=0
                for j=1,2 do local n=2*((r.ball.position[j]-b.ball.position[j])/dt2-(b.ball.position[j]-a.ball.position[j])/dt1)/(dt1+dt2);horizontal=horizontal+n*n end
                g=g-math.log(1-self.profile.physics.BALL_DRAG)*r.ball.velocity[3]
                if g< -150 and g> -2000 and horizontal<250^2 then gravity[#gravity+1]=g end
            end
        end
    end
    local g=median(gravity);local deviations={}
    if g then for _,n in ipairs(gravity)do deviations[#deviations+1]=abs(n-g)end end
    self.motion.summary={samples=#samples,gravity_samples=#gravity,gravity=g,
        gravity_consistent=#gravity>=6 and median(deviations)<max(35,abs(g)*.08)or false,
        verified_ball_radius=median(radii),ground_acceleration_median=median(accel),braking_median=median(brakes),
        note='Acceleration/braking describe the sampled speeds and surface. Static landmarks and this recording do not identify masses or train the actor.'}
    return self.motion.summary
end
function Calibration:export()return {version=1,place=101880234193261,reference=self.reference,points=copy(self.points),motion=copy(self.motion)}end
function Calibration:load(data)
    assert(type(data)=='table'and data.version==1 and data.place==101880234193261,'Unsupported calibration file')
    assert(type(data.points)=='table','Calibration file has no points')
    local points={};local nextIndex=10
    for i,s in ipairs(Calibration.steps)do
        local p=data.points[s[1]]
        if p then
            assert(vector(p.point)and vector(p.root)and vector(p.forward)and vector(p.up),'Invalid saved landmark')
            assert(p.reference=='bumper'or p.reference=='center','Invalid saved reference')
            points[s[1]]=copy(p)
        else nextIndex=min(nextIndex,i)end
    end
    local old=self.points;self.points=points
    local ok,candidate=true,nil
    if nextIndex==10 then ok,candidate=pcall(function()return self:fit()end)end
    self.points=old
    if not ok then error(candidate)end
    local loadedMotion
    if data.motion then
        assert(type(data.motion.samples)=='table'and #data.motion.samples<=250,'Invalid motion recording')
        for _,r in ipairs(data.motion.samples)do
            assert(type(r.time)=='number'and r.time==r.time and abs(r.time)<1e9 and type(r.radius)=='number'and r.radius>0 and r.radius<1000,'Invalid motion sample')
            for _,body in ipairs({r.car,r.ball})do
                assert(type(body)=='table'and vector(body.position)and vector(body.velocity),'Invalid recorded pose')
            end
            assert(vector(r.car.forward)and vector(r.car.up)and type(r.keys)=='table','Invalid recorded controls')
        end
        local temporary=setmetatable({profile=self.profile,motion=copy(data.motion)},Calibration)
        temporary:summarizeMotion();loadedMotion=temporary.motion
    end
    self.points=points;self.candidate=candidate;self.index=nextIndex
    self.history={};self.recordingUntil=nil;self.motionAt=nil;self.crossbar=nil
    if loadedMotion then self.motion=loadedMotion end
    if data.reference=='bumper'or data.reference=='center'then self.reference=data.reference end
end
function Calibration:report()return {baseline=copy(self.baseline),points=copy(self.points),candidate=copy(self.candidate),active=copy(self.active),motion=self.motion and copy(self.motion.summary)or nil}end
return Calibration

end)()
local GoalSafety=(function()
-- Conservative ground-touch guards. Does not simulate future car-ball impacts.
local Safety={}
Safety.__index=Safety
local sqrt,abs,min,max=math.sqrt,math.abs,math.min,math.max
local function dot(a,b)return a[1]*b[1]+a[2]*b[2]+a[3]*b[3]end
local function sub(a,b)return {a[1]-b[1],a[2]-b[2],a[3]-b[3]}end
local function distance(a,b)local d=sub(a,b);return sqrt(dot(d,d))end
function Safety.new(profile,arena,physics,calibration)
    return setmetatable({profile=profile,arena=arena,physics=physics,calibration=calibration},Safety)
end
function Safety:fits(goal,p,radius,margin)
    local x=abs(dot(sub(p,goal.origin),goal.side))+margin
    local z=p[3]-goal.origin[3]
    if x+radius>goal.half_width or z+radius+margin>goal.height or z<radius-2 then return false end
    local r=goal.fillet
    local dx=x-(goal.half_width-r)
    local dz=abs(z-goal.height/2)-(goal.height/2-r)
    local inside=r-sqrt(max(dx,0)^2+max(dz,0)^2)-min(max(dx,dz),0)
    return inside>=radius-2
end
function Safety:crossing(goal,trajectory,radius)
    for i=2,#trajectory do
        local a,b=trajectory[i-1],trajectory[i]
        local da=dot(sub(a.position,goal.origin),goal.normal)
        local db=dot(sub(b.position,goal.origin),goal.normal)
        local plane=radius+10
        if da<plane and db>=plane then
            local f=(plane-da)/max(db-da,.00001);local p={}
            for j=1,3 do p[j]=a.position[j]+(b.position[j]-a.position[j])*f end
            if (b.obstructions or 0)==0 and self:fits(goal,p,radius,35)then return {position=p,time=a.time+(b.time-a.time)*f}end
        end
    end
end
function Safety:step(packet,action,now)
    self.last=nil
    local car,ball=packet.car,packet.ball
    if self.physics.mismatch or not packet.ground_estimate or car.up[3]<.9 or action[6]~=0 then return nil end
    local radius=packet.ball_radius or self.profile.physics.BALL_RADIUS
    local worldRadius=radius*self.profile.physics.BALL_WORLD_RADIUS/self.profile.physics.BALL_RADIUS
    if ball.position[3]>worldRadius+120 or abs(ball.velocity[3])>250 then return nil end
    local cfg=self.profile.car_presets[packet.car_preset or 'standard']or self.profile.car_presets.standard
    local own=self.calibration:goal(packet.team)
    local target=self.calibration:goal(1-packet.team)
    local forwardSpeed=dot(car.velocity,car.forward)
    local centre={}
    local f,u=car.forward,car.up
    local right={u[2]*f[3]-u[3]*f[2],u[3]*f[1]-u[1]*f[3],u[1]*f[2]-u[2]*f[1]}
    for i=1,3 do centre[i]=car.position[i]+f[i]*cfg.offset[1]+right[i]*cfg.offset[2]+u[i]*cfg.offset[3]end
    local delta=sub(ball.position,centre);local gap=sqrt(dot(delta,delta))
    -- A straight, close ground push through our own mouth is avoidable. Turns,
    -- jumps and aerial saves retain the actor's command.
    if gap<radius+cfg.size[1]/2+75 and gap>1 and abs(action[2])<.5
        and(action[1]>.5 or action[7]~=0)and forwardSpeed>-100
        and dot(sub(ball.position,own.origin),own.normal)>-1600 then
        local direction={delta[1]/gap,delta[2]/gap,delta[3]/gap}
        local towards=dot(direction,own.normal)
        if towards>.7 and dot(direction,car.forward)>.75 then
            local t=-dot(sub(ball.position,own.origin),own.normal)/towards
            local cross={ball.position[1]+direction[1]*t,ball.position[2]+direction[2]*t,ball.position[3]+direction[3]*t}
            if t>0 and self:fits(own,cross,worldRadius,0)then
                local a=table.clone(action);a[1]=forwardSpeed>150 and -1 or 0;a[7]=0;a[8]=0
                self.last={mode='Own-goal push guard',time=now,crossing=cross}
                return a,self.last.mode
            end
        end
    end
    if gap>850 or (packet.unknown_cars or 0)>0 or dot(ball.velocity,target.normal)<450
        or dot(sub(ball.position,target.origin),target.normal)<-1800
        or dot(sub(car.position,ball.position),target.normal)>-40 then return nil end
    local relative=sub(car.velocity,ball.velocity)
    local speed2=dot(relative,relative)
    if speed2<120^2 then return nil end
    local d=sub(ball.position,car.position)
    local nearTime=math.clamp(dot(d,relative)/speed2,0,.5)
    local separation={d[1]-relative[1]*nearTime,d[2]-relative[2]*nearTime,d[3]-relative[3]*nearTime}
    if sqrt(dot(separation,separation))>radius+cfg.size[1]/2+50 or dot(d,relative)<=0 then return nil end
    local trajectory=self.physics:predict(ball,radius,1.5)
    local cross=self:crossing(target,trajectory,worldRadius)
    if not cross then return nil end
    for _,other in ipairs(packet.other_cars or {})do
        for _,sample in ipairs(trajectory)do
                if sample.time>cross.time then break end
                local t=min(sample.time,.8);local v=other.velocity or {0,0,0}
                local p={other.position[1]+v[1]*t,other.position[2]+v[2]*t,other.position[3]+v[3]*t}
                if distance(p,sample.position)<450+radius+800*min(sample.time,.8)^2 then return nil end
        end
    end
    local a={forwardSpeed>200 and -1 or 0,0,0,0,0,0,0,0}
    self.last={mode='Leave clear shot',time=now,crossing=cross.position,crossing_seconds=cross.time,
        calibrated_geometry=self.calibration.active~=nil or self.calibration.baseline~=nil}
    return a,self.last.mode
end
return Safety

end)()
local Window=(function()
-- Draggable while paused; F4 can minimize while mouse boost is active.
local Window={}
Window.__index=Window
function Window.new(gui,input,connect,canDrag,title,height)
    height=height or 372
    local panel=Instance.new('Frame',gui);panel.Name='Window'
    panel.Size=UDim2.fromOffset(480,height);panel.Position=UDim2.fromOffset(20,20)
    panel.BackgroundColor3=Color3.fromRGB(18,22,30)
    local header=Instance.new('TextButton',panel);header.Name='Titlebar'
    header.Position=UDim2.fromOffset(8,2);header.Size=UDim2.fromOffset(420,30)
    header.BackgroundTransparency=1;header.Text=title;header.TextColor3=Color3.new(1,1,1)
    header.Font=Enum.Font.Code;header.TextSize=13
    local mini=Instance.new('TextButton',panel);mini.Name='Minimize'
    mini.Position=UDim2.fromOffset(442,4);mini.Size=UDim2.fromOffset(28,26);mini.Text='–'
    local body=Instance.new('Frame',panel);body.Name='Body';body.BackgroundTransparency=1
    body.Position=UDim2.fromOffset(0,34);body.Size=UDim2.fromOffset(480,height-38)
    local self=setmetatable({panel=panel,body=body,header=header,mini=mini,minimized=false,height=height},Window)
    connect(mini.Activated,function()self:toggle()end)
    local drag
    connect(header.InputBegan,function(event)
        if canDrag()and(event.UserInputType==Enum.UserInputType.MouseButton1 or event.UserInputType==Enum.UserInputType.Touch)then
            drag={at=event.Position,position=panel.Position,event=event}
        end
    end)
    connect(input.InputChanged,function(event)
        if drag and(event==drag.event or event.UserInputType==Enum.UserInputType.MouseMovement)then
            local delta=event.Position-drag.at
            local camera=game:GetService('Workspace').CurrentCamera
            local size=camera and camera.ViewportSize or Vector3.new(1920,1080,0)
            panel.Position=UDim2.fromOffset(math.clamp(drag.position.X.Offset+delta.X,0,math.max(0,size.X-480)),
                math.clamp(drag.position.Y.Offset+delta.Y,0,math.max(0,size.Y-34)))
        end
    end)
    connect(input.InputEnded,function(event)
        if drag and(event==drag.event or event.UserInputType==Enum.UserInputType.MouseButton1)then drag=nil end
    end)
    return self
end
function Window:toggle()
    self.minimized=not self.minimized;self.body.Visible=not self.minimized
    self.panel.Size=UDim2.fromOffset(480,self.minimized and 34 or self.height)
    self.mini.Text=self.minimized and '+'or '–'
end
return Window

end)()
local Worker=(function()
-- One cancellable inference job. Only resume it once per Heartbeat.
local Worker={}
Worker.__index=Worker
function Worker.new(predict,clock)
    return setmetatable({predict=predict,clock=clock or os.clock,generation=0,
        peak_slice_ms=0,cancelled=0,completed=0},Worker)
end
function Worker:cancel()
    if self.job then self.cancelled+=1 end
    self.generation+=1;self.job=nil
end
function Worker:start(query,context,metadata)
    assert(not self.job,'Inference is already running')
    local job={context=context,metadata=metadata,at=self.clock(),cpu=0,slices=0,generation=self.generation}
    job.thread=coroutine.create(function()
        local function checkpoint()
            if self.clock()>=self.deadline then coroutine.yield()end
        end
        if type(query)=='function'then query,context=query(checkpoint);job.context=context end
        return self.predict(query,context,checkpoint)
    end)
    self.job=job
end
function Worker:step(budget)
    local job=self.job
    if not job then return nil end
    local began=self.clock()
    self.deadline=began+math.clamp(budget or .0015,.00025,.003)
    local ok,index,logits=coroutine.resume(job.thread)
    local spent=self.clock()-began
    job.cpu+=spent;job.slices+=1
    self.peak_slice_ms=math.max(self.peak_slice_ms,spent*1000)
    self.last_slice_ms=spent*1000
    if not ok then self.job=nil;error(index,0)end
    if self.job~=job or self.generation~=job.generation then return nil end
    if coroutine.status(job.thread)=='dead'then
        self.job=nil;self.completed+=1
        job.index=index;job.logits=logits;job.thread=nil
        job.wall=self.clock()-job.at
        self.wall=self.wall and self.wall*.75+job.wall*.25 or job.wall
        self.last=job
        return job
    end
end
function Worker:report()
    return {busy=self.job~=nil,completed=self.completed,cancelled=self.cancelled,backend=self.backend,
        peak_slice_ms=self.peak_slice_ms,last_slice_ms=self.last_slice_ms,
        last_cpu_ms=self.last and self.last.cpu*1000 or nil,
        last_wall_ms=self.last and self.last.wall*1000 or nil,
        last_slices=self.last and self.last.slices or nil}
end
return Worker

end)()
local Latency=(function()
-- Turbo Soccer already predicts server snapshots. Never add a full ping again.
local Latency={}
Latency.__index=Latency
local clamp,min,max=math.clamp,math.min,math.max
local function distance(a,b)return math.sqrt((a[1]-b[1])^2+(a[2]-b[2])^2+(a[3]-b[3])^2)end
function Latency.new(player)
    return setmetatable({player=player,enabled=true,pingAt=-math.huge,frame=1/120,input=0,
        rejected=0,horizon=0},Latency)
end
function Latency:sample(now,dt)
    if dt and dt>0 and dt<.25 then self.frame=self.frame*.9+dt*.1 end
    if now-self.pingAt<.5 then return end
    self.pingAt=now
    local ok,seconds=pcall(function()return self.player:GetNetworkPing()end)
    local source='GetNetworkPing'
    if not ok or type(seconds)~='number'or seconds~=seconds or seconds<0 or seconds>3 then
        ok,seconds=pcall(function()
            return game:GetService('Stats').Network.ServerStatsItem['Data Ping']:GetValue()/1000
        end)
        source='Stats Data Ping'
    end
    if ok and type(seconds)=='number'and seconds==seconds and seconds>=0 and seconds<=3 then
        self.jitter=self.ping and(self.jitter or 0)*.8+math.abs(seconds-self.ping)*.2 or 0
        self.ping=self.ping and self.ping*.8+seconds*.2 or seconds
        self.pingSource=source;self.pingSeen=now
    elseif self.pingSeen and now-self.pingSeen>3 then self.ping=nil;self.jitter=nil end
end
function Latency:budget()
    -- Preserve short frames; permit up to 3 ms on slower render loops.
    return clamp(self.frame*.18,.00075,.003)
end
function Latency:lead(packet,wall)
    if not self.enabled then self.horizon=0;return 0 end
    local cap=.16
    if(self.ping or 0)>.25 or(self.jitter or 0)>.04 then cap=.08 end
    local h=(wall or .035)+self.frame+clamp(packet.sample_dt or 0,0,.07)*.5+self.input
    self.horizon=clamp(h,0,cap)
    return self.horizon
end
local function advance(body,seconds,ground,gravity)
    local out=table.clone(body)
    out.position=table.clone(body.position);out.velocity=table.clone(body.velocity)
    out.forward=body.forward and table.clone(body.forward)or nil
    out.up=body.up and table.clone(body.up)or nil
    out.angular_velocity=table.clone(body.angular_velocity or {0,0,0})
    for i=1,3 do out.position[i]+=body.velocity[i]*seconds end
    if not ground then
        out.position[3]+=.5*gravity*seconds*seconds
        out.velocity[3]+=gravity*seconds
    end
    -- Small-angle orientation lead, renormalized to an orthogonal basis.
    if out.forward and out.up then
        local w=out.angular_velocity
        local function rotate(v)
            local a={v[1]+(w[2]*v[3]-w[3]*v[2])*seconds,
                v[2]+(w[3]*v[1]-w[1]*v[3])*seconds,v[3]+(w[1]*v[2]-w[2]*v[1])*seconds}
            local n=math.sqrt(a[1]^2+a[2]^2+a[3]^2)
            for i=1,3 do a[i]/=max(n,1e-9)end
            return a
        end
        out.forward=rotate(out.forward);out.up=rotate(out.up)
        local f,u=out.forward,out.up
        local dot=f[1]*u[1]+f[2]*u[2]+f[3]*u[3]
        for i=1,3 do u[i]-=dot*f[i]end
        local n=math.sqrt(u[1]^2+u[2]^2+u[3]^2)
        for i=1,3 do u[i]/=max(n,1e-9)end
    end
    return out
end
function Latency:project(packet,physics,wall,checkpoint)
    local h=self:lead(packet,wall)
    if h==0 then return packet end
    local out=table.clone(packet)
    local radius=packet.ball_radius or physics.profile.physics.BALL_RADIUS
    local future=physics:predict(packet.ball,radius,h,1000,checkpoint)
    local last=future[#future]
    out.ball=table.clone(packet.ball);out.ball.position=last.position;out.ball.velocity=last.velocity
    out.car=advance(packet.car,h,packet.ground_estimate,physics.gravity)
    out.other_cars={}
    for _,car in ipairs(packet.other_cars or {})do
        out.other_cars[#out.other_cars+1]=advance(car,h,car.ground_estimate,physics.gravity)
    end
    return out
end
function Latency:fresh(job,packet,now,epoch)
    local m=job.metadata
    local age=now-m.at
    local limit=((self.jitter or 0)>.04 or(self.ping or 0)>.25)and .22 or .35
    local valid=m.epoch==epoch and m.team==packet.team and m.scene==packet.scene_token
        and age>=0 and age<=limit and m.ground==packet.ground_estimate
    -- Account for travel since the predicted target time before checking a correction.
    local dt=clamp(now-m.targetAt,-.2,.2)
    local function expected(body)
        return {body.position[1]+body.velocity[1]*dt,body.position[2]+body.velocity[2]*dt,body.position[3]+body.velocity[3]*dt}
    end
    valid=valid and distance(expected(m.car),packet.car.position)<260
        and distance(expected(m.ball),packet.ball.position)<350
    if not valid then self.rejected+=1 end
    return valid
end
function Latency:report()
    return {enabled=self.enabled,ping_ms=self.ping and self.ping*1000 or nil,ping_source=self.pingSource,
        jitter_ms=self.jitter and self.jitter*1000 or nil,frame_ms=self.frame*1000,
        lookahead_ms=self.horizon*1000,rejected_actions=self.rejected,
        network_lead_ms=0,reason='Game state is already client-predicted; lead only measured AI, sampling and input delay'}
end
return Latency

end)()
local Graphics=(function()
-- Bounded, reversible local rendering changes. Preserve gameplay/readout cues.
local Graphics={}
Graphics.__index=Graphics
function Graphics.new(world,lighting)
    return setmetatable({world=world,lighting=lighting,enabled=false,changes=setmetatable({},{__mode='k'}),
        queue={},head=1,tail=0,seen=setmetatable({},{__mode='k'}),changed=0,limit=8192},Graphics)
end
function Graphics:remember(object,key,value)
    local ok,old=pcall(function()return object[key]end)
    if not ok or old==nil or old==value then return end
    local fields=self.changes[object]
    if not fields then fields={};self.changes[object]=fields end
    if fields[key]then return end
    if pcall(function()object[key]=value end)then
        fields[key]={before=old,applied=value};self.changed+=1
    end
end
function Graphics:protected(object)
    local p=object
    for _=1,14 do
        if not p or p==self.world then break end
        if p.Name=='PadRing'or p.Name=='PadHalo'or p.Name=='Nametag'or p.Name=='CarSound'or p.Name=='BallSound'then return true end
        if p:IsA('BillboardGui')or p:IsA('GuiObject')then return true end
        if p:IsA('Model')and p.PrimaryPart then return true end
        p=p.Parent
    end
    return false
end
function Graphics:apply(object)
    if object:IsA('ParticleEmitter')or object:IsA('Trail')or object:IsA('Beam')or object:IsA('Smoke')
        or object:IsA('Fire')or object:IsA('Sparkles')or object:IsA('PostEffect')then
        self:remember(object,'Enabled',false)
        if object:IsA('ParticleEmitter')then self:remember(object,'Rate',0)end
    elseif object:IsA('Light')then self:remember(object,'Shadows',false)
    elseif object:IsA('Terrain')then
        self:remember(object,'WaterWaveSize',0);self:remember(object,'WaterWaveSpeed',0)
        self:remember(object,'WaterReflectance',0)
    elseif object:IsA('BasePart')then
        self:remember(object,'CastShadow',false)
        if not self:protected(object)then
            self:remember(object,'Reflectance',0)
            if Enum.Material then self:remember(object,'Material',Enum.Material.SmoothPlastic)end
            if object:IsA('MeshPart')then self:remember(object,'TextureID','')end
        end
    elseif not self:protected(object)then
        if object:IsA('Decal')or object:IsA('Texture')then self:remember(object,'Transparency',1)
        elseif object:IsA('SpecialMesh')then self:remember(object,'TextureId','')
        elseif object:IsA('SurfaceAppearance')then
            for _,key in ipairs({'ColorMap','NormalMap','RoughnessMap','MetalnessMap'})do self:remember(object,key,'')end
        end
    end
end
function Graphics:enqueue(object)
    if not self.enabled or self.seen[object]or self.tail-self.head>=self.limit then return end
    self.seen[object]=true;self.tail+=1;self.queue[self.tail]=object
end
function Graphics:setEnabled(enabled)
    if self.closed or self.enabled==enabled then return end
    self.enabled=enabled
    if self.added then self.added:Disconnect();self.added=nil end
    self.queue={};self.head=1;self.tail=0;self.children=nil;self.childAt=nil
    self.seen=setmetatable({},{__mode='k'})
    if enabled then
        -- Finish restoration before recording a new baseline on a quick re-toggle.
        self:restore()
        if self.lighting then self:remember(self.lighting,'GlobalShadows',false)end
        self:enqueue(self.world)
        if self.lighting then self:enqueue(self.lighting)end
        if self.world.DescendantAdded then
            self.added=self.world.DescendantAdded:Connect(function(object)self:enqueue(object)end)
        end
        if self.lighting and self.lighting.DescendantAdded then
            self.lightAdded=self.lighting.DescendantAdded:Connect(function(object)self:enqueue(object)end)
        end
    else
        if self.lightAdded then self.lightAdded:Disconnect();self.lightAdded=nil end
        self:restore()
    end
end
function Graphics:restore()
    for object,fields in pairs(self.changes)do
        for key,saved in pairs(fields)do
            pcall(function()
                -- Do not overwrite a later game/user change to this property.
                if object[key]==saved.applied then object[key]=saved.before end
            end)
        end
    end
    self.changes=setmetatable({},{__mode='k'});self.changed=0
end
function Graphics:step(budget)
    if not self.enabled or self.closed then return end
    local deadline=os.clock()+(budget or .00035)
    local count=0
    repeat
        if self.children then
            local object=self.children[self.childAt]
            if object then self:enqueue(object);self.childAt+=1
            else self.children=nil end
        elseif self.head<=self.tail then
            local object=self.queue[self.head];self.queue[self.head]=nil;self.head+=1
            if object and object.Parent then
                pcall(function()self:apply(object);self.children=object:GetChildren();self.childAt=1 end)
            elseif object==self.world then self.children=object:GetChildren();self.childAt=1 end
        else
            self.queue={};self.head=1;self.tail=0;break
        end
        count+=1
    until count>=48 or os.clock()>=deadline
end
function Graphics:close()
    self:setEnabled(false);self.closed=true
end
function Graphics:report()return {enabled=self.enabled,changed_properties=self.changed,pending=math.max(0,self.tail-self.head+1)}end
return Graphics

end)()
local Startup=(function()
-- Startup gets a larger work slice than live inference, with bounded waits.
local Startup={}
Startup.__index=Startup
function Startup.new(options)
    options=options or {}
    local clock=options.clock or os.clock
    local now=clock()
    return setmetatable({clock=clock,wait=options.wait or task.wait,spawn=options.spawn or task.spawn,
        fetch=options.fetch or function(url)return game:HttpGet(url)end,
        alive=options.alive or function()return true end,render=options.render or function()end,
        budget=options.budget or .008,timeout=options.timeout or 120,downloadTimeout=options.downloadTimeout or 60,
        began=now,sliceAt=now,uiAt=-math.huge,stage='Preparing model'},Startup)
end
function Startup:show(force)
    local now=self.clock()
    if force or now-self.uiAt>=.1 then
        self.uiAt=now
        self.render(self.stage,self.done,self.total,now-self.began)
    end
end
function Startup:progress(stage,done,total)
    local changed=stage~=self.stage
    self.stage=stage;self.done=done;self.total=total
    self:show(changed)
end
function Startup:checkpoint(force)
    assert(self.alive(),'Model loading cancelled')
    assert(self.clock()-self.began<self.timeout,'Model preparation timed out after 120s. Close the panel and retry.')
    self:show(false)
    if force or self.clock()-self.sliceAt>=self.budget then
        self.wait()
        self.sliceAt=self.clock()
        assert(self.alive(),'Model loading cancelled')
    end
end
function Startup:download(url,expectedBytes)
    self:progress(('Downloading FP32 model (%.1f MB)'):format(expectedBytes/1000000))
    local request={active=true,done=false}
    self.spawn(function()
        local ok,data=pcall(self.fetch,url)
        if request.active and self.alive()then request.ok=ok;request.data=data;request.done=true end
    end)
    local began=self.clock()
    while not request.done and self.alive()and self.clock()-began<self.downloadTimeout do
        self:show(false);self.wait(.1)
    end
    request.active=false -- a timed-out/cancelled HTTP reply can never start the model
    assert(self.alive(),'Model loading cancelled')
    assert(request.done,('Model download timed out after %ds. Close the panel and retry.'):format(self.downloadTimeout))
    assert(request.ok,'Model download failed: '..tostring(request.data))
    assert(type(request.data)=='string'and #request.data==expectedBytes,
        'Incomplete model download. Close the panel and retry.')
    return request.data
end
return Startup

end)()
local RUNTIME=
{["cooperative"]=true,["light_graphics"]=true,["latency"]=true,["version"]="6.10"}
local ADAPTER_VERSION=RUNTIME.version or '6.8'
local PROFILE=
{["version"]=1,["name"]="turbo_soccer_standard",["provenance"]={["kind"]="numeric collision/physics specification from user-provided saved place",["place_sha256"]="00ea1fbc258e3d5e317daf5bef484368490726d006d53176e94a42375b1ee733",["geometry_source_sha256"]="d8f35aa62627d23a68ee3a51ef315c1b8b9e53ec4ba0a14cfa3f6a76dab467c0",["constants_source_sha256"]="3274f6c9d71e5e86d9708694e59599f1de71a8dfc41db0028567c0bffe8d541c"},["roblox_studs_per_sim_unit"]=0.1,["arena"]={["EXTENT_X"]=4096.0,["EXTENT_Y"]=5120.0,["HEIGHT"]=2048.0,["CORNER"]=8064.0,["EDGE_RADIUS"]=256.0,["BACK_RAMP_RADIUS"]=160.0,["CEILING_RADIUS"]=512.0,["SIDE_CORNER_RADIUS"]=852.0,["BACK_CORNER_RADIUS"]=874.0,["GOAL_HALF_WIDTH"]=893.0,["GOAL_HEIGHT"]=642.775,["GOAL_BACK_Y"]=6000.0,["GOAL_TOP_RADIUS"]=130.0,["GOAL_BOTTOM_RADIUS"]=70.0,["GOAL_LIP_RADIUS"]=80.0,["GOAL_BACK_RADIUS"]=300.0,["MOUTH_HALF_WIDTH"]=896.0,["MOUTH_HEIGHT"]=640.0,["MOUTH_FILLET"]=96.0,["MOUTH_LIP"]=8.0},["ramp_facets_degrees"]={0,11.617,22.892,33.984,45,56.016,67.108,78.383,90},["physics"]={["GRAVITY_Z"]=-650.0,["BALL_RADIUS"]=91.25,["BALL_WORLD_RADIUS"]=93.15,["BALL_REST_Z"]=93.15,["CAR_MAX_SPEED"]=2300.0,["CAR_MAX_ANG_SPEED"]=5.5,["BALL_MAX_SPEED"]=6000.0,["BALL_MAX_ANG_SPEED"]=6.0,["BALL_DRAG"]=0.03,["BOOST_USED_PER_SECOND"]=33.333333333333336,["BOOST_ACCEL_GROUND"]=991.6666666666666,["BOOST_ACCEL_AIR"]=1058.3333333333333,["DOUBLEJUMP_MAX_DELAY"]=1.25,["MAX_SUSPENSION_TRAVEL"]=12.0,["WHEEL_RAY_MIN_HIT_DIST"]=17.079519899575633,["CAR_SPAWN_REST_Z"]=17.0,["TICK_RATE"]=120,["BALLWORLD_FRICTION"]=0.35,["BALLWORLD_RESTITUTION"]=0.6,["SOLVER_ERP2"]=0.8,["RESTITUTION_VEL_THRESHOLD"]=10,["CONTACT_BREAKING_THRESHOLD"]=1,["BALL_WORLD_CONTACT_FLAT"]=0.0050000000000001155,["BALL_SLEEP_LIN_SPEED"]=40,["BALL_SLEEP_ANG_SPEED"]=1,["BALL_SLEEP_TIME"]=2,["CAR_MASS"]=180,["THROTTLE_TORQUE_AMOUNT"]=72000,["DRIVE_SPEED_TORQUE_FACTOR"]={{0,1},{1400,0.1},{1410,0}}},["car_presets"]={["standard"]={["size"]={120.50700378417969,86.69940185546875,38.65909957885742},["offset"]={13.875699996948242,0.0,20.7549991607666},["front"]={["radius"]=12.5,["rest_length"]=38.755,["offset"]={51.25,25.899999618530273,20.7549991607666}},["back"]={["radius"]=15.0,["rest_length"]=37.055,["offset"]={-33.75,29.5,20.7549991607666}}},["low"]={["size"]={130.427001953125,85.77989959716797,33.79999923706055},["offset"]={9.0,0.0,15.75},["front"]={["radius"]=12.0,["rest_length"]=33.95,["offset"]={50.29999923706055,31.100000381469727,15.75}},["back"]={["radius"]=13.5,["rest_length"]=33.85,["offset"]={-34.75,33.0,15.75}}},["flat"]={["size"]={131.32000732421875,87.17040252685547,31.894399642944336},["offset"]={9.008569717407227,0.0,12.094200134277344},["front"]={["radius"]=12.5,["rest_length"]=31.9242,["offset"]={49.970001220703125,27.799999237060547,12.094200134277344}},["back"]={["radius"]=17.0,["rest_length"]=27.9242,["offset"]={-35.43000030517578,20.280000686645508,12.094200134277344}}},["wedge"]={["size"]={133.99200439453125,83.02100372314453,32.79999923706055},["offset"]={12.5,0.0,11.75},["front"]={["radius"]=13.5,["rest_length"]=29.7,["offset"]={51.5,26.670000076293945,11.75}},["back"]={["radius"]=15.0,["rest_length"]=29.666,["offset"]={-35.75,35.0,11.75}}},["long"]={["size"]={129.5189971923828,84.68789672851562,36.65909957885742},["offset"]={13.875699996948242,0.0,20.7549991607666},["front"]={["radius"]=12.5,["rest_length"]=38.755,["offset"]={51.25,25.899999618530273,20.7549991607666}},["back"]={["radius"]=15.0,["rest_length"]=37.055,["offset"]={-34.0,29.5,20.7549991607666}}},["tall"]={["size"]={123.22000122070312,79.21029663085938,44.15909957885742},["offset"]={11.375699996948242,0.0,21.5049991607666},["front"]={["radius"]=15.0,["rest_length"]=39.505,["offset"]={51.25,25.899999618530273,21.5049991607666}},["back"]={["radius"]=15.0,["rest_length"]=39.105,["offset"]={-33.75,29.5,21.5049991607666}}}},["boost_positions"]={["big"]={{-3584.0,0.0,73.0},{3584.0,0.0,73.0},{-3072.0,4096.0,73.0},{3072.0,4096.0,73.0},{-3072.0,-4096.0,73.0},{3072.0,-4096.0,73.0}},["small"]={{0.0,-4240.0,70.0},{-1792.0,-4184.0,70.0},{1792.0,-4184.0,70.0},{-940.0,-3308.0,70.0},{940.0,-3308.0,70.0},{0.0,-2816.0,70.0},{-3584.0,-2484.0,70.0},{3584.0,-2484.0,70.0},{-1788.0,-2300.0,70.0},{1788.0,-2300.0,70.0},{-2048.0,-1036.0,70.0},{0.0,-1024.0,70.0},{2048.0,-1036.0,70.0},{-1024.0,0.0,70.0},{1024.0,0.0,70.0},{-2048.0,1036.0,70.0},{0.0,1024.0,70.0},{2048.0,1036.0,70.0},{-1788.0,2300.0,70.0},{1788.0,2300.0,70.0},{-3584.0,2484.0,70.0},{3584.0,2484.0,70.0},{0.0,2816.0,70.0},{-940.0,3308.0,70.0},{940.0,3308.0,70.0},{-1792.0,4184.0,70.0},{1792.0,4184.0,70.0},{0.0,4240.0,70.0}}},["policy_boost_limit"]=34,["recovery"]={["enabled"]=true,["stuck_seconds"]=2.2,["minimum_travel"]=45,["escape_seconds"]=0.65,["cooldown_seconds"]=3},["goal_defaults"]={["version"]=1,["source"]="builtin_measurements",["goals"]={{["origin"]={-0.10539187018261847,-5156.06088311565,0.0},["side"]={-0.9999997941940588,-0.0006415698245800758,0.0},["normal"]={0.0006415698245800758,-0.9999997941940588,0.0},["half_width"]=893.3817832411139,["height"]=639.0078980633016,["back_depth"]=830.1082496030729,["fillet"]=96.0,["back_reference"]="wall_supported_body"},{["origin"]={-0.5865567549764439,5137.970467167625,0.0},["side"]={-0.999943937915091,-0.01058872168209319,0.0},["normal"]={-0.01058872168209319,0.999943937915091,0.0},["half_width"]=894.5282420002634,["height"]=644.1573434119969,["back_depth"]=850.0714001682221,["fillet"]=96.0,["back_reference"]="wall_supported_body"}},["note"]="Latest measured posts and rear-wall samples; earlier consistent blue crossbar replaces a low high-scatter flight reading. Numeric fitted geometry only; no raw capture poses or timestamps.",["warnings"]={"Rear body support depth is approximate; collision profile retains its saved curved net surface."}}}
local arenaAdapter=Arena.new(PROFILE)
local padReader=Pads.new(PROFILE)
local carReader=Cars.new(PROFILE,Arena)
local kickoff=Kickoff.new(PROFILE)
local physics=Physics.new(PROFILE,arenaAdapter)
local intercept=Intercept.new(PROFILE,arenaAdapter,physics)
local calibration=Calibration.new(PROFILE)
intercept.calibration=calibration
local safety=GoalSafety.new(PROFILE,arenaAdapter,physics,calibration)
local safetyEnabled=true
local MODEL_NAME="Chronos V2.1"
local physicsEnabled=false
local timing=Timing.new(15)
local TEAM,manualTeam=nil,nil
local HZ=30 -- pose sampling; policy decisions target 15 Hz (tick skip 8 at 120 Hz)
local player=game:GetService("Players").LocalPlayer
local latency=Latency.new(player)
latency.enabled=RUNTIME.latency==true
local worker,graphics,lastAppliedAt,lastJumpPress
local pg=assert(player:FindFirstChildOfClass("PlayerGui"),"Join first")
local teamReader=Teams.new(player)
carReader.teams=teamReader
assert(not pg:FindFirstChild("Update271Standalone"),"Close the old standalone panel first")
local gui=Instance.new("ScreenGui")
gui.Name="Update271Standalone";gui.ResetOnSpawn=false;gui.DisplayOrder=1000072
local enabled=false
local connections={}
local function connect(signal,callback)
    local connection=signal:Connect(callback);connections[#connections+1]=connection
end
local window=Window.new(gui,game:GetService('UserInputService'),connect,function()return not enabled end,
    MODEL_NAME..' v'..ADAPTER_VERSION..' | F4 minimize',RUNTIME.cooperative and 410 or 372)
local panel=window.panel
local main=Instance.new('Frame',window.body);main.Name='Main';main.Size=UDim2.fromScale(1,1);main.BackgroundTransparency=1
local label=Instance.new("TextLabel",main)
label.Position=UDim2.fromOffset(10,8);label.Size=UDim2.new(1,-20,0,172)
label.BackgroundTransparency=1;label.TextColor3=Color3.new(1,1,1)
label.TextSize=14;label.Font=Enum.Font.Code;label.TextWrapped=true
label.Text=MODEL_NAME.." LOCAL: loading model..."
local start=Instance.new("TextButton",main)
start.Position=UDim2.fromOffset(10,185);start.Size=UDim2.fromOffset(150,30)
start.Text="Start bot / F6";start.Active=false
local teamButton=Instance.new("TextButton",main)
teamButton.Position=UDim2.fromOffset(170,185);teamButton.Size=UDim2.fromOffset(140,30)
teamButton.Text="Team: AUTO"
local close=Instance.new("TextButton",main)
close.Position=UDim2.fromOffset(320,185);close.Size=UDim2.fromOffset(150,30);close.Text="Close"
local physicsButton=Instance.new("TextButton",main)
physicsButton.Position=UDim2.fromOffset(10,222);physicsButton.Size=UDim2.fromOffset(220,28)
physicsButton.Text=physicsEnabled and "Physics assist: ON"or "Physics assist: OFF"
local reportButton=Instance.new("TextButton",main)
reportButton.Position=UDim2.fromOffset(240,222);reportButton.Size=UDim2.fromOffset(230,28)
reportButton.Text="Save physics report"
local supportButton=Instance.new("TextButton",main)
supportButton.Position=UDim2.fromOffset(10,259);supportButton.Size=UDim2.fromOffset(220,28)
supportButton.Text="Yield to teammate: OFF"
local calibrationButton=Instance.new('TextButton',main)
calibrationButton.Position=UDim2.fromOffset(240,259);calibrationButton.Size=UDim2.fromOffset(230,28)
calibrationButton.Text='Calibration / physics test'
local safetyButton=Instance.new('TextButton',main)
safetyButton.Position=UDim2.fromOffset(10,296);safetyButton.Size=UDim2.fromOffset(220,28);safetyButton.Text='Goal safety: ON'
local markerLabel=Instance.new('TextLabel',main)
markerLabel.Position=UDim2.fromOffset(240,296);markerLabel.Size=UDim2.fromOffset(230,28)
markerLabel.BackgroundTransparency=1;markerLabel.TextColor3=Color3.new(1,1,1);markerLabel.Text='F9 marks a bad decision'
local graphicsButton=Instance.new('TextButton',main)
graphicsButton.Position=UDim2.fromOffset(10,333);graphicsButton.Size=UDim2.fromOffset(220,28)
graphicsButton.Text='Game optimization: ON';graphicsButton.Visible=RUNTIME.cooperative==true
local latencyButton=Instance.new('TextButton',main)
latencyButton.Position=UDim2.fromOffset(240,333);latencyButton.Size=UDim2.fromOffset(230,28)
latencyButton.Text='Lag compensation: ON';latencyButton.Visible=RUNTIME.cooperative==true
gui.Parent=pg
local input=game:GetService("UserInputService")
local world=game:GetService("Workspace")
local alive,ready,armAt=true,false,0
local calibrating=false
local calView,refreshCalibration,captureCalibration
local lastStopReason,lastStopAt,lastReadReason
local testingKeyboard=false
local epoch=0
local sampleAt,decisionAt,previousPeriod=nil,nil,nil
local held={}
local pressLeft,releaseLeft,pressRight,releaseRight
local activeWindow=isrbxactive or isgameactive
local keyboard=Keyboard.new(input)
local keyboardKey={W=true,S=true,A=true,D=true,Q=true,E=true,SHIFT=true}
local order={"W","S","A","D","Q","E","SHIFT","LMB","RMB"}
local previous=table.create(8,0)
local jumpAt,usedFlip,lastGround=nil,false,true
local pendingJump=nil
local focus=true
local function event(key,down)
    if keyboardKey[key]then keyboard:event(key,down)
    elseif key=="LMB"then (down and pressLeft or releaseLeft)()
    else (down and pressRight or releaseRight)()end
end
local function release()
    for _,key in ipairs(order)do
        if held[key]then
            -- Try every release even if one executor API fails.
            if pcall(event,key,false)then held[key]=nil end
        end
    end
    previous=table.create(8,0);jumpAt=nil;usedFlip=false
    if worker then worker:cancel()end
    lastAppliedAt=nil;lastJumpPress=nil
    if Policy.reset then Policy.reset()end
    pendingJump=nil
    keyboard:release()
    arenaAdapter:resetRecovery()
    kickoff:reset()
    intercept:reset();physics.plan=nil
    decisionAt=nil;previousPeriod=nil
end
local function pressOwned(key,expectedEpoch)
    if epoch~=expectedEpoch or not enabled or not alive or not focus then release();return false end
    held[key]=true;event(key,true)
    if epoch~=expectedEpoch or not enabled or not alive or not focus then
        -- A yielding press may finish after F8 already released the key.
        held[key]=true;release();return false
    end
    return true
end
local function recordJump(request,now)
    lastJumpPress=now
    if request.ground then jumpAt=now else usedFlip=true end
    local events=physics.jumpEvents or {};physics.jumpEvents=events
    local actual=table.clone(request.actual);actual[6]=1
    events[#events+1]={time=now,requested=table.clone(request.action),mapped=actual,
        ground_estimate=request.ground,observed_keys=keyboard:observed(),wait_ms=(now-request.at)*1000}
    if #events>24 then table.remove(events,1)end
end
local function controls()
    start.Visible=not enabled and not testingKeyboard
    teamButton.Visible=not enabled and not testingKeyboard
    close.Visible=not enabled and not testingKeyboard
    physicsButton.Visible=not enabled and not testingKeyboard
    reportButton.Visible=not enabled and not testingKeyboard
    supportButton.Visible=not enabled and not testingKeyboard
    calibrationButton.Visible=not enabled and not testingKeyboard
    safetyButton.Visible=not enabled and not testingKeyboard
    graphicsButton.Visible=RUNTIME.cooperative==true and not enabled and not testingKeyboard
    latencyButton.Visible=RUNTIME.cooperative==true and not enabled and not testingKeyboard
    window.mini.Visible=not enabled
    main.Visible=not calibrating
    if calView then calView.Visible=calibrating end
end
local function runtimeSnapshot(now)
    local keys={};for _,key in ipairs(order)do if held[key]then keys[#keys+1]=key end end
    local phase=not alive and "closed"or(testingKeyboard and "keyboard test"
        or(enabled and(now<armAt and "arming"or(lastReadReason and "waiting"or "running"))or "paused"))
    return {enabled=enabled,ready=ready,phase=phase,focused=focus,keyboard=keyboard.name,
        keyboard_observed=keyboard:observed(),held_inputs=keys,last_stop_reason=lastStopReason,
        last_stop_time=lastStopAt,read_reason=lastReadReason,time=now,
        pending_jump=pendingJump~=nil,pending_jump_age=pendingJump and now-pendingJump.at or nil}
end
local function stop(reason)
    epoch=epoch+1;enabled=false;testingKeyboard=false;release();controls()
    lastStopReason=reason or "paused by control";lastStopAt=os.clock()
    physics:mark("stop",lastStopAt,lastStopReason)
    physics.runtime=runtimeSnapshot(lastStopAt)
    if reason then label.Text=reason end
end
local function saveReport(filename,savedFrom)
    assert(type(writefile)=="function","Executor writefile is unavailable")
    physics.runtime=runtimeSnapshot(os.clock())
    local report=physics:report()
    report.physics_assist_enabled=physicsEnabled;report.saved_from=savedFrom
    report.teammate_yield_enabled=intercept.supportEnabled;report.model_name=MODEL_NAME
    report.performance=timing:report()
    report.performance.cooperative=worker and worker:report()or nil
    report.performance.latency=RUNTIME.cooperative and latency:report()or nil
    report.performance.graphics=graphics and graphics:report()or nil
    report.adapter_version=ADAPTER_VERSION
    report.performance.last_active_age=timing.last and os.clock()-timing.last.time or nil
    report.jump_events=physics.jumpEvents or {}
    report.goal_safety_enabled=safetyEnabled;report.goal_safety=safety.last
    report.calibration=calibration:report();report.incidents=physics.incidents or {}
    report.control_requirements={default_keyboard_bindings=true,invertPitch=false,aerialSafety=false}
    report.model_sha256="0fe5bbe1318632b1934076230fc7426ae07db797e75b46f8d667b633f4e3a16f";report.place=game.PlaceId
    local body=game:GetService("HttpService"):JSONEncode(report)
    writefile(filename,body)
end
local function toggle()
    if calibrating then calibration.message='Close calibration before starting the bot';return end
    if not ready then return end
    if enabled or testingKeyboard then stop("LOCAL paused. F6 starts; F8 stops.");return end
    epoch=epoch+1
    if keyboard.selected then
        enabled=true;armAt=os.clock()+.5;physics:mark("start",os.clock());controls();return
    end
    testingKeyboard=true;controls()
    local testEpoch=epoch
    task.spawn(function()
        local function cancelled()
            return epoch~=testEpoch or not alive or not focus or input:GetFocusedTextBox()
                or input:IsKeyDown(Enum.KeyCode.F8)or(activeWindow and not activeWindow())
        end
        local ok,passed,reason=pcall(function()
            -- Let the launch hotkey/button settle before testing physical inputs.
            task.wait(.3)
            if cancelled()then return false,"Keyboard test cancelled"end
            return keyboard:probe(cancelled,function(message)label.Text="LOCAL keyboard test\n"..message end)
        end)
        if epoch~=testEpoch or not alive then keyboard:release();return end
        testingKeyboard=false
        if not ok or not passed then
            stop("LOCAL keyboard stopped: "..tostring(ok and reason or passed));return
        end
        label.Text="LOCAL keyboard verified: "..keyboard.name.."\nStarting model. F8 stops."
        enabled=true;armAt=os.clock()+.3;controls()
        physics:mark("start",os.clock(),"keyboard verified")
    end)
end
start.Activated:Connect(toggle)
teamButton.Activated:Connect(function()
    stop();manualTeam=manualTeam==nil and 0 or(manualTeam==0 and 1 or nil)
    teamReader.at=-math.huge
    teamButton.Text=manualTeam==nil and "Team: AUTO"or(manualTeam==0 and "Manual: BLUE"or "Manual: ORANGE")
end)
physicsButton.Activated:Connect(function()
    stop();physicsEnabled=not physicsEnabled
    physicsButton.Text=physicsEnabled and "Physics assist: ON"or "Physics assist: OFF"
    label.Text=physicsEnabled and "Physics ground approach enabled. F6 starts."
        or "Model only. Ball monitoring remains active. F6 starts."
end)
supportButton.Activated:Connect(function()
    stop();intercept.supportEnabled=not intercept.supportEnabled
    supportButton.Text=intercept.supportEnabled and "Yield to teammate: ON"or "Yield to teammate: OFF"
    label.Text=intercept.supportEnabled and "Ground assist may yield to a nearby, aligned teammate actively approaching the ball."
        or "Scripted teammate yielding disabled. F6 starts."
end)
safetyButton.Activated:Connect(function()
    stop();safetyEnabled=not safetyEnabled
    safetyButton.Text=safetyEnabled and 'Goal safety: ON'or 'Goal safety: OFF'
    label.Text=safetyEnabled and 'Conservative ground goal guards enabled.'or 'Goal guards disabled. F6 starts.'
end)
graphicsButton.Activated:Connect(function()
    if graphics then
        graphics:setEnabled(not graphics.enabled)
        graphicsButton.Text=graphics.enabled and 'Game optimization: ON'or 'Game optimization: OFF'
    end
end)
latencyButton.Activated:Connect(function()
    latency.enabled=not latency.enabled
    if worker then worker:cancel()end
    latencyButton.Text=latency.enabled and 'Lag compensation: ON'or 'Lag compensation: OFF'
end)
if RUNTIME.light_graphics then
    local ok,lighting=pcall(function()return game:GetService('Lighting')end)
    graphics=Graphics.new(world,ok and lighting or nil)
    graphics:setEnabled(true)
    connect(game:GetService('RunService').Heartbeat,function()
        if alive then graphics:step(.0003)end
    end)
end
do
    calView=Instance.new('Frame',window.body);calView.Name='Calibration';calView.Visible=false
    calView.Size=UDim2.fromScale(1,1);calView.BackgroundTransparency=1
    local function button(text,x,y,w,callback)
        local b=Instance.new('TextButton',calView);b.Text=text;b.Position=UDim2.fromOffset(x,y);b.Size=UDim2.fromOffset(w,28)
        connect(b.Activated,function()
            local ok,err=pcall(callback)
            if not ok then calibration.message=tostring(err)end
            refreshCalibration(os.clock())
        end)
        return b
    end
    local function text(y,h,size)
        local t=Instance.new('TextLabel',calView);t.Position=UDim2.fromOffset(10,y);t.Size=UDim2.fromOffset(460,h)
        t.BackgroundTransparency=1;t.TextColor3=Color3.new(1,1,1);t.TextWrapped=true;t.Font=Enum.Font.Code;t.TextSize=size
        return t
    end
    local title=text(39,28,14);local instruction=text(70,92,12)
    button('Goal landmarks',10,4,220,function()calibration.tab='geometry';calibration.message=nil end)
    button('Motion / physics test',240,4,230,function()calibration.crossbar=nil;calibration.tab='motion';calibration.message=nil end)
    local reference=button('Reference: front bumper',10,166,460,function()
        calibration.reference=calibration.reference=='bumper'and 'center'or 'bumper'
    end)
    captureCalibration=function()
        if calibration.tab=='motion'then
            if calibration.recordingUntil then calibration.recordingUntil=nil;calibration:summarizeMotion()
            else calibration:startMotion(os.clock())end
        else calibration:capture();return end
        calibration.message=nil
    end
    local capture=button('Capture point',10,203,220,captureCalibration)
    local back=button('Back',240,203,110,function()calibration:back();calibration.message=nil end)
    button('Reset',360,203,110,function()
        if calibration.tab=='motion'then
            calibration.motion=nil;calibration.recordingUntil=nil
            physics.gravity=PROFILE.physics.GRAVITY_Z;physics.observedGravity=nil;physics.gravitySamples={};physics:reset()
        else calibration:begin();calibration.active=nil end
        calibration.message='Calibration reset to the saved defaults'
    end)
    local apply=button('Apply goal measurements',10,240,460,function()
        if calibration.tab=='motion'then
            assert(not calibration.recordingUntil,'Finish recording first')
            local result=calibration:summarizeMotion()
            assert(result and result.gravity_consistent,'Need at least six consistent isolated airborne samples; launch the ball and record again')
            physics.gravity=result.gravity;physics.observedGravity=result.gravity;physics:reset()
            calibration.message=string.format('Applied gravity %.1f; masses and actor unchanged',result.gravity)
        else
            local data=calibration:apply();safety.last=nil
            intercept:reset();calibration.message='Applied to goal guards and optional ground aiming: '..data.summary
        end
    end)
    button('Save test file',10,277,150,function()
        assert(type(writefile)=='function','Executor writefile is unavailable')
        writefile('TurboBall_Calibration.json',game:GetService('HttpService'):JSONEncode(calibration:export()))
        calibration.message='Saved TurboBall_Calibration.json in the executor workspace'
    end)
    button('Load test file',170,277,150,function()
        assert(type(readfile)=='function','Executor readfile is unavailable')
        local data=readfile('TurboBall_Calibration.json');assert(#data<5000000,'Calibration file is too large')
        calibration:load(game:GetService('HttpService'):JSONDecode(data))
        calibration.message='Loaded measurements; review and Apply to use them'
    end)
    button('Close test',330,277,140,function()
        calibration.crossbar=nil;calibration.recordingUntil=nil;if calibration.motion then calibration:summarizeMotion()end
        calibrating=false;controls()
    end)
    refreshCalibration=function(now)
        local geometry=calibration.tab=='geometry'
        reference.Visible=geometry;back.Visible=geometry
        reference.Text=calibration.reference=='bumper'and 'Reference: front bumper contact'or 'Reference: car centre on marker'
        if geometry then
            local step=Calibration.steps[calibration.index]
            title.Text=step and string.format('%d/9  %s',calibration.index,step[2])or '9/9  Review goal measurements'
            local message=step and step[3]or(calibration.candidate and calibration.candidate.summary or 'Capture every landmark before applying')
            if calibration.reference=='center'and step and step[1]~='center'then message='Place the CAR CENTRE directly on the geometric marker; no bumper offset will be added.'end
            local last=calibration.history[#calibration.history]
            local body=last and ('\nBody: '..last.preset..(last.verified and ' verified'or ' / source offsets'))or ''
            local flying=step and (step[1]=='orange_top'or step[1]=='blue_top')
            instruction.Text=message..body..'\n'..(calibration.message or (flying and 'F10 arms flying capture; F4 minimizes.'or 'Hold still. F10 captures; F4 minimizes this window.'))
            capture.Text=flying and (calibration.crossbar and 'Cancel flying capture'or 'Arm flying capture / F10')or 'Capture point';apply.Text='Apply goal measurements'
        else
            title.Text='20-second manual physics recording'
            local result=calibration.motion and calibration.motion.summary
            local status=calibration.recordingUntil and string.format('Recording: %.0f s left',math.max(0,calibration.recordingUntil-now))
                or(result and string.format('%d samples | gravity %s | acceleration %s',result.samples,
                    result.gravity_consistent and string.format('%.1f',result.gravity)or 'needs clear flight',
                    result.ground_acceleration_median and string.format('%.0f',result.ground_acceleration_median)or 'not measured')or 'Ready')
            instruction.Text='In freeplay: drive straight, brake, then launch the ball into clear flight. You drive; the bot stays paused.\n'..status..'\n'..(calibration.message or 'Landmarks measure geometry. Motion samples do not identify masses.')
            capture.Text=calibration.recordingUntil and 'Finish recording'or 'Record 20 seconds';apply.Text='Apply consistent gravity estimate'
        end
    end
    calibrationButton.Activated:Connect(function()
        stop('Calibration: bot paused for manual placement')
        if not calibration.started then calibration:begin();calibration.started=true end
        calibrating=true;controls();refreshCalibration(os.clock())
    end)
end
reportButton.Activated:Connect(function()
    local savedFrom=runtimeSnapshot(os.clock())
    stop("Paused to save physics report.")
    local ok,reason=pcall(function()
        saveReport("TurboBall_Physics_Report.json",savedFrom)
    end)
    label.Text=ok and "Saved TurboBall_Physics_Report.json in the executor workspace."
        or("Could not save physics report: "..tostring(reason))
end)
connect(input.InputBegan,function(key,processed)
    if key.KeyCode==Enum.KeyCode.F8 then stop("STOPPED by F8. F6 starts again.")
    elseif not processed then
        if key.KeyCode==Enum.KeyCode.F6 then toggle()
        elseif key.KeyCode==Enum.KeyCode.F4 then window:toggle()
        elseif key.KeyCode==Enum.KeyCode.F10 and calibrating then
            local ok,err=pcall(captureCalibration)
            if not ok then calibration.message=tostring(err)end
            refreshCalibration(os.clock())
        elseif key.KeyCode==Enum.KeyCode.F9 then
            local rows={};local now=os.clock()
            for _,row in ipairs(physics.trace)do if now-row.time<=8 then rows[#rows+1]=row end end
            physics.incidents=physics.incidents or {}
            physics.incidents[#physics.incidents+1]={time=now,trace=rows,decision=physics.decision,goal_safety=safety.last}
            if #physics.incidents>2 then table.remove(physics.incidents,1)end
            physics:mark('Incident marker',now,#rows..' recent poses retained')
        end
    end
end)
connect(input.WindowFocusReleased,function()focus=false;stop("Paused: Roblox lost focus. F6 restarts.")end)
connect(input.WindowFocused,function()focus=true end)
close.Activated:Connect(function()
    alive=false;stop()
    if graphics then graphics:close()end
    for _,connection in ipairs(connections)do connection:Disconnect()end
    gui:Destroy()
end)
local function teamChanged()
    if testingKeyboard then stop("Team changed during keyboard test. F6 restarts.");return end
    epoch=epoch+1;release();carReader.tracked={};carReader.scanAt=-math.huge
    lastGround=true;armAt=os.clock()+.15
end
local scene,car,ball,carRoot,ballRoot,lastCar,lastBall,lastTime
local function nearest(anchor,excluded)
    if not anchor then return nil end
    local best,distance=nil,3
    for _,model in ipairs(scene:GetDescendants())do
        if model:IsA("Model")and model~=excluded and model.PrimaryPart then
            local d=(model.PrimaryPart.Position-anchor.Position).Magnitude
            if d<distance then best,distance=model,d end
        end
    end
    return best
end
local boostLabel
local function boost()
    if boostLabel and boostLabel:IsDescendantOf(pg)then
        local value=tonumber(boostLabel.Text)
        if value and value>=0 and value<=100 then return value end
    end
    local hud=pg:FindFirstChild("CarSoccerHud")
    local holder=hud and hud:FindFirstChild("Boost",true)
    holder=holder and(holder:FindFirstChild("BoostS1",true)or holder)
    if holder then
        for _,item in ipairs(holder:GetDescendants())do
            if item:IsA("TextLabel")then
                local value=tonumber(item.Text)
                if value and value>=0 and value<=100 then boostLabel=item;return value end
            end
        end
    end
end
local function sim(v,k)return {v.X*k,v.Z*k,v.Y*k}end
local function pose(frame,previous,dt)
    local delta=frame.Position-previous.Position
    local axis,angle=previous:ToObjectSpace(frame):ToAxisAngle()
    local omega=previous:VectorToWorldSpace(axis)*(angle/dt)
    local scale=arenaAdapter and 1/arenaAdapter.profile.roblox_studs_per_sim_unit or 10
    return {position=sim(frame.Position,scale),velocity=sim(delta/dt,scale),
        forward=sim(frame.LookVector,1),up=sim(frame.UpVector,1),
        angular_velocity=sim(omega,-1)},delta.Magnitude
end
local function read()
    local current=world:FindFirstChild("CarSoccer")
    if current~=scene then scene=current;car=nil;ball=nil end
    if not scene then return nil,"scene unavailable"end
    if not car or not ball or not carRoot:IsDescendantOf(scene)
        or not ballRoot:IsDescendantOf(scene)or car.PrimaryPart~=carRoot or ball.PrimaryPart~=ballRoot then
        local sounds=scene:FindFirstChild("Sounds")
        car=nearest(sounds and sounds:FindFirstChild("CarSound"))
        ball=car and nearest(sounds and sounds:FindFirstChild("BallSound"),car)
        if not car or not ball then return nil,"goal/reset: waiting for car and ball"end
        carRoot,ballRoot=car.PrimaryPart,ball.PrimaryPart
        if arenaAdapter then arenaAdapter:measureCar(car,carRoot)end
        lastCar,lastBall,lastTime=carRoot.CFrame,ballRoot.CFrame,os.clock()
        return nil,"warming up poses"
    end
    local now=os.clock()
    local detected,teamSource=teamReader:detect(pg,scene,carRoot,now,manualTeam)
    teamButton.Text=manualTeam==nil and("AUTO: "..(detected==nil and "?"or(detected==0 and "BLUE"or "ORANGE")))
        or(manualTeam==0 and "Manual: BLUE"or "Manual: ORANGE")
    if detected==nil then return nil,teamSource end
    if detected~=TEAM then
        local previousTeam=TEAM;TEAM=detected
        if previousTeam~=nil then teamChanged()end
        lastCar,lastBall,lastTime=carRoot.CFrame,ballRoot.CFrame,now
        return nil,"team identified; warming up poses"
    end
    local dt=now-lastTime
    local cf,bf=carRoot.CFrame,ballRoot.CFrame
    if dt<=0 then return nil,"waiting for next frame"end
    local cp,cd=pose(cf,lastCar,dt);local bp,bd=pose(bf,lastBall,dt)
    lastCar,lastBall,lastTime=cf,bf,now
    if dt>.3 or cd/dt>350 or bd/dt>800 then return nil,"pose discontinuity/reset"end
    local b=boost()
    if b==nil then return nil,"numeric boost HUD missing"end
    local p,u=cp.position,cp.up
    -- Contact estimate for the standard soccer arena, NOT internal wheel state.
    local grounded=(p[3]<38 and u[3]>.65)
        or(p[3]>2006 and u[3]<-.65)
        or(math.abs(p[1])>4058 and u[1]*p[1]<-2500)
        or(math.abs(p[2])>5082 and math.abs(p[1])>1000 and u[2]*p[2]<-3200)
    local contacts,ballContacts,ballRadius,ballSizeVerified
    if arenaAdapter then
        if scene:FindFirstChild("ArenaFree")then return nil,"alternate arena needs its own physics profile"end
        if now-(arenaAdapter.lastMeasure or -math.huge)>2 then arenaAdapter:measureCar(car,carRoot)end
        ballRadius,ballSizeVerified=arenaAdapter:ballRadius(ballRoot)
        grounded,contacts,ballContacts=arenaAdapter:ground(cp,bp,ballRadius)
    end
    local packet={car=cp,ball=bp,boost=b,team=TEAM,ground_estimate=grounded,valid=true,sample_dt=dt}
    packet.team_source=teamSource
    if arenaAdapter then
        packet.ball_radius,packet.ball_size_verified=ballRadius,ballSizeVerified
        packet.car_preset=arenaAdapter.preset;packet.car_size_verified=arenaAdapter.hitboxVerified
        packet.car_dimensions_verified=arenaAdapter.sizeVerified==true
        packet.wheel_contacts=contacts
        packet.ball_wheel_contacts=ballContacts
    end
    if padReader then
        packet.boost_pads=padReader:read(car.Parent or scene,cp.position,now)
        packet.boost_known=padReader.known;packet.boost_total=padReader.total
        packet.pad_folder_found=padReader.folder~=nil
    end
    if carReader then
        packet.other_cars=carReader:read(scene,carRoot,ballRoot,now,pose,bp,ballRadius,TEAM)
        packet.opponents=carReader.opponents;packet.teammates=carReader.teammates
        packet.unknown_cars=carReader.unknown
    end
    if arenaAdapter then packet.hitbox_probe=arenaAdapter.hitboxProbe end
    return packet
end

local startup=RUNTIME.cooperative and Startup.new({alive=function()return alive end,
    render=function(stage,done,total,elapsed)
        local progress=total and(' | %.0f%%'):format(math.clamp(done/total,0,1)*100)or ''
        label.Text=MODEL_NAME..' LOCAL v'..ADAPTER_VERSION..': loading\n'..stage..progress..
            ('\nElapsed %.1fs | Close cancels loading'):format(elapsed)
    end})or nil
local function loadingYield(force)
    assert(alive,'Model loading cancelled')
    if startup then startup:checkpoint(force)end
end
local function loadingProgress(stage,done,total)
    if startup then startup:progress(stage,done,total)end
end
local function downloadModel(url,layout,count)
    local raw=startup:download(url,count*4)
    loadingProgress('Opening FP32 model',0,1)
    return Policy.loadBuffer(buffer.fromstring(raw),layout,count)
end
local function loadTensors()
return downloadModel("https://raw.githubusercontent.com/DMDIASSS/Chat_GPT_AI/aa6141f163cc3a059509019c178bbd527238356d/downloads/ChronosV2_1_FP32.bin",{["shared.0.weight"]={1,216000},["shared.0.bias"]={216001,960},["shared.1.weight"]={216961,960},["shared.1.bias"]={217921,960},["shared.3.weight"]={218881,921600},["shared.3.bias"]={1140481,960},["shared.4.weight"]={1141441,960},["shared.4.bias"]={1142401,960},["policy.0.weight"]={1143361,921600},["policy.0.bias"]={2064961,960},["policy.1.weight"]={2065921,960},["policy.1.bias"]={2066881,960},["policy.3.weight"]={2067841,768000},["policy.3.bias"]={2835841,800},["policy.4.weight"]={2836641,800},["policy.4.bias"]={2837441,800},["policy.6.weight"]={2838241,512000},["policy.6.bias"]={3350241,640},["policy.7.weight"]={3350881,640},["policy.7.bias"]={3351521,640},["policy.9.weight"]={3352161,409600},["policy.9.bias"]={3761761,640},["policy.10.weight"]={3762401,640},["policy.10.bias"]={3763041,640},["policy.12.weight"]={3763681,57600},["policy.12.bias"]={3821281,90}},3821370)
end
task.spawn(function()
    local ok,errorText=pcall(function()
        assert(player.Name=="Deadline_coolgun"and game.PlaceId==101880234193261,
            "This adapter targets Deadline_coolgun / place 101880234193261")
        assert(not pg:FindFirstChild("Update271Bridge"),
            "Close the old bridge panel and stop START_FILE_BOT.bat before using LOCAL mode")
        pressLeft,releaseLeft=mouse1press,mouse1release
        pressRight,releaseRight=mouse2press,mouse2release
        for name,fn in pairs({mouse1press=pressLeft or false,mouse1release=releaseLeft or false,
            mouse2press=pressRight or false,mouse2release=releaseRight or false})do
            assert(type(fn)=="function","Missing executor input function: "..name)
        end
        if type(activeWindow)~="function"then activeWindow=nil end
        loadingProgress('Decoding embedded model',0,1)
        local tensors=loadTensors()
        local predict,backend=Policy.new(tensors,{yieldWork=RUNTIME.cooperative and loadingYield or nil,
            progress=RUNTIME.cooperative and loadingProgress or nil})
        tensors=nil
        worker=RUNTIME.cooperative and Worker.new(predict)or nil
        if worker then worker.backend=backend end
        local cases=
{{["query"]={0.03999999910593033,-0.17000000178813934,0.02800000086426735,-0.104347825050354,0.30434781312942505,0.0782608687877655,0.36666667461395264,-0.06666667014360428,0.7666666507720947,0.0,0.0,-1.0,0.0,-1.0,1.0,0.0,1.0,0.5555555820465088,1.0,1.0,0.5555555820465088,1.0,1.0,0.5555555820465088,1.0,1.0,0.5555555820465088,1.0,1.0,0.5555555820465088,1.0,1.0,0.5555555820465088,1.0,1.0,0.5555555820465088,1.0,1.0,0.5555555820465088,1.0,1.0,0.5555555820465088,1.0,1.0,0.5555555820465088,1.0,1.0,0.5555555820465088,1.0,1.0,0.5555555820465088,-0.23999999463558197,-0.4399999976158142,0.0034000000450760126,0.6000000238418579,0.800000011920929,0.0,0.0,0.0,1.0,0.15217390656471252,0.3913043439388275,0.0,0.06666667014360428,-0.13333334028720856,0.23333333432674408,-0.06666667014360428,-0.13333334028720856,0.23333333432674408,0.3840000033378601,-0.06199999898672104,0.02459999918937683,-0.2234782576560974,0.1530434787273407,0.0782608687877655,0.0,1.0,1.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.23999999463558197,0.30000001192092896,0.0034000000450760126,0.6000000238418579,0.800000011920929,0.0,0.0,0.0,1.0,0.15217390656471252,0.3913043439388275,0.0,0.06666667014360428,-0.13333334028720856,0.23333333432674408,-0.06666667014360428,-0.13333334028720856,0.23333333432674408,-0.4959999918937683,-0.12200000137090683,0.02459999918937683,-0.2234782576560974,0.1530434787273407,0.0782608687877655,0.4699999988079071,1.0,1.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0},["entities"]={["mirror"]=false,["entity_count"]=3,["mask"]={true,true,true,true,true,true,true,true,true,true,true,true,true,true,false,false,true,true,false,false,true,true,false,false,false,false,false,false,false,false,false,false,true,true,false,false,true,true,false,false,true,true,false,false,false,false,false,false,false,false,false,false,false,false,true,true,true,true,false,false,true,true,false,false,false,false,false,false,false,false,false,false,false,false,true,true,false,false,true,true,false,false,true,true,false,false,false,false,false,false}},["logits"]={-5.291416168212891,-2.014817237854004,-4.932028770446777,-1.1257866621017456,-4.942924499511719,-0.8784714937210083,-1.2893162965774536,-0.952355682849884,-0.31672438979148865,-0.19907450675964355,-0.17740195989608765,0.2568320631980896,0.328666627407074,-0.004868499934673309,-1.928029179573059,-2.204322099685669,1.3744202852249146,0.8697283864021301,-0.5415624380111694,-1.0272008180618286,1.694141149520874,1.2367713451385498,-0.27748021483421326,-0.7919295430183411,0.1878625750541687,-2.126471996307373,-1.5832457542419434,-1.9418123960494995,-1.516956090927124,-2.167556047439575,-0.8573437333106995,-1.0934919118881226,-1.0713995695114136,-0.7498037815093994,-0.5114719867706299,-1.0101914405822754,-0.11998432874679565,-0.11965906620025635,-0.6953950524330139,-0.946064829826355,-0.22924566268920898,-0.32168757915496826,-0.21046334505081177,-0.5965220928192139,-0.10551763325929642,-0.5626041889190674,-0.28236159682273865,-0.47359955310821533,-1.3002849817276,-1.7067209482192993,-1.1078376770019531,-1.6115026473999023,-0.3810573220252991,-0.8740625381469727,-0.9870334267616272,-0.9403840899467468,-0.6989277601242065,-0.2910904586315155,-0.35898083448410034,-0.49576377868652344,-0.4245234429836273,-0.4113968312740326,0.008852306753396988,-0.2614593803882599,0.22079548239707947,-0.054765790700912476,-1.0550618171691895,-1.424460768699646,-0.7578265070915222,-1.1617575883865356,-0.751014232635498,-1.0305590629577637,-0.13666875660419464,-0.4018688201904297,-1.329315185546875,-1.147667646408081,0.045121386647224426,-0.1327541172504425,-0.8213202357292175,-0.7858514189720154,-0.020773787051439285,-0.1470351219177246,-0.6287323236465454,-0.8377785086631775,0.12169691920280457,0.09368512034416199,0.4822734296321869,0.3390386402606964,0.4596523344516754,0.38919004797935486},["action"]=21},{["query"]={0.03999999910593033,-0.17000000178813934,0.02800000086426735,-0.104347825050354,0.30434781312942505,0.0782608687877655,0.36666667461395264,-0.06666667014360428,0.7666666507720947,0.0,0.0,-1.0,0.0,-1.0,1.0,0.0,1.0,0.5555555820465088,1.0,1.0,0.5555555820465088,1.0,1.0,0.5555555820465088,1.0,1.0,0.5555555820465088,1.0,1.0,0.5555555820465088,1.0,1.0,0.5555555820465088,1.0,1.0,0.5555555820465088,1.0,1.0,0.5555555820465088,1.0,1.0,0.5555555820465088,1.0,1.0,0.5555555820465088,1.0,1.0,0.5555555820465088,1.0,1.0,0.5555555820465088,-0.23999999463558197,-0.4399999976158142,0.12399999797344208,0.6000000238418579,0.800000011920929,0.0,0.0,0.0,1.0,0.15217390656471252,0.3913043439388275,0.12173912674188614,0.06666667014360428,-0.13333334028720856,0.23333333432674408,-0.06666667014360428,-0.13333334028720856,0.23333333432674408,0.3840000033378601,-0.06199999898672104,-0.09600000083446503,-0.2234782576560974,0.1530434787273407,-0.043478261679410934,0.6299999952316284,0.0,1.0,0.0,1.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.23999999463558197,0.30000001192092896,0.0034000000450760126,0.6000000238418579,0.800000011920929,0.0,0.0,0.0,1.0,0.15217390656471252,0.3913043439388275,0.12173912674188614,0.06666667014360428,-0.13333334028720856,0.23333333432674408,-0.06666667014360428,-0.13333334028720856,0.23333333432674408,-0.4959999918937683,-0.12200000137090683,0.02459999918937683,-0.2234782576560974,0.1530434787273407,-0.043478261679410934,0.4699999988079071,1.0,1.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0},["entities"]={["mirror"]=false,["entity_count"]=3,["mask"]={false,false,false,false,false,false,false,true,true,false,false,true,false,false,false,true,false,false,true,false,false,false,false,true,false,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true}},["logits"]={1.3033148050308228,1.1148731708526611,1.2297334671020508,1.30888831615448,1.0427772998809814,1.1269190311431885,1.1471805572509766,1.189188838005066,1.2745749950408936,1.1866340637207031,1.1234054565429688,1.0806010961532593,0.8161332011222839,0.9400590062141418,-1.2809163331985474,-1.2909519672393799,1.3314839601516724,1.221498727798462,-1.1897708177566528,-1.405148983001709,1.145812749862671,1.0228160619735718,-0.7621920108795166,-1.5521953105926514,-0.07863865047693253,-0.3636576533317566,1.9002904891967773,-0.469480037689209,1.9863852262496948,-0.5811082124710083,1.7425456047058105,-0.49638766050338745,-9.70887279510498,-11.749975204467773,1.9534395933151245,-0.47745633125305176,-9.85193920135498,-11.93628978729248,1.9850986003875732,-0.40017884969711304,-10.450535774230957,-12.508299827575684,1.6314287185668945,-1.069643497467041,1.788388967514038,-0.6309098601341248,1.8771569728851318,-0.6416705250740051,1.1351395845413208,-1.1844614744186401,1.191107153892517,-1.3449747562408447,0.9015588760375977,-1.5509974956512451,-10.695297241210938,-12.459525108337402,-10.636164665222168,-12.552587509155273,1.046370506286621,-1.2297165393829346,-11.44066333770752,-13.111077308654785,0.837751567363739,-1.747881531715393,1.1108587980270386,-1.453656554222107,0.20043933391571045,-2.329965353012085,0.27277398109436035,-2.4472687244415283,0.3019118010997772,-2.3618733882904053,0.02847505733370781,-2.6530885696411133,-11.85720443725586,-13.823758125305176,0.24881421029567719,-2.3872437477111816,-12.023894309997559,-13.729981422424316,0.2316356599330902,-2.322655439376831,-12.101036071777344,-13.735015869140625,-0.204204261302948,-2.7405381202697754,0.0487750880420208,-2.718906879425049,0.14807851612567902,-2.4892547130584717},["action"]=29},{["query"]={-0.03999999910593033,-0.17000000178813934,0.02800000086426735,0.104347825050354,0.30434781312942505,0.0782608687877655,0.36666667461395264,0.06666667014360428,-0.7666666507720947,0.0,-0.0,-1.0,-0.0,1.0,1.0,0.0,1.0,0.5555555820465088,1.0,1.0,1.0,0.5555555820465088,0.5555555820465088,1.0,1.0,0.5555555820465088,1.0,1.0,1.0,1.0,1.0,0.5555555820465088,0.5555555820465088,1.0,1.0,0.5555555820465088,0.5555555820465088,1.0,1.0,1.0,1.0,1.0,0.5555555820465088,1.0,1.0,0.5555555820465088,0.5555555820465088,1.0,1.0,1.0,0.5555555820465088,-0.23999999463558197,-0.4399999976158142,0.0034000000450760126,-0.6000000238418579,0.800000011920929,0.0,-0.0,0.0,1.0,-0.15217390656471252,0.3913043439388275,0.0,0.06666667014360428,0.13333334028720856,-0.23333333432674408,0.06666667014360428,-0.13333334028720856,-0.23333333432674408,0.09600000083446503,-0.32199999690055847,0.02459999918937683,-0.2234782576560974,-0.1530434787273407,0.0782608687877655,0.0,1.0,1.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.23999999463558197,0.30000001192092896,0.0034000000450760126,-0.6000000238418579,0.800000011920929,0.0,-0.0,0.0,1.0,-0.15217390656471252,0.3913043439388275,0.0,0.06666667014360428,0.13333334028720856,-0.23333333432674408,0.06666667014360428,-0.13333334028720856,-0.23333333432674408,-0.20800000429153442,0.5059999823570251,0.02459999918937683,-0.2234782576560974,-0.1530434787273407,0.0782608687877655,0.4699999988079071,1.0,1.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0},["entities"]={["mirror"]=true,["entity_count"]=3,["mask"]={true,true,true,true,true,true,true,true,true,true,true,true,true,true,false,false,true,true,false,false,true,true,false,false,false,false,false,false,false,false,false,false,true,true,false,false,true,true,false,false,true,true,false,false,false,false,false,false,false,false,false,false,false,false,true,true,true,true,false,false,true,true,false,false,false,false,false,false,false,false,false,false,false,false,true,true,false,false,true,true,false,false,true,true,false,false,false,false,false,false}},["logits"]={1.9295421838760376,3.985813856124878,-1.683353066444397,-1.022207260131836,-6.6163859367370605,-7.5930585861206055,8.133238792419434,5.395382881164551,2.643002986907959,-0.30294206738471985,-4.361215114593506,-7.48032808303833,10.15656566619873,6.732245922088623,2.1609201431274414,-1.458385705947876,3.568082094192505,0.2754383385181427,-4.8166279792785645,-8.187567710876465,-4.517442226409912,-6.696316719055176,-13.377774238586426,-15.07448673248291,-0.45801711082458496,1.0098199844360352,6.254347324371338,0.2545281946659088,4.751773357391357,-1.4997847080230713,1.882885456085205,-4.137321472167969,-37.8518180847168,-42.27798843383789,1.3673642873764038,-5.6704816818237305,-38.36101531982422,-43.37583541870117,0.1561693400144577,-6.592461585998535,-38.75037384033203,-43.64466094970703,-4.107732772827148,-11.338050842285156,-4.762243270874023,-11.756463050842285,-5.874118328094482,-13.87502384185791,7.817548751831055,1.7865543365478516,5.328036308288574,-0.9086031913757324,3.2629878520965576,-3.669563055038452,-37.13389205932617,-40.908451080322266,-35.878684997558594,-41.71923065185547,0.6150826215744019,-6.006789684295654,-39.120418548583984,-43.27080154418945,-3.3176939487457275,-10.609206199645996,-5.415691375732422,-13.010334014892578,7.380345821380615,1.2436420917510986,6.7335991859436035,0.4974396228790283,4.841264247894287,-0.9530702233314514,2.7078826427459717,-3.9845550060272217,-37.04104995727539,-41.71159362792969,1.7609500885009766,-5.0613579750061035,-39.24421310424805,-43.639129638671875,-0.08515264093875885,-6.693944454193115,-39.940574645996094,-44.92692565917969,-3.851472854614258,-10.649638175964355,-4.603366374969482,-11.699009895324707,-6.029959678649902,-13.10116958618164},["action"]=13},{["query"]={-0.03999999910593033,-0.17000000178813934,0.02800000086426735,0.104347825050354,0.30434781312942505,0.0782608687877655,0.36666667461395264,0.06666667014360428,-0.7666666507720947,0.0,-0.0,-1.0,-0.0,1.0,1.0,0.0,1.0,0.5555555820465088,1.0,1.0,1.0,0.5555555820465088,0.5555555820465088,1.0,1.0,0.5555555820465088,1.0,1.0,1.0,1.0,1.0,0.5555555820465088,0.5555555820465088,1.0,1.0,0.5555555820465088,0.5555555820465088,1.0,1.0,1.0,1.0,1.0,0.5555555820465088,1.0,1.0,0.5555555820465088,0.5555555820465088,1.0,1.0,1.0,0.5555555820465088,-0.23999999463558197,-0.4399999976158142,0.12399999797344208,-0.6000000238418579,0.800000011920929,0.0,-0.0,0.0,1.0,-0.15217390656471252,0.3913043439388275,0.12173912674188614,0.06666667014360428,0.13333334028720856,-0.23333333432674408,0.06666667014360428,-0.13333334028720856,-0.23333333432674408,0.09600000083446503,-0.32199999690055847,-0.09600000083446503,-0.2234782576560974,-0.1530434787273407,-0.043478261679410934,0.6299999952316284,0.0,0.0,0.0,1.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.23999999463558197,0.30000001192092896,0.0034000000450760126,-0.6000000238418579,0.800000011920929,0.0,-0.0,0.0,1.0,-0.15217390656471252,0.3913043439388275,0.12173912674188614,0.06666667014360428,0.13333334028720856,-0.23333333432674408,0.06666667014360428,-0.13333334028720856,-0.23333333432674408,-0.20800000429153442,0.5059999823570251,0.02459999918937683,-0.2234782576560974,-0.1530434787273407,-0.043478261679410934,0.4699999988079071,1.0,1.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0},["entities"]={["mirror"]=true,["entity_count"]=3,["mask"]={false,false,false,false,false,false,false,true,true,false,false,true,false,false,false,true,false,false,true,false,false,false,false,true,false,true,true,true,true,true,true,true,false,false,true,true,false,false,true,true,false,false,true,true,true,true,true,true,true,true,true,true,true,true,false,false,false,false,true,true,false,false,true,true,true,true,true,true,true,true,true,true,true,true,false,false,true,true,false,false,true,true,false,false,true,true,true,true,true,true}},["logits"]={3.521994113922119,3.9897472858428955,3.447909116744995,4.1052680015563965,3.9359686374664307,4.791965961456299,2.1738405227661133,3.1706037521362305,3.3151051998138428,3.289335012435913,2.96229887008667,3.6222236156463623,-0.3807785212993622,1.0206737518310547,-9.582764625549316,-8.148521423339844,-1.5288734436035156,1.167863130569458,-9.16451358795166,-7.7986226081848145,-0.19854958355426788,1.4826467037200928,-8.410591125488281,-8.105408668518066,-0.03793102502822876,-8.266571998596191,3.284684658050537,-8.564835548400879,3.103008508682251,-8.72490406036377,3.456331968307495,-8.243932723999023,-10.897789001464844,-20.657161712646484,3.696880578994751,-8.602972030639648,-12.531856536865234,-23.155622482299805,3.412646532058716,-8.765633583068848,-10.778974533081055,-21.788122177124023,3.601545810699463,-8.328871726989746,3.8241939544677734,-8.116769790649414,3.5554730892181396,-8.492389678955078,3.175168037414551,-8.713350296020508,3.035114288330078,-8.727123260498047,3.5451126098632812,-8.72982406616211,-8.776886940002441,-18.340784072875977,-9.589343070983887,-20.858428955078125,3.2691893577575684,-8.970597267150879,-12.535298347473145,-22.255224227905273,3.695945978164673,-8.366937637329102,3.514871120452881,-8.620265007019043,0.48938778042793274,-11.712417602539062,0.25292307138442993,-11.846220016479492,-0.132730171084404,-12.020262718200684,0.6339959502220154,-11.551535606384277,-4.489907741546631,-15.664778709411621,0.5498747229576111,-11.668059349060059,-4.933588027954102,-17.26424789428711,0.35560086369514465,-12.056536674499512,-8.624528884887695,-20.104875564575195,0.771274209022522,-11.393145561218262,0.7401770353317261,-11.606931686401367,0.4365518093109131,-11.928467750549316},["action"]=45},{["query"]={0.03999999910593033,0.17000000178813934,0.02800000086426735,-0.104347825050354,-0.30434781312942505,0.0782608687877655,-0.36666667461395264,-0.06666667014360428,-0.7666666507720947,0.0,-0.0,-1.0,-0.0,1.0,1.0,0.0,1.0,0.5555555820465088,1.0,1.0,1.0,0.5555555820465088,0.5555555820465088,1.0,1.0,0.5555555820465088,1.0,1.0,1.0,1.0,1.0,0.5555555820465088,0.5555555820465088,1.0,1.0,0.5555555820465088,0.5555555820465088,1.0,1.0,1.0,1.0,1.0,0.5555555820465088,1.0,1.0,0.5555555820465088,0.5555555820465088,1.0,1.0,1.0,0.5555555820465088,-0.23999999463558197,0.4399999976158142,0.0034000000450760126,0.6000000238418579,-0.800000011920929,0.0,0.0,-0.0,1.0,0.15217390656471252,-0.3913043439388275,0.0,-0.06666667014360428,-0.13333334028720856,-0.23333333432674408,0.06666667014360428,-0.13333334028720856,-0.23333333432674408,0.3840000033378601,0.06199999898672104,0.02459999918937683,-0.2234782576560974,-0.1530434787273407,0.0782608687877655,0.0,1.0,1.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.23999999463558197,-0.30000001192092896,0.0034000000450760126,0.6000000238418579,-0.800000011920929,0.0,0.0,-0.0,1.0,0.15217390656471252,-0.3913043439388275,0.0,-0.06666667014360428,-0.13333334028720856,-0.23333333432674408,0.06666667014360428,-0.13333334028720856,-0.23333333432674408,-0.4959999918937683,0.12200000137090683,0.02459999918937683,-0.2234782576560974,-0.1530434787273407,0.0782608687877655,0.4699999988079071,1.0,1.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0},["entities"]={["mirror"]=true,["entity_count"]=3,["mask"]={true,true,true,true,true,true,true,true,true,true,true,true,true,true,false,false,true,true,false,false,true,true,false,false,false,false,false,false,false,false,false,false,true,true,false,false,true,true,false,false,true,true,false,false,false,false,false,false,false,false,false,false,false,false,true,true,true,true,false,false,true,true,false,false,false,false,false,false,false,false,false,false,false,false,true,true,false,false,true,true,false,false,true,true,false,false,false,false,false,false}},["logits"]={-10.58230972290039,-3.1734893321990967,-11.49697494506836,-3.4185752868652344,-12.925215721130371,-5.932242393493652,-0.5093814730644226,-0.20839722454547882,-1.1288050413131714,-0.6343116760253906,-3.890131950378418,-2.7637932300567627,5.322591304779053,2.8550827503204346,3.2122910022735596,0.8676686882972717,4.260080814361572,2.2811152935028076,2.346449613571167,0.2993970811367035,0.7986934781074524,-0.5419595837593079,-1.140973448753357,-2.294489860534668,0.08473493158817291,1.5638376474380493,-0.5044600367546082,2.0433566570281982,-0.8260102272033691,1.5894337892532349,-1.0798441171646118,1.1926157474517822,-9.432085037231445,-8.166254997253418,-0.7314831614494324,1.3952581882476807,-10.583769798278809,-9.162774085998535,-1.2259875535964966,1.0973429679870605,-11.087748527526855,-9.901707649230957,-2.186086416244507,-0.23645681142807007,-2.022568464279175,-0.09205799549818039,-2.908172130584717,-0.5941528081893921,-0.5153395533561707,2.082054853439331,-0.7609013319015503,1.5409351587295532,-0.9715911149978638,1.2891032695770264,-8.837386131286621,-7.585688591003418,-10.810749053955078,-7.925305366516113,-1.3413115739822388,1.226685643196106,-10.299928665161133,-8.750406265258789,-2.548600435256958,-0.23001040518283844,-2.669654607772827,-0.6340840458869934,-0.7012649774551392,2.0160510540008545,-0.524398684501648,1.8945033550262451,-0.8638961911201477,1.7172441482543945,-1.0518392324447632,1.4835871458053589,-8.350245475769043,-7.267808437347412,-1.282893419265747,1.236372470855713,-9.196533203125,-7.7229084968566895,-1.5271494388580322,0.9971002340316772,-9.393471717834473,-8.138040542602539,-2.6162362098693848,0.05218400061130524,-2.481245756149292,-0.34180888533592224,-2.866530418395996,-0.6453761458396912},["action"]=13},{["query"]={0.03999999910593033,0.17000000178813934,0.02800000086426735,-0.104347825050354,-0.30434781312942505,0.0782608687877655,-0.36666667461395264,-0.06666667014360428,-0.7666666507720947,0.0,-0.0,-1.0,-0.0,1.0,1.0,0.0,1.0,0.5555555820465088,1.0,1.0,1.0,0.5555555820465088,0.5555555820465088,1.0,1.0,0.5555555820465088,1.0,1.0,1.0,1.0,1.0,0.5555555820465088,0.5555555820465088,1.0,1.0,0.5555555820465088,0.5555555820465088,1.0,1.0,1.0,1.0,1.0,0.5555555820465088,1.0,1.0,0.5555555820465088,0.5555555820465088,1.0,1.0,1.0,0.5555555820465088,-0.23999999463558197,0.4399999976158142,0.12399999797344208,0.6000000238418579,-0.800000011920929,0.0,0.0,-0.0,1.0,0.15217390656471252,-0.3913043439388275,0.12173912674188614,-0.06666667014360428,-0.13333334028720856,-0.23333333432674408,0.06666667014360428,-0.13333334028720856,-0.23333333432674408,0.3840000033378601,0.06199999898672104,-0.09600000083446503,-0.2234782576560974,-0.1530434787273407,-0.043478261679410934,0.6299999952316284,0.0,1.0,0.0,1.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.23999999463558197,-0.30000001192092896,0.0034000000450760126,0.6000000238418579,-0.800000011920929,0.0,0.0,-0.0,1.0,0.15217390656471252,-0.3913043439388275,0.12173912674188614,-0.06666667014360428,-0.13333334028720856,-0.23333333432674408,0.06666667014360428,-0.13333334028720856,-0.23333333432674408,-0.4959999918937683,0.12200000137090683,0.02459999918937683,-0.2234782576560974,-0.1530434787273407,-0.043478261679410934,0.4699999988079071,1.0,1.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0},["entities"]={["mirror"]=true,["entity_count"]=3,["mask"]={false,false,false,false,false,false,false,true,true,false,false,true,false,false,false,true,false,false,true,false,false,false,false,true,false,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true,true}},["logits"]={0.29597097635269165,0.5464302897453308,0.4557229280471802,1.0847885608673096,1.076715111732483,1.0948107242584229,0.7823916673660278,1.0750503540039062,0.7762617468833923,0.9737034440040588,0.5522121787071228,0.36700254678726196,0.7470955848693848,0.8136203289031982,0.8540469408035278,0.531348705291748,0.7324318289756775,0.9099802374839783,0.23142006993293762,0.16728879511356354,0.30698686838150024,0.23842495679855347,-0.166950985789299,-0.45488494634628296,-0.0069182198494672775,3.2473978996276855,3.558042287826538,2.903390884399414,3.094677686691284,2.3271474838256836,3.080794334411621,2.6722428798675537,-14.739212036132812,-14.660958290100098,3.2179293632507324,2.5181143283843994,-16.08509635925293,-15.78075122833252,2.938318967819214,2.2513320446014404,-17.910152435302734,-17.98356819152832,2.516188859939575,1.662187933921814,2.737668514251709,2.178632974624634,2.7483577728271484,1.9491603374481201,1.4554715156555176,1.0095411539077759,0.6385032534599304,-0.14603786170482635,0.6739846467971802,0.055183421820402145,-16.71668815612793,-16.031858444213867,-17.610807418823242,-16.7523136138916,0.09307028353214264,-0.29751840233802795,-18.888690948486328,-19.12308692932129,0.2913163900375366,-0.5771316885948181,0.13564249873161316,-0.8219778537750244,-0.7388151288032532,-1.171377420425415,-1.3318372964859009,-1.8496158123016357,-1.8850173950195312,-2.471510171890259,-1.4213347434997559,-2.05587100982666,-18.448408126831055,-18.165428161621094,-1.63840651512146,-2.3230302333831787,-19.301668167114258,-18.655803680419922,-2.134093999862671,-2.7819197177886963,-20.153846740722656,-19.40740203857422,-1.95772123336792,-2.5763049125671387,-2.068382501602173,-3.0166890621185303,-2.3594038486480713,-3.1768457889556885},["action"]=27},{["query"]={-0.03999999910593033,0.17000000178813934,0.02800000086426735,0.104347825050354,-0.30434781312942505,0.0782608687877655,-0.36666667461395264,0.06666667014360428,0.7666666507720947,0.0,0.0,-1.0,0.0,-1.0,1.0,0.0,1.0,0.5555555820465088,1.0,1.0,0.5555555820465088,1.0,1.0,0.5555555820465088,1.0,1.0,0.5555555820465088,1.0,1.0,0.5555555820465088,1.0,1.0,0.5555555820465088,1.0,1.0,0.5555555820465088,1.0,1.0,0.5555555820465088,1.0,1.0,0.5555555820465088,1.0,1.0,0.5555555820465088,1.0,1.0,0.5555555820465088,1.0,1.0,0.5555555820465088,-0.23999999463558197,0.4399999976158142,0.0034000000450760126,-0.6000000238418579,-0.800000011920929,0.0,-0.0,-0.0,1.0,-0.15217390656471252,-0.3913043439388275,0.0,-0.06666667014360428,0.13333334028720856,0.23333333432674408,-0.06666667014360428,-0.13333334028720856,0.23333333432674408,0.09600000083446503,0.32199999690055847,0.02459999918937683,-0.2234782576560974,0.1530434787273407,0.0782608687877655,0.0,1.0,1.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.23999999463558197,-0.30000001192092896,0.0034000000450760126,-0.6000000238418579,-0.800000011920929,0.0,-0.0,-0.0,1.0,-0.15217390656471252,-0.3913043439388275,0.0,-0.06666667014360428,0.13333334028720856,0.23333333432674408,-0.06666667014360428,-0.13333334028720856,0.23333333432674408,-0.20800000429153442,-0.5059999823570251,0.02459999918937683,-0.2234782576560974,0.1530434787273407,0.0782608687877655,0.4699999988079071,1.0,1.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0},["entities"]={["mirror"]=false,["entity_count"]=3,["mask"]={true,true,true,true,true,true,true,true,true,true,true,true,true,true,false,false,true,true,false,false,true,true,false,false,false,false,false,false,false,false,false,false,true,true,false,false,true,true,false,false,true,true,false,false,false,false,false,false,false,false,false,false,false,false,true,true,true,true,false,false,true,true,false,false,false,false,false,false,false,false,false,false,false,false,true,true,false,false,true,true,false,false,true,true,false,false,false,false,false,false}},["logits"]={-15.396682739257812,-11.297772407531738,-12.25236701965332,-5.593748569488525,-9.373778343200684,-1.8797224760055542,-8.366474151611328,-8.774084091186523,-1.6055035591125488,-2.61057186126709,2.8592007160186768,1.4833464622497559,-4.047510147094727,-6.532037734985352,-6.278012275695801,-8.251789093017578,4.2068281173706055,0.958328127861023,1.9486535787582397,-1.2716187238693237,9.53769302368164,5.377333641052246,6.8712873458862305,3.194899082183838,-0.19086550176143646,-6.9856648445129395,-7.175393581390381,-5.009004592895508,-6.221485614776611,-4.312963962554932,-2.9855234622955322,-0.7758875489234924,-19.338199615478516,-17.439207077026367,-1.5499241352081299,0.6389274001121521,-18.63199806213379,-16.926959991455078,-1.0646016597747803,1.4569907188415527,-17.314289093017578,-15.85779094696045,1.4102551937103271,4.0900959968566895,2.5558621883392334,5.259303569793701,2.6611697673797607,5.448369026184082,-8.768138885498047,-6.497905254364014,-6.545124530792236,-3.844667911529541,-3.1422321796417236,-0.8008092641830444,-18.088088989257812,-16.38141632080078,-17.011743545532227,-14.081877708435059,-1.0590835809707642,2.040236711502075,-15.584043502807617,-14.26148509979248,1.1927002668380737,4.003005027770996,3.1872341632843018,5.964290618896484,-8.638533592224121,-6.562497615814209,-6.588585376739502,-4.514937400817871,-5.481610298156738,-3.3528947830200195,-2.6871140003204346,-0.4009213447570801,-17.29346466064453,-15.333334922790527,-1.2587730884552002,1.4552006721496582,-16.603349685668945,-14.291640281677246,-0.11925812810659409,2.538876533508301,-15.111252784729004,-13.319189071655273,1.5691665410995483,4.502838134765625,2.978992462158203,6.338138580322266,3.9095115661621094,7.079095363616943},["action"]=21},{["query"]={-0.03999999910593033,0.17000000178813934,0.02800000086426735,0.104347825050354,-0.30434781312942505,0.0782608687877655,-0.36666667461395264,0.06666667014360428,0.7666666507720947,0.0,0.0,-1.0,0.0,-1.0,1.0,0.0,1.0,0.5555555820465088,1.0,1.0,0.5555555820465088,1.0,1.0,0.5555555820465088,1.0,1.0,0.5555555820465088,1.0,1.0,0.5555555820465088,1.0,1.0,0.5555555820465088,1.0,1.0,0.5555555820465088,1.0,1.0,0.5555555820465088,1.0,1.0,0.5555555820465088,1.0,1.0,0.5555555820465088,1.0,1.0,0.5555555820465088,1.0,1.0,0.5555555820465088,-0.23999999463558197,0.4399999976158142,0.12399999797344208,-0.6000000238418579,-0.800000011920929,0.0,-0.0,-0.0,1.0,-0.15217390656471252,-0.3913043439388275,0.12173912674188614,-0.06666667014360428,0.13333334028720856,0.23333333432674408,-0.06666667014360428,-0.13333334028720856,0.23333333432674408,0.09600000083446503,0.32199999690055847,-0.09600000083446503,-0.2234782576560974,0.1530434787273407,-0.043478261679410934,0.6299999952316284,0.0,0.0,0.0,1.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.23999999463558197,-0.30000001192092896,0.0034000000450760126,-0.6000000238418579,-0.800000011920929,0.0,-0.0,-0.0,1.0,-0.15217390656471252,-0.3913043439388275,0.12173912674188614,-0.06666667014360428,0.13333334028720856,0.23333333432674408,-0.06666667014360428,-0.13333334028720856,0.23333333432674408,-0.20800000429153442,-0.5059999823570251,0.02459999918937683,-0.2234782576560974,0.1530434787273407,-0.043478261679410934,0.4699999988079071,1.0,1.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0,0.0},["entities"]={["mirror"]=false,["entity_count"]=3,["mask"]={false,false,false,false,false,false,false,true,true,false,false,true,false,false,false,true,false,false,true,false,false,false,false,true,false,true,true,true,true,true,true,true,false,false,true,true,false,false,true,true,false,false,true,true,true,true,true,true,true,true,true,true,true,true,false,false,false,false,true,true,false,false,true,true,true,true,true,true,true,true,true,true,true,true,false,false,true,true,false,false,true,true,false,false,true,true,true,true,true,true}},["logits"]={-1.3766218423843384,-1.3193198442459106,-1.7412337064743042,-1.3900290727615356,-1.4211432933807373,-1.08222496509552,-1.2426069974899292,-1.1111164093017578,-1.1467353105545044,-1.097947597503662,-1.3040820360183716,-1.0188663005828857,-1.2491517066955566,-0.9685445427894592,0.023792054504156113,-0.023240625858306885,-1.3997668027877808,-0.9484094381332397,-0.26132437586784363,0.01994495652616024,-1.3570590019226074,-0.8980372548103333,-0.4780541956424713,-0.20007023215293884,-0.020329101011157036,-0.23349295556545258,-1.0789350271224976,-0.0545271560549736,-0.9218944907188416,0.0587933324277401,-1.1855835914611816,-0.3124867081642151,-5.7544474601745605,-5.259127616882324,-0.982638418674469,-0.14887958765029907,-5.971480846405029,-5.270435810089111,-0.9607980847358704,-0.019307898357510567,-4.344217300415039,-3.965989828109741,-1.1864640712738037,-0.24169671535491943,-0.9450298547744751,-0.029225965961813927,-0.8533310294151306,-0.04620695486664772,-1.214228868484497,-0.21889351308345795,-0.8018544912338257,-0.049532532691955566,-1.2188438177108765,-0.39653143286705017,-5.221975803375244,-4.654606342315674,-4.529522895812988,-4.212033748626709,-1.040842056274414,-0.064039446413517,-3.8310904502868652,-3.3572843074798584,-1.1459887027740479,-0.1455458104610443,-0.8611934185028076,-0.02970324456691742,-1.4472711086273193,-0.5394878387451172,-1.3351919651031494,-0.42213016748428345,-1.1811308860778809,-0.34977206587791443,-1.405320644378662,-0.5522270798683167,-4.743769645690918,-4.367840766906738,-1.1417800188064575,-0.3029904067516327,-4.304181098937988,-3.94529390335083,-0.9785968661308289,-0.338297963142395,-3.3515946865081787,-3.1326937675476074,-1.2440558671951294,-0.371310293674469,-1.0690525770187378,-0.3109356462955475,-0.9539833664894104,-0.17430561780929565},["action"]=30}}
        local peak=0
        for caseIndex,case in ipairs(cases)do
            loadingProgress('Checking model outputs',caseIndex-1,#cases)
            local began=os.clock()
            local action,logits
            if worker then
                worker:start(case.query,case.entities,{})
                local completed
                repeat
                    completed=worker:step(.0025)
                    if not completed then loadingYield()end
                until completed
                action,logits=completed.index,completed.logits
                began=os.clock()-completed.cpu
            else action,logits=predict(case.query,case.entities)end
            peak=math.max(peak,os.clock()-began)
            for i,value in ipairs(logits)do
                assert(math.abs(value-case.logits[i])<.0003+math.abs(case.logits[i])*.0001,
                    "Runtime model parity check failed at logit "..i)
            end
            assert(action==case.action,"Runtime model action check failed")
        end
        cases=nil
        if not alive then return end
        if not worker then assert(peak<.2,"Local inference exceeds 200ms: this runtime is too slow")end
        if worker then worker:cancel();worker.wall=nil;worker.last=nil end
        local period=1/15 -- target cadence; missed slots are skipped, never replayed in a burst
        local actions=Policy.actions()
        ready=true;start.Active=true
        label.Text=(MODEL_NAME.." LOCAL v"..ADAPTER_VERSION.." ready | model self-test passed\nModel 0fe5bbe1318632b1934076230fc7426ae07db797e75b46f8d667b633f4e3a16f\nInference CPU peak %.1f ms | target %.1f Hz\nGround assist %s | teammate yield OFF | F6 starts.")
            :format(peak*1000,1/period,physicsEnabled and "ON"or "OFF")..(calibration.baseline and "\nMeasured goal defaults active."or "")
        if worker then label.Text..='\nSmooth scheduling active | game optimization '..(graphics and graphics.enabled and 'ON'or 'OFF')end
        local lastTick,lastUi=os.clock(),-math.huge
        local lastFrame=os.clock()
        local function startJob(packet,hasFlip,now)
            packet.has_jumped=jumpAt~=nil
            local controls=table.clone(previous)
            local metadata={at=now,epoch=epoch,team=packet.team,scene=packet.scene_token,ground=packet.ground_estimate}
            worker:start(function(checkpoint)
                local projected=latency:project(packet,physics,worker.wall,checkpoint)
                metadata.car=projected.car;metadata.ball=projected.ball;metadata.targetAt=now+latency.horizon
                return Policy.observe(projected,controls,hasFlip)
            end,nil,metadata)
        end
        local busy=false
        local rate=0
        connect(game:GetService("RunService").Heartbeat,function(frameDt)
            if not alive or busy then return end
            local now=os.clock()
            local completed
            if worker then
                latency:sample(now,frameDt or now-lastFrame);lastFrame=now
                if enabled and(not focus or input:GetFocusedTextBox()or input:IsKeyDown(Enum.KeyCode.F8)
                    or(activeWindow and not activeWindow()))then stop('LOCAL paused: focus/chat/F8. F6 restarts.')end
                if not enabled or now<armAt then worker:cancel()
                else
                    if held.RMB and lastJumpPress and now-lastJumpPress>.12 then
                        if not pcall(event,'RMB',false)then stop('LOCAL paused: jump release failed');return end
                        held.RMB=nil;previous[6]=0
                    end
                    if lastAppliedAt and now-lastAppliedAt>.25 and held.LMB then
                        if not pcall(event,'LMB',false)then stop('LOCAL paused: boost release failed');return end
                        held.LMB=nil;previous[7]=0
                    end
                    if worker.job and now-worker.job.at>.4 then release()end
                    local ok,result=pcall(worker.step,worker,latency:budget())
                    if not ok then stop('LOCAL inference stopped: '..tostring(result));return end
                    completed=result
                end
            end
            local sampleDue,nextSample=Timing.due(now,sampleAt,(enabled or (calibrating and calibration.crossbar))and 1/HZ or .1)
            if not sampleDue and not completed then return end
            sampleAt=nextSample
            local elapsed=now-lastTick;lastTick=now
            busy=true
            local stage="frame guard"
            local attemptAt=os.clock()
            local success,err=pcall(function()
                if enabled and(elapsed>.3 or not focus or input:GetFocusedTextBox()
                    or input:IsKeyDown(Enum.KeyCode.F8)or(activeWindow and not activeWindow()))then
                    stop("LOCAL paused: focus/chat/F8 or stalled frame. F6 restarts.")
                end
                stage="reading poses"
                local poseAt=os.clock()
                local packet,reason=read()
                if packet then packet.scene_token=scene end
                local poseMs=(os.clock()-poseAt)*1000
                if reason~=lastReadReason then physics:mark(packet and "poses ready"or "waiting",now,reason)end
                lastReadReason=reason
                physics.runtime=runtimeSnapshot(now)
                stage="observing ball physics"
                local observeAt=os.clock()
                physics:observe(packet,now,worker~=nil and not physicsEnabled and not calibrating)
                local observeMs=(os.clock()-observeAt)*1000
                if calibrating then
                    local keys={}
                    for _,name in ipairs({'W','S'})do keys[name]=input:IsKeyDown(Enum.KeyCode[name])end
                    keys.LMB=input:IsMouseButtonPressed(Enum.UserInputType.MouseButton1)
                    calibration:observe(packet,now,keys,physics)
                    refreshCalibration(now)
                end
                if not enabled or now<armAt then return end
                stage="verifying keyboard"
                local keyboardOk,keyboardReason=keyboard:verify()
                assert(keyboardOk,keyboardReason)
                if not packet then
                    release();label.Text="LOCAL waiting: "..tostring(reason);return
                end
                if pendingJump then
                    stage="waiting for jump direction keys"
                    local matched,key=keyboard:matches(pendingJump.keys)
                    assert(now-pendingJump.at<.15,"Jump direction did not reach Roblox: "..tostring(key))
                    if not matched then return end
                    local request=pendingJump
                    stage="pressing deferred RMB"
                    local inputAt=os.clock()
                    if not pressOwned("RMB",request.epoch)then return end
                    assert(os.clock()-inputAt<.2,"Executor input calls exceeded 200ms")
                    recordJump(request,os.clock());pendingJump=nil
                    previous=table.clone(previous);previous[6]=1
                    -- Give the game a frame to consume the rising jump edge.
                    return
                end
                stage="kickoff"
                local override,recovery=kickoff:step(packet,now,pg)
                local decisionPeriod=override and 1/30 or period
                if previousPeriod~=decisionPeriod then decisionAt=nil;previousPeriod=decisionPeriod end
                local due,nextDecision,late=Timing.due(now,decisionAt,decisionPeriod)
                if worker and not override then
                    if completed then due=true;nextDecision=decisionAt
                    elseif worker.job then return end
                end
                if not due then return end
                decisionAt=nextDecision
                local decisionEpoch=epoch
                local began=os.clock()
                local ground=packet.ground_estimate
                if ground and(not lastGround or previous[6]==0)then jumpAt=nil;usedFlip=false end
                lastGround=ground
                local hasFlip=ground or(not usedFlip and(not jumpAt or now-jumpAt<PROFILE.physics.DOUBLEJUMP_MAX_DELAY))
                local action=override
                if worker and action then worker:cancel();completed=nil end
                local modelMs,planningMs,entityCount,safetyMs=0,0,0,0
                local modelRan=false
                physics.plan=nil
                if not action then
                    stage="recovery"
                    action,recovery=arenaAdapter:recovery(packet,previous,now)
                    local needsPolicy
                    if not action and physicsEnabled then
                        stage="ground interception"
                        local planningAt=os.clock()
                        action,recovery,needsPolicy=intercept:step(packet,nil,now)
                        planningMs=(os.clock()-planningAt)*1000
                    end
                    if not action then
                        stage="model observation"
                        if worker then
                            if completed and latency:fresh(completed,packet,now,epoch)then
                                modelMs=completed.cpu*1000;modelRan=true
                                entityCount=completed.context.entity_count or 0
                                -- Remove actions that became unavailable while the model yielded.
                                local mask=Policy.mask(ground,packet.boost,hasFlip,packet.turtled)
                                local index,value=nil,-math.huge
                                for i,v in ipairs(completed.logits)do if mask[i]and v>value then index,value=i,v end end
                                action=Policy.action(assert(index),completed.context)
                            else
                                if not worker.job then startJob(packet,hasFlip,now)end
                                if now-lastUi>.25 then
                                    lastUi=now
                                    label.Text=(MODEL_NAME..' v'..ADAPTER_VERSION..' | %.0f FPS | computing across frames\nPing %s | lead %.0f ms | AI slice %.2f ms\nGame optimization %s | F8 stop')
                                        :format(1/latency.frame,latency.ping and('%.0f ms'):format(latency.ping*1000)or '?',
                                            latency.horizon*1000,worker.last_slice_ms or 0,graphics and graphics.enabled and 'ON'or 'OFF')
                                end
                                return
                            end
                        else
                            packet.has_jumped=jumpAt~=nil
                            local query,entities=Policy.observe(packet,previous,hasFlip)
                            entityCount=entities.entity_count or #entities
                            stage="model inference"
                            local modelAt=os.clock()
                            local index=predict(query,entities)
                            modelMs=(os.clock()-modelAt)*1000;modelRan=true
                            action=Policy.action and Policy.action(index,entities)or actions[index]
                        end
                        if needsPolicy then
                            stage="ground interception"
                            local planningAt=os.clock()
                            local assisted,mode=intercept:step(packet,action,now)
                            planningMs=planningMs+(os.clock()-planningAt)*1000
                            if assisted then action,recovery=assisted,mode end
                        end
                    end
                end
                local proposed=table.clone(action)
                safety.last=nil
                if modelRan and safetyEnabled then
                    stage='ground goal safety'
                    local safetyAt=os.clock()
                    local guarded,mode=safety:step(packet,action,now)
                    safetyMs=(os.clock()-safetyAt)*1000
                    if guarded then action,recovery=guarded,mode end
                end
                stage="mapping inputs"
                local wanted,actual=Policy.keys(action,ground)
                local inferenceMs=(os.clock()-began)*1000
                assert(inferenceMs<200,"Local inference exceeded 200ms")
                -- Recheck before pressing: executor calls and prediction can yield.
                if epoch~=decisionEpoch or not enabled or not alive or not focus or input:GetFocusedTextBox()
                    or input:IsKeyDown(Enum.KeyCode.F8)or(activeWindow and not activeWindow())then
                    stop("LOCAL stopped before applying inputs");return
                end
                local inputAt=os.clock()
                stage="releasing inputs"
                for _,key in ipairs(order)do
                    if held[key]and not wanted[key]then event(key,false);held[key]=nil end
                end
                for _,key in ipairs(order)do
                    if key~="RMB"and wanted[key]and not held[key]then
                        stage="pressing "..key
                        if not pressOwned(key,decisionEpoch)then return end
                        assert(os.clock()-inputAt<.2,"Executor input calls exceeded 200ms")
                    end
                end
                if wanted.RMB and not held.RMB then
                    local request={keys=wanted,action=table.clone(action),actual=table.clone(actual),
                        ground=ground,at=os.clock(),epoch=decisionEpoch}
                    stage="checking jump direction keys"
                    if keyboard:matches(wanted)then
                        stage="pressing RMB"
                        if not pressOwned("RMB",decisionEpoch)then return end
                        recordJump(request,os.clock())
                    else pendingJump=request end
                end
                actual[6]=held.RMB and 1 or 0
                local inputMs=(os.clock()-inputAt)*1000
                if worker then latency.input=latency.input*.8+math.min(inputMs/1000,.08)*.2 end
                stage="input timing"
                assert(inputMs<200,"Executor input calls exceeded 200ms")
                physics.decision={time=now,mode=recovery or "model",milliseconds=inferenceMs,
                    input_milliseconds=inputMs,action=table.clone(actual),model_milliseconds=modelMs,
                    planning_milliseconds=planningMs,model_ran=modelRan,entity_count=entityCount,
                    proposed_action=proposed,goal_safety=safety.last,goal_safety_milliseconds=safetyMs}
                timing:record({time=now,model_ran=modelRan,entities=entityCount,pose_ms=poseMs,observe_ms=observeMs,
                    model_ms=modelMs,planning_ms=planningMs,safety_ms=safetyMs,decision_ms=inferenceMs,input_ms=inputMs,schedule_late_ms=late*1000})
                previous=actual;rate=timing.rate
                lastAppliedAt=now
                if now-lastUi>=.2 then
                    stage="panel update"
                    lastUi=now
                    local names={};for _,key in ipairs(order)do if held[key]then names[#names+1]=key end end
                    label.Text=(MODEL_NAME.." v"..ADAPTER_VERSION.." | %.1f Hz | %s\nDecision %.1f ms | inputs %.1f ms | %s\n%s %s | want %s | seen %s\nOpponents %d | teammates %d | unknown %d\nPads %d/%d -> %d | car %s%s\nBall %.2f%s | contacts %d | F8 stop\nPhysics %s | g %.0f | flight error %s")
                        :format(rate,keyboard.name,inferenceMs,inputMs,recovery or "model",manualTeam==nil and "AUTO"or "MANUAL",TEAM==0 and "BLUE"or "ORANGE",table.concat(names," "),keyboard:observed(),
                            packet.opponents or 0,packet.teammates or 0,packet.unknown_cars or 0,
                            packet.boost_known or 0,packet.boost_total or 0,#(packet.boost_pads or {}),
                            packet.car_preset or "standard",packet.car_size_verified and ""or "?",
                            packet.ball_radius or PROFILE.physics.BALL_RADIUS,packet.ball_size_verified and ""or "?",packet.wheel_contacts or 0,
                            physics.mismatch and "MISMATCH / model"or physics.status,physics.gravity,
                            physics.error and("%.1f units"):format(physics.error)or "unmeasured")
                    if worker then
                        label.Text..=('\n%.0f FPS | ping %s | AI %.2f ms slice / %.0f ms age')
                            :format(1/latency.frame,latency.ping and('%.0f ms'):format(latency.ping*1000)or '?',
                                worker.last_slice_ms or 0,completed and(now-completed.metadata.at)*1000 or 0)
                    end
                end
            end)
            busy=false
            -- Keep the first stopped-run error. A broken pose source can also
            -- fail while paused; never overwrite the useful report every frame.
            if not success and(enabled or not physics.lastError)then
                local beforeStop=runtimeSnapshot(os.clock())
                physics.lastError={time=now,stage=stage,reason=tostring(err),
                    frame_seconds=elapsed,attempt_milliseconds=(os.clock()-attemptAt)*1000}
                stop("LOCAL stopped at "..stage..": "..tostring(err))
                if type(writefile)=="function"then
                    local saved=pcall(saveReport,"TurboBall_Last_Error.json",beforeStop)
                    if saved then label.Text=label.Text.."\nSaved TurboBall_Last_Error.json"end
                end
            end
        end)
    end)
    if not ok and alive then stop("LOCAL startup stopped: "..tostring(errorText))end
end)
return {started=true,version="local-"..ADAPTER_VERSION}
