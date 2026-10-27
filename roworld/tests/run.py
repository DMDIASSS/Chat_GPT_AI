"""Run Luau behavior tests, standalone compilation, and UI teardown checks.

Usage: python roworld/tests/run.py --luau /path/to/luau --compiler /path/to/luau-compile
"""
import argparse
import importlib.util
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--luau", default="luau")
    parser.add_argument("--compiler", default="luau-compile")
    args = parser.parse_args()
    spec = importlib.util.spec_from_file_location("roworld_build", ROOT / "build.py")
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    source = build.source()
    assert (ROOT / "RoWorld_Bot.lua").read_text(encoding="utf8") == source, "Rebuild the standalone script"
    for name in ("test_policy.lua", "test_adapter.lua"):
        subprocess.run([args.luau, str(ROOT / "tests" / name)], check=True, timeout=30)
    compiled = subprocess.run([args.compiler, str(ROOT / "RoWorld_Bot.lua")], capture_output=True, text=True, timeout=30)
    assert compiled.returncode == 0, compiled.stderr
    fixture = (ROOT / "tests/client_fixture.lua").read_text(encoding="utf8")
    assertions = r'''
local first = assert(env.__RoWorldBot)
assert(first.alive and not first.enabled)
local toggle, label, buttons = nil, nil, 0
for _, obj in ipairs(created) do
    if obj.ClassName == "TextButton" then buttons += 1; toggle = obj end
    if obj.ClassName == "TextLabel" and obj.Name == "Status" then label = obj end
end
assert(buttons == 1 and toggle.Text == "Start bot")
step(); assert(not first.enabled and #warnings == 0)
toggle.Activated:Fire(); step()
assert(first.enabled and label.Text:find("Waiting for the RoWorld client"))
toggle.Activated:Fire(); step()
assert(not first.enabled and toggle.Text == "Start bot")
input.InputBegan:Fire({KeyCode = Enum.KeyCode.F6}, false); step(); assert(first.enabled)
local world = makeWorld()
cachedMain = world.main
local scripts, client, module = object("PlayerScripts"), object("LocalScript"), object("ModuleScript")
services.Players.LocalPlayer.children.PlayerScripts = scripts
scripts.children.AirfrontClient = client
client.children.Main = module
for _ = 1,18 do step() end
assert(#world.session.sent > 0 and world.session.sent[1].type == "attack")
toggle.Activated:Fire()
local count = #world.session.sent
for _ = 1,6 do step() end
assert(#world.session.sent == count and not first.enabled)
'''
    after = r'''
local second = assert(env.__RoWorldBot)
assert(second ~= first and not first.alive and not first.enabled)
assert(second.alive and not second.enabled)
for _, c in ipairs(first.connections) do assert(not c.active) end
step()
second.destroy(); step()
assert(env.__RoWorldBot == nil and not second.alive and #warnings == 0)
print("PASS", "single button, waiting status, stop, hotkey and reinjection teardown")
'''
    with tempfile.TemporaryDirectory() as directory:
        test = Path(directory) / "client_test.luau"
        # Each injection has its own locals, just as separate executor runs do.
        world_fixture = "local makeWorld = (function()\n" + (ROOT / "tests/fixture.lua").read_text(encoding="utf8") + "\nend)()\n"
        test.write_text(fixture + world_fixture + "\ndo\n" + source + "\nend\n" + assertions + "\ndo\n" + source + "\nend\n" + after,
                        encoding="utf8")
        subprocess.run([args.luau, str(test)], check=True, timeout=30)
    print("PASS standalone generation and Luau compilation")


if __name__ == "__main__":
    main()
