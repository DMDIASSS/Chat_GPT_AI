"""Offline Luau simulator worker; the very same observation/actions/model run in game.

Original game sources are supplied locally by the user, never fetched from OpenFront.
"""
import hashlib
import importlib.util
import json
import posixpath
import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("roworld_v3_build", ROOT/"build.py")
build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(build)


def engine_source(path):
    bundle = json.loads(Path(path).read_text(encoding="utf8"))
    modules = bundle["modules"]
    digest = hashlib.sha256(json.dumps(modules, sort_keys=True).encode()).hexdigest()
    if digest != bundle["engine_sha256"]:
        raise ValueError("Simulator bundle hash mismatch; prepare it again")
    collected = {}

    def add(key):
        if key in collected:
            return
        if key == "Net/Coop":
            collected[key] = "return {check=function() end,checkpoint=function() end}"
            return
        code = modules[key]
        collected[key] = ""

        def replace(match):
            name = posixpath.normpath(posixpath.join(posixpath.dirname(key), match[1]))
            add(name)
            return "load(" + json.dumps(name) + ")"

        collected[key] = re.sub(r'require\("([^"\n]+)"\)', replace, code)

    for key in ("Core/Sim", "Core/WorldMap", "Core/Rules"):
        add(key)
    source = "local factories,cache={},{}\nlocal function load(key) if cache[key] then return cache[key] end;cache[key]=assert(factories[key],key)();return cache[key] end\n"
    for key, code in collected.items():
        source += "factories[" + json.dumps(key) + "]=function()\n" + code + "\nend\n"
    return source, digest


def run(luau, engine, weights, seed, seconds=180, stage=1, stochastic=True, opponent=None):
    original, digest = engine_source(engine)
    config = {"seed": seed, "seconds": seconds, "stage": stage, "stochastic": stochastic}
    source = original + build.modules_source()
    source += "\nlocal weights=" + build.literal(weights) + "\nlocal opponentWeights=" + build.literal(opponent)
    source += "\nlocal config=" + build.literal(config) + "\n" + (ROOT/"training/worker.lua").read_text(encoding="utf8")
    with tempfile.TemporaryDirectory(prefix="roworld-v3-") as directory:
        script = Path(directory)/"worker.luau"
        script.write_text(source, encoding="utf8")
        result = subprocess.run([str(luau), str(script)], capture_output=True, text=True, timeout=max(120, seconds*2))
        if result.returncode:
            raise RuntimeError(result.stderr[-5000:] or result.stdout[-5000:])
        for line in reversed(result.stdout.splitlines()):
            if line.startswith("ROWORLD_EPISODE "):
                episode = json.loads(line.removeprefix("ROWORLD_EPISODE "))
                episode["engine_sha256"] = digest
                return episode
        raise RuntimeError("Simulator worker returned no episode: " + result.stdout[-3000:])
