-- Local, asset-independent cabin. Geometry and instruments are allocated once.
-- Car local forward is -Z; recommended eye is (+/-1.15, 1.45, .35).
local Cockpit={};Cockpit.__index=Cockpit
local ink=Color3.fromRGB(19,24,25)
local metal=Color3.fromRGB(105,116,115)
local trim=Color3.fromRGB(48,57,57)
local function part(parent,name,size,cf,color,material)
 local p=Instance.new('Part');p.Name=name;p.Size=size;p.CFrame=cf;p.Color=color
 p.Material=material or Enum.Material.SmoothPlastic;p.Anchored=true;p.CanCollide=false;p.CanTouch=false;p.CanQuery=false;p.CastShadow=false
 p.TopSurface=Enum.SurfaceType.Smooth;p.BottomSurface=Enum.SurfaceType.Smooth;p.Parent=parent;return p
end
local function text(parent,name,value,x,y,w,h,size,color)
 local t=Instance.new('TextLabel');t.Name=name;t.Text=value;t.Position=UDim2.fromOffset(x,y);t.Size=UDim2.fromOffset(w,h)
 t.BackgroundTransparency=1;t.TextColor3=color or Color3.fromRGB(231,234,215);t.Font=Enum.Font.Code;t.TextSize=size
 t.TextXAlignment=Enum.TextXAlignment.Left;t.Parent=parent;return t
end
function Cockpit.new(parent,car,options)
 local model=Instance.new('Model');model.Name='RallyCockpit';model.Parent=parent
 local root=part(model,'Cabin root',Vector3.new(.05,.05,.05),CFrame.new(),ink);root.Transparency=1;model.PrimaryPart=root
 local self=setmetatable({model=model,car=car,visual=options and options.visual,wheel={},instrumentAt=0,visible=true,parts={}},Cockpit)
 part(model,'Padded dashboard',Vector3.new(4.45,.27,1.03),CFrame.new(0,.41,-1.5),ink)
 part(model,'Dashboard brow',Vector3.new(2.35,.1,.54),CFrame.new(-1.06,.81,-1.44),trim)
 local panel=part(model,'Driver instrument panel',Vector3.new(2.22,.59,.08),CFrame.new(-1.06,.48,-1.28),ink)
 part(model,'Passenger glovebox',Vector3.new(1.83,.48,.1),CFrame.new(1.14,.43,-.97),trim)
 part(model,'Centre console',Vector3.new(.44,.45,1.4),CFrame.new(.15,-.12,-.22),ink)
 part(model,'Gear stick',Vector3.new(.09,.48,.09),CFrame.new(.18,.17,-.22),metal,Enum.Material.Metal)
 part(model,'Gear knob',Vector3.new(.23,.17,.23),CFrame.new(.18,.46,-.22),trim)
 for _,side in ipairs({-1,1})do
  part(model,'Lower door trim',Vector3.new(.14,.59,2.8),CFrame.new(side*2.22,.06,.18),ink)
  part(model,'Window sill',Vector3.new(.17,.12,3.2),CFrame.new(side*2.22,.71,.1),trim)
  part(model,'Front roll cage',Vector3.new(.055,1.83,.055),CFrame.new(side*2.18,1.37,-1.73)*CFrame.Angles(.12,0,side*.04),metal,Enum.Material.Metal)
  part(model,'Roof cage rail',Vector3.new(.055,.055,3.2),CFrame.new(side*2.16,2.28,-.1),metal,Enum.Material.Metal)
 end
 part(model,'Top windscreen rail',Vector3.new(4.35,.055,.055),CFrame.new(0,2.28,-1.73),metal,Enum.Material.Metal)
 -- The steering rim is twelve flat segments, with no hidden external meshes.
 local hub=CFrame.new(-1.15,.53,-1.12)*CFrame.Angles(math.rad(10),0,0)
 self.hub=hub
 for i=1,12 do
  local angle=(i-1)*math.pi/6
  local localFrame=hub*CFrame.Angles(0,0,angle)*CFrame.new(0,.31,0)
  local p=part(model,'Steering rim',Vector3.new(.162,.045,.045),localFrame,ink)
  self.wheel[#self.wheel+1]={part=p,localFrame=hub:Inverse()*localFrame}
 end
 for i=1,3 do
  local a=(i-1)*math.pi*2/3
  local localFrame=hub*CFrame.Angles(0,0,a)*CFrame.new(0,.13,0)
  local p=part(model,'Steering spoke',Vector3.new(.045,.25,.045),localFrame,metal,Enum.Material.Metal)
  self.wheel[#self.wheel+1]={part=p,localFrame=hub:Inverse()*localFrame}
 end
 part(model,'Steering centre',Vector3.new(.14,.14,.065),hub,trim)
 local gui=Instance.new('SurfaceGui');gui.Name='LiveInstruments';gui.Face=Enum.NormalId.Back;gui.CanvasSize=Vector2.new(720,210)
 gui.LightInfluence=0;gui.Brightness=1.3;gui.Parent=panel
 local background=Instance.new('Frame');background.Size=UDim2.fromScale(1,1);background.BorderSizePixel=0;background.BackgroundColor3=Color3.fromRGB(7,14,15);background.Parent=gui
 text(background,'Brand','EXPEDITION / RALLY COMPUTER',16,8,690,27,25,Color3.fromRGB(177,195,166))
 self.speed=text(background,'Speed','000',16,39,255,111,98)
 text(background,'Speed unit','KM/H',30,154,200,30,25,Color3.fromRGB(137,158,144))
 self.gear=text(background,'Gear','N',295,45,115,108,98,Color3.fromRGB(242,186,78))
 text(background,'Gear legend','GEAR',301,154,128,30,25,Color3.fromRGB(137,158,144))
 self.rpm=text(background,'RPM','0850 RPM',451,48,255,45,37)
 self.status=text(background,'Status','SYSTEMS READY',451,108,255,36,23,Color3.fromRGB(137,187,148))
 self.pressure=text(background,'Pressure','TYRES  100%',451,154,255,32,24,Color3.fromRGB(177,195,166))
 self.revBars={}
 for i=1,10 do
  local bar=Instance.new('Frame');bar.Name='ShiftLight';bar.Position=UDim2.fromOffset(16+(i-1)*70,191);bar.Size=UDim2.fromOffset(62,7)
  bar.BackgroundColor3=Color3.fromRGB(32,49,40);bar.BorderSizePixel=0;bar.Parent=background;self.revBars[i]=bar
 end
 for _,p in ipairs(model:GetDescendants())do if p:IsA('BasePart')then self.parts[#self.parts+1]={part=p,transparency=p.Transparency}end end
 self:_refreshSource()
 return self
end
-- Original cabin geometry belongs to the imported visual, never this fallback model.
-- An available original interior must not be overlaid with a second dashboard/wheel.
function Cockpit:source()
 if self.originalModel and self.originalModel.Parent then return 'original'end
 local visual=self.visual
 if visual and ((visual.interiorReady==true and (not visual.interior or visual.interior.Parent))or (visual.interior and visual.interior.Parent))then return 'original'end
 if visual and visual.skinStatus=='loading'then return 'loading'end
 return 'fallback'
end
function Cockpit:setOriginal(model,steeringParts)
 self.originalModel=model;self.originalSteering=steeringParts;self:_refreshSource()
end
function Cockpit:_refreshSource()
 local source=self:source();local show=self.visible and source=='fallback'
 if self.appliedVisible==show then return end
 self.appliedVisible=show
 for _,entry in ipairs(self.parts)do if entry.part.Parent then entry.part.Transparency=show and entry.transparency or 1 end end
 local panel=self.model:FindFirstChild('Driver instrument panel')
 if panel and panel:FindFirstChild('LiveInstruments')then panel.LiveInstruments.Enabled=show end
end
function Cockpit:setVisible(visible)
 self.visible=visible;self:_refreshSource()
end
function Cockpit:update(cf,state,dt,passenger)
 self:_refreshSource()
 local original=self:source()=='original'
 if original then
  for _,entry in ipairs(self.visual and self.visual.instrumentParts or {})do if entry.part.Parent then
   local value=entry.kind=='Speedo'and math.abs(state.v or 0)*.28*3.6 or (state.rpm or 850)
   local angle=entry.zero+(entry.finish-entry.zero)*math.clamp(value/math.max(1,entry.max),0,1)
   entry.part.CFrame=cf*entry.hub*CFrame.Angles(0,0,math.rad(angle))*entry.localFrame
  end end
  local entries=self.originalSteering or (self.visual and self.visual.steeringParts)
  for _,entry in ipairs(entries or {})do if entry.part and entry.part.Parent and entry.hub and entry.localFrame then
   entry.part.CFrame=cf*entry.hub*CFrame.Angles(0,0,-(state.steer or 0)*math.rad(entry.range or 125))*entry.localFrame
  end end
 end
 -- Keep the portable model's pivot for view continuity, even while fully hidden.
 self.model:PivotTo(cf)
 if original or self:source()=='loading'then return end
 local steering=CFrame.Angles(0,0,-(state.steer or 0)*math.rad(125))
 for _,entry in ipairs(self.wheel)do entry.part.CFrame=cf*self.hub*steering*entry.localFrame end
 self.instrumentAt+=math.max(0,dt or 0)
 if self.instrumentAt<.1 then return end;self.instrumentAt=0
 local speed=math.abs(state.v or 0)*.28*3.6
 self.speed.Text=string.format('%03d',math.floor(speed+.5))
 self.gear.Text=(state.v or 0)<-.5 and 'R'or(speed<1 and 'N'or tostring(state.gear or 1))
 local rpm=math.max(800,state.rpm or (800+speed*29));self.rpm.Text=string.format('%04d RPM',math.floor(rpm+.5))
 local pressure,count,punctured=0,0,false
 for _,tyre in pairs(state.tyres or {})do pressure+=tyre.pressure or 1;count+=1;punctured=punctured or tyre.punctured==true end
 self.pressure.Text=string.format('TYRES  %d%%',math.floor((count>0 and pressure/count or 1)*100+.5))
 self.status.Text=punctured and 'PUNCTURE / PIT'or((state.damage or 0)>55 and 'DAMAGE / PIT'or(passenger and 'CO-DRIVER' or 'SYSTEMS READY'))
 self.status.TextColor3=(punctured or (state.damage or 0)>55)and Color3.fromRGB(239,110,75)or Color3.fromRGB(137,187,148)
 local maxRPM=self.car.shiftRpm or 6500;local fraction=math.clamp(rpm/maxRPM,0,1)
 for i,bar in ipairs(self.revBars)do
  bar.BackgroundColor3=fraction>=i/10 and (i>=9 and Color3.fromRGB(236,83,57)or Color3.fromRGB(216,185,77))or Color3.fromRGB(32,49,40)
 end
end
function Cockpit:destroy()self.model:Destroy();self.wheel={};self.parts={}end
return Cockpit
