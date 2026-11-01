"""Append an isolated script tree to RBXL without reserializing original objects.

Every original INST, PROP, SSTR and metadata chunk is copied verbatim. Only header
counts and the PRNT relationship table change; all original parent pairs survive.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import hashlib
from pathlib import Path
import struct

MAGIC = b"<roblox!\x89\xff\r\n\x1a\n"


def u32(value):
    return struct.pack("<I", value)


def string(value):
    value = value.encode("utf-8")
    return u32(len(value)) + value


def references(values):
    encoded, previous = [], 0
    for value in values:
        delta = value - previous
        previous = value
        encoded.append(((delta << 1) ^ (delta >> 31)) & 0xFFFFFFFF)
    return b"".join(bytes((value >> shift) & 255 for value in encoded)
                    for shift in (24, 16, 8, 0))


def read_references(data, count):
    if len(data) != count * 4:
        raise ValueError("Incorrect reference array length")
    out, previous = [], 0
    for i in range(count):
        value = sum(data[plane * count + i] << shift
                    for plane, shift in enumerate((24, 16, 8, 0)))
        previous += (value >> 1) ^ -(value & 1)
        out.append(previous)
    return out


def chunk(tag, payload):
    return struct.pack("<4sIII", tag, 0, len(payload), 0) + payload


@dataclass
class Chunk:
    tag: bytes
    raw: bytes
    payload: bytes


class Place:
    def __init__(self, data):
        if data[:14] != MAGIC or struct.unpack_from("<H", data, 14)[0] != 0:
            raise ValueError("Expected a version 0 binary Roblox place")
        self.data, self.header = data, data[:32]
        self.class_count, self.instance_count = struct.unpack_from("<II", data, 16)
        self.chunks, self.classes, self.names = [], {}, {}
        self.children, self.parents = [], []
        at = 32
        while at < len(data):
            if at + 16 > len(data):
                raise ValueError("Truncated chunk header")
            tag, compressed, size, reserved = struct.unpack_from("<4sIII", data, at)
            end = at + 16 + (compressed or size)
            if end > len(data):
                raise ValueError("Truncated chunk")
            payload = data[at + 16:end]
            if compressed:
                if payload.startswith(b"\x28\xb5\x2f\xfd"):
                    import zstandard
                    payload = zstandard.ZstdDecompressor().decompress(payload, max_output_size=size)
                else:
                    import lz4.block
                    payload = lz4.block.decompress(payload, uncompressed_size=size)
            if len(payload) != size:
                raise ValueError("Incorrect decompressed size")
            self.chunks.append(Chunk(tag, data[at:end], payload))
            at = end
            if tag == b"INST":
                class_id, length = struct.unpack_from("<II", payload)
                name = payload[8:8 + length].decode("utf-8")
                service = bool(payload[8 + length])
                count = struct.unpack_from("<I", payload, 9 + length)[0]
                refs = read_references(payload[13 + length:13 + length + 4 * count], count)
                if class_id in self.classes:
                    raise ValueError("Duplicate class group")
                self.classes[class_id] = (name, refs, service)
            elif tag == b"PROP":
                class_id, length = struct.unpack_from("<II", payload)
                name = payload[8:8 + length].decode("utf-8")
                if name == "Name" and payload[8 + length] == 1:
                    pos = 9 + length
                    for ref in self.classes[class_id][1]:
                        n = struct.unpack_from("<I", payload, pos)[0]
                        self.names[ref] = payload[pos + 4:pos + 4 + n].decode("utf-8")
                        pos += 4 + n
            elif tag == b"PRNT":
                if payload[0] != 0 or self.children:
                    raise ValueError("Expected one version 0 parent table")
                count = struct.unpack_from("<I", payload, 1)[0]
                self.children = read_references(payload[5:5 + count * 4], count)
                self.parents = read_references(payload[5 + count * 4:], count)
            elif tag == b"END\x00":
                if at != len(data):
                    raise ValueError("Unexpected bytes after END")
        all_refs = [ref for _, refs, _ in self.classes.values() for ref in refs]
        if len(all_refs) != self.instance_count or len(set(all_refs)) != len(all_refs):
            raise ValueError("Invalid original instance counts")
        if set(all_refs) != set(self.children):
            raise ValueError("Incomplete hierarchy")
        self.all_refs = set(all_refs)
        self.parent_map = dict(zip(self.children, self.parents))

    def service(self, name):
        matches = [ref for cls, refs, _ in self.classes.values() if cls == name for ref in refs]
        if len(matches) > 1:
            raise ValueError(f"Ambiguous service {name}")
        return matches[0] if matches else None


def add_expansion(data: bytes, src: Path):
    original = Place(data)
    if "BackseatExpedition" in original.names.values():
        raise ValueError("This place already contains the expansion; no changes made")
    nodes = []
    next_ref = max(original.all_refs, default=-1) + 1

    def add(cls, name, parent=-1, source=None, service=False):
        nonlocal next_ref
        node = dict(cls=cls, name=name, parent=parent, ref=next_ref, source=source, service=service)
        next_ref += 1
        nodes.append(node)
        return node["ref"]

    def service(name, parent=-1):
        ref = original.service(name)
        return ref if ref is not None else add(name, name, parent, service=True)

    rs = service("ReplicatedStorage")
    sss = service("ServerScriptService")
    sp = service("StarterPlayer")
    sps = service("StarterPlayerScripts", sp)
    shared = add("Folder", "BackseatExpedition", rs)
    shared_modules = add("Folder", "Shared", shared)
    remotes = add("Folder", "Remotes", shared)
    for name, cls in (("Action", "RemoteEvent"), ("Request", "RemoteFunction"),
                      ("State", "UnreliableRemoteEvent"), ("Input", "UnreliableRemoteEvent")):
        add(cls, name, remotes)
    server = add("Folder", "BackseatExpeditionServer", sss)
    client = add("Folder", "BackseatExpeditionClient", sps)
    for group, parent in (("Shared", shared_modules), ("Server", server), ("Client", client)):
        for path in sorted((src / group).glob("*.lua")):
            cls = "Script" if ".server." in path.name else "LocalScript" if ".client." in path.name else "ModuleScript"
            add(cls, path.name.split(".")[0], parent, path.read_text())
    groups = defaultdict(list)
    for node in nodes:
        groups[node["cls"]].append(node)
    new_chunks = []
    next_class = max(original.classes, default=-1) + 1
    for cls, group in groups.items():
        class_id = next_class
        next_class += 1
        is_service = any(n["service"] for n in group)
        inst = u32(class_id) + string(cls) + bytes([is_service]) + u32(len(group))
        inst += references([n["ref"] for n in group])
        if is_service:
            inst += bytes(n["service"] for n in group)
        new_chunks.append(chunk(b"INST", inst))

        def prop(name, kind, values):
            new_chunks.append(chunk(b"PROP", u32(class_id) + string(name) + bytes([kind]) + values))

        prop("Name", 1, b"".join(string(n["name"]) for n in group))
        if any(n["source"] is not None for n in group):
            prop("Source", 1, b"".join(string(n["source"] or "") for n in group))
        if cls in ("Script", "LocalScript"):
            prop("Disabled", 2, bytes(len(group)))
    children = original.children + [n["ref"] for n in nodes]
    parents = original.parents + [n["parent"] for n in nodes]
    parent_chunk = chunk(b"PRNT", b"\x00" + u32(len(children)) + references(children) + references(parents))
    header = bytearray(original.header)
    struct.pack_into("<II", header, 16, next_class, original.instance_count + len(nodes))
    out = bytes(header)
    for existing in original.chunks:
        if existing.tag == b"PRNT":
            out += b"".join(new_chunks) + parent_chunk
        else:
            out += existing.raw
    report = verify_addition(data, out)
    report["added_objects"] = [{k: n[k] for k in ("ref", "cls", "name", "parent")} for n in nodes]
    return out, report


def verify_addition(before, after):
    original, result = Place(before), Place(after)
    retained = [c.raw for c in result.chunks]
    position = 0
    for c in original.chunks:
        if c.tag == b"PRNT":
            continue
        while position < len(retained) and retained[position] != c.raw:
            position += 1
        if position == len(retained):
            raise AssertionError(f"Original {c.tag!r} chunk was changed or removed")
        position += 1
    for ref, parent in original.parent_map.items():
        if result.parent_map.get(ref) != parent:
            raise AssertionError(f"Original instance {ref} was moved or removed")
    return {
        "base_sha256": hashlib.sha256(before).hexdigest(),
        "result_sha256": hashlib.sha256(after).hexdigest(),
        "original_instances": original.instance_count,
        "result_instances": result.instance_count,
        "added_instances": result.instance_count - original.instance_count,
        "original_class_and_property_chunks_byte_identical": True,
        "original_parent_relationships_unchanged": True,
        "existing_scripts_disabled_moved_or_deleted": 0,
    }
