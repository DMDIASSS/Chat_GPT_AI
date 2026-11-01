-- Original lightweight models; optional skins are harvested from the user's place by Installer.
local Assets={}
local Loader=require(script.Parent.AssetLoader)
local function color(t)return Color3.new(t[1],t[2],t[3])end
function Assets.part(parent,name,size,cf,tint,material,shape)
 local p=Instance.new('Part');p.Name=name;p.Size=size;p.CFrame=cf;p.Anchored=true
 p.Color=typeof(tint)=='Color3'and tint or color(tint);p.Material=material or Enum.Material.SmoothPlastic
 p.TopSurface=Enum.SurfaceType.Smooth;p.BottomSurface=Enum.SurfaceType.Smooth;p.CastShadow=false
 p.CanCollide=false;p.CanTouch=false;p.CanQuery=false;if shape then p.Shape=shape end;p.Parent=parent;return p
end
local function box(model,name,size,position,tint,material)
 return Assets.part(model,name,size,CFrame.new(position),tint,material)
end
local dark={.075,.09,.095};local glass={.14,.24,.25};local metal={.50,.55,.54}
function Assets.car(parent,car,ghost,useOriginal,withAudio)
 local model=Instance.new('Model');model.Name=ghost and 'SavedGhost'or car.name
 local body=box(model,'Chassis',Vector3.new(5.7,1.55,9.4),Vector3.zero,car.color);model.PrimaryPart=body
 box(model,'Bonnet',Vector3.new(5.55,.55,2.7),Vector3.new(0,.9,-3),car.color)
 box(model,'Roof',Vector3.new(4.6,.35,4.7),Vector3.new(0,2.2,.4),car.color)
 box(model,'Cabin',Vector3.new(4.5,1.5,4.3),Vector3.new(0,1.4,.4),glass)
 box(model,'Windscreen',Vector3.new(4.5,1.25,.12),Vector3.new(0,1.5,-1.8),glass)
 for _,side in ipairs({-1,1})do
  box(model,'A pillar',Vector3.new(.18,1.65,.22),Vector3.new(side*2.25,1.5,-1.8),car.color)
  box(model,'B pillar',Vector3.new(.18,1.65,.20),Vector3.new(side*2.25,1.5,.3),car.color)
  box(model,'C pillar',Vector3.new(.18,1.65,.22),Vector3.new(side*2.25,1.5,2.4),car.color)
  box(model,'Mirror',Vector3.new(.55,.25,.7),Vector3.new(side*3,1,-1.45),dark)
  box(model,'Sill',Vector3.new(.15,.3,6.2),Vector3.new(side*2.9,-.4,.3),dark)
  box(model,'Headlamp',Vector3.new(1.5,.45,.12),Vector3.new(side*1.65,.4,-4.76),{.99,.91,.64},Enum.Material.Neon)
  box(model,'Tail lamp',Vector3.new(1.1,.32,.12),Vector3.new(side*1.85,.45,4.76),{.72,.13,.1},Enum.Material.Neon)
 end
 box(model,'Front bumper',Vector3.new(5.9,.55,.4),Vector3.new(0,-.3,-4.8),dark)
 box(model,'Rear bumper',Vector3.new(5.9,.55,.4),Vector3.new(0,-.3,4.8),dark)
 box(model,'Grille',Vector3.new(2.3,.5,.15),Vector3.new(0,.3,-4.78),dark)
 box(model,'Rally stripe',Vector3.new(.8,.04,9.1),Vector3.new(.8,.8,0),{.94,.91,.79})
 if car.id=='scout'then
  box(model,'Roof rack',Vector3.new(4.9,.2,4.7),Vector3.new(0,2.5,.4),dark)
  box(model,'Expedition case',Vector3.new(3.5,.55,2.7),Vector3.new(0,2.9,.8),{.45,.37,.24})
 elseif car.id=='coupe'then
  box(model,'Spoiler',Vector3.new(6,.2,.8),Vector3.new(0,1.35,4.1),dark)
 end
 local wheels={}
 for _,front in ipairs({true,false})do for _,sign in ipairs({-1,1})do
  local tyre=Assets.part(model,'Tyre',Vector3.new(.8,2.4,2.4),CFrame.new(sign*3,-1,front and -3.8 or 3.8),dark,Enum.Material.SmoothPlastic,Enum.PartType.Cylinder)
  local rim=Assets.part(model,'Wheel',Vector3.new(.83,1.4,1.4),tyre.CFrame,metal,Enum.Material.Metal,Enum.PartType.Cylinder)
  wheels[#wheels+1]={tyre=tyre,rim=rim,side=sign,front=front}
 end end
 local root=game:GetService('ReplicatedStorage'):FindFirstChild('BackseatExpedition')
 local library=root and root:FindFirstChild('ImportedCars')
 local template=useOriginal~=false and library and library:FindFirstChild(car.template)
 local parts={}
 for _,p in ipairs(model:GetDescendants())do if p:IsA('BasePart')then
  p.Anchored=true;p.CanCollide=false;p.CanTouch=false;p.CanQuery=false;p.CastShadow=not ghost
  if ghost then p.Color=Color3.fromRGB(107,220,201);p.Transparency=.65;p.Material=Enum.Material.ForceField end
  parts[#parts+1]=p
 end end
 local sounds={};local bank=withAudio and root and root:FindFirstChild('ImportedAudio')
 if bank and not ghost then for _,name in ipairs({'Idle','Run','High'})do
  local source=bank:FindFirstChild(name)
  if source and source:IsA('Sound')then local sound=source:Clone();sound.Parent=body;sound.Volume=0;sound:Play();sounds[#sounds+1]=sound end
 end end
 model.Parent=parent
 model:SetAttribute('VisualSource','BuiltIn')
 local visual={model=model,wheels=wheels,parts=parts,spin=0,audio=sounds}
 if template and not ghost then
  Loader.check(template,function(ready)
   if not ready or not model.Parent then return end
   local skin=template:Clone()
   if not skin.PrimaryPart then skin:Destroy();return end
   skin.Name='Original exterior';skin:PivotTo(model:GetPivot())
   for _,part in ipairs(skin:GetDescendants())do if part:IsA('BasePart')then
    part.Anchored=true;part.CanCollide=false;part.CanTouch=false;part.CanQuery=false
   end end
   skin.Parent=model
   -- Keep a complete body until all external assets are confirmed available.
   for _,part in ipairs(parts)do
    if part.Name~='Tyre'and part.Name~='Wheel'then part.Transparency=1 end
   end
   model:SetAttribute('VisualSource','Original')
  end)
 end
 return visual
end
function Assets.pose(visual,s,route,offset,dt)
 local D=require(script.Parent.Dynamics)
 local y,pitch,roll=D.pose(s,route)
 local cf=CFrame.new(Vector3.new(s.x,y,s.z)+offset)*CFrame.Angles(0,math.pi+s.yaw,0)*CFrame.Angles(pitch,0,roll)
 visual.model:PivotTo(cf);visual.spin=(visual.spin+s.v*(dt or 0)/1.2)%(math.pi*2)
 for _,wheel in ipairs(visual.wheels)do
  local z=wheel.front and -3.8 or 3.8
  local pos=cf:PointToWorldSpace(Vector3.new(wheel.side*3,0,z))
  local localPos=pos-offset;local ground=route:ground(localPos.X,localPos.Z)
  local at=Vector3.new(pos.X,ground+1.2+offset.Y,pos.Z)
  local wc=CFrame.new(at)*cf.Rotation*CFrame.Angles(0,wheel.front and -s.steer*.32 or 0,0)*CFrame.Angles(visual.spin,0,0)
  wheel.tyre.CFrame=wc;wheel.rim.CFrame=wc
 end
 for i,sound in ipairs(visual.audio or {})do
  local speed=math.abs(s.v);local gear=(speed%32)/32
  sound.PlaybackSpeed=math.clamp(.65+gear*.8,.5,1.6)
  local gain=i==1 and math.clamp(1-speed/35,0,1)or(i==2 and math.clamp(speed/45,0,1)or math.clamp((speed-65)/65,0,1))
  sound.Volume=(dt or 0)>0 and gain*.17 or 0
 end
 return cf
end
function Assets.park(parent)
 local ground=Assets.part(parent,'Service park',Vector3.new(160,2,150),CFrame.new(0,-1,0),{.21,.25,.22},Enum.Material.Asphalt)
 ground.CanCollide=true;ground.CanQuery=true
 for i,car in ipairs(require(script.Parent.Config).Cars)do
  local visual=Assets.car(parent,car,false,true)
  visual.model:PivotTo(CFrame.new((i-2)*20,2.2,-12)*CFrame.Angles(0,math.pi,0))
 end
 Assets.part(parent,'Workshop',Vector3.new(64,14,22),CFrame.new(0,7,-42),{.24,.30,.29},Enum.Material.WoodPlanks)
 Assets.part(parent,'Roof',Vector3.new(70,1,28),CFrame.new(0,14,-42),{.12,.18,.18},Enum.Material.Metal)
 for _,x in ipairs({-21,0,21})do Assets.part(parent,'Garage door',Vector3.new(17,10,.25),CFrame.new(x,5,-30.8),{.10,.14,.15},Enum.Material.Metal)end
 for _,x in ipairs({-44,44})do
  Assets.part(parent,'Lamp',Vector3.new(.5,12,.5),CFrame.new(x,6,5),metal,Enum.Material.Metal)
  Assets.part(parent,'Lantern',Vector3.new(2,.4,3),CFrame.new(x,12,5),{.99,.79,.48},Enum.Material.Neon)
 end
 local sign=Assets.part(parent,'Expedition sign',Vector3.new(45,4,.4),CFrame.new(0,12,-30.5),dark)
 local gui=Instance.new('SurfaceGui');gui.Face=Enum.NormalId.Back;gui.CanvasSize=Vector2.new(1000,100);gui.Parent=sign
 local text=Instance.new('TextLabel');text.Size=UDim2.fromScale(1,1);text.BackgroundTransparency=1;text.Text='BACKSEAT / EXPEDITION'
 text.TextColor3=Color3.fromRGB(239,222,183);text.Font=Enum.Font.GothamBold;text.TextScaled=true;text.Parent=gui
end
return Assets
