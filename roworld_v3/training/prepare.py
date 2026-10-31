"""Prepare a private simulator bundle from your supplied RoWorld v111 .rbxl or extracted scripts.

Never uploads or includes the game's source in a public release.
"""
import argparse
import hashlib
import json
import struct
from pathlib import Path

PLACE_SHA = "8be1727d80e44d4c1b0045b7ff7f19c39f8251e58efedca18f2243676f988399"


class Reader:
    def __init__(self, data):
        self.data, self.offset = data, 0

    def u32(self):
        value = struct.unpack_from("<I", self.data, self.offset)[0]
        self.offset += 4
        return value

    def byte(self):
        value = self.data[self.offset]
        self.offset += 1
        return value

    def string(self):
        n = self.u32()
        value = self.data[self.offset:self.offset+n]
        self.offset += n
        return value.decode("utf8", "replace")

    def refs(self, n):
        raw = self.data[self.offset:self.offset+n*4]
        self.offset += n*4
        refs, total = [], 0
        for i in range(n):
            value = sum(raw[j*n+i] << (24-8*j) for j in range(4))
            total += (value >> 1) ^ -(value & 1)
            refs.append(total)
        return refs


def extract(path):
    import lz4.block
    import zstandard
    data = path.read_bytes()
    sha = hashlib.sha256(data).hexdigest()
    if sha != PLACE_SHA:
        raise ValueError("Unsupported place hash. This adapter is verified against the supplied v111 place only.")
    nodes, classes, sources = {}, {}, {}
    offset = 32
    while offset+16 <= len(data):
        tag, compressed, size, _ = struct.unpack_from("<4sIII", data, offset)
        offset += 16
        raw = data[offset:offset+(compressed or size)]
        offset += len(raw)
        if compressed:
            raw = zstandard.ZstdDecompressor().decompress(raw, max_output_size=size) if raw.startswith(b"\x28\xb5\x2f\xfd") else lz4.block.decompress(raw, uncompressed_size=size)
        if len(raw) != size:
            raise ValueError("Corrupt place chunk")
        r = Reader(raw)
        if tag == b"INST":
            ident, name, _service, count = r.u32(), r.string(), r.byte(), r.u32()
            refs = r.refs(count)
            classes[ident] = refs
            for ref in refs:
                nodes[ref] = {"name": name, "parent": -1}
        elif tag == b"PROP":
            ident, prop, kind = r.u32(), r.string(), r.byte()
            if kind == 1:
                for ref in classes[ident]:
                    value = r.string()
                    if prop == "Name":
                        nodes[ref]["name"] = value
                    elif prop == "Source":
                        sources[ref] = value
        elif tag == b"PRNT":
            if r.byte() != 0:
                raise ValueError("Unsupported parent chunk")
            n = r.u32()
            children, parents = r.refs(n), r.refs(n)
            for child, parent in zip(children, parents):
                nodes[child]["parent"] = parent
        elif tag == b"END\x00":
            break
    result = {}
    for ref, source in sources.items():
        parts, seen = [], set()
        while ref in nodes and ref not in seen:
            seen.add(ref)
            parts.append(nodes[ref]["name"])
            ref = nodes[ref]["parent"]
        full = ".".join(reversed(parts))
        if full.startswith("ReplicatedStorage.Airfront."):
            result[full.removeprefix("ReplicatedStorage.Airfront.").replace(".", "/")] = source
    return result, sha


def main():
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--place", type=Path)
    mode.add_argument("--sources", type=Path, help="Existing scripts.json extraction, local development alternative")
    p.add_argument("--out", type=Path, default=Path("private/engine.json"))
    args = p.parse_args()
    if args.place:
        modules, source_sha = extract(args.place)
    else:
        modules = {r["path"].removeprefix("ReplicatedStorage.Airfront.").replace(".", "/"): (args.sources/r["file"]).read_text(encoding="utf8")
                   for r in json.loads((args.sources/"scripts.json").read_text()) if r["path"].startswith("ReplicatedStorage.Airfront.")}
        source_sha = "local-extracted-sources"
    for name in ("Core/Sim", "Core/WorldMap", "Core/Rules", "Core/SimAI"):
        if name not in modules:
            p.error("Missing original module " + name)
    digest = hashlib.sha256(json.dumps(modules, sort_keys=True).encode()).hexdigest()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"version": 1, "source_sha256": source_sha, "engine_sha256": digest, "modules": modules}), encoding="utf8")
    print(f"Private simulator ready: {args.out}; {len(modules)} modules. Nothing uploaded.")


if __name__ == "__main__":
    main()
