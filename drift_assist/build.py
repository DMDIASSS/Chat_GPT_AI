"""Build a pasteable Roblox client script; no external runtime dependencies."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MODULES = (("Controller", "controller.lua"), ("Roads", "roads.lua"), ("InputLease", "input_lease.lua"))


def source():
    code = "-- HowToDrift Assist 1.0.0 | client driving panel\n-- Built from reviewed local modules. No downloads, admin remotes, or score submission.\n"
    for name, filename in MODULES:
        code += f"\nlocal {name} = (function()\n{(ROOT/filename).read_text(encoding='utf8')}\nend)()\n"
    return code + "\n" + (ROOT / "client.lua").read_text(encoding="utf8")


if __name__ == "__main__":
    target = ROOT / "HowToDrift_Assist.lua"
    target.write_text(source(), encoding="utf8", newline="\n")
    print(target)
