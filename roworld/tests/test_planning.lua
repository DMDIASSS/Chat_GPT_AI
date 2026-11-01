local Atlas=require('../atlas')
local Planner=require('../planner')
local Profiles=require('../profiles')
local Investment=require('../investment')
local Policy=require('../policy')
local Strategy=require('../strategy')
local Diplomacy=require('../diplomacy')
local fixture=require('./fixture')
local n=0
local function test(name,fn) fn();n+=1;print('PASS',name) end
local function army() return {home=50000,reserve=35000,available=15000,incoming=0,outgoing={},targets={},enemyActive=0,neutralActive=0} end
local function scan(f,a,budget)
 for i=1,500 do a:update(f,budget);f.state.tick+=1;f.now+=.1;if a.summary.ready then return end end
 error('atlas did not complete')
end
local function board() return {core={at_risk=true,incoming=0},recover=false,leaders={},committed=0,overextended=false} end

test('atlas finds disconnected holdings and identifies the valuable economic component',function()
 local f=fixture();for t=0,f.map.N-1 do f.set(t,0) end
 for _,t in ipairs({33,34,65,66,500,501}) do f.set(t,1) end
 f.state.structures[9]={owner=1,kind=0,tile=500,level=8}
 local a=Atlas.new();scan(f,a,17)
 assert(a.summary.component_count==2 and a.summary.own_land==6)
 assert(a:component(f,500).id==a.summary.main_component and a:component(f,33).land==4)
end)
test('atlas snapshot is coherent while live ownership changes and stale lookups are refused',function()
 local f=fixture();local a=Atlas.new();a:update(f,1);f.set(0,1)
 scan(f,a,31);assert(a.summary.own_land==63 and not a:component(f,0))
 f.now=a.summary.snapshot_at+31;assert(not a:component(f,f.info.label_tile))
end)
test('atlas records public foreign adjacency without inventing a connection across a row edge',function()
 local f=fixture();for t=0,f.map.N-1 do f.set(t,0) end
 f.set(31,2);f.set(32,3);local a=Atlas.new();scan(f,a)
 assert(#a.summary.relations==0)
 f.now+=6;f.set(30,3);a.summary.ready=false;scan(f,a)
 assert(#a.summary.relations==2)
end)
test('short incremental budgets do not require a whole-map decision and report stays bounded',function()
 local f=fixture();local a=Atlas.new();a:update(f,4);assert(not a.summary.ready and a.work.scan<=4)
 scan(f,a,50);assert(a:report(f.now).age_seconds>=0 and #a.summary.components<=32)
end)
test('planner reassesses a stale quiet guard without releasing its defensive bank',function()
 local f=fixture();local p=Planner.new();local b=board();local a=army()
 p:update(f,b,a,{},Atlas.new());assert(not b.permit_expansion)
 f.now+=40;p:update(f,b,a,{[0]={}},Atlas.new())
 assert(b.permit_expansion and b.expansion_budget<=6000 and a.reserve==35000)
 assert(p.report.waiting_cost>0 and p.report.objective=='expand')
end)
test('fresh invasion suppresses the waiting-cost expansion exception',function()
 local f=fixture();local p=Planner.new();local b=board();local a=army()
 p:update(f,b,a,{});f.now+=120;a.incoming=30000;b.recover=true
 p:update(f,b,a,{[0]={}});assert(not b.permit_expansion and p.report.objective=='defend')
end)
test('planner ranks actual feasible actions and reports the selected alternative',function()
 local f=fixture();local p=Planner.new();p:update(f,board(),army(),{})
 local choices={{intent={type='build',kind='factory'},investment={score=30},label='Factory'},
  {intent={type='ally_reply'},label='Respond'}}
 assert(p:choose(f,choices).label=='Respond' and #p.report.actions==2)
end)
test('investment compares marginal growth and viable production rather than fixed purchase order',function()
 local f,p=fixture(),Policy.new();for t=0,f.map.N-1 do f.set(t,1) end;f.info.gold=2000000
 f.state.structures[1]={owner=1,kind=0,tile=389,level=12}
 local city=Investment.evaluate(p,f,'city',{tile=389,upgrade=true},{[0]=1},{[0]=12})
 local factory=Investment.evaluate(p,f,'factory',{tile=399,upgrade=false},{[0]=1},{[0]=12})
 assert(factory.score>city.score and factory.return_is_proxy)
 assert(not city.estimated_payback_seconds)
end)
test('exposed or detached economic sites score below otherwise identical safe sites',function()
 local f,p=fixture(),Policy.new();p.atlas={siteRisk=function() return 0 end}
 local good=Investment.evaluate(p,f,'city',{tile=389},{},{})
 p.atlas.siteRisk=function() return 1 end
 local bad=Investment.evaluate(p,f,'city',{tile=389},{},{})
 assert(good.score>bad.score)
end)
test('level-heavy cities raise production targets even when city count is small',function()
 local f,p=fixture(),Policy.new();for t=0,f.map.N-1 do f.set(t,1) end;f.info.gold=10000000
 f.state.structures[1]={owner=1,kind=0,tile=389,level=12}
 f.state.structures[2]={owner=1,kind=2,tile=399,level=1}
 f.info.troops=95000
 local a=assert(p:economy(f,{389,399,405},army()))
 assert(a.intent.kind=='factory' and #p.economyPlan.candidates>1)
end)
test('campaign capture has a named objective and recalls after that exact objective is secured',function()
 local f=fixture();f.set(393,2);f.state.owners[2].kind=0
 f.state.structures[9]={sid=9,owner=2,kind=1,tile=393,level=1}
 local s=Strategy.new(f)
 s:sent({intent={type='attack',tile=393,ratio=.1},plan={objective_sid=9}},f.state,1,f.now)
 assert(s.campaigns[2].objective.kind=='capture_asset')
 f.state.structures[9].owner=1;f.now+=2;s:observe(f)
 f.now+=9;s:observe(f)
 local a=army();a.outgoing={{aid=2,target=2,troops=4000,anchor_tile=393}}
 assert(s:review(f,a).label:find('objective secured'))
end)
test('another player taking enemy land does not reset our stalled campaign timer',function()
 local f=fixture();f.set(393,2);f.state.owners[2].tiles=100;local s=Strategy.new(f)
 s:sent({intent={type='attack',tile=393,ratio=.1}},f.state,1,f.now)
 local at=s.campaigns[2].lastProgress;f.now+=12;f.state.owners[2].tiles=50;s:observe(f)
 assert(s.campaigns[2].lastProgress==at)
end)
test('campaign time and total budget limit reinforcement without changing legal order reserves',function()
 local f=fixture();f.set(393,2);local s=Strategy.new(f)
 s:sent({intent={type='attack',tile=393,ratio=.3}},f.state,1,f.now);f.now+=46
 local a=army();a.targets[2]=5000;assert(not s:canTarget(f,2,a))
 a.outgoing={{aid=2,target=2,troops=5000,anchor_tile=393}}
 assert(s:review(f,a).label:find('budget or time'))
end)
test('profiles retain confirmed betrayal after quarantine and serialize to bounded plain data',function()
 local f,p=fixture(),Policy.new();f.state.owners[2].kind=2;p:reset(f)
 p.strategy:allianceEnded(f,2,true,'partner broke alliance');f.now+=181
 assert(p.strategy:trustworthy(f,2))
 local assessment=p.profiles:assessment(f,2);assert(assessment.betrayal_penalty>=5)
 local d=Diplomacy.evaluate(p,f,2,army(),{[2]={}},'accept')
 assert(not d.eligible)
 local restored=Profiles.new(p.profiles:export());assert(restored:assessment(f,2).betrayal_penalty>0)
end)
test('profile identity does not follow reused nation IDs into a new named player',function()
 local f=fixture();f.state.owners[2].kind=2;local p=Profiles.new();p:start(f);p:betrayed(f,2)
 f.state.owners[2].name='Different player';p:start(f)
 assert(p:assessment(f,2).betrayal_penalty==0)
end)
test('profiles count observed attacks once and restore only validated numeric evidence',function()
 local f=fixture();f.state.owners[2].kind=2
 local p=Profiles.new({version=1,records={{name='Enemy',attacks=0/0,betrayals=-5},{name='Other',attacks='code'}}})
 p:start(f);f.state.attacks[5]={attacker=2,target=1,troops=1000};p:observe(f);p:observe(f)
 local a=p:assessment(f,2);assert(a.observed_attacks==1 and a.betrayal_penalty==0 and a.attack_fraction>0)
end)
test('limited maritime expansion leaves reserves intact and does not recall immediately for static guard',function()
 local f,p=fixture(),Policy.new();for y=0,23 do f.map.water[y*32+20]=true end;f.refresh();p:reset(f)
 p.strategy.board={mode='guard',permit_expansion=true}
 p.strategy.core.summary={at_risk=true,needs_buffer=true}
 local a=army();local order=assert(p:naval(f,a));assert(order.intent.ratio<=.12)
 assert(order.reserve>=a.reserve)
end)
test('an affordable initial campaign allocation is not immediately recalled as over budget',function()
 local f=fixture();f.set(393,2);f.state.owners[2].kind=1;local s=Strategy.new(f)
 s:sent({intent={type='attack',tile=393,ratio=.55}},f.state,1,f.now)
 assert(s.campaigns[2].budget>s.campaigns[2].spent)
 local a=army();a.outgoing={{aid=9,target=2,anchor_tile=393,troops=20000}}
 assert(not s:review(f,a))
end)
test('a tribe campaign does not stop after taking only its first border tiles',function()
 local f=fixture();f.set(393,2);f.state.owners[2].kind=1;local s=Strategy.new(f)
 s:sent({intent={type='attack',tile=393,ratio=.1}},f.state,1,f.now)
 f.set(393,1);f.info.tiles+=150;f.now+=4;s:observe(f)
 assert(s.campaigns[2].objective.kind=='defeat_tribe' and s.campaigns[2].objective.status=='active')
end)
test('bounded profile storage can remember new opponents after reaching its limit',function()
 local p=Profiles.new()
 for i=1,140 do p:record({kind=2,name='Player '..i}) end
 assert(#p:export().records==128 and p.records['Player 140'] and not p.records['Player 1'])
end)
test('quiet static core risk does not prevent saving for an affordable future SAM',function()
 local f,p=fixture(),Policy.new();for t=0,f.map.N-1 do f.set(t,1) end;p:reset(f)
 f.info.gold=1000000;p.strategy.core.summary={at_risk=true}
 for i=1,3 do f.state.structures[i]={owner=1,kind=i==3 and 2 or 0,tile=100+i,level=1} end
 f.state.structures[4]={owner=2,kind=5,tile=10,level=1,shots={},active_tick=0}
 function f.ctx.rules:cost(kind) return kind=='sam' and 1500000 or 125000 end
 p:economy(f,{f.info.label_tile},army());assert(p.economyPlan.saving_for=='sam')
end)
test('confirmed in-match betrayal survives restarting the policy in the same match',function()
 local f=fixture();f.state.owners[2].kind=2;local profiles=Profiles.new()
 local p=Policy.new(profiles);p:reset(f);p.strategy:allianceEnded(f,2,true,'partner broke alliance')
 local restarted=Policy.new(profiles);restarted:reset(f)
 assert(restarted.profiles:assessment(f,2).betrayal_penalty>=5)
end)
print('PLANNING TESTS',n)
