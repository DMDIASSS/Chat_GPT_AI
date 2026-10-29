-- Optional local loader. Put RoWorld_V3.lua in the JJSploit workspace first.
-- Pasting the complete RoWorld_V3.lua directly also works; no file/HTTP API required.
assert(type(readfile)=='function','Paste the complete RoWorld_V3.lua into your executor instead')
local source=readfile('RoWorld_V3.lua')
assert(type(source)=='string' and source:find('RoWorld 3.0.0',1,true),'Wrong file; copy RoWorld_V3.lua into the executor workspace')
local run,reason=loadstring(source)
assert(run,reason)
run()
