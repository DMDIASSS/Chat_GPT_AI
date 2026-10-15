-- Paste this file as plain Lua, using GitHub Raw or the code block Copy button.
print("[botrblx] Launcher executed")
local gui,report,cancelled
local stage="creating launcher panel"
local function show(message)
    print("[botrblx] "..message)
    if report and not cancelled then report.Text="botrblx launcher\n"..message end
end
local ok,err=pcall(function()
    local player=assert(game:GetService("Players").LocalPlayer,"Join the game first")
    local pg=assert(player:FindFirstChildOfClass("PlayerGui"),"PlayerGui unavailable")
    local existing=pg:FindFirstChild("Update271Loader")
    assert(not existing,"A launcher is already open. Close its panel before running again.")
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
    report.TextXAlignment=Enum.TextXAlignment.Left;report.TextYAlignment=Enum.TextYAlignment.Top
    local close=Instance.new("TextButton",panel)
    close.Size=UDim2.new(1,-20,0,30);close.Position=UDim2.new(0,10,1,-35)
    close.Text="Close launcher"
    close.Activated:Connect(function()cancelled=true;gui:Destroy()end)
    gui.Parent=pg
end)
if not ok then warn("[botrblx] Cannot show launcher: "..tostring(err));return end
show("Starting. A separate bot panel will appear after the client loads.")
task.spawn(function()
    local success,errorText=pcall(function()
        stage="selecting HTTP request function"
        local f=type(request)=="function"and request or http_request
        assert(type(f)=="function","HTTP request function unavailable")
        stage="GET http://127.0.0.1:28771/client"
        show(stage.."\nKeep START_BOT.bat open.")
        local response=f({Url="http://127.0.0.1:28771/client",Method="GET",Timeout=3})
        if cancelled then return end
        local body,status
        if type(response)=="string"then
            body=response
        elseif type(response)=="table"then
            body=response.Body or response.body
            local code=response.StatusCode or response.Status or response.status_code or response.status
            if code~=nil then
                status=tonumber(code)
                assert(status,"Unrecognized HTTP status: "..tostring(code))
            end
        end
        assert(type(body)=="string"and #body>0,"HTTP response has no Lua body")
        assert(not status or status==200,"HTTP "..tostring(status)..": "..body:sub(1,200))
        stage="compiling downloaded Lua"
        show("Received "..#body.." bytes. "..stage.."...")
        assert(type(loadstring)=="function","loadstring is unavailable")
        local run,compileError=loadstring(body)
        assert(type(run)=="function",compileError or "Lua compilation failed")
        stage="starting client"
        show("Starting the client and its control panel...")
        local result=run()
        if cancelled then return end
        if type(result)=="table"and result.started==true then
            show("Client panel created. Focus Roblox and click Start bot or press F6.")
            gui:Destroy()
        else
            show("Client returned without startup confirmation. Read any other bot panel.\nIf none appeared, update the complete botrblx folder and restart START_BOT.bat.")
        end
    end)
    if not success and not cancelled then
        show("STOPPED at "..stage.."\n"..tostring(errorText).."\nClick this text, Ctrl+A, Ctrl+C to copy the error.")
    end
end)
