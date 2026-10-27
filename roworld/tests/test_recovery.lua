local Policy=require('../policy')
local Strategy=require('../strategy')
local Mirror=require('../mirror')
local vectors=require('./wire_vectors')
local Wire=require('../wire')
local fixture=require('./fixture')
local n=0
local function test(name,fn) fn();n+=1;print('PASS',name) end
local function bytes(hex) local b=buffer.create(#hex/2);for i=1,#hex,2 do buffer.writeu8(b,(i-1)/2,tonumber(hex:sub(i,i+1),16)) end;return b end
local function world()
 local data=Wire.snapshot(bytes(vectors.snapshot));local raw=buffer.create(768);buffer.fill(raw,0,128)
 local map=Mirror.map({width=32,height=24,k_lin=2},raw,data)
 return Mirror.snapshot(data,map,1),map
end
test('confirmed partner betrayal quarantines proposals and triggers recovery near that partner',function()
 local s,map=world();s.alliances[1026]=true
 local f={state=s,map=map,me=1,info=s.owners[1],now=10};local st=Strategy.new(f)
 st.adjacentAllies={[2]=true};st.peace[2]=100
 Mirror.delta(s,{t=11,ev={{18,1,2,2,false},{22,2,311}}});st:observe(f)
 assert(st.relationships[1].confirmed_betrayal and not st:trustworthy(f,2))
 assert(st.peace[2]==nil and st.recoverUntil>f.now)
 st:observe(f);assert(#st.relationships==1)
end)
test('expiry is not mislabeled as betrayal even if a traitor flag exists',function()
 local s,map=world();s.alliances[1026]=true;s.owners[2].traitor_until=1000
 local f={state=s,map=map,me=1,info=s.owners[1],now=10};local st=Strategy.new(f)
 Mirror.delta(s,{t=11,ev={{18,1,2,0,true}}});st:observe(f)
 assert(st.relationships[1].reason=='expired' and not st.relationships[1].confirmed_betrayal)
 assert(st:trustworthy(f,2))
end)
test('repeat alliance requests back off without blocking incoming acceptance',function()
 local f=fixture();local st=Strategy.new(f)
 st:sent({intent={type='ally_request',target=2}},f.state,1,f.now)
 f.now+=50;assert(not st:canAsk(f,2) and st:trustworthy(f,2))
 f.now+=80;assert(st:canAsk(f,2))
end)
test('unexplained alliance loss on the native route is not asserted as confirmed betrayal',function()
 local f=fixture();f.state.allied[1026]=true;local st=Strategy.new(f)
 f.state.allied={};st:observe(f)
 assert(not st.relationships[1].confirmed_betrayal and st:trustworthy(f,2))
end)
test('factory placement prefers a nearby usable city connection and rejects fallout links',function()
 local f,p=fixture(),Policy.new();for t=0,f.map.N-1 do f.set(t,1) end
 f.state.structures[3]={owner=1,kind=0,tile=12*32+5,level=1}
 assert(p:incomeLink(f,12*32+15,'factory')>0)
 f.state.flags[12*32+10]=true
 assert(p:incomeLink(f,12*32+15,'factory')==0)
end)
test('stranded guard mode can transition to a capped relocation instead of permanent idle',function()
 local f=fixture();local st=Strategy.new(f)
 st.core.summary={center_tile=389,clearable_tiles=0,friendly_fraction=.05,at_risk=true,incoming=0,threat_pressure=0,naval_incoming=0}
 local function army() return {home=50000,reserve=17500,available=32500,incoming=0,outgoing={},targets={}} end
 assert(not st:updateBoard(f,{},army()).escape)
 f.now+=21;local a=army();local b=st:updateBoard(f,{},a)
 assert(b.escape and b.mode=='relocate' and a.reserve>=37500)
end)
test('escape state never overrides an actual incoming land invasion',function()
 local f=fixture();local st=Strategy.new(f);st.strandedSince=0
 st.core.summary={center_tile=389,clearable_tiles=0,friendly_fraction=.05,at_risk=true,incoming=10000,naval_incoming=0,threat_pressure=0}
 local a={home=50000,reserve=17500,available=32500,incoming=10000,outgoing={},targets={}}
 assert(not st:updateBoard(f,{},a).escape)
end)
test('relocation sends only a small neutral expedition and remembers its expansion anchor',function()
 local f,p=fixture(),Policy.new();for y=0,23 do f.map.water[y*32+20]=true end;f.refresh();p:reset(f)
 p.strategy.board={mode='relocate',escape=true};p.strategy.core.summary={at_risk=true,needs_buffer=false}
 local a={home=50000,reserve=37500,available=12500,incoming=0,enemyActive=0,targets={}}
 local order=assert(p:naval(f,a));assert(order.escape and order.intent.ratio<=.1 and f.state:tile_owner(order.intent.tile)==0)
 p:sent(order,f.now);assert(p.strategy.core.relocation.tile==order.intent.tile)
end)
print('RECOVERY TESTS',n)
