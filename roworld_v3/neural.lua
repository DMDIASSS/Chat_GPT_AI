-- Small residual actor-critic. Same equations as training/model.py; no runtime Python.
local Neural={}
local Schema=require('./schema')
local function finite(n) return type(n)=='number' and n==n and math.abs(n)<1e6 end
local shapes={context={Schema.hidden,Schema.context},action={Schema.hidden,Schema.action},
    fusion={Schema.hidden,Schema.hidden},score={1,Schema.hidden},value={1,Schema.hidden}}
function Neural.validate(weights)
    if type(weights)~='table' or weights.schema~=Schema.version or weights.version~=1 then return nil,'Model schema mismatch' end
    for name,shape in pairs(shapes) do
        local layer=weights[name]
        if type(layer)~='table' or type(layer.w)~='table' or type(layer.b)~='table' or #layer.w~=shape[1] or #layer.b~=shape[1] then return nil,'Bad layer '..name end
        for i=1,shape[1] do
            if type(layer.w[i])~='table' or #layer.w[i]~=shape[2] or not finite(layer.b[i]) then return nil,'Bad shape '..name end
            for _,v in ipairs(layer.w[i]) do if not finite(v) then return nil,'Non-finite model' end end
        end
    end
    return weights
end
local function linear(layer,x,relu)
    local y={}
    for i,row in ipairs(layer.w) do
        local n=layer.b[i]
        for j,w in ipairs(row) do n+=w*x[j] end
        y[i]=relu and math.max(0,n) or n
    end
    return y
end
function Neural.score(weights,context,candidates)
    local logits={}
    if not weights then for i,a in ipairs(candidates) do logits[i]=a.bias or 0 end;return logits,0 end
    local state=linear(weights.context,context,true)
    local fused=linear(weights.fusion,state,true)
    for i,a in ipairs(candidates) do
        local token=linear(weights.action,a.features,true)
        local dot=0;for j,v in ipairs(token) do dot+=v*fused[j] end
        local residual=dot/math.sqrt(Schema.hidden)+linear(weights.score,token,false)[1]
        logits[i]=(a.bias or 0)+residual
    end
    return logits,linear(weights.value,fused,false)[1]
end
function Neural.pick(logits,uniform)
    local best=1;for i=2,#logits do if logits[i]>logits[best] then best=i end end
    local z=0;local probs={}
    for i,v in ipairs(logits) do probs[i]=math.exp(math.clamp(v-logits[best],-80,0));z+=probs[i] end
    for i,v in ipairs(probs) do probs[i]=v/z end
    if uniform then
        local sum=0
        for i,p in ipairs(probs) do sum+=p;if uniform<=sum then return i,probs end end
    end
    return best,probs
end
return Neural
