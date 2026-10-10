#!/usr/bin/env python3
"""Read-only structural inspector for Blaku TAS Plugin .data files.

The field mapping is NOT verified: generic names are intentional.
Never run DLLs or load pickle files to inspect TAS inputs.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import struct
import sys

VERSION = 1
HEADER = struct.Struct("<II")
FRAME = struct.Struct("<I7f")
TAIL_SIZE = 128
MAX_FRAMES = 10_000_000

def inspect(path, csv_dir=None):
    path = Path(path)
    data = path.read_bytes()
    if len(data) < HEADER.size + TAIL_SIZE:
        raise ValueError("Too short for TAS header and state trailer")
    version, frames = HEADER.unpack_from(data)
    if version != VERSION:
        raise ValueError(f"Unsupported format version: {version}")
    if frames > MAX_FRAMES:
        raise ValueError("Frame count exceeds safety limit")
    expected = HEADER.size + FRAME.size * frames + TAIL_SIZE
    if expected != len(data):
        raise ValueError(f"Size mismatch: expected {expected}, got {len(data)}")
    first = HEADER.size
    trailer = data[first + FRAME.size * frames:]
    result = {
        "file": path.name,
        "sha256": hashlib.sha256(data).hexdigest(),
        "version": version,
        "frames": frames,
        "frame_bytes": FRAME.size,
        "trailer_bytes": TAIL_SIZE,
        "estimated_seconds_at_120hz": round(frames / 120, 3),
        "important": "Fields are RAW. Button-mask and float meanings have NOT been validated against plugin source.",
        "flag_values": {},
        "raw_float_ranges": {},
        "starting_state_trailer_hex": trailer.hex(),
    }
    flags = {}
    minima, maxima = [float("inf")] * 7, [float("-inf")] * 7
    csv_path = None
    writer = None
    if csv_dir:
        csv_dir = Path(csv_dir)
        csv_dir.mkdir(parents=True, exist_ok=True)
        csv_path = csv_dir / f"{path.stem}_raw_inputs.csv"
        f = csv_path.open("w", newline="", encoding="utf-8")
        writer = csv.writer(f)
        writer.writerow(["frame_index", "raw_uint32_flags"] + [f"raw_float_{i}" for i in range(1, 8)])
    try:
        for i in range(frames):
            mask, *values = FRAME.unpack_from(data, first + i * FRAME.size)
            flags[mask] = flags.get(mask, 0) + 1
            for j, v in enumerate(values):
                if math.isfinite(v):
                    minima[j] = min(minima[j], v)
                    maxima[j] = max(maxima[j], v)
            if writer:
                writer.writerow([i, mask, *values])
    finally:
        if writer:
            f.close()
    result["flag_values"] = {str(k): v for k, v in sorted(flags.items())}
    result["raw_float_ranges"] = {
        f"raw_float_{i+1}": [round(minima[i], 6), round(maxima[i], 6)]
        if minima[i] != float("inf") else None for i in range(7)
    }
    if csv_path:
        result["csv_path"] = str(csv_path)
    return result

def main():
    parser = argparse.ArgumentParser(description="Read-only Rocket League TAS binary structure inspector")
    parser.add_argument("files", nargs="+", help="One or more .data paths")
    parser.add_argument("--csv-dir", help="Optional folder for raw (unverified) input CSVs")
    parser.add_argument("--report", help="Optional JSON report filename")
    args = parser.parse_args()
    reports = []
    errors = []
    for name in args.files:
        try:
            result = inspect(name, args.csv_dir)
            reports.append(result)
            print(f"{result['file']}: {result['frames']} frame records; version {result['version']}; SHA {result['sha256'][:12]}")
        except (ValueError, OSError, struct.error) as exc:
            print(f"ERROR {name}: {exc}", file=sys.stderr)
            errors.append({"file": name, "error": str(exc)})
    if args.report:
        Path(args.report).write_text(json.dumps({"files": reports, "errors": errors}, indent=2), encoding="utf-8")
        print(f"Saved report: {args.report}")
    return 1 if errors else 0

if __name__ == "__main__":
    raise SystemExit(main())
