local Policy=require('../policy')
local Strategy=require('../strategy')
local fixture=require('./fixture')
local n=0;local function test(name,fn) fn();n+=1;print('PASS',name) end
local function setup()
 local f,p=fixture(),Policy.new();f.info.tiles=1000;f.info.max_troops=50000
 f.state.owners[2].kind=0;f.state.owners[2].tiles=100;f.state.owners[2].gold=150000
 f.state.owners[2].max_troops=10000;f.set(393,2);f.refresh();p:reset(f);p:observe(f)
 return f,p,{home=50000,reserve=17500,available=32500,incoming=0,outgoing={},targets={},enemyActive=0}
end
test('weak wealthy country has a finish objective while a powerful one does not',function()
 local f,p,a=setup();local q=p.strategy:conquest(f,2,a);assert(q.finish and q.expected_conquest_gold==150000)
 f.state.owners[2].troops=50000;assert(not p.strategy:conquest(f,2,a).finish)
 f.state.owners[2].kind=2;assert(not p.strategy:conquest(f,2,a))
end)
test('useful production and levels improve target value and defense reduces it',function()
 local f,p,a=setup();local base=p.strategy:conquest(f,2,a)
 f.state.structures[9]={sid=9,owner=2,kind=2,tile=393,level=3}
 local rich=p.strategy:conquest(f,2,a);assert(rich.score>base.score and rich.buildings==1)
 f.state.structures[10]={owner=2,kind=3,tile=394,level=10}
 assert(p.strategy:conquest(f,2,a).score<rich.score)
end)
test('conquest chooses a decisive affordable allocation and avoids duplicate reinforcement',function()
 local f,p,a=setup();local g={id=2,tile=393,front=5,tiles={393}}
 local plan=assert(p:enemyPlan(f,g,a,{[2]=g}));assert(plan.conquest.finish and plan.amount<=a.home*.4)
 a.targets[2]=20000;assert(not p:enemyPlan(f,g,a,{[2]=g}))
end)
test('country finish continues after taking the target building rather than recalling',function()
 local f,p,a=setup();f.state.structures[9]={sid=9,owner=2,kind=2,tile=393,level=1}
 local q=p.strategy:conquest(f,2,a)
 p.strategy:sent({intent={type='attack',tile=393,ratio=.08},plan={conquest=q,objective_sid=9}},f.state,1,f.now)
 f.state.structures[9].owner=1;f.set(393,1);f.info.tiles+=150;f.now+=10;p.strategy:observe(f)
 a.targets[2]=3000;a.outgoing={{aid=7,target=2,troops=3000,anchor_tile=393}}
 assert(p.strategy.campaigns[2].objective.kind=='eliminate_country')
 assert(p.strategy.campaigns[2].objective.status=='active' and not p.strategy:review(f,a))
end)
test('actual home invasion interrupts a finish even after some assets were captured',function()
 local f,p,a=setup();local q=p.strategy:conquest(f,2,a)
 p.strategy:sent({intent={type='attack',tile=393,ratio=.1},plan={conquest=q}},f.state,1,f.now)
 a.incoming=50000;a.outgoing={{aid=7,target=2,troops=1000,anchor_tile=393}}
 assert(p.strategy:review(f,a).intent.type=='retreat')
end)
test('a wealthy remnant beats an otherwise identical poor country in utility',function()
 local f,p,a=setup();local g={id=2,tile=393,front=2,tiles={393}}
 local plan={amount=1000,score=0};f.state.owners[2].gold=1000
 local poor=p.strategy:utility(f,g,plan,a);f.state.owners[2].gold=1000000
 assert(p.strategy:utility(f,g,plan,a)>poor)
end)
test('elimination is recorded only after the observed owner is no longer alive',function()
 local f,p,a=setup();p.strategy:sent({intent={type='attack',tile=393,ratio=.1},plan={conquest=p.strategy:conquest(f,2,a)}},f.state,1,f.now)
 f.state.owners[2].alive=false;p.strategy:observe(f)
 assert(not p.strategy.campaigns[2] and #p.strategy.campaignHistory==1)
end)
test('missile alerts identify nearby asset danger and record it only once',function()
 local f,p,a=setup();local Weapons=require('../weapons')
 local tile=f.info.label_tile;f.state.structures[8]={owner=1,kind=0,tile=tile,level=1}
 f.state.nukes[9]={owner=2,kind=0,to_tile=tile,launch_tick=1,flight_ticks=100}
 local rows=Weapons.alerts(f.state,1);assert(#rows==1 and rows[1].own_assets==1 and rows[1].eta_seconds==10)
 f.state.tick+=2;p:observe(f);f.state.tick+=2;p:observe(f)
 assert(#p.missileHistory==1 and #p:report().missile_alerts==1)
end)
test('unrelated distant launches do not become local attack warnings',function()
 local f,p,a=setup();local Weapons=require('../weapons')
 f.state.nukes[9]={owner=2,kind=0,to_tile=23*32+31,launch_tick=1,flight_ticks=100}
 assert(#Weapons.alerts(f.state,1)==0)
end)
print('CONQUEST TESTS',n)
