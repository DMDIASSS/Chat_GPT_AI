-- Local, reversible ownership of the view while the optional expansion is open.
local Players=game:GetService('Players')
local Lighting=game:GetService('Lighting')
local RunService=game:GetService('RunService')
local Context=game:GetService('ContextActionService')
local UIS=game:GetService('UserInputService')
local Presence={};Presence.__index=Presence
local daylight={ClockTime=15.8,Brightness=2.2,Ambient=Color3.fromRGB(114,122,114),
 OutdoorAmbient=Color3.fromRGB(148,155,144),FogStart=800,FogEnd=6000,FogColor=Color3.fromRGB(195,213,219)}
local atmosphere={Density=.18,Haze=.5,Glare=.1,Offset=0,Color=Color3.fromRGB(205,219,229),Decay=Color3.fromRGB(139,153,157)}
function Presence.new(gui)
 return setmetatable({gui=gui,active=false,screens={},connections={},environment={}},Presence)
end
function Presence:environmentProfile(object,profile)
 if self.environment[object]then return end
 local entry={before={},after=profile};self.environment[object]=entry
 for property in pairs(profile)do entry.before[property]=object[property]end
 for property,value in pairs(profile)do object[property]=value end
end
function Presence:effect(effect)
 if effect:IsA('Atmosphere')then self:environmentProfile(effect,atmosphere)
 elseif effect:IsA('PostEffect')then self:environmentProfile(effect,{Enabled=false})end
end
function Presence:time(clock)
 if self.environment[Lighting]then self.environment[Lighting].after.ClockTime=clock;Lighting.ClockTime=clock end
end
function Presence:hide(screen)
 if screen==self.gui or not screen:IsA('ScreenGui')or self.screens[screen]then return end
 self.screens[screen]={enabled=screen.Enabled}
 screen.Enabled=false
 self.connections[#self.connections+1]=screen:GetPropertyChangedSignal('Enabled'):Connect(function()
  if self.active and screen.Enabled then screen.Enabled=false end
 end)
end
function Presence:open()
 if self.active then return end
 self.active=true
 local camera=workspace.CurrentCamera
 self.camera={object=camera,cf=camera.CFrame,kind=camera.CameraType,subject=camera.CameraSubject,fov=camera.FieldOfView}
 self.clock=Lighting.ClockTime
 self:environmentProfile(Lighting,table.clone(daylight))
 for _,effect in ipairs(Lighting:GetChildren())do self:effect(effect)end
 self.connections[#self.connections+1]=Lighting.ChildAdded:Connect(function(effect)self:effect(effect)end)
 local pg=Players.LocalPlayer:WaitForChild('PlayerGui')
 for _,screen in ipairs(pg:GetChildren())do self:hide(screen)end
 self.connections[#self.connections+1]=pg.ChildAdded:Connect(function(screen)self:hide(screen)end)
 Context:BindActionAtPriority('ExpeditionControls',function(_,state,input)
  if UIS:GetFocusedTextBox()and state~=Enum.UserInputState.End and state~=Enum.UserInputState.Cancel then return Enum.ContextActionResult.Pass end
  if self.input then self.input(input,state)end
  return Enum.ContextActionResult.Sink
 end,false,4000,Enum.KeyCode.W,Enum.KeyCode.S,Enum.KeyCode.A,Enum.KeyCode.D,Enum.KeyCode.Space,
  Enum.KeyCode.Up,Enum.KeyCode.Down,Enum.KeyCode.Left,Enum.KeyCode.Right,
  Enum.KeyCode.Thumbstick1,Enum.KeyCode.ButtonR2,Enum.KeyCode.ButtonL2)
 RunService:BindToRenderStep('ExpeditionCamera',Enum.RenderPriority.Last.Value,function()
  if self.active then for object,entry in pairs(self.environment)do
   if object==Lighting or object.Parent then for property,value in pairs(entry.after)do
    if object[property]~=value then object[property]=value end
   end end
  end end
  if self.active and self.desired then
   local current=workspace.CurrentCamera;current.CameraType=Enum.CameraType.Scriptable
   current.CFrame=self.desired;current.FieldOfView=self.fov or 72
  end
 end)
end
function Presence:view(cf,fov)
 self.desired=cf;self.fov=fov or 72
end
function Presence:close()
 if not self.active then return end
 self.active=false
 RunService:UnbindFromRenderStep('ExpeditionCamera');Context:UnbindAction('ExpeditionControls')
 for _,connection in ipairs(self.connections)do connection:Disconnect()end
 self.connections={}
 for screen,data in pairs(self.screens)do if screen.Parent then screen.Enabled=data.enabled end end
 self.screens={}
 local old=self.camera;local camera=workspace.CurrentCamera
 if old and camera==old.object then
  camera.CameraType=old.kind;camera.CameraSubject=old.subject;camera.CFrame=old.cf;camera.FieldOfView=old.fov
 end
 Lighting.ClockTime=self.clock
 for object,entry in pairs(self.environment)do if object==Lighting or object.Parent then
  for property,value in pairs(entry.before)do object[property]=value end
 end end
 self.environment={}
 self.desired=nil;self.camera=nil
end
return Presence
