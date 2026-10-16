"""Live client behaviours under synthetic Roblox APIs."""
CASES = [('live_frames_and_close',
  '\n'
  'task.wait=function(dt)\n'
  ' move(dt)\n'
  " if now>.2 and not startedBot then startedBot=true;click('Start bot / F6')end\n"
  " if now>=12 then click('Close')end\n"
  'end\n',
  '\n'
  "assert(#packets>150,'Did not stream at live frequency')\n"
  'local running=0\n'
  'for i,p in ipairs(packets)do\n'
  ' if i>1 then assert(p.seq>packets[i-1].seq)end\n'
  ' if p.enabled and p.valid then\n'
  '  running=running+1\n'
  '  assert(p.boost~=nil and p.car and p.ball)\n'
  "  assert(type(p.ground_estimate)=='boolean')\n"
  ' end\n'
  'end\n'
  "assert(running>100,'Bot never enabled')\n"
  "assert(packets[#packets].enabled==false,'Close did not send stop')\n"
  'assert(playerGui.children.Update271Bridge.destroyed)\n'
  'assert(not services.UserInputService.InputBegan.listeners[1].connection.enabled)\n'),
 ('goal_respawn_resumes',
  '\n'
  'local removed,restored=false,false\n'
  'task.wait=function(dt)\n'
  ' move(dt)\n'
  " if now>.2 and not startedBot then startedBot=true;click('Start bot / F6')end\n"
  ' if now>=5 and not removed then removed=true;ballRoot.Parent=nil;ball.PrimaryPart=nil end\n'
  ' if now>=8 and not restored then\n'
  '  restored=true\n'
  "  local replacement=object('Model','NewBall');replacement.Parent=scene\n"
  "  ballRoot=object('Part','Root');ballRoot.Parent=replacement\n"
  '  ballRoot.CFrame=frame(5+now*2);ballRoot.Position=ballRoot.CFrame.Position\n'
  '  replacement.PrimaryPart=ballRoot\n'
  ' end\n'
  " if now>=12 then click('Close')end\n"
  'end\n',
  '\n'
  'local waiting,resumed=0,0\n'
  'for _,p in ipairs(packets)do\n'
  " if p.enabled and not p.valid and string.find(p.reason,'goal/reset',1,true)then "
  'waiting=waiting+1 end\n'
  ' if waiting>0 and p.enabled and p.valid then resumed=resumed+1 end\n'
  'end\n'
  "assert(waiting>30,'Missing nonfatal reset wait')\n"
  "assert(resumed>30,'Did not resume after respawn')\n"),
 ('teleport_invalidates_frame',
  '\n'
  'task.wait=function(dt)\n'
  ' move(dt)\n'
  " if now>.2 and not startedBot then startedBot=true;click('Start bot / F6')end\n"
  " if now>=27 then click('Close')end\n"
  'end\n',
  '\n'
  'local jumped=false\n'
  'for _,p in ipairs(packets)do\n'
  " if p.reason=='pose discontinuity/reset'then assert(not p.valid);jumped=true end\n"
  'end\n'
  "assert(jumped,'Teleport was used as real motion')\n"),
 ('missing_boost_no_fake_state',
  '\n'
  'task.wait=function(dt)\n'
  " move(dt);boostLabel.Text='BOOST'\n"
  " if now>.2 and not startedBot then startedBot=true;click('Start bot / F6')end\n"
  " if now>=5 then click('Close')end\n"
  'end\n',
  '\n'
  'local missing=0\n'
  'for _,p in ipairs(packets)do\n'
  ' if p.enabled then\n'
  "  assert(not p.valid,'Fabricated boost state')\n"
  "  if p.reason=='numeric boost HUD missing'then missing=missing+1 end\n"
  ' end\n'
  'end\n'
  'assert(missing>30)\n')]
