local P=require(game:GetService('ReplicatedStorage').BackseatExpedition.Shared.Preferences)
local UIS=game:GetService('UserInputService')
local Settings={};Settings.__index=Settings
local color={ink=Color3.fromRGB(18,28,29),panel=Color3.fromRGB(28,43,43),card=Color3.fromRGB(41,59,57),gold=Color3.fromRGB(238,184,83),text=Color3.fromRGB(243,237,216),muted=Color3.fromRGB(171,188,177)}
local function box(parent,cls,name,x,y,w,h)
 local o=Instance.new(cls);o.Name=name;o.Position=UDim2.fromOffset(x,y);o.Size=UDim2.fromOffset(w,h);o.BackgroundColor3=color.panel;o.BorderSizePixel=0;o.Parent=parent;return o
end
local function text(parent,value,x,y,w,h,size,tint)
 local o=box(parent,'TextLabel','Label',x,y,w,h);o.BackgroundTransparency=1;o.Text=value;o.TextSize=size or 15;o.TextColor3=tint or color.text
 o.TextXAlignment=Enum.TextXAlignment.Left;o.TextWrapped=true;o.Font=Enum.Font.Gotham;return o
end
local function button(parent,value,x,y,w,h,fn)
 local b=box(parent,'TextButton','Button',x,y,w,h);b.Text=value;b.TextSize=14;b.TextColor3=color.text;b.Font=Enum.Font.GothamBold;b.AutoButtonColor=true;b.BackgroundColor3=color.card
 b.Activated:Connect(fn);return b
end
local function display(value,key)
 if type(value)=='boolean'then return value and 'ON'or 'OFF'end
 if key=='tyrePressure'then return string.format('%.2f ×',value)end
 if key=='fov'then return tostring(value)..'°'end
 if type(value)=='number'then return string.format('%.2f',value):gsub('0+$',''):gsub('%.$','')end
 return tostring(value):upper()
end
function Settings.new(parent,onChanged)
 local self=setmetatable({data=P.defaults(),onChanged=onChanged,section='Driving',rows={},tabs={},bindingRows={},connections={}},Settings)
 local overlay=box(parent,'Frame','RallySettingsOverlay',0,0,0,0);overlay.Size=UDim2.fromScale(1,1);overlay.BackgroundColor3=Color3.new(0,0,0);overlay.BackgroundTransparency=.25;overlay.Visible=false;overlay.ZIndex=40;self.overlay=overlay
 local panel=box(overlay,'Frame','RallySettings',0,0,720,590);panel.AnchorPoint=Vector2.new(.5,.5);panel.Position=UDim2.fromScale(.5,.5);panel.ZIndex=41;self.panel=panel
 local scale=Instance.new('UIScale');scale.Parent=panel;self.scale=scale
 text(panel,'SETUP / MAKE THE CAR YOURS',26,18,600,30,20,color.gold).Font=Enum.Font.GothamBold
 text(panel,'First-person driving · replay cameras stay independent',26,50,650,24,13,color.muted)
 button(panel,'CLOSE',598,19,96,34,function()self:toggle(false)end)
 for i,section in ipairs({'Driving','Graphics','Controls'})do
  self.tabs[section]=button(panel,section:upper(),26+(i-1)*225,88,214,38,function()self.section=section;self:_render()end)
 end
 local scroll=box(panel,'ScrollingFrame','Options',26,142,668,369);scroll.BackgroundTransparency=1;scroll.ScrollBarThickness=5;scroll.ScrollingDirection=Enum.ScrollingDirection.Y;scroll.CanvasSize=UDim2.fromOffset(0,0);self.scroll=scroll
 self.help=text(panel,'Settings apply immediately. Car setup applies when starting or servicing.',26,521,560,48,12,color.muted)
 button(panel,'RESET',598,529,96,34,function()self:load(P.defaults());self:_changed()end)
 -- Set draw order explicitly so the panel remains above the driving HUD.
 for _,o in ipairs(panel:GetDescendants())do if o:IsA('GuiObject')or o:IsA('TextButton')or o:IsA('TextLabel')or o:IsA('Frame')or o:IsA('ScrollingFrame')then o.ZIndex=42 end end
 self.connections[#self.connections+1]=workspace.CurrentCamera:GetPropertyChangedSignal('ViewportSize'):Connect(function()self:_resize()end)
 self:_resize();self:_render();return self
end
function Settings:_resize()
 local camera=workspace.CurrentCamera;local size=camera and camera.ViewportSize or Vector2.new(1280,720)
 self.scale.Scale=math.min(1,(size.X-24)/720,(size.Y-24)/590)
end
function Settings:_changed()if self.onChanged then self.onChanged(self:values(),self:snapshot())end end
function Settings:_render()
 self.pending=nil;self.bindingRows={}
 for _,o in ipairs(self.scroll:GetChildren())do o:Destroy()end
 for section,b in pairs(self.tabs)do b.BackgroundColor3=section==self.section and Color3.fromRGB(70,87,64)or color.card end
 local y=0
 if self.section=='Controls'then
  for _,action in ipairs(P.actions)do
   text(self.scroll,action.name,8,y+6,450,32,15)
   local b; b=button(self.scroll,self.data.bindings[action.id],486,y+4,160,34,function()
    self.pending=action.id;self.help.Text='Press a keyboard key for '..action.name..'. Escape cancels. Existing keys swap.'
    for id,row in pairs(self.bindingRows)do row.Text=id==action.id and 'PRESS KEY…'or self.data.bindings[id]end
   end)
   self.bindingRows[action.id]=b;y+=46
  end
 else
  for _,d in ipairs(P.definitions)do if d.section==self.section then
   text(self.scroll,d.name,8,y+2,414,27,15)
   text(self.scroll,d.help,8,y+29,452,32,11,color.muted)
   local value=text(self.scroll,display(self.data.values[d.key],d.key),503,y+7,89,34,14,color.gold);value.TextXAlignment=Enum.TextXAlignment.Center
   local function change(direction)
    local current=self.data.values[d.key]
    if d.choices then local index=table.find(d.choices,current)or 1;self:set(d.key,d.choices[(index-1+direction)%#d.choices+1])else self:set(d.key,current+direction*d.step)end
    value.Text=display(self.data.values[d.key],d.key)
   end
   button(self.scroll,'−',467,y+7,32,34,function()change(-1)end)
   button(self.scroll,'+',596,y+7,42,34,function()change(1)end);y+=76
  end end
 end
 for _,o in ipairs(self.scroll:GetDescendants())do if o:IsA('TextButton')or o:IsA('TextLabel')then o.ZIndex=43 end end
 self.scroll.CanvasSize=UDim2.fromOffset(0,y);self.scroll.CanvasPosition=Vector2.new(0,0)
 self.help.Text=self.section=='Controls'and 'Select a binding, then press a keyboard key. Duplicates swap places.'or 'Settings apply immediately. Car setup applies when starting or servicing.'
end
function Settings:values()return P.copy(self.data).values end
function Settings:binds()return P.keyMap(self.data.bindings)end
function Settings:snapshot()return P.copy(self.data)end
function Settings:load(snapshot)
 self.data=P.normalize(snapshot)
 -- Ignore nonexistent enum values in imported/saved settings, keeping keys unique.
 local incoming=self.data.bindings;self.data.bindings=P.defaults().bindings
 for _,action in ipairs(P.actions)do
  local key=incoming[action.id];local ok,result=pcall(function()return Enum.KeyCode[key]end)
  if ok and result then P.rebind(self.data.bindings,action.id,key)end
 end
 self:_render()
end
function Settings:set(key,value)
 local normalized=P.value(key,value);if normalized==nil then return false end
 self.data.values[key]=normalized;self:_changed();return true
end
function Settings:toggle(force)
 self.overlay.Visible=force==nil and not self.overlay.Visible or force==true
 if not self.overlay.Visible then self.pending=nil end
 self:_resize();return self.overlay.Visible
end
function Settings:isOpen()return self.overlay.Visible end
function Settings:capture(input)
 if not self.overlay.Visible then return false end
 local key=input and input.KeyCode and input.KeyCode.Name or 'Unknown'
 if key=='Escape'then
  if self.pending then self.pending=nil;self:_render()else self:toggle(false)end
  return true
 end
 if self.pending then
  if input.UserInputType and input.UserInputType~=Enum.UserInputType.Keyboard then return true end
  local ok,enum=pcall(function()return Enum.KeyCode[key]end)
  if ok and enum and P.validKey(key)then
   P.rebind(self.data.bindings,self.pending,key);self.pending=nil;self:_render();self:_changed()
  end
 end
 return true
end
function Settings:destroy()
 for _,c in ipairs(self.connections)do c:Disconnect()end
 self.connections={};self.overlay:Destroy()
end
return Settings
