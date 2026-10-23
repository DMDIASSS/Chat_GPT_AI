-- Execute this complete file after START_FILE_BOT.bat says READY FILE MODE.
-- Reads only the client installed in your executor workspace. No HTTP.
print("[botrblx] File launcher executed")
local gui,report
local function show(text)
    print("[botrblx] "..text)
    if report then report.Text="botrblx file launcher\n"..text end
end
local ok,err=pcall(function()
    local pg=assert(game:GetService("Players").LocalPlayer:FindFirstChildOfClass("PlayerGui"),"Join first")
    assert(not pg:FindFirstChild("Update271Loader"),"Close the old launcher panel first")
    gui=Instance.new("ScreenGui")
    gui.Name="Update271Loader";gui.ResetOnSpawn=false;gui.DisplayOrder=1000072
    local panel=Instance.new("Frame",gui)
    panel.Size=UDim2.fromOffset(470,200);panel.Position=UDim2.fromOffset(20,190)
    panel.BackgroundColor3=Color3.fromRGB(18,22,30)
    report=Instance.new("TextBox",panel)
    report.Name="StartupReport";report.Position=UDim2.fromOffset(10,10)
    report.Size=UDim2.new(1,-20,1,-55)
    report.ClearTextOnFocus=false;report.MultiLine=true;report.TextWrapped=true
    report.BackgroundTransparency=1;report.TextColor3=Color3.new(1,1,1)
    report.TextSize=14;report.Font=Enum.Font.Code
    local close=Instance.new("TextButton",panel)
    close.Size=UDim2.new(1,-20,0,30);close.Position=UDim2.new(0,10,1,-35)
    close.Text="Close launcher"
    close.Activated:Connect(function()gui:Destroy()end)
    gui.Parent=pg
    show("Checking executor file functions...")
    assert(type(readfile)=="function"and type(writefile)=="function",
        "This executor needs both readfile and writefile for file mode")
    local loaded,source=pcall(readfile,"botrblx_client.lua")
    assert(loaded and type(source)=="string"and #source>0,
        "botrblx_client.lua was not found. Start START_FILE_BOT.bat and select this executor's workspace folder. "..tostring(source):sub(1,180))
    assert(type(loadstring)=="function","loadstring unavailable")
    local run,compileError=loadstring(source)
    assert(type(run)=="function",compileError or "Lua compilation failed")
    local result=run()
    if type(result)=="table"and result.started then gui:Destroy()
    else show("Read the Update271 panel for startup errors.")end
end)
if not ok then show("STOPPED\n"..tostring(err).."\nClick this text, Ctrl+A, Ctrl+C to copy.")end
