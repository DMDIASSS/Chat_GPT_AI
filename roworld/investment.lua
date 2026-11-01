-- Marginal benefit and exposure estimates. Production returns are proxies, not guaranteed cashflows.
local Investment={}
local function growth(h,cap) return math.max(0,(h^.73/4+10)*(1-h/math.max(1,cap))*10) end
function Investment.evaluate(policy,frame,kind,place,counts,levels)
 local cost=frame.ctx.rules:cost(kind);local info=frame.info;local cap=math.max(1,info.max_troops or 1)
 local risk=policy.riskCache and policy.riskCache[place.tile]
 if risk==nil then
  risk=policy.atlas and policy.atlas:siteRisk(frame,place.tile) or 0
  if policy.riskCache then policy.riskCache[place.tile]=risk end
 end
 local benefit,reason,proxy=0,'',nil
 if kind=='city' then
  local delta=growth(info.troops or 0,cap+250000)-growth(info.troops or 0,cap)
  benefit=4+math.min(12,delta/50)+((counts[0] or 0)==0 and 12 or 0)
  if (counts[2] or 0)==0 and (counts[0] or 0)>0 then benefit-=7 end
  reason='250K marginal capacity and growth at the current bank'
 elseif kind=='factory' then
  local link=policy:incomeLink(frame,place.tile,kind)
  benefit=link>0 and 15+math.min(6,link/5) or 2
  if (counts[2] or 0)==0 and (counts[0] or 0)>0 and link>0 then benefit+=10 end
  if (levels[0] or 0)>math.max(1,levels[2] or 0)*3 then benefit+=5 end
  proxy=link>0 and 2500 or nil;reason='Observed potential land-production link; actual routing is not guaranteed'
 elseif kind=='port' then
  local partners=0
  for _,b in pairs(frame.state.structures) do
   if b.kind==1 and b.owner~=frame.me and b.owner>0 and frame.state:are_allies(frame.me,b.owner)
    and type(frame.map.coast_body_of)=='function' and frame.map:coast_body_of(place.tile)>0
    and frame.map:coast_body_of(place.tile)==frame.map:coast_body_of(b.tile) then partners+=1 end
  end
  benefit=8+math.min(12,partners*3)+((counts[1] or 0)==0 and 8 or 0)
  proxy=partners>0 and 1000*math.min(4,partners) or nil;reason='Coastal access and visible allied trade partners'
 elseif kind=='sam' then benefit=35;reason='Coverage of exposed productive assets'
 elseif kind=='defense' then benefit=16;reason='Cover an observed threatened core'
 elseif kind=='silo' then benefit=5;reason='Future counterstrike option after production investment'
 end
 local priceFactor=125000/math.max(125000,cost)
 local score=benefit*priceFactor*(1-risk*.75)
 if kind=='sam' then score=40*(1-risk*.5) end
 if place.upgrade and kind=='city' then
  local level=1
  for _,b in pairs(frame.state.structures) do if b.owner==frame.me and b.kind==0 and b.tile==place.tile then level=b.level or 1 end end
  score/=1+(level-1)*.12
  reason..='; concentrated city levels increase asset-loss exposure'
 end
 return {kind=kind,cost=cost,score=score,risk=risk,upgrade=place.upgrade==true,
  estimated_payback_seconds=proxy and cost/proxy or nil,return_is_proxy=true,reason=reason}
end
return Investment
