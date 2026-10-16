-- Installed/configured as botrblx_diagnose.lua by DIAGNOSE.bat.
-- File API diagnostics only: no model, game modules, remotes or input events.
local gui,box,progress
local report={schema=1,capabilities={},static={},own={},generations={},warnings={}}
local function clean(value)
    local text=tostring(value)
    -- Redact the full bearer value before a generic Authorization key can
    -- remove its scheme word and leave the credential behind.
    text=text:gsub("([Bb][Ee][Aa][Rr][Ee][Rr]%s+)[%w_%.%-]+","%1<redacted>")
    for _,key in ipairs({"token","api_key","authorization","password","secret"})do
        local pattern=key:gsub("%a",function(c)return "["..c:lower()..c:upper().."]"end)
        text=text:gsub('("'..pattern..'"%s*:%s*")[^"]*"','%1<redacted>"')
        text=text:gsub("("..pattern.."%s*[=:]%s*)[^%s,;}]+","%1<redacted>")
    end
    return text:sub(1,240)
end
local function stage(text)
    if progress then progress.Text=text end
    print("[botrblx diagnostics] "..text)
end
local shown,showError=pcall(function()
    local player=assert(game:GetService("Players").LocalPlayer,"Join first")
    local pg=assert(player:FindFirstChildOfClass("PlayerGui"),"PlayerGui unavailable")
    assert(not pg:FindFirstChild("BotrblxDiagnostics"),"Close the old diagnostic panel first")
    gui=Instance.new("ScreenGui")
    gui.Name="BotrblxDiagnostics";gui.ResetOnSpawn=false;gui.DisplayOrder=1000075
    local panel=Instance.new("Frame",gui)
    panel.Position=UDim2.fromScale(.05,.08);panel.Size=UDim2.fromScale(.9,.84)
    panel.BackgroundColor3=Color3.fromRGB(18,22,30)
    progress=Instance.new("TextLabel",panel)
    progress.Position=UDim2.fromOffset(10,5);progress.Size=UDim2.new(1,-20,0,48)
    progress.BackgroundTransparency=1;progress.TextColor3=Color3.new(1,1,1)
    progress.Font=Enum.Font.Code;progress.TextSize=14;progress.TextWrapped=true
    box=Instance.new("TextBox",panel)
    box.Name="DiagnosticReport";box.Position=UDim2.fromOffset(10,55)
    box.Size=UDim2.new(1,-20,1,-100);box.MultiLine=true;box.ClearTextOnFocus=false
    box.TextEditable=false;box.TextWrapped=false;box.TextSize=12;box.Font=Enum.Font.Code
    box.TextXAlignment=Enum.TextXAlignment.Left;box.TextYAlignment=Enum.TextYAlignment.Top
    box.TextColor3=Color3.new(1,1,1);box.BackgroundColor3=Color3.fromRGB(12,15,21)
    box.Text="Diagnostics starting. The completed report stays here for copying."
    local close=Instance.new("TextButton",panel)
    close.Position=UDim2.new(0,10,1,-35);close.Size=UDim2.new(1,-20,0,30)
    close.Text="Close diagnostics"
    close.Activated:Connect(function()gui:Destroy()end)
    gui.Parent=pg
end)
if not shown then warn("[botrblx diagnostics] "..clean(showError));return end

local http=game:GetService("HttpService") -- JSON only.
local function api(fn,...)
    local began=os.clock()
    if type(fn)~="function"then return {ok=false,type=type(fn),error="API unavailable",ms=0}end
    local ok,value=pcall(fn,...)
    local result={ok=ok,type=type(value),ms=math.floor((os.clock()-began)*1000+.5)}
    if not ok then result.error=clean(value)
    elseif type(value)=="boolean"or type(value)=="number"then result.value=value
    elseif type(value)=="string"then result.bytes=#value end
    return result
end
local function read(path,expected)
    local began=os.clock()
    if type(readfile)~="function"then return {ok=false,type=type(readfile),match=false,error="readfile unavailable",ms=0}end
    local ok,body=pcall(readfile,path)
    local result={ok=ok,type=type(body),match=false,ms=math.floor((os.clock()-began)*1000+.5)}
    if not ok then result.error=clean(body)
    elseif type(body)=="string"then
        result.bytes=#body
        result.match=expected~=nil and body==expected
    end
    return result
end
local function aliases(item,r)
    item.read_ok=r.ok;item.matches=r.match;item.value_type=r.type;item.error=r.error
end
local function publicText()
    local ok,encoded=pcall(function()return http:JSONEncode(report)end)
    return ok and encoded or "Report JSON encoding failed: "..clean(encoded)
end
local function run()
    local config
    local ok,errorText=pcall(function()
        config=http:JSONDecode([====[__BOTRBLX_DIAGNOSTIC_CONFIG_JSON__]====])
        assert(type(config)=="table"and config.schema==1 and type(config.nonce)=="string",
            "Run DIAGNOSE.bat first, then execute the configured botrblx_diagnose.lua")
        report.nonce=config.nonce
        report.context={place_id=game.PlaceId,account=game:GetService("Players").LocalPlayer.Name}
        stage("Diagnostic run "..config.nonce..". Testing file API; no driving inputs.")
        local functions={readfile=readfile,writefile=writefile,isfile=isfile,isfolder=isfolder,
            makefolder=makefolder,delfile=delfile,listfiles=listfiles,request=request,http_request=http_request}
        for _,name in ipairs({"readfile","writefile","isfile","isfolder","makefolder","delfile","listfiles","request","http_request"})do
            report.capabilities[name]=type(functions[name])
        end
        if type(identifyexecutor)=="function"then
            local named,name,revision=pcall(identifyexecutor)
            report.executor=named and {name=clean(name),version=clean(revision)}or {error=clean(name)}
        end
        for index,spec in ipairs(config.cases or {})do
            stage("Static paths "..index.."/"..#config.cases.." ("..spec.id..")")
            local r=read(spec.path,spec.expected)
            local item={id=spec.id,path=spec.path,kind=spec.kind,read=r,
                isfile=api(isfile,spec.path),isfolder=api(isfolder,spec.path)}
            aliases(item,r)
            if spec.kind=="directory"and type(listfiles)=="function"then
                -- Only list the dedicated diagnostic folder. Never list the
                -- workspace root or copy arbitrary filenames into the report.
                local listed,entries=pcall(listfiles,spec.path)
                item.listfiles={ok=listed,type=type(entries)}
                if listed and type(entries)=="table"then item.listfiles.count=#entries
                elseif not listed then item.listfiles.error=clean(entries)end
            end
            report.static[#report.static+1]=item
            task.wait(.01)
        end
        for index,spec in ipairs(config.own_tests or {})do
            stage("Lua write/read "..index.."/"..#config.own_tests)
            local item={id=spec.id,path=spec.path}
            item.write_first=api(writefile,spec.path,spec.first)
            item.read_first=read(spec.path,spec.first)
            item.write_second=api(writefile,spec.path,spec.second)
            item.read_second=read(spec.path,spec.second)
            item.first_ok=item.write_first.ok and item.read_first.match
            item.second_ok=item.write_second.ok and item.read_second.match
            report.own[#report.own+1]=item
            task.wait(.01)
        end
        for _,generation in ipairs(config.generations or {})do
            stage("Python round trip / caching generation "..generation.id)
            local began=os.clock()
            local encoded=http:JSONEncode({nonce=config.nonce,kind="generation",generation=generation.id,seq=generation.id})
            local sent=api(writefile,config.control_path,encoded)
            local item={id=generation.id,expected=generation.expected,send=sent,results={}}
            for _,spec in ipairs(generation.paths or {})do
                item.results[#item.results+1]={id=spec.id,path=spec.path,match=false,matches=false,attempts=0}
            end
            local deadline=os.clock()+4
            if sent.ok then
                while os.clock()<deadline do
                    local remaining=0
                    for index,spec in ipairs(generation.paths or {})do
                        local result=item.results[index]
                        if not result.match then
                            local r=read(spec.path,generation.expected)
                            result.attempts=result.attempts+1
                            result.match=r.match;result.matches=r.match
                            result.read_ok=r.ok;result.value_type=r.type;result.error=r.error
                            result.bytes=r.bytes
                            if r.match then
                                result.ms=math.floor((os.clock()-began)*1000+.5)
                                result.latency_ms=result.ms
                            else remaining=remaining+1 end
                        end
                    end
                    if remaining==0 then break end
                    task.wait(.04)
                end
            end
            item.elapsed_ms=math.floor((os.clock()-began)*1000+.5)
            report.generations[#report.generations+1]=item
        end
    end)
    if not ok then report.warnings[#report.warnings+1]=clean(errorText)end
    report.complete=ok
    local encoded=publicText()
    local saved={ok=false,error="No configured output path"}
    if config and type(config.report_path)=="string"then saved=api(writefile,config.report_path,encoded)end
    if not saved.ok then
        report.warnings[#report.warnings+1]="Could not export the report: "..(saved.error or "writefile returned "..saved.type)
        encoded=publicText()
    end
    box.Text=encoded
    stage(saved.ok and "Finished. Check CMD for DIAGNOSTIC_REPORT.txt. Copyable Lua report below."
        or "Finished. Report export failed. Click the text, Ctrl+A, Ctrl+C and send it.")
end
task.spawn(run)
return {started=true,version=1}
