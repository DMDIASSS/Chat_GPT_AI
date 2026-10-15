-- File transport: generated into the standalone client instead of HTTP.
local fileHttp=game:GetService("HttpService") -- JSON/UUID only; no network calls.
local fileSession=fileHttp:GenerateGUID(false)
local fileId=0
local function bridge_call(path,packet,token)
    assert(type(readfile)=="function"and type(writefile)=="function",
        "File mode needs both readfile and writefile; this executor does not expose them")
    fileId=fileId+1
    local id=fileId
    local encoded=fileHttp:JSONEncode({session=fileSession,id=id,route=path,token=token or "",packet=packet})
    local wrote,writeError=pcall(writefile,"botrblx_exchange/request.json",encoded)
    assert(wrote,"Cannot write file telemetry. Select the executor workspace in START_FILE_BOT.bat: "..tostring(writeError))
    local deadline=os.clock()+1
    while os.clock()<deadline do
        assert(id==fileId,"File request superseded")
        local ok,body=pcall(readfile,"botrblx_exchange/response.json")
        if ok and type(body)=="string"then
            local decoded,response=pcall(function()return fileHttp:JSONDecode(body)end)
            if decoded and type(response)=="table"and response.session==fileSession and response.id==id then
                return fileHttp:JSONEncode(response.data),response.status
            end
        end
        task.wait(.005)
    end
    error("No file reply. Keep START_FILE_BOT.bat open and select the same executor workspace.",0)
end
