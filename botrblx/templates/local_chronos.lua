-- Chronos V2.1: full float32 weights, double accumulation, no runtime HTTP.
-- COMMON_ADAPTER_HERE
local PADS=
-- CHRONOS_PADS_HERE
local MIRROR_PADS=
-- CHRONOS_MIRROR_PADS_HERE
local ACTIONS=Policy.actions()
local max,sqrt,abs=math.max,math.sqrt,math.abs

local function dense(layer,x)
    local w,b,width,rows=layer.w,layer.b,layer.width,layer.rows
    local out=table.create(rows)
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
    end
    for r=last+1,rows do
        local value=b[r]
        for c=1,width do value=value+w[base+c]*x[c]end
        out[r]=value;base=base+width
    end
    return out
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

function Policy.new(tensors)
    local layers={}
    local function layer(prefix,width,rows,norm)
        local l={w=assert(tensors[prefix..'.weight']),b=assert(tensors[prefix..'.bias']),width=width,rows=rows}
        assert(#l.w==width*rows and #l.b==rows,'Chronos tensor shape mismatch')
        if norm then
            l.nw=assert(tensors[norm..'.weight']);l.nb=assert(tensors[norm..'.bias'])
            assert(#l.nw==rows and #l.nb==rows,'Chronos normalization shape mismatch')
        end
        layers[#layers+1]=l
    end
    layer('shared.0',225,960,'shared.1')
    layer('shared.3',960,960,'shared.4')
    layer('policy.0',960,960,'policy.1')
    layer('policy.3',960,800,'policy.4')
    layer('policy.6',800,640,'policy.7')
    layer('policy.9',640,640,'policy.10')
    layer('policy.12',640,90)
    return function(obs,context)
        assert(#obs==225 and #context.mask==90,'Expected Chronos observation/action mask')
        local x=obs
        for _,l in ipairs(layers)do
            x=dense(l,x)
            if l.nw then normalizeRelu(x,l.nw,l.nb)end
        end
        local best,peak=nil,-math.huge
        for i,v in ipairs(x)do
            assert(v==v and abs(v)<math.huge,'Non-finite Chronos output')
            if context.mask[i]and v>peak then best,peak=i,v end
        end
        assert(best,'Chronos action mask is empty')
        return best,x
    end
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
