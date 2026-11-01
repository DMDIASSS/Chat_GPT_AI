local Agent=require('../agent')
local Adapter=require('../shared/adapter')
local fixture=require('./fixture')
local n=0;local function test(name,fn) fn();n+=1;print('PASS',name) end
local function world()
 local f=fixture();f.set(393,2);f.refresh()
 local p=f.state.owners[2];p.kind=0;p.tiles=8;p.gold=600000;p.troops=100;p.max_troops=1000
 return f
end
local function finish(f)
 local p=Agent.new();p:prepare(f)
 for _,a in ipairs(p.candidates) do if (a.plan or {}).country_finish then return a,p end end
 return nil,p
end
test('weak wealthy country completion outranks neutral expansion and preserves home reserves',function()
 local f=world();local a,p=finish(f);assert(a and a.plan.country_finish.expected_treasury==600000)
 assert(a.plan.amount>=8*25*4 and f.info.troops-a.plan.amount>=f.info.troops*.55)
 assert(p:decide(f)==nil) -- prepare already consumed this authoritative tick.
 local chosen=assert(Agent.new():decide(f));assert(chosen.plan.country_finish)
end)
test('remaining land receives a top-up even when the old defender-bank estimate was already funded',function()
 local f=world();f.state.attacks[4]={attacker=1,target=2,troops=2000}
 assert(finish(f))
 f.state.attacks[4].troops=30000;assert(not finish(f))
end)
test('strong large empty or human nations receive no country-treasury finishing priority',function()
 for _,key in ipairs({'strong','large','empty','human'}) do
  local f=world();local p=f.state.owners[2]
  if key=='strong' then p.troops=100000 elseif key=='large' then p.tiles=10000
  elseif key=='empty' then p.gold=0 else p.kind=2 end
  assert(not finish(f))
 end
end)
test('invasion and allied country completion are excluded',function()
 local f=world();f.state.attacks[4]={attacker=2,target=1,troops=20000};assert(not finish(f))
 f=world();f.state.allied[1026]=true;assert(not finish(f))
end)
test('campaign budget is retained instead of resetting it for a promised treasury',function()
 local f=world();local a,p=finish(f);assert(a);p:sent(a,f.now)
 local c=p.campaigns[2];c.spent=c.budget
 f.now+=2;f.state.tick+=20;p:prepare(f)
 for _,x in ipairs(p.candidates) do assert(not (x.plan or {}).country_finish) end
end)
test('finishing order is cancelled when the target treasury vanishes before dispatch',function()
 local f=world();local a=assert(finish(f));f.state.owners[2].gold=0
 local sender=Adapter.new({},nil,function() return f.now end);sender.main=f.main
 assert(not sender:send(a,f) and #f.session.sent==0)
end)
print('V3 COUNTRY FINISH SCENARIOS',n)
