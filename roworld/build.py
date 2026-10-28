"""Build a self-contained executor script; no HTTP or local bridge at runtime."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def source():
    parts = ["-- RoWorld Bot 2.1.0 | paste this entire file into JJSploit.\n"
             "-- No external script downloads or localhost bridge.\n"]
    modules = ("Weapons", "Cooperation", "Core", "Atlas", "Profiles", "Planner", "Investment", "Strategy",
               "Diplomacy", "Recorder", "Policy", "Adapter", "Wire", "Mirror", "Network")
    for name in modules:
        parts.append(f"local {name} = (function()\n")
        module = (ROOT / (name.lower() + ".lua")).read_text(encoding="utf8")
        for dependency in modules:
            module = module.replace(f'local {dependency} = require("./{dependency.lower()}")', '')
        parts.append(module)
        parts.append("\nend)()\n")
    parts.append((ROOT / "client.lua").read_text(encoding="utf8"))
    return "\n".join(parts)


if __name__ == "__main__":
    target = ROOT / "RoWorld_Bot.lua"
    target.write_text(source(), encoding="utf8", newline="\n")
    print(target)
