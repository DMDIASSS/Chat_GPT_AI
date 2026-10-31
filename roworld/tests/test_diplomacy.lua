local D=require('../diplomacy')
local Policy=require('../policy')
local Adapter=require('../adapter')
local Mirror=require('../mirror')
local Wire=require('../wire')
local vectors=require('./wire_vectors')
local fixture=require('./fixture')
local n=0
local function test(name,fn) fn();n+=1;print('PASS',name) end
local function army(f) return {home=f.info.troops,incoming=0,outgoing={},targets={},enemyActive=0,strongest=0} end
local function score(f,kind,mode)
 f.state.owners[2].kind=kind
 return D.evaluate(Policy.new(),f,2,army(f),{[2]={}},mode or 'accept')
end
local function bytes(hex) local b=buffer.create(#hex/2);for i=1,#hex,2 do buffer.writeu8(b,(i-1)/2,tonumber(hex:sub(i,i+1),16)) end;return b end
local function mirror()
 local data=Wire.snapshot(bytes(vectors.snapshot));local raw=buffer.create(768);buffer.fill(raw,0,128)
 local m=Mirror.map({width=32,height=24,k_lin=2},raw,data);return Mirror.snapshot(data,m,1)
end
test('humans receive preference while weak countries remain expansion candidates',function()
 local f=fixture();assert(score(f,2).eligible);assert(not score(f,0).eligible)
end)
test('shared active threats can make a balanced country alliance worthwhile',function()
 local f=fixture();f.state.owners[2].troops=40000
 local before=score(f,0).score
 f.state.attacks[1]={attacker=3,target=1,troops=10000};f.state.attacks[2]={attacker=2,target=3,troops=10000}
 local after=score(f,0);assert(after.eligible and after.score>before and after.shared_enemy)
end)
test('a dominant bordering country is not accepted just because it is strong',function()
 local f=fixture();f.state.owners[2].troops=300000
 assert(not score(f,0).eligible)
end)
test('early country grace lowers priority without promising immunity',function()
 local f=fixture();f.state.owners[2].troops=40000;f.state.playing_since=0;f.state.tick=100
 local early=score(f,0).score;f.state.tick=2000
 assert(score(f,0).score>early)
end)
test('fast expansion and concentrated warships lower otherwise comparable scores',function()
 local f,p=fixture(),Policy.new();p:reset(f);p.strategy:updateCore(f);f.state.owners[2].kind=2;f.state.owners[2].troops=100000
 local a=army(f);local base=D.evaluate(p,f,2,a,{[2]={}},'accept').score
 p.opponents[2]={landTrend=100};f.state.units={[8]={kind=2,owner=2,path={f.info.spawn_tile},start_tick=1},[9]={kind=2,owner=2,path={f.info.spawn_tile},start_tick=1}}
 assert(D.evaluate(p,f,2,a,{[2]={}},'accept').score<base)
end)
test('renewal state tracks window, two parties, completion and expiry',function()
 local s=mirror();Mirror.delta(s,{t=11,ev={{17,1,2,300}}})
 assert(s:alliance_info(1,2).can_extend)
 Mirror.delta(s,{t=12,ev={{30,1,2,300,1}}});assert(not s:alliance_info(1,2).can_extend and s:alliance_info(2,1).can_extend)
 Mirror.delta(s,{t=13,ev={{30,1,2,3013,0}}});assert(not s:alliance_info(1,2).in_window)
 Mirror.delta(s,{t=14,ev={{18,1,2,0,true}}});assert(not s:alliance_info(1,2))
end)
test('policy renews a useful human alliance but leaves an unhelpful weak country to expire',function()
 for _,kind in ipairs({0,2}) do
  local f,p=fixture(),Policy.new();f.state.allied[1026]=true;f.state.owners[2].kind=kind
  function f.state:alliance_info(_,id) return id==2 and {can_extend=true} or nil end
  p.adjacentAllies={[2]=true}
  local action=p:diplomacy(f,{},army(f))
  if kind==2 then assert(action.intent.type=='ally_extend') else assert(not action) end
 end
end)
test('renewal is rechecked at send time after its window closes',function()
 local f=fixture();f.state.allied[1026]=true
 function f.state:alliance_info() return {can_extend=false} end
 local a=Adapter.new({},function() error('reuse') end,function() return f.now end);a.main=f.main
 assert(not a:send({intent={type='ally_extend',target=2}},assert(a:frame())))
end)
test('spawn can move during countdown but never after the match has started',function()
 local f=fixture();f.state.phase=0
 local a=Adapter.new({},function() error('reuse') end,function() return f.now end);a.main=f.main
 assert(a:send({intent={type='spawn',tile=0}},assert(a:frame())))
 f.now+=1;f.state.phase=1
 assert(not a:send({intent={type='spawn',tile=0}},assert(a:frame())))
end)
test('a newly crowded countdown spawn is reconsidered for a substantially safer location',function()
 local f,p=fixture(),Policy.new();f.state.phase=0;f.state.owners[2].kind=2;f.state.owners[2].spawn_tile=f.info.spawn_tile+1
 local action=assert(p:decide(f));assert(action.intent.type=='spawn' and action.intent.tile~=f.info.spawn_tile)
end)
test('survival boat spending is narrowly limited to neutral destinations under overwhelming attack',function()
 local f=fixture();for y=0,23 do f.map.water[y*32+20]=true end;f.refresh()
 local a=Adapter.new({},function() error('reuse') end,function() return f.now end);a.main=f.main
 f.state.attacks[1]={attacker=2,target=1,troops=100000}
 local order={intent={type='boat',tile=12*32+19,ratio=.1},survival=true}
 assert(a:send(order,assert(a:frame())) and f.session.sent[1].ratio<=.1)
 f.now+=1;f.state.attacks={};assert(not a:send(order,assert(a:frame())))
end)
test('overwhelming attack triggers emergency decisions before routine industry',function()
 local f,p=fixture(),Policy.new();f.info.gold=200000
 f.state.attacks[9]={attacker=2,target=1,troops=100000};f.state.owners[2].kind=1
 local action=p:decide(f)
 assert(not action or action.intent.type~='build' or action.intent.kind=='defense')
 assert(p:report().strategy.emergency)
end)
test('last-resort peace can outweigh ordinary aggression when already being overrun',function()
 local f,p=fixture(),Policy.new();f.state.owners[2].kind=0;f.state.owners[2].troops=300000
 f.state.attacks[1]={attacker=2,target=1,troops=200000};p.opponents[2]={heat=3}
 local a=army(f);a.incoming=200000
 assert(D.evaluate(p,f,2,a,{[2]={}},'offer').eligible)
end)
print('DIPLOMACY AND EMERGENCY TESTS',n)
