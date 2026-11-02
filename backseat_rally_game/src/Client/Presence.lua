-- Local, reversible ownership of the view while the optional expansion is open.
local Players=game:GetService('Players')
local Lighting=game:GetService('Lighting')
local RunService=game:GetService('RunService')
local Context=game:GetService('ContextActionService')
local UIS=game:GetService('UserInputService')
local Presence={};Presence.__index=Presence
local function finite(n)return type(n)=='number'and n==n and math.abs(n)<1e9 end
function Presence.validFrame(value)
 if typeof(value)~='CFrame'then return false end
 for _,v in ipairs({value.Position,value.RightVector,value.UpVector,value.LookVector})do
  if not finite(v.X)or not finite(v.Y)or not finite(v.Z)then return false end
 end
 local look=value.LookVector.Magnitude;local up=value.UpVector.Magnitude
 return look>.5 and look<1.5 and up>.5 and up<1.5
end
local daylight={ClockTime=15.8,Brightness=2.2,Ambient=Color3.fromRGB(114,122,114),
 OutdoorAmbient=Color3.fromRGB(148,155,144),GlobalShadows=false,FogStart=800,FogEnd=6000,FogColor=Color3.fromRGB(195,213,219)}
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
function Presence:bindKeys(map)
 self.keyMap=map
 if self.active then self:bindControls()end
end
function Presence:bindControls()
 Context:UnbindAction('ExpeditionControls')
 local keys={Enum.KeyCode.Thumbstick1,Enum.KeyCode.ButtonR2,Enum.KeyCode.ButtonL2}
 for name in pairs(self.keyMap or {W=true,S=true,A=true,D=true,Space=true,Up=true,Down=true,Left=true,Right=true})do
  local ok,key=pcall(function()return Enum.KeyCode[name]end);if ok and key then keys[#keys+1]=key end
 end
 Context:BindActionAtPriority('ExpeditionControls',function(_,state,input)
  if UIS:GetFocusedTextBox()and state~=Enum.UserInputState.End and state~=Enum.UserInputState.Cancel then return Enum.ContextActionResult.Pass end
  if self.input then self.input(input,state)end
  return Enum.ContextActionResult.Sink
 end,false,4000,table.unpack(keys))
end
function Presence:sceneProfile(original)
 self.originalScene=original==true
 for object,entry in pairs(self.environment)do
  if object==Lighting then
   entry.after=self.originalScene and table.clone(entry.before)or table.clone(daylight)
   if self.originalScene then entry.after.FogEnd=math.max(1200,tonumber(entry.before.FogEnd)or 6000)end
  elseif object:IsA('Atmosphere')then
   entry.after=self.originalScene and table.clone(entry.before)or atmosphere
   if self.originalScene then entry.after.Density=math.min(.32,tonumber(entry.before.Density)or .18);entry.after.Haze=math.min(2,tonumber(entry.before.Haze)or .5)end
  elseif object:IsA('PostEffect')then
   local keep=self.originalScene and not object:IsA('BlurEffect')and not object:IsA('DepthOfFieldEffect')
   entry.after={Enabled=keep and entry.before.Enabled or false}
  end
 end
end
function Presence:climate(conditions,quality)
 local light=self.environment[Lighting]
 if light then
  light.after.FogEnd=self.originalScene and math.max(1200,(tonumber(light.before.FogEnd)or 6000)*(conditions.wetness>.3 and .85 or 1))or (conditions.wetness>.3 and 2600 or 6000)
  light.after.GlobalShadows=self.originalScene and quality~='low'or quality=='high'
 end
end
function Presence:open()
 if self.active then return end
 self.active=true
 local camera=workspace.CurrentCamera
 self.camera={object=camera,parent=camera.Parent,cf=camera.CFrame,focus=camera.Focus,kind=camera.CameraType,subject=camera.CameraSubject,fov=camera.FieldOfView}
 -- Old controllers cache their Camera instance. Keep that instance intact while
 -- the expansion owns a separate view. Cameras are stored under a folder because
 -- CurrentCamera replacement can delete other cameras directly under Workspace.
 self.cameraStore=Instance.new('Folder');self.cameraStore.Name='ExpeditionCameraStore';self.cameraStore.Parent=workspace
 camera.Parent=self.cameraStore;camera.CameraType=Enum.CameraType.Scriptable
 self:ensureCamera()
 self.clock=Lighting.ClockTime
 self:environmentProfile(Lighting,table.clone(daylight))
 for _,effect in ipairs(Lighting:GetChildren())do self:effect(effect)end
 self.connections[#self.connections+1]=Lighting.ChildAdded:Connect(function(effect)self:effect(effect)end)
 local pg=Players.LocalPlayer:WaitForChild('PlayerGui')
 for _,screen in ipairs(pg:GetChildren())do self:hide(screen)end
 self.connections[#self.connections+1]=pg.ChildAdded:Connect(function(screen)self:hide(screen)end)
 self:bindControls()
 RunService:BindToRenderStep('ExpeditionCamera',Enum.RenderPriority.Last.Value,function()
  if self.active then for object,entry in pairs(self.environment)do
   if object==Lighting or object.Parent then for property,value in pairs(entry.after)do
    if object[property]~=value then object[property]=value end
   end end
  end end
  if self.active and self.desired then
   local current=self:ensureCamera();current.CameraType=Enum.CameraType.Scriptable
   current.CFrame=self.desired;current.Focus=self.desired*CFrame.new(0,0,-32);current.FieldOfView=self.fov or 72
  end
 end)
end
function Presence:ensureCamera()
 local current=self.managedCamera
 if not current or current.Parent~=self.cameraStore then
  current=Instance.new('Camera');current.Name='ExpeditionView';current.Parent=self.cameraStore
  local previous=workspace.CurrentCamera
  if previous then
   -- ViewportSize is renderer-owned in Studio; copying only supports test doubles.
   pcall(function()current.ViewportSize=previous.ViewportSize end)
  end
  current.CameraType=Enum.CameraType.Scriptable
  if self.desired then current.CFrame=self.desired end
  current.FieldOfView=self.fov or 72;self.managedCamera=current
 end
 if workspace.CurrentCamera~=current then workspace.CurrentCamera=current end
 return current
end
function Presence:view(cf,fov)
 if not Presence.validFrame(cf)then
  self.invalidFrames=(self.invalidFrames or 0)+1;self.gui:SetAttribute('RejectedViewFrames',self.invalidFrames)
  return false
 end
 self.desired=cf;self.fov=finite(fov)and math.clamp(fov,20,110)or 72
 return true
end
function Presence:close()
 if not self.active then return end
 self.active=false
 RunService:UnbindFromRenderStep('ExpeditionCamera');Context:UnbindAction('ExpeditionControls')
 for _,connection in ipairs(self.connections)do connection:Disconnect()end
 self.connections={}
 for screen,data in pairs(self.screens)do if screen.Parent then screen.Enabled=data.enabled end end
 self.screens={}
 local old=self.camera
 if old then
  local camera=old.object
  workspace.CurrentCamera=camera
  camera.Parent=old.parent;camera.CameraType=old.kind;camera.CameraSubject=old.subject;camera.CFrame=old.cf;camera.FieldOfView=old.fov
  if old.focus then camera.Focus=old.focus end
 end
 if self.cameraStore then self.cameraStore:Destroy()end
 self.cameraStore=nil;self.managedCamera=nil
 Lighting.ClockTime=self.clock
 for object,entry in pairs(self.environment)do if object==Lighting or object.Parent then
  for property,value in pairs(entry.before)do object[property]=value end
 end end
 self.environment={}
 self.desired=nil;self.camera=nil
end
return Presence
