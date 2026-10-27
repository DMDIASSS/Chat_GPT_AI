"""Build a self-contained executor script; no HTTP or local bridge at runtime."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def source():
    parts = ["-- RoWorld Bot 1.0.0 | paste this entire file into JJSploit.\n"
             "-- No downloads, localhost bridge, or external service at runtime.\n"]
    for name in ("Policy", "Adapter"):
        parts.append(f"local {name} = (function()\n")
        parts.append((ROOT / (name.lower() + ".lua")).read_text(encoding="utf8"))
        parts.append("\nend)()\n")
    parts.append((ROOT / "client.lua").read_text(encoding="utf8"))
    return "\n".join(parts)


if __name__ == "__main__":
    target = ROOT / "RoWorld_Bot.lua"
    target.write_text(source(), encoding="utf8", newline="\n")
    print(target)
