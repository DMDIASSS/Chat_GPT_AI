"""Append an isolated script tree to RBXL without reserializing original objects.

Every original INST, PROP, SSTR and metadata chunk is copied verbatim. Only header
counts and the PRNT relationship table change; all original parent pairs survive.
Known exported-script faults are repaired through explicit Source overrides, with
original Sources copied into inert backup modules and changes listed in the report.
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



def property_rows(place, name):
    """Effective string properties; later PROP chunks replace earlier values."""
    rows = {}
    for block in place.chunks:
        if block.tag != b"PROP":
            continue
        cid, length = struct.unpack_from("<II", block.payload)
        prop = block.payload[8:8 + length].decode("utf-8")
        if prop != name or block.payload[8 + length] != 1:
            continue
        pos = 9 + length
        for ref in place.classes[cid][1]:
            size = struct.unpack_from("<I", block.payload, pos)[0]
            rows[ref] = block.payload[pos + 4:pos + 4 + size].decode("utf-8")
            pos += 4 + size
        if pos != len(block.payload):
            raise ValueError(f"Invalid {name} property length")
    return rows


def instance_paths(place):
    paths = {}
    def path(ref):
        if ref not in paths:
            parent = place.parent_map[ref]
            paths[ref] = (path(parent) + "." if parent != -1 else "") + place.names[ref]
        return paths[ref]
    for ref in place.all_refs:
        path(ref)
    return paths


def legacy_source_repairs(place):
    """Match known exported code narrowly; never guess a replacement backend."""
    repairs = []
    paths = instance_paths(place)
    for ref, before in property_rows(place, "Source").items():
        path, after, reasons = paths[ref], before, []
        if path == "ReplicatedStorage.Shared.Zone":
            old = 'if v2 and v2:FindFirstChild(v3) then\n    return require(v2.Value)\nend'
            new = ('-- DM: the exported reference can point back to this same Zone module.\n'
                   'if v2 and v2:IsA("ObjectValue") and v2.Value and v2.Value ~= script\n'
                   '    and v2.Value:IsA("ModuleScript") and v2:FindFirstChild(v3) then\n'
                   '    return require(v2.Value)\nend')
            if old in after:
                after = after.replace(old, new, 1)
                reasons.append("Reject self-requiring ZonePlus references")
        if path == "StarterPlayer.StarterPlayerScripts.Client.Init.Data.DataController":
            old = 'local t2 = {}'
            if old in after and 'function t1.Initialize()' in after:
                after = after.replace(old, old + '\nlocal _dmInitialized = false\nlocal _dmLastWarning = setmetatable({}, {__mode = "k"})', 1)
                warning = '    warn(("[DataController]: Data for user %* not found"):format(p5.UserId))'
                warning2 = '    warn((("[DataController]: Data for user %* not found"):format(p5.UserId)))'
                replacement = ('    local now = os.clock()\n'
                               '    if not _dmLastWarning[p5] or now - _dmLastWarning[p5] >= 30 then\n'
                               '        _dmLastWarning[p5] = now\n'
                               '        warn(("[DataController]: Waiting for session profile for user %*"):format(p5.UserId))\n'
                               '    end')
                if warning2 in after:
                    after = after.replace(warning2, replacement, 1)
                elif warning in after:
                    after = after.replace(warning, replacement, 1)
                after = after.replace('function t1.Initialize()', 'function t1.Initialize()\n    if _dmInitialized then return end\n    _dmInitialized = true', 1)
                after = after.replace('        t2[Player] = p7', '        _dmLastWarning[Player] = nil\n        t2[Player] = p7', 1)
                reasons.append("Register one replica listener and rate-limit missing-profile warnings")
        if path.startswith("StarterPlayer.PlayerModule."):
            replacements = {
                'script.Parent.Parent:WaitForChild("InputContexts")': '_dmLegacyInput.get(script.Parent.Parent)',
                'script.Parent:WaitForChild("InputContexts")': '_dmLegacyInput.get(script.Parent)',
                'script.Parent.Parent:FindFirstChild("InputContexts")': '_dmLegacyInput.get(script.Parent.Parent)',
                'script.Parent.Parent.InputContexts': '_dmLegacyInput.get(script.Parent.Parent)',
                'StarterPlayer.PlayerModule.InputContexts': '_dmLegacyInput.get(StarterPlayer.PlayerModule)',
            }
            for old, new in replacements.items():
                after = after.replace(old, new)
            if after != before:
                after = ('-- DM: restore the preserved native input graph when the export omits it at runtime.\n'
                         'local _dmLegacyInput = require(game:GetService("ReplicatedStorage"):WaitForChild("BackseatExpedition"):WaitForChild("Shared"):WaitForChild("LegacyInput"))\n' + after)
                reasons.append("Resolve the preserved native input graph without infinite waits")
        if after != before:
            repairs.append(dict(ref=ref, path=path, before=before, after=after, reason="; ".join(reasons)))
    return repairs

def add_expansion(data: bytes, src: Path):
    original = Place(data)
    if "BackseatExpedition" in original.names.values():
        raise ValueError("This place already contains the expansion; no changes made")
    repairs = legacy_source_repairs(original)
    nodes = []
    next_ref = max(original.all_refs, default=-1) + 1

    def add(cls, name, parent=-1, source=None, service=False):
        nonlocal next_ref
        node = dict(cls=cls, name=name, parent=parent, ref=next_ref, source=source, service=service)
        next_ref += 1
        nodes.append(node)
        return node["ref"]

    def service(name, parent=-1, is_service=True):
        ref = original.service(name)
        return ref if ref is not None else add(name, name, parent, service=is_service)

    rs = service("ReplicatedStorage")
    sss = service("ServerScriptService")
    sp = service("StarterPlayer")
    sps = service("StarterPlayerScripts", sp, is_service=False)
    shared = add("Folder", "BackseatExpedition", rs)
    shared_modules = add("Folder", "Shared", shared)
    remotes = add("Folder", "Remotes", shared)
    for name, cls in (("Action", "RemoteEvent"), ("Request", "RemoteFunction"),
                      ("State", "RemoteEvent"), ("Input", "UnreliableRemoteEvent")):
        add(cls, name, remotes)
    # Mirror the actual native InputAction graph, including key codes and scales.
    paths = instance_paths(original)
    selected = {ref for ref, path in paths.items()
                if path.startswith("StarterPlayer.PlayerModule.InputContexts.")}
    native_map = {}
    if selected:
        context_root = add("Folder", "LegacyInputContexts", shared)
        old_root = next(ref for ref, path in paths.items()
                        if path == "StarterPlayer.PlayerModule.InputContexts")
        native_map[old_root] = context_root
        for cid, (cls, refs, _) in original.classes.items():
            chosen = set(refs) & selected
            if chosen:
                if chosen != set(refs):
                    raise ValueError(f"Cannot safely clone a partial native input class: {cls}")
                for ref in refs:
                    native_map[ref] = add(cls, original.names[ref])
                    nodes[-1]["native_class"] = cid
        for node in nodes:
            if "native_class" in node:
                old_ref = next(ref for ref, new_ref in native_map.items() if new_ref == node["ref"])
                node["parent"] = native_map[original.parent_map[old_ref]]
    if repairs:
        storage = service("ServerStorage")
        backups = add("Folder", "BackseatLegacySourceBackups", storage)
        for repair in repairs:
            repair["backup_ref"] = add("ModuleScript", str(repair["ref"]) + "_" + original.names[repair["ref"]], backups, repair["before"])
            nodes[-1]["source_backup"] = True
    server = add("Folder", "BackseatExpeditionServer", sss)
    client = add("Folder", "BackseatExpeditionClient", sps)
    for group, parent in (("Shared", shared_modules), ("Server", server), ("Client", client)):
        for path in sorted((src / group).glob("*.lua")):
            cls = "Script" if ".server." in path.name else "LocalScript" if ".client." in path.name else "ModuleScript"
            add(cls, path.name.split(".")[0], parent, path.read_text())
    groups = defaultdict(list)
    for node in nodes:
        groups[(node["cls"], node.get("native_class"))].append(node)
    new_chunks = []
    next_class = max(original.classes, default=-1) + 1
    for (cls, native_class), group in groups.items():
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
        if native_class is not None:
            for block in original.chunks:
                if block.tag != b"PROP":
                    continue
                cid, length = struct.unpack_from("<II", block.payload)
                name = block.payload[8:8 + length].decode()
                kind, values = block.payload[8 + length], block.payload[9 + length:]
                if cid != native_class or name in ("Name", "UniqueId", "HistoryId"):
                    continue
                if kind == 19:
                    values = references([native_map.get(ref, ref) for ref in read_references(values, len(group))])
                prop(name, kind, values)
            prop("Archivable", 2, bytes([1]) * len(group))
        if any(n["source"] is not None for n in group):
            prop("Source", 1, b"".join(string(n["source"] or "") for n in group))
        if cls in ("Script", "LocalScript"):
            prop("Disabled", 2, bytes(len(group)))
    if repairs:
        repaired_sources = {repair["ref"]: repair["after"] for repair in repairs}
        sources = property_rows(original, "Source")
        for cid, (_, refs, _) in original.classes.items():
            if not set(refs) & set(repaired_sources):
                continue
            payload = u32(cid) + string("Source") + b"\x01"
            payload += b"".join(string(repaired_sources.get(ref, sources.get(ref, ""))) for ref in refs)
            # Original raw chunks remain; this final property is the explicit patch.
            import zstandard
            compressed = zstandard.ZstdCompressor(level=7).compress(payload)
            new_chunks.append(struct.pack("<4sIII", b"PROP", len(compressed), len(payload), 0) + compressed)
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
    changes = [{k: r[k] for k in ("ref", "path", "reason", "backup_ref")} | {
        "before_sha256": hashlib.sha256(r["before"].encode()).hexdigest(),
        "after_sha256": hashlib.sha256(r["after"].encode()).hexdigest(),
    } for r in repairs]
    report = verify_addition(data, out, allowed_source_changes=changes)
    report["legacy_source_changes"] = changes
    report["native_input_graph_objects_added"] = len(native_map)
    report["added_objects"] = [{k: n[k] for k in ("ref", "cls", "name", "parent")} |
                               ({"source_backup": True} if n.get("source_backup") else {}) for n in nodes]
    return out, report


def verify_addition(before, after, allowed_source_changes=()):
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
    allowed = {r["ref"]: r for r in allowed_source_changes}
    old_sources, new_sources = property_rows(original, "Source"), property_rows(result, "Source")
    changed = {ref for ref, source in old_sources.items() if new_sources.get(ref) != source}
    if changed != set(allowed):
        raise AssertionError(f"Unapproved Source changes: actual={sorted(changed)}, allowed={sorted(allowed)}")
    for ref, repair in allowed.items():
        if hashlib.sha256(old_sources[ref].encode()).hexdigest() != repair["before_sha256"]:
            raise AssertionError(f"Original Source hash mismatch: {ref}")
        if hashlib.sha256(new_sources[ref].encode()).hexdigest() != repair["after_sha256"]:
            raise AssertionError(f"Repaired Source hash mismatch: {ref}")
        if new_sources.get(repair["backup_ref"]) != old_sources[ref]:
            raise AssertionError(f"Original Source backup mismatch: {ref}")
    # A second PROP can silently replace an earlier one. Compare effective encoded
    # properties too; retaining the original bytes alone is insufficient.
    def effective(place):
        props = {}
        for block in place.chunks:
            if block.tag == b"PROP":
                cid, n = struct.unpack_from("<II", block.payload)
                name = block.payload[8:8+n].decode()
                if cid in original.classes:
                    props[(cid, name)] = block.payload
        return props
    old_props, new_props = effective(original), effective(result)
    for key in set(old_props) | set(new_props):
        if old_props.get(key) != new_props.get(key):
            cid, name = key
            if name != "Source" or not set(original.classes[cid][1]) & set(allowed):
                raise AssertionError(f"Original effective property changed: {key}")
    return {
        "base_sha256": hashlib.sha256(before).hexdigest(),
        "result_sha256": hashlib.sha256(after).hexdigest(),
        "original_instances": original.instance_count,
        "result_instances": result.instance_count,
        "added_instances": result.instance_count - original.instance_count,
        "original_class_and_property_chunks_byte_identical": True,
        "effective_original_properties_unchanged_except_listed_sources": True,
        "effective_original_source_changes": len(changed),
        "original_parent_relationships_unchanged": True,
        "existing_scripts_disabled_moved_or_deleted": 0,
    }


def standalone_base():
    """Small native floor and spawn point; no imported scripts or asset references."""
    def number(value):
        bits = struct.unpack('<I', struct.pack('<f', value))[0]
        return struct.pack('>I', ((bits << 1) | (bits >> 31)) & 0xFFFFFFFF)

    def vector(x, y, z):
        return number(x) + number(y) + number(z)

    def frame(x, y, z):
        return b'\x00' + struct.pack('<9f', 1, 0, 0, 0, 1, 0, 0, 0, 1) + vector(x, y, z)

    blocks = []
    for cid, cls, name, ref, is_service in (
        (0, 'Workspace', 'Workspace', 0, True),
        (1, 'Part', 'PreviewFloor', 1, False),
        (2, 'SpawnLocation', 'PreviewSpawn', 2, False),
    ):
        payload = u32(cid) + string(cls) + bytes([is_service]) + u32(1) + references([ref])
        if is_service:
            payload += b'\x01'
        blocks.append(chunk(b'INST', payload))
        blocks.append(chunk(b'PROP', u32(cid) + string('Name') + b'\x01' + string(name)))

    def prop(cid, name, kind, value):
        blocks.append(chunk(b'PROP', u32(cid) + string(name) + bytes([kind]) + value))

    prop(0, 'StreamingEnabled', 2, b'\x01')
    prop(0, 'Gravity', 4, number(130))
    for cid in (1, 2):
        prop(cid, 'Anchored', 2, b'\x01')
        prop(cid, 'CanCollide', 2, b'\x01')
    prop(1, 'size', 14, vector(160, 2, 150))
    prop(1, 'CFrame', 16, frame(0, -1, 0))
    prop(2, 'size', 14, vector(10, 1, 8))
    prop(2, 'CFrame', 16, frame(0, .5, 18))
    prop(2, 'Transparency', 4, number(1))
    prop(2, 'Neutral', 2, b'\x01')
    blocks.append(chunk(b'PRNT', b'\x00' + u32(3) + references([0, 1, 2]) + references([-1, 0, 0])))
    blocks.append(chunk(b'END\x00', b'</roblox>'))
    return MAGIC + b'\x00\x00' + u32(3) + u32(3) + bytes(8) + b''.join(blocks)
