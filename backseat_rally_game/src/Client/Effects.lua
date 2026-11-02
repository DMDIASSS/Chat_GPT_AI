-- Finite, non-graphic impact and weather overlays. No assets or frame-time allocation.
local Effects={};Effects.__index=Effects
local function frame(parent,name,color,z)
 local f=Instance.new('Frame');f.Name=name;f.Size=UDim2.fromScale(1,1);f.BorderSizePixel=0
 f.BackgroundColor3=color;f.BackgroundTransparency=1;f.ZIndex=z;f.Active=false;f.Parent=parent;return f
end
function Effects.new(gui)
 local container=frame(gui,'RallyEffects',Color3.new(0,0,0),20)
 local self=setmetatable({root=container,red=frame(container,'ImpactRed',Color3.fromRGB(140,17,13),22),
  black=frame(container,'ImpactBlackout',Color3.new(0,0,0),23),rain={},time=0,impactAge=100,strength=0,severe=false,lastImpact=0,lastCrashes=0},Effects)
 for i=1,24 do
  local streak=frame(container,'RainStreak',Color3.fromRGB(201,218,225),21);streak.Size=UDim2.fromOffset(1,28+i%5*4)
  streak.Rotation=-12;streak.Visible=false;self.rain[i]=streak
 end
 return self
end
function Effects:reset()
 self.impactAge=100;self.strength=0;self.severe=false;self.lastImpact=0;self.lastCrashes=0
 self.red.BackgroundTransparency=1;self.black.BackgroundTransparency=1
 for _,streak in ipairs(self.rain)do streak.Visible=false end
end
function Effects:update(state,dt,settings,isReplay,weather)
 dt=math.clamp(dt or 0,0,.1);settings=settings or {};self.time+=dt;self.impactAge+=dt
 local impact=state.impact or 0;local crashes=state.crashes or 0
 if not isReplay and (crashes>self.lastCrashes or impact>self.lastImpact+.25)then
  local speed=math.abs(state.impactSpeed or state.crashSpeed or state.v or 0)
  self.strength=math.clamp(.25+speed/140,.25,1);self.severe=speed>=84;self.impactAge=0
 end
 self.lastImpact=impact;self.lastCrashes=crashes
 local mode=settings.crashEffects or 'red'
 local red=0;local black=0
 if not isReplay and mode~='off'then
  red=self.strength*math.max(0,1-self.impactAge/1.15)*.52
  if mode=='blackout'and self.severe then
   black=self.impactAge<.42 and 1 or math.max(0,1-(self.impactAge-.42)/1.1)
   red*=1-black
  end
 end
 self.red.BackgroundTransparency=1-red;self.black.BackgroundTransparency=1-black
 local wetness=weather and weather.wetness or state.wetness or 0
 local amount=not isReplay and wetness>.26 and (settings.quality=='low'and 8 or 24)or 0
 for i,streak in ipairs(self.rain)do
  streak.Visible=i<=amount
  if i<=amount then
   local x=((i*.61803398875+self.time*.017)%1)
   local y=((i*.38196601125+self.time*(.73+i%5*.08))%1)
   streak.Position=UDim2.fromScale(x,y);streak.BackgroundTransparency=math.clamp(.94-wetness*.18,.72,.96)
  end
 end
end
function Effects:destroy()self.root:Destroy();self.rain={}end
return Effects
