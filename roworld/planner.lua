-- Compare strategic alternatives; scores are transparent heuristics, not simulated futures.
local Planner={};Planner.__index=Planner
function Planner.new() return setmetatable({history={}},Planner) end
function Planner:update(frame,b,a,groups,atlas,profiles)
 local land=frame.info.tiles or 0
 if not self.checkpoint or land>self.checkpoint*1.03+10 then self.checkpoint=land;self.progressAt=frame.now end
 if land<(self.checkpoint or land)*.8 then self.checkpoint=land;self.progressAt=frame.now end
 local stalled=math.max(0,frame.now-(self.progressAt or frame.now))
 local core=b.core or {};local incoming=math.max(a.incoming or 0,core.incoming or 0)
 local acute=b.recover or core.critical or incoming>a.home*.15
 local opportunity=groups[0]~=nil
 for id,g in pairs(groups) do
  local o=frame.state.owners[id]
  if id>0 and o and (o.kind==1 or o.kind==0) and (o.troops or 0)<a.available*.4 then opportunity=true end
 end
 local rivalGrowth=0
 for _,row in ipairs(b.leaders or {}) do
  local o=frame.state.owners[row.nation]
  if o and not frame.state:are_allies(frame.me,row.nation) then
   local old=(self.leaders or {})[row.nation]
   if old and frame.now-old.at>=10 then rivalGrowth=math.max(rivalGrowth,(row.land-old.land)/math.max(1,old.land)) end
  end
 end
 if not self.leaderAt or frame.now-self.leaderAt>=30 then
  self.leaders={};for _,row in ipairs(b.leaders or {}) do self.leaders[row.nation]={land=row.land,at=frame.now} end
  self.leaderAt=frame.now
 end
 local waitingCost=math.min(10,stalled/15)+math.min(5,math.max(0,rivalGrowth)*10)
 b.permit_expansion=not acute and stalled>=30 and a.available>=a.home*.075 and (b.committed or 0)==0
 b.expansion_budget=b.permit_expansion and math.min(a.available,a.home*.12) or 0
 local rows={
  {kind='defend',score=acute and 30+incoming/math.max(1,a.home)*10 or core.at_risk and 7 or 1,reason=acute and 'Active invasion or recent losses' or 'Protect exposed core'},
  {kind='invest',score=7+((b.ally_reserve or 0)>0 and 3 or 0)+(a.home/math.max(1,frame.info.max_troops or a.home)>.75 and 3 or 0),reason='Improve productive capacity and recruitment'},
  {kind='expand',score=(opportunity and 9 or 2)+waitingCost-(acute and 30 or 0),reason='Compare safe growth against the cost of waiting'},
  {kind='negotiate',score=(b.overextended and 12 or 4)+(core.at_risk and 2 or 0),reason='Reduce a visible strategic threat'},
  {kind='relocate',score=b.escape and 40 or 0,reason=b.relocation_reason or 'Preserve a viable replacement base'},
 }
 table.sort(rows,function(x,y) if x.score==y.score then return x.kind<y.kind end;return x.score>y.score end)
 local selected=rows[1]
 if self.selected and not acute and not b.escape then
  for _,row in ipairs(rows) do if row.kind==self.selected and row.score>=selected.score-1.5 then selected=row end end
 end
 if self.selected~=selected.kind then
  table.insert(self.history,{tick=frame.state.tick,objective=selected.kind,reason=selected.reason})
  if #self.history>32 then table.remove(self.history,1) end
 end
 self.selected=selected.kind
 self.report={objective=selected.kind,reason=selected.reason,alternatives=rows,stalled_seconds=stalled,
  waiting_cost=waitingCost,limited_expansion=b.permit_expansion,expansion_budget=b.expansion_budget,
  scope='Heuristic alternatives; all orders retain independent legality and reserve checks',history=self.history}
 b.planner=self.report
end
function Planner:choose(frame,actions)
 local ranked={};local best,bestScore
 for _,a in ipairs(actions) do
  local t=a.intent.type;local kind=a.objective or (t=='build' and 'invest' or t=='ally_request' and 'negotiate'
   or t=='ally_reply' and 'negotiate' or t=='ally_extend' and 'negotiate' or t=='move_warship' and 'defend' or 'expand')
  if a.escape then kind='relocate' end
  if t=='build' and (a.intent.kind=='sam' or a.intent.kind=='defense' or a.intent.kind=='warship') then kind='defend' end
  if t=='nuke' then kind='defend' end
  local score=0
  for _,row in ipairs(self.report and self.report.alternatives or {}) do if row.kind==kind then score=row.score end end
  if a.investment then score+=a.investment.score*.75 end
  if a.plan and a.plan.utility then score+=math.clamp(a.plan.utility,-5,10) end
  if t=='donate' then score+=5+math.min(18,((a.plan or {}).support_urgency or 0)*5) end
  if t=='ally_reply' then score+=25 elseif t=='ally_extend' then score+=8 end
  if a.objective=='expand' and a.intent.type=='attack' and frame.state:tile_owner(a.intent.tile)==0 then score+=2 end
  table.insert(ranked,{kind=kind,type=t,score=score,label=a.label})
  if not bestScore or score>bestScore then best,bestScore=a,score end
 end
 table.sort(ranked,function(a,b) return a.score>b.score end)
 if self.report then self.report.actions=ranked;self.report.chosen=best and best.label or 'No safe legal action available' end
 return best
end
return Planner
