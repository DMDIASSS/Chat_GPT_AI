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
