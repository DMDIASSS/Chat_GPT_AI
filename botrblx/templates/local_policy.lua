-- Float32 model storage, double-precision accumulation. No HTTP or file IO.
local Policy={}
local sqrt,exp,max=math.sqrt,math.exp,math.max

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

local function dense(layer,x,relu,first,rows)
    local w,b=layer.w,layer.b
    local width=layer.width
    local out=table.create(rows or layer.rows)
    local base=((first or 1)-1)*width
    for r=1,rows or layer.rows do
        local value=b[(first or 1)+r-1]
        -- The exported widths are all multiples of four.
        for c=1,width,4 do
            value=value+w[base+c]*x[c]+w[base+c+1]*x[c+1]
                +w[base+c+2]*x[c+2]+w[base+c+3]*x[c+3]
        end
        out[r]=relu and max(0,value)or value
        base=base+width
    end
    return out
end

local function norm(x,layer)
    local mean=0
    for i=1,128 do mean=mean+x[i]end
    mean=mean/128
    local variance=0
    for i=1,128 do local d=x[i]-mean;variance=variance+d*d end
    local scale=1/sqrt(variance/128+1e-5)
    local out=table.create(128)
    for i=1,128 do out[i]=(x[i]-mean)*scale*layer.w[i]+layer.b[i]end
    return out
end

function Policy.new(tensors)
    local function layer(prefix,width,rows)
        return {w=assert(tensors[prefix..".weight"]),b=assert(tensors[prefix..".bias"]),width=width,rows=rows}
    end
    local q0=layer("net.earl.query_preprocess.0",32,128)
    local q1=layer("net.earl.query_preprocess.2",128,128)
    local k0=layer("net.earl.key_value_preprocess.0",24,128)
    local k1=layer("net.earl.key_value_preprocess.2",128,128)
    local blocks={}
    for i=0,1 do
        local prefix="net.earl.blocks."..i
        blocks[i+1]={
            projection={w=assert(tensors[prefix..".attention.in_proj_weight"]),
                b=assert(tensors[prefix..".attention.in_proj_bias"]),width=128,rows=384},
            output=layer(prefix..".attention.out_proj",128,128),
            linear1=layer(prefix..".linear1",128,512),linear2=layer(prefix..".linear2",512,128),
            norm1=layer(prefix..".norm1",128,128),norm2=layer(prefix..".norm2",128,128),
            norm3=layer(prefix..".norm3",128,128)}
    end
    local output=layer("net.output.emb_convertor",128,32)
    local actions=assert(tensors.action_embeddings)
    return function(query,entities)
        -- Unknown pads remain omitted. Verified live pads use the existing
        -- boost entity fields; no new/untrained feature slots are introduced.
        assert(#query==32 and #entities>=2 and #entities<=36,"Expected query/self/ball/known pads")
        local x=dense(q1,dense(q0,query,true),true)
        local kv={}
        local count=#entities
        for i=1,count do kv[i]=dense(k1,dense(k0,entities[i],true),true)end
        for _,block in ipairs(blocks)do
            local q=dense(block.projection,norm(x,block.norm1),false,1,128)
            local keys,values={},{}
            for i=1,count do
                local normalized=norm(kv[i],block.norm2)
                keys[i]=dense(block.projection,normalized,false,129,128)
                values[i]=dense(block.projection,normalized,false,257,128)
            end
            local attended=table.create(128)
            for head=0,3 do
                local first=head*32+1
                local scores,peak={},-math.huge
                for i=1,count do
                    local score=0
                    for j=first,first+31 do score=score+q[j]*keys[i][j]end
                    score=score/sqrt(32);scores[i]=score;peak=max(peak,score)
                end
                local total=0
                for i=1,count do scores[i]=exp(scores[i]-peak);total=total+scores[i]end
                for j=first,first+31 do
                    local value=0
                    for i=1,count do value=value+scores[i]/total*values[i][j]end
                    attended[j]=value
                end
            end
            local attention=dense(block.output,attended,false)
            for i=1,128 do x[i]=x[i]+attention[i]end
            local feed=dense(block.linear2,dense(block.linear1,norm(x,block.norm3),true),false)
            for i=1,128 do x[i]=x[i]+feed[i]end
        end
        for i=1,128 do x[i]=max(0,x[i])end
        local embedding=dense(output,x,false)
        local logits=table.create(90)
        local best,bestValue=1,-math.huge
        for a=1,90 do
            local value=0;local base=(a-1)*32
            for j=1,32 do value=value+actions[base+j]*embedding[j]end
            assert(value==value and math.abs(value)<math.huge,"Non-finite policy output")
            logits[a]=value
            if value>bestValue then best,bestValue=a,value end
        end
        return best,logits
    end
end

function Policy.observe(packet,previous,hasFlip)
    local car,ball=packet.car,packet.ball
    local kv={table.create(24,0),table.create(24,0)}
    kv[1][1]=1;kv[1][packet.team==0 and 2 or 3]=1;kv[2][4]=1
    for row,body in ipairs({car,ball})do
        for i=1,3 do
            kv[row][5+i]=body.position[i];kv[row][8+i]=body.velocity[i]
            kv[row][17+i]=body.angular_velocity[i]
        end
    end
    for i=1,3 do kv[1][11+i]=car.forward[i];kv[1][14+i]=car.up[i]end
    kv[1][21]=packet.boost/100;kv[1][23]=packet.ground_estimate and 1 or 0
    kv[1][24]=hasFlip and 1 or 0
    for i,pad in ipairs(packet.boost_pads or {})do
        assert(i<=34 and type(pad.active)=="boolean"and type(pad.is_big)=="boolean","Unverified pad")
        local row=table.create(24,0);row[5]=1
        for j=1,3 do row[5+j]=pad.position[j]end
        row[21]=pad.is_big and 1 or .12
        row[22]=pad.active and 1 or 0 -- Matches update271's original Nexto builder.
        kv[#kv+1]=row
    end
    for _,row in ipairs(kv)do
        if packet.team==1 then
            for i=6,20,3 do row[i]=-row[i];row[i+1]=-row[i+1]end
            row[2],row[3]=row[3],row[2]
        end
        for i=6,11 do row[i]=row[i]/2300 end
        for i=18,20 do row[i]=row[i]/5.5 end
    end
    local query=table.clone(kv[1])
    for i=1,8 do query[24+i]=previous[i]end
    local theta=math.atan2(query[12],query[13])
    local ct,st=math.cos(theta),math.sin(theta)
    for _,row in ipairs(kv)do
        for i=6,8 do row[i]=row[i]-query[i]end
        for i=6,20,3 do local x,y=row[i],row[i+1];row[i]=ct*x-st*y;row[i+1]=st*x+ct*y end
    end
    return query,kv
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
    local t=ground and action[1]or -action[3]
    local s=ground and action[2]or action[4]
    local keys={}
    if t>.5 then keys.W=true elseif t<-.5 then keys.S=true end
    if s>.5 then keys.D=true elseif s<-.5 then keys.A=true end
    if action[5]>.5 then keys.E=true elseif action[5]<-.5 then keys.Q=true end
    if action[6]~=0 then keys.RMB=true end
    if action[7]~=0 then keys.LMB=true end
    if action[8]~=0 and ground then keys.SHIFT=true end
    t=(keys.W and 1 or 0)-(keys.S and 1 or 0)
    s=(keys.D and 1 or 0)-(keys.A and 1 or 0)
    local r=(keys.E and 1 or 0)-(keys.Q and 1 or 0)
    local y=(r~=0 or not keys.SHIFT)and s or 0
    if r==0 and keys.SHIFT then r=s end
    return keys,{t,s,-t,y,r,keys.RMB and 1 or 0,keys.LMB and 1 or 0,keys.SHIFT and 1 or 0}
end
return Policy
