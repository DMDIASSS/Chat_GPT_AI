-- Local, reversible ownership of the view while the optional expansion is open.
local Players=game:GetService('Players')
local Lighting=game:GetService('Lighting')
local RunService=game:GetService('RunService')
local Context=game:GetService('ContextActionService')
local Presence={};Presence.__index=Presence
function Presence.new(gui)
 return setmetatable({gui=gui,active=false,screens={},connections={}},Presence)
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
 local pg=Players.LocalPlayer:WaitForChild('PlayerGui')
 for _,screen in ipairs(pg:GetChildren())do self:hide(screen)end
 self.connections[#self.connections+1]=pg.ChildAdded:Connect(function(screen)self:hide(screen)end)
 Context:BindActionAtPriority('ExpeditionControls',function()return Enum.ContextActionResult.Sink end,false,4000,
  Enum.PlayerActions.CharacterForward,Enum.PlayerActions.CharacterBackward,Enum.PlayerActions.CharacterLeft,
  Enum.PlayerActions.CharacterRight,Enum.PlayerActions.CharacterJump)
 RunService:BindToRenderStep('ExpeditionCamera',Enum.RenderPriority.Last.Value,function()
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
 self.desired=nil;self.camera=nil
end
return Presence
