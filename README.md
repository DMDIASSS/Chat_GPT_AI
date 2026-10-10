# TAS Data Inspector v1 — read-only

Examines binary `.data` recordings from Blaku's TAS Plugin, without loading or executing any DLL.

## Running (PowerShell)

```powershell
python tas_data_inspector.py "C:\path\to\shot.data" --csv-dir extracted --report report.json
```

You may pass multiple `.data` files. The script uses Python's standard library.

## Verified structure in the three provided examples

- First 4 bytes: little-endian format/version integer `1`.
- Next 4 bytes: frame count.
- Exactly `frame_count × 32` bytes follow: each record can be represented as a raw 32-bit field and seven raw IEEE-754 floats.
- Exactly 128 trailing bytes remain, consistent with a saved state block.

**Not yet verified:** semantics of flag bits and analog fields, interpretation of the 128-byte trailer, true capture tick rate, and reproducibility in RocketSim. Frame lengths at 120 Hz are estimates.

Do **not** use raw field names as Rocket League controller labels for training until validated. Realistic demonstration replay, physics compatibility, checkpoint safety, and behavioral cloning design are separate engineering tasks.

## Safety

The inspector never modifies `.data` files and does not load DLLs. The source/shot author and permission to reuse examples are separate concerns. Avoid using plugin injection outside allowed offline/freeplay conditions.
