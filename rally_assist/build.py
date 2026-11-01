"""Build the standalone client from independent modules and numeric route data."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent


def literal(value):
    if isinstance(value,dict):
        return "{"+",".join("["+json.dumps(k)+"]="+literal(v) for k,v in value.items())+"}"
    if isinstance(value,list):return "{"+",".join(map(literal,value))+"}"
    if value is None:return "nil"
    if isinstance(value,bool):return "true" if value else "false"
    return json.dumps(value,allow_nan=False,ensure_ascii=True)


def source():
    text="-- Backseat Rally Assist 1.0.0 | F6 assists, F7 autodrive, F8 stop\n"
    text+="-- Independent controller; numeric stage/showcase reference, not a world-record claim.\n"
    for name,file in (("Route","route.lua"),("Driver","controller.lua"),("Ghost","ghost.lua"),
                      ("Input","input.lua"),("Adapter","adapter.lua")):
        text+="\nlocal "+name+"=(function()\n"+(ROOT/file).read_text()+"\nend)()\n"
    text+="\nlocal PROFILES="+literal(json.loads((ROOT/"stage_profiles.json").read_text()))+"\n"
    text+="local SHOWCASES="+literal(json.loads((ROOT/"showcase_lines.json").read_text()))+"\n"
    return text+(ROOT/"client.lua").read_text()


if __name__=="__main__":
    target=ROOT/"Backseat_Rally_Assist.lua"
    target.write_text(source(),encoding="utf-8",newline="\n")
    print(target)
