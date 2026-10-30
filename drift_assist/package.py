"""Build and byte-check a ZIP containing only this independent assist and its own sources."""
import hashlib
import importlib.util
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT.parent / "downloads" / "HowToDrift_Assist.zip"


def main():
    spec = importlib.util.spec_from_file_location("drift_build", ROOT / "build.py")
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    (ROOT / "HowToDrift_Assist.lua").write_text(builder.source(), encoding="utf8", newline="\n")
    files = sorted(p for p in ROOT.rglob("*") if p.is_file() and p.suffix in (".lua", ".py", ".md", ".json")
                   and "__pycache__" not in p.parts and p.name != "SOURCE_INFO.json")
    manifest = {"version": "1.3.0", "entrypoint": "HowToDrift_Assist.lua", "files": {
        p.relative_to(ROOT).as_posix(): {"sha256": hashlib.sha256(p.read_bytes()).hexdigest(), "bytes": p.stat().st_size}
        for p in files}, "uploaded_place_sha256": "b89c3d8616755662bcd2e642de1f4ea08b89e3a114852a4754b32a179c00ae32",
        "includes_original_game_sources": False}
    info = ROOT / "SOURCE_INFO.json"
    info.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf8")
    files.append(info)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUTPUT, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for p in files:
            item = zipfile.ZipInfo("HowToDrift_Assist/" + p.relative_to(ROOT).as_posix(), (2026, 10, 31, 0, 0, 0))
            item.compress_type = zipfile.ZIP_DEFLATED
            item.external_attr = 0o644 << 16
            archive.writestr(item, p.read_bytes())
    with zipfile.ZipFile(OUTPUT) as archive:
        assert archive.testzip() is None
        assert len(archive.namelist()) == len(files)
        for p in files:
            name = "HowToDrift_Assist/" + p.relative_to(ROOT).as_posix()
            assert archive.read(name) == p.read_bytes(), name
    print(json.dumps({"zip": str(OUTPUT), "bytes": OUTPUT.stat().st_size,
                      "sha256": hashlib.sha256(OUTPUT.read_bytes()).hexdigest(), "files": len(files)}, indent=2))


if __name__ == "__main__":
    main()
