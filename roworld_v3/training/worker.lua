-- This worker is embedded with the user's private original simulator, not distributed game code.
local function json(v)
    local t=type(v)
    if t=='nil' then return 'null' elseif t=='boolean' then return v and 'true' or 'false'
    elseif t=='number' then assert(v==v and math.abs(v)<math.huge);return string.format('%.12g',v)
    elseif t=='string' then return '"'..v:gsub('[%z\1-\31\\"]',function(c)
        return c=='\\' and '\\\\' or c=='"' and '\\"' or string.format('\\u%04x',string.byte(c)) end)..'"'
    elseif t=='table' then
        local parts={}
        if #v>0 then for _,x in ipairs(v) do table.insert(parts,json(x)) end;return '['..table.concat(parts,',')..']' end
        for k,x in pairs(v) do table.insert(parts,json(tostring(k))..':'..json(x)) end
        table.sort(parts);return '{'..table.concat(parts,',')..'}'
    end
    error('Unsupported JSON value '..t)
end
local Sim,WorldMap=load('Core/Sim'),load('Core/WorldMap')
local width,height=96,72
local raw=buffer.create(width*height)
for y=0,height-1 do for x=0,width-1 do
    local water=x<2 or y<2 or x>width-3 or y>height-3
    if config.stage>=2 then water=water or (x>=45 and x<=49 and (config.seed%2==0 or y<height-8)) end
    local elevation=(x*11+y*7+config.seed)%37==0 and 3 or 0
    buffer.writeu8(raw,y*width+x,water and 0 or 128+elevation)
end end
local nations={}
if config.stage>=1 then
    for i,p in ipairs({{16,15},{80,55},{80,15},{16,55}}) do table.insert(nations,{name='Country '..i,tile=p[2]*width+p[1]}) end
end
local meta={id='roworld-training-'..config.stage,width=width,height=height,k_lin=4,terrain=raw,nations=nations}
local nativeMap=WorldMap.from_terrain(meta)
local selfplay=config.stage>=3
local sim=Sim.new(nativeMap,{seed=config.seed,difficulty=config.stage>=2 and 1 or 0,tribes=config.stage==0 and 8 or 12,
    max_humans=selfplay and 2 or 1,solo_countdown_ticks=1,spawn_ticks=10})
local me=sim:add_human('agent','Agent')
local ownTile=36*width+(config.seed%2==0 and 26 or 69)
assert(sim:human_start(me,ownTile))
local opponent
if selfplay then opponent=sim:add_human('opponent','Opponent');assert(sim:human_start(opponent,36*width+(config.seed%2==0 and 69 or 26))) end
for _=1,12 do sim:step() end
-- Begin on a decision boundary so a time-limit bootstrap follows a full interval,
-- rather than using a fraction-of-a-second outcome with a one-second discount.
while sim.tick%Schema.decision_ticks~=0 do sim:step() end
local snapshot=sim:snapshot();local map=Mirror.map(meta,raw,snapshot)
local s=Mirror.snapshot(snapshot,map,me)
local session={state=s,connected=true}
function session:send_intent(intent) sim:submit(me,intent) end
local ctx=Mirror.context(session);local agent=Agent.new(nil,weights);agent.seed=config.seed+17
agent.stochastic=config.stochastic
local other=opponent and Agent.new(nil,opponentWeights)
if other then other.seed=config.seed+37 end
local otherState,otherCtx,otherSession
if opponent then
    otherState=Mirror.snapshot(sim:snapshot(),map,opponent);otherSession={state=otherState,connected=true}
    function otherSession:send_intent(intent) sim:submit(opponent,intent) end
    otherCtx=Mirror.context(otherSession)
end
local currentFrame
local adapter=Adapter.new({},nil,function() return s.tick/10 end)
function adapter:frame() return currentFrame end
local rows={};local lastRow;local orders=0;local rejected=0;local timings={}
local function potential()
    local p=s.owners[me];local leader=0
    for id,o in pairs(s.owners) do if id~=me and o.alive then leader=math.max(leader,o.tiles or 0) end end
    return 2*math.log(1+(p.tiles or 0))+.2*math.log(1+(p.income or 0))+.1*math.log(1+(p.troops or 0))
        +.5*(p.tiles or 0)/math.max(1,(p.tiles or 0)+leader)
end
local function terminal()
    return not s.owners[me].alive or sim.phase==2
end
local function won()
    return sim.winner==me or (sim.winner_team or 0)>0 and s.owners[me].team==sim.winner_team
end
local oldPhi=potential()
local function finalize(row,done)
    local phi=done and 0 or potential()
    local reward=.997*phi-oldPhi
    if done then reward+=won() and 10 or -10 end
    row.reward=reward;row.done=done;oldPhi=phi
end
for step=1,config.seconds*10 do
    if sim.tick%Schema.decision_ticks==0 and not terminal() then
        if lastRow then finalize(lastRow,false) end
        local info=s.owners[me]
        currentFrame={state=s,map=map,me=me,info=info,ctx=ctx,session=session,now=s.tick/10}
        local began=os.clock();local action=agent:decide(currentFrame);table.insert(timings,(os.clock()-began)*1000)
        local obs,candidates=agent.observation,agent.candidates
        local row={context=obs.context,candidates={},priors={},choice=agent.selected,logp=math.log(agent.probabilities[agent.selected]),
            value=agent.value,land=info.tiles,tick=s.tick}
        for _,a in ipairs(candidates) do table.insert(row.candidates,a.features);table.insert(row.priors,a.bias or 0) end
        table.insert(rows,row);lastRow=row
        if action then
            local sent,reason=adapter:send(action,currentFrame)
            if sent then agent:sent(action,currentFrame.now);orders+=1 else agent:rejected(reason);rejected+=1 end
        end
        if other and otherState.owners[opponent].alive then
            local f={state=otherState,map=map,me=opponent,info=otherState.owners[opponent],ctx=otherCtx,session=otherSession,now=sim.tick/10}
            local a=other:decide(f)
            if a then
                local otherAdapter=Adapter.new({},nil,function() return f.now end)
                function otherAdapter:frame() return f end
                local ok=otherAdapter:send(a,f);if ok then other:sent(a,f.now) end
            end
        end
    end
    local delta=sim:step();Mirror.delta(s,delta);if otherState then Mirror.delta(otherState,delta) end
    if terminal() then break end
end
local done=terminal();if lastRow then finalize(lastRow,done) end
local bootstrap=0
if not done then
    local f={state=s,map=map,me=me,info=s.owners[me],ctx=ctx,session=session,now=s.tick/10}
    local _,_,_,v=agent:prepare(f);bootstrap=v
end
local p=s.owners[me];local builds=0
for _,b in pairs(s.structures) do if b.owner==me then builds+=1 end end
table.sort(timings)
print('ROWORLD_EPISODE '..json({version=1,schema=Schema.version,seed=config.seed,stage=config.stage,rows=rows,
    bootstrap=bootstrap,terminated=done,truncated=not done,win=done and won(),alive=p.alive,
    land=p.tiles,home=p.troops,gold=p.gold,buildings=builds,orders=orders,rejected=rejected,tick=s.tick,
    decision_median_ms=timings[math.max(1,math.ceil(#timings*.5))] or 0,decision_p95_ms=timings[math.max(1,math.ceil(#timings*.95))] or 0,
    opponents=selfplay and 'frozen policy plus built-in countries/tribes' or 'built-in countries/tribes',
    scope='Synthetic RoWorld original-engine curriculum; not a multiplayer replay or human win-rate measurement'}))
