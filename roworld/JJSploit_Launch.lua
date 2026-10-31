-- Put RoWorld_Bot.lua directly inside the JJSploit workspace first.
assert(type(readfile) == "function", "Paste the full RoWorld_Bot.lua instead; readfile is unavailable")
assert(type(loadstring) == "function", "loadstring is unavailable")
local ok, source = pcall(readfile, "RoWorld_Bot.lua")
assert(ok and type(source) == "string", "Copy RoWorld_Bot.lua into the JJSploit workspace first")
local run, err = loadstring(source, "RoWorld_Bot")
assert(run, err)
run()
