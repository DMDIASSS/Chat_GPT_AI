-- Draggable while paused; F4 can minimize while mouse boost is active.
local Window={}
Window.__index=Window
function Window.new(gui,input,connect,canDrag,title)
    local panel=Instance.new('Frame',gui);panel.Name='Window'
    panel.Size=UDim2.fromOffset(480,372);panel.Position=UDim2.fromOffset(20,20)
    panel.BackgroundColor3=Color3.fromRGB(18,22,30)
    local header=Instance.new('TextButton',panel);header.Name='Titlebar'
    header.Position=UDim2.fromOffset(8,2);header.Size=UDim2.fromOffset(420,30)
    header.BackgroundTransparency=1;header.Text=title;header.TextColor3=Color3.new(1,1,1)
    header.Font=Enum.Font.Code;header.TextSize=13
    local mini=Instance.new('TextButton',panel);mini.Name='Minimize'
    mini.Position=UDim2.fromOffset(442,4);mini.Size=UDim2.fromOffset(28,26);mini.Text='–'
    local body=Instance.new('Frame',panel);body.Name='Body';body.BackgroundTransparency=1
    body.Position=UDim2.fromOffset(0,34);body.Size=UDim2.fromOffset(480,334)
    local self=setmetatable({panel=panel,body=body,header=header,mini=mini,minimized=false},Window)
    connect(mini.Activated,function()self:toggle()end)
    local drag
    connect(header.InputBegan,function(event)
        if canDrag()and(event.UserInputType==Enum.UserInputType.MouseButton1 or event.UserInputType==Enum.UserInputType.Touch)then
            drag={at=event.Position,position=panel.Position,event=event}
        end
    end)
    connect(input.InputChanged,function(event)
        if drag and(event==drag.event or event.UserInputType==Enum.UserInputType.MouseMovement)then
            local delta=event.Position-drag.at
            local camera=game:GetService('Workspace').CurrentCamera
            local size=camera and camera.ViewportSize or Vector3.new(1920,1080,0)
            panel.Position=UDim2.fromOffset(math.clamp(drag.position.X.Offset+delta.X,0,math.max(0,size.X-480)),
                math.clamp(drag.position.Y.Offset+delta.Y,0,math.max(0,size.Y-34)))
        end
    end)
    connect(input.InputEnded,function(event)
        if drag and(event==drag.event or event.UserInputType==Enum.UserInputType.MouseButton1)then drag=nil end
    end)
    return self
end
function Window:toggle()
    self.minimized=not self.minimized;self.body.Visible=not self.minimized
    self.panel.Size=UDim2.fromOffset(480,self.minimized and 34 or 372)
    self.mini.Text=self.minimized and '+'or '–'
end
return Window
