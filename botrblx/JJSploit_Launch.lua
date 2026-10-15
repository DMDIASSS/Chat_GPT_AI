local f=request or http_request
assert(type(f)=="function","HTTP requests unavailable")
local r=f({Url="http://127.0.0.1:28771/client",Method="GET",Timeout=3})
assert(r and r.StatusCode==200 and type(r.Body)=="string","Start START_BOT.bat first")
local run,err=loadstring(r.Body)
assert(run,err)
run()
