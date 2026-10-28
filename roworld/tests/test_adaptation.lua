local Policy=require('../policy')
local Strategy=require('../strategy')
local Recorder=require('../recorder')
local fixture=require('./fixture')
local n=0
local function test(name,fn) fn();n+=1;print('PASS',name) end
local function army() return {home=50000,reserve=17500,available=32500,incoming=0,outgoing={},enemyActive=0,neutralActive=0,targets={}} end

test('emergency build cannot bypass the three-post limit including posts under construction',function()
 local f,p=fixture(),Policy.new();for t=0,f.map.N-1 do f.set(t,1) end;f.info.gold=1000000
 for i=1,3 do f.state.structures[i]={owner=1,kind=3,tile=100+i,active_tick=9999} end
 assert(not p:build(f,{f.info.label_tile},'defense',{}))
end)
test('lost posts cannot trigger an endless replacement spending loop',function()
 local f,p=fixture(),Policy.new();for t=0,f.map.N-1 do f.set(t,1) end;p:reset(f);f.info.gold=1000000
 local order={intent={type='build',kind='defense'},channel='build',cooldown=6,label='Defense'}
 for i=1,3 do p:sent(order,f.now);f.now+=7 end
 assert(not p:build(f,{f.info.label_tile},'defense',{}))
 f.now+=61;assert(p:build(f,{f.info.label_tile},'defense',{}))
end)
test('destroyed-core regression relocates despite residual clearable tiles and allied territory',function()
 local f=fixture();local st=Strategy.new(f);f.info.tiles=30000
 st.core.summary={center_tile=389,clearable_tiles=146,friendly_fraction=.38,owned_fraction=.98,protected_building_count=4,incoming=0}
 st:updateBoard(f,{},army());f.now+=10;f.info.tiles=203
 st.core.summary.owned_fraction=.011;st.core.summary.protected_building_count=0
 st:updateBoard(f,{},army());f.now+=21;st:updateBoard(f,{},army());f.now+=21
 assert(st:updateBoard(f,{},army()).escape and st.board.relocation_reason)
end)
test('ongoing productive recovery does not trigger relocation just for a low core fraction',function()
 local f=fixture();local st=Strategy.new(f)
 st.core.summary={center_tile=389,clearable_tiles=146,friendly_fraction=.38,owned_fraction=.011,protected_building_count=0,incoming=0}
 for i=1,8 do f.info.tiles=200+i*50;f.now+=10;assert(not st:updateBoard(f,{},army()).escape) end
end)
test('new growth after a major defeat resets the relocation stall clock',function()
 local f=fixture();local st=Strategy.new(f);f.info.tiles=30000
 st.core.summary={center_tile=389,clearable_tiles=100,friendly_fraction=.4,owned_fraction=.01,protected_building_count=0,incoming=0}
 st:updateBoard(f,{},army());f.info.tiles=203;f.now+=10;st:updateBoard(f,{},army())
 for i=1,6 do f.info.tiles+=60;f.now+=10;assert(not st:updateBoard(f,{},army()).escape) end
end)
test('a low enemy bank alone no longer starts a distant human landing',function()
 local f,p=fixture(),Policy.new();p:reset(f);f.state.owners[2].kind=2
 local tile=12*32+19;f.set(tile,2);f.map.water[tile+1]=true;f.refresh()
 p.landSample=function() return tile end
 p.strategy.board={mode='develop'};p.strategy.core.summary={at_risk=false,needs_buffer=false}
 assert(not p:naval(f,army()))
 f.state.structures[4]={owner=2,kind=0,tile=tile,level=1}
 f.state.attacks[9]={attacker=3,target=2,troops=800}
 assert(p:naval(f,army()).intent.type=='boat')
end)
test('no second expedition launches while another transport is still at sea',function()
 local f,p=fixture(),Policy.new();p:reset(f);f.ctx.rules.transportCount=1
 assert(not p:naval(f,army()))
end)
test('escape destination avoids a dominant human center and tolerates an allied center',function()
 local f,p=fixture(),Policy.new();local tile=12*32+19
 f.state.owners[2].kind=2;f.state.owners[2].label_tile=tile;f.state.owners[2].troops=500000
 assert(p:landingScore(f,tile,army(),true)==nil)
 f.state.allied[1026]=true;assert(p:landingScore(f,tile,army(),true)~=nil)
end)
test('uncovered productive core saves for SAM rather than buying another cheaper city',function()
 local f,p=fixture(),Policy.new();for t=0,f.map.N-1 do f.set(t,1) end;p:reset(f)
 f.info.gold=1000000
 for i=1,3 do f.state.structures[i]={owner=1,kind=0,tile=100+i,level=1} end
 f.state.structures[3].kind=2
 f.state.structures[4]={owner=2,kind=5,tile=10,level=1,shots={},active_tick=0}
 function f.ctx.rules:cost(kind) return kind=='sam' and 1500000 or 125000 end
 assert(not p:economy(f,{f.info.label_tile},army()))
 assert(p.economyPlan.saving_for=='sam' and p.economyPlan.reserve==1500000)
end)
test('recorder distinguishes initial snapshot from later observed construction and attacks',function()
 local f=fixture();f.state.owners[2].kind=2;f.state.owners[2].tiles=100
 f.state.structures[1]={owner=2,kind=0,tile=20,level=1}
 f.state.attacks[1]={attacker=2,target=1,troops=500}
 local r=Recorder.new(f);r:observe(f);assert(#r.events==0)
 f.state.tick+=10;f.state.structures[1].level=2;f.state.attacks[2]={attacker=2,target=1,troops=300}
 r:observe(f);assert(#r.events==2 and r.players[2].observed_attacks==1)
 r:observe(f);assert(#r.events==2)
end)
test('recorder retains early game plus recent history within fixed limits',function()
 local f=fixture();local r=Recorder.new(f)
 for i=1,250 do
  f.state.tick=i*100;r:observe(f);r:event({tick=i,type='test'});r:event({tick=i,type='test'})
 end
 local report=r:report()
 assert(#report.samples==180 and #report.events==256 and report.samples_dropped==70)
 assert(report.samples[1].tick==100 and report.samples[60].tick==6000 and report.samples[180].tick==25000)
 assert(report.events_dropped==244 and report.scope:find('Not training labels'))
end)
print('ADAPTATION TESTS',n)
