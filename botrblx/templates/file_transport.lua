-- File transport: generated into the standalone client instead of HTTP.
label.Text="Update271 file client v3.1: connecting to Python..."
local fileHttp=game:GetService("HttpService") -- JSON/UUID only; no network calls.
local fileSession=fileHttp:GenerateGUID(false)
local fileId=0
local function bridge_call(path,packet,token)
    assert(type(readfile)=="function"and type(writefile)=="function",
        "File mode needs both readfile and writefile; this executor does not expose them")
    fileId=fileId+1
    local id=fileId
    local replyPath="botrblx_exchange/replies/reply_"..fileSession.."_"..id..".json"
    local encoded=fileHttp:JSONEncode({session=fileSession,id=id,route=path,file_protocol=3,token=token or "",packet=packet})
    local wrote,writeError=pcall(writefile,"botrblx_exchange/request.json",encoded)
    assert(wrote,"Cannot write file telemetry. Select the executor workspace in START_FILE_BOT.bat: "..tostring(writeError))
    -- Some executor file calls yield for appreciable time. Handshakes carry no
    -- inputs and can wait longer; live telemetry still has the Python watchdog.
    local deadline=os.clock()+(path=="/hello"and 4 or 1)
    local detail="readfile was not called"
    while os.clock()<deadline do
        assert(id==fileId,"File request superseded")
        -- The executor's existence metadata need not reflect files published by
        -- Python. Always try the content read; missing files are retryable.
        local ok,body=pcall(readfile,replyPath)
        if not ok then
            detail="readfile failed: "..tostring(body):sub(1,160)
        elseif type(body)~="string"then
            detail="readfile returned "..type(body)..", expected string"
        else
            -- A BOM is not part of JSON but can be introduced by Windows tools.
            if body:sub(1,3)==string.char(239,187,191)then body=body:sub(4)end
            local decoded,response=pcall(function()return fileHttp:JSONDecode(body)end)
            if not decoded then
                detail="JSON decode failed ("..#body.." bytes) in request-specific reply"
            elseif type(response)~="table"then
                detail="decoded response is "..type(response)..", expected table"
            elseif response.session~=fileSession then
                detail="reply belongs to another client; close other bot panels/bridges"
            elseif tonumber(response.id)~=id then
                detail="reply id="..tostring(response.id)..", waiting for id="..id
            elseif response.file_protocol~=3 then
                detail="Python reply is not file transport v3"
            elseif type(response.data)~="table"or not tonumber(response.status)then
                detail="reply is missing data/status"
            else
                return fileHttp:JSONEncode(response.data),tonumber(response.status)
            end
        end
        task.wait(.01)
    end
    error("No matching file reply for request "..id..": "..detail..". Keep Python open (file transport v3).",0)
end
