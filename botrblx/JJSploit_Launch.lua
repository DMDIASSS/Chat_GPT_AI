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
-- HTTP_COMPAT_BEGIN: inline copy shared by the launcher and standalone client.
local http_preferred
local function http_response_detail(value)
    if type(value)~="table"then return "returned "..type(value)end
    local fields={}
    for key,item in pairs(value)do
        fields[#fields+1]=tostring(key)..":"..type(item)..(type(item)=="string"and "("..#item..")"or "")
        if #fields>=10 then break end
    end
    table.sort(fields)
    local code=value.StatusCode or value.Status or value.status_code or value.status
    local message=value.StatusMessage or value.status_message or value.Error or value.error or value.Message
    return "fields={"..table.concat(fields,",").."}; status="..tostring(code)
        ..(type(message)=="string"and "; message="..message:sub(1,160)or "")
end
local function http_response_parts(first,second)
    if first==false then return nil,nil,"returned false: "..tostring(second):sub(1,160)end
    local value=first
    if (value==nil or value==true)and second~=nil then value=second;second=nil end
    local body,code
    if type(value)=="string"then body=value
    elseif type(value)=="table"then
        code=value.StatusCode or value.Status or value.status_code or value.status
        for _,key in ipairs({"Body","body","ResponseBody","responseBody"})do
            if type(value[key])=="string"and #value[key]>0 then body=value[key];break end
        end
    end
    if (not body or #body==0)and type(second)=="string"and #second>0 then body=second end
    if type(body)~="string"or #body==0 then
        return nil,nil,"no response body; "..http_response_detail(value)
    end
    local status=code~=nil and tonumber(code)or nil
    if code~=nil and not status then return nil,nil,"Unrecognized HTTP status: "..tostring(code)end
    return body,status
end
local function http_request_checked(options)
    local candidates={}
    local function add(name,fn)
        if type(fn)~="function"then return end
        for _,entry in ipairs(candidates)do if entry.fn==fn then return end end
        candidates[#candidates+1]={name=name,fn=fn}
    end
    if http_preferred then add(http_preferred.name,http_preferred.fn)end
    add("request",request);add("http_request",http_request)
    assert(#candidates>0,"HTTP request function unavailable")
    local errors={}
    for _,entry in ipairs(candidates)do
        local ok,first,second=pcall(entry.fn,options)
        if ok then
            local body,status,detail=http_response_parts(first,second)
            if body then http_preferred=entry;return body,status end
            errors[#errors+1]=entry.name..": "..detail
        else
            errors[#errors+1]=entry.name..": "..tostring(first):sub(1,240)
        end
    end
    error("No usable HTTP response. "..table.concat(errors," | "),0)
end
-- HTTP_COMPAT_END

task.spawn(function()
    local success,errorText=pcall(function()
        stage="GET http://127.0.0.1:28771/client"
        show(stage.."\nKeep START_BOT.bat open.")
        local fetched,body,status=pcall(http_request_checked,{Url="http://127.0.0.1:28771/client",Method="GET",Timeout=3})
        if cancelled then return end
        if not fetched then
            local failure=body
            stage="reading local client after HTTP failure"
            show(tostring(failure).."\nTrying client271.lua in the executor workspace...")
            body=nil
            if type(readfile)=="function"then
                for _,path in ipairs({"botrblx/client271.lua","client271.lua"})do
                    local read_ok,source=pcall(readfile,path)
                    if read_ok and type(source)=="string"and #source>0 then
                        body=source;show("Loaded local "..path);break
                    end
                end
            end
            assert(body,tostring(failure).."\nLocal client unavailable. You can execute client271.lua directly instead of this launcher.")
            status=nil
        end
        if cancelled then return end
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
