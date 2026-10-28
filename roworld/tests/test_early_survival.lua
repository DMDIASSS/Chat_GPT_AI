local Strategy=require('../strategy')
local fixture=require('./fixture')
local n=0;local function test(name,fn) fn();n+=1;print('PASS',name) end
local function world()
 local f=fixture();f.info.tiles=1000;f.state.owners[2].kind=0;f.state.owners[2].tiles=1000;f.set(393,2)
 return f,Strategy.new(f)
end
local function army() return {home=50000,reserve=17500,available=32500,incoming=0,outgoing={},targets={}} end
test('one-second country gain no longer completes a corridor objective',function()
 local f,s=world();s:sent({intent={type='attack',tile=393,ratio=.2}},f.state,1,f.now)
 f.set(393,1);f.info.tiles=1250;f.state.owners[2].tiles=600;f.now+=1;s:observe(f)
 assert(s.campaigns[2].objective.status=='active')
 f.now+=8;s:observe(f);assert(s.campaigns[2].objective.status=='complete')
end)
test('unrelated own expansion does not complete a country corridor',function()
 local f,s=world();s:sent({intent={type='attack',tile=393,ratio=.2}},f.state,1,f.now)
 f.set(393,1);f.info.tiles=1400;f.now+=10;s:observe(f)
 assert(s.campaigns[2].objective.status=='active')
end)
test('cheap local clearance may finish without pretending there is a gold reward',function()
 local f,s=world();f.state.owners[2].tiles=100;f.state.owners[2].gold=0
 s.core.fronts[2]={};s.core.summary={needs_buffer=true}
 local q=s:conquest(f,2,army());assert(q.finish and q.expected_conquest_gold==0 and q.finish_reason:find('corridor'))
end)
test('affordable live corridor becomes elimination without resetting spending',function()
 local f,s=world();f.state.owners[2].tiles=100;f.state.owners[2].gold=100000
 s:sent({intent={type='attack',tile=393,ratio=.1}},f.state,1,f.now)
 local budget,spent=s.campaigns[2].budget,s.campaigns[2].spent
 local a=army();a.targets[2]=5000;s:updateBoard(f,{[2]={}},a)
 assert(s.campaigns[2].objective.kind=='eliminate_country' and s.campaigns[2].budget==budget and s.campaigns[2].spent==spent)
end)
test('dominant treaty ally creates a bounded reserve and historical warning without hostility',function()
 local f,s=world();f.state.owners[2].kind=2;f.state.owners[2].troops=120000;f.state.allied[1026]=true
 local a=army();local b=s:updateBoard(f,{},a,{}, {[2]=true})
 assert(#b.ally_warnings==1 and a.reserve==30000 and not b.recover and b.human_neighbours==0)
 assert(#s.allyWarningHistory==1 and f.state:are_allies(1,2))
 s:updateBoard(f,{},army(),{}, {[2]=true});assert(#s.allyWarningHistory==1)
end)
test('same-team and balanced allies do not cause treaty dominance warnings',function()
 local f,s=world();f.state.owners[2].kind=2;f.state.owners[2].troops=120000;f.state.allied[1026]=true
 f.info.team=1;f.state.owners[2].team=1
 assert(#s:updateBoard(f,{},army(),{}, {[2]=true}).ally_warnings==0)
 f.info.team=0;f.state.owners[2].team=0;f.state.owners[2].troops=50000
 assert(#s:updateBoard(f,{},army(),{}, {[2]=true}).ally_warnings==0)
end)
print('EARLY SURVIVAL TESTS',n)
