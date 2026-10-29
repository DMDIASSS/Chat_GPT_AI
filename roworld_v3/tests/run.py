"""No training dependencies required: behavior, transport regression, generated source and UI lifecycle."""
import argparse
import importlib.util
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--luau", default="luau")
    p.add_argument("--compiler", default="luau-compile")
    args = p.parse_args()
    spec = importlib.util.spec_from_file_location("build_v3", ROOT/"build.py")
    build = importlib.util.module_from_spec(spec);spec.loader.exec_module(build)
    source = build.source()
    assert (ROOT/"RoWorld_V3.lua").read_text(encoding="utf8")==source
    for name in ("test_adapter.lua","test_network.lua","test_weapons.lua","test_agent.lua","test_coalition.lua"):
        subprocess.run([args.luau,str(ROOT/"tests"/name)],check=True,timeout=30)
    compiled = subprocess.run([args.compiler,str(ROOT/"RoWorld_V3.lua")],capture_output=True,text=True,timeout=30)
    assert compiled.returncode==0,compiled.stderr
    fixture = (ROOT/"tests/client_fixture.lua").read_text(encoding="utf8")
    world = "local makeWorld=(function()\n"+(ROOT/"tests/fixture.lua").read_text(encoding="utf8")+"\nend)()\n"
    checks = r'''
local first=assert(env.__RoWorldBot)
assert(first.alive and not first.enabled and first.helpFriends)
local toggle,export,friends,status
for _,o in ipairs(created) do
 if o.Name=='Toggle' then toggle=o elseif o.Name=='ExportReport' then export=o elseif o.Name=='FriendsToggle' then friends=o elseif o.Name=='Status' then status=o end
end
friends.Activated:Fire();assert(not first.helpFriends)
export.Activated:Fire();assert(status.Text:find('Executor file writing unavailable'))
toggle.Activated:Fire();step();assert(first.enabled)
local f=makeWorld();cachedMain=f.main
local scripts,client,module=object('PlayerScripts'),object('LocalScript'),object('ModuleScript')
services.Players.LocalPlayer.children.PlayerScripts=scripts;scripts.children.AirfrontClient=client;client.children.Main=module
for _=1,18 do f.state.tick+=1;step() end
assert(#f.session.sent>0 and f.session.sent[1].type=='attack')
local files={}
services.HttpService={JSONEncode=function(_,r) assert(r.version=='3.1.0' or r.version==1);return 'json' end}
writefile=function(name,body) files[name]=body end
export.Activated:Fire();assert(files['RoWorld_Match_Report.json'] and first.report().schema=='roworld-observation-v1')
toggle.Activated:Fire();local count=#f.session.sent
for _=1,4 do f.state.tick+=1;step() end
assert(#f.session.sent==count and not first.enabled)
'''
    after = r'''
local second=assert(env.__RoWorldBot)
assert(second~=first and not first.alive and not first.enabled and second.alive and not second.enabled and not second.helpFriends)
for _,c in ipairs(first.connections) do assert(not c.active) end
second.destroy();step();assert(env.__RoWorldBot==nil and #warnings==0)
print('PASS V3 dashboard, report, stop, friend toggle and reinjection lifecycle')
'''
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/"lifecycle.luau"
        path.write_text(fixture+world+"\ndo\n"+source+"\nend\n"+checks+"\ndo\n"+source+"\nend\n"+after,encoding="utf8")
        subprocess.run([args.luau,str(path)],check=True,timeout=30)
    print("PASS V3 generated source and standalone compilation")


if __name__=="__main__":
    main()
