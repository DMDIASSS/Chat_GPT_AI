"""Bounded filesystem diagnostics for the Roblox bridge; sends no game inputs.

This program deliberately uses only Python's standard library. It never imports
bridge271, Torch, or executor internals and never reads live mailbox bodies.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import subprocess
import sys
import time


APP_DIR = Path(__file__).resolve().parent
SCHEMA = 1
PLACEHOLDER = "__BOTRBLX_DIAGNOSTIC_CONFIG_JSON__"
MAX_DOCUMENT = 1024 * 1024
SECRET_KEYS = re.compile(r"token|api[_-]?key|authorization|password|secret|cookie", re.I)


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def sanitize(value, depth=0):
    """Keep diagnostic data, redact credentials even inside exception strings."""
    if depth > 12:
        return "[depth limit]"
    if isinstance(value, dict):
        return {str(key)[:120]: "[REDACTED]" if SECRET_KEYS.search(str(key))
                else sanitize(item, depth + 1) for key, item in list(value.items())[:200]}
    if isinstance(value, (list, tuple)):
        return [sanitize(item, depth + 1) for item in value[:300]]
    if isinstance(value, str):
        value = re.sub(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+", "Bearer [REDACTED]", value)
        value = re.sub(
            r'''(?ix)(["']?(?:token|api[_-]?key|authorization|password|secret|cookie)["']?\s*[:=]\s*)
            (?:"[^"\r\n]*"|'[^'\r\n]*'|[^\s,;}]+)''',
            r"\1[REDACTED]", value)
        return value[:1600]
    if type(value) is float and not math.isfinite(value):
        return "[non-finite number]"
    if value is None or type(value) in (bool, int, float):
        return value
    return type(value).__name__


def read_json(path, limit=MAX_DOCUMENT):
    with Path(path).open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("JSON document exceeds diagnostic size limit")
    return json.loads(data)


def path_kind(path):
    path = Path(path)
    if path.is_symlink():
        return "symlink"
    if path.is_file():
        return "file"
    if path.is_dir():
        return "directory"
    return "missing" if not path.exists() else "other"


def resolve_workspace(workspace, config_path=APP_DIR / "file_connection.json", environ=None):
    environ = os.environ if environ is None else environ
    if workspace is None and Path(config_path).is_file():
        settings = read_json(config_path)
        if isinstance(settings, dict) and isinstance(settings.get("workspace"), str):
            workspace = settings["workspace"]
    if workspace is None and environ.get("APPDATA"):
        workspace = Path(environ["APPDATA"]) / "jjsploit" / "workspace"
    if workspace is None:
        raise ValueError("No workspace configured. Pass --workspace with JJSploit's workspace folder.")
    result = Path(workspace).expanduser().resolve()
    if not result.is_dir():
        raise ValueError("Executor workspace is not a directory: " + str(result))
    return result


class DiagnosticLock:
    def __init__(self, path):
        self.path = Path(path)
        self.acquired = False

    def __enter__(self):
        try:
            fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as error:
            raise RuntimeError("Another diagnostic is running, or its lock remains after a crash. "
                               "Close the other DIAGNOSE window first. If none is running, remove "
                               + str(self.path)) from error
        self.acquired = True
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump({"pid": os.getpid(), "started_utc": utc_now()}, stream)
        return self

    def __exit__(self, *_):
        if self.acquired:
            self.path.unlink(missing_ok=True)


class DiagnosticSession:
    def __init__(self, workspace, app_dir=APP_DIR, nonce=None, clock=time.monotonic):
        self.workspace = Path(workspace).resolve()
        self.app_dir = Path(app_dir)
        self.nonce = secrets.token_hex(6) if nonce is None else nonce
        if not re.fullmatch(r"[a-zA-Z0-9_-]{6,32}", self.nonce):
            raise ValueError("Invalid diagnostic nonce")
        self.prefix = "botrblx_diag_" + self.nonce
        self.clock = clock
        self.events = []
        self.owned_files = set()
        self.owned_dirs = set()
        self.first_seen = {}
        self.generation_methods = {}
        self.last_seq = -1
        self.generation_ids = set()
        self.installed = None
        self.installed_before = None
        self.installed_bytes = None
        self.config = {
            "schema": SCHEMA, "nonce": self.nonce,
            "control_path": self.prefix + "_control.json",
            "report_path": self.prefix + "_report.json",
            "cases": [], "own_tests": [], "generations": [],
        }
        self.started_utc = utc_now()

    def event(self, name, **details):
        self.events.append(sanitize({"event": name, "utc": utc_now(), **details}))

    def local_path(self, relative):
        """Only resolve our namespace. Backslash aliases have Windows semantics."""
        if not isinstance(relative, str) or "\x00" in relative:
            raise ValueError("Invalid diagnostic path")
        normalized = relative.replace("\\", "/")
        pure = PurePosixPath(normalized)
        if pure.is_absolute() or ".." in pure.parts or ":" in normalized:
            raise ValueError("Diagnostic path escapes the workspace")
        parts = tuple(part for part in pure.parts if part != ".")
        if not parts or not (parts[0] == self.prefix or parts[0].startswith(self.prefix + "_")):
            raise ValueError("Diagnostic path is outside the owned namespace")
        result = self.workspace.joinpath(*parts)
        # Reject symlinks and junctions that would redirect our owned paths.
        if not result.resolve().is_relative_to(self.workspace):
            raise ValueError("Diagnostic path resolves outside the workspace")
        current = self.workspace
        for part in parts:
            current = current / part
            if current.is_symlink() or (hasattr(current, "is_junction") and current.is_junction()):
                raise ValueError("Diagnostic paths may not traverse links")
        return result

    def remember(self, relative):
        path = self.local_path(relative)
        self.first_seen.setdefault(path, path_kind(path))
        return path

    def ensure_parents(self, path):
        missing = []
        parent = path.parent
        while parent != self.workspace:
            if not parent.exists():
                missing.append(parent)
            elif not parent.is_dir():
                raise ValueError("Fixture parent is not a directory: " + str(parent))
            parent = parent.parent
        for directory in reversed(missing):
            directory.mkdir()
            self.owned_dirs.add(directory)

    def write(self, relative, contents, method="inplace"):
        path = self.remember(relative)
        if self.first_seen[path] != "missing" and path not in self.owned_files:
            raise FileExistsError("Refusing to overwrite a pre-existing diagnostic fixture: " + str(path))
        self.ensure_parents(path)
        if method == "atomic":
            temporary = self.local_path(relative + ".temporary")
            if temporary.exists() and temporary not in self.owned_files:
                raise FileExistsError("Pre-existing temporary fixture")
            self.owned_files.add(temporary)
            temporary.write_text(contents, encoding="utf-8")
            temporary.replace(path)
        else:
            path.write_text(contents, encoding="utf-8")
        self.owned_files.add(path)
        return path

    def prepare(self):
        marker = "BOTRBLX_DIAGNOSTIC:" + self.nonce + ":STATIC"
        variants = [
            ("root_txt", self.prefix + "_root.txt"),
            ("root_json", self.prefix + "_root.json"),
            ("root_long", self.prefix + "_reply_" + "a" * 42 + "_0000123456789.json"),
            ("one_txt", self.prefix + "/one.txt"),
            ("one_json", self.prefix + "/one.json"),
            ("deep_json", self.prefix + "/deep/reply_" + "b" * 38 + "_1.json"),
        ]
        for identifier, relative in variants:
            self.write(relative, marker)
            self.config["cases"].append(dict(id=identifier, path=relative, expected=marker, kind="file"))
        for identifier, relative in [
            ("one_backslash", self.prefix + "\\one.txt"),
            ("root_dot_forward", "./" + self.prefix + "_root.txt"),
            ("root_dot_backslash", ".\\" + self.prefix + "_root.txt"),
            ("deep_backslash", self.prefix + "\\deep\\reply_" + "b" * 38 + "_1.json"),
        ]:
            self.config["cases"].append(dict(id=identifier, path=relative, expected=marker, kind="file"))
        self.config["cases"].extend([
            dict(id="directory_control", path=self.prefix, expected=None, kind="directory"),
            dict(id="missing_control", path=self.prefix + "_absent.txt", expected=None, kind="missing"),
        ])
        for identifier, relative in [("own_root", self.prefix + "_own.txt"),
                                     ("own_nested", self.prefix + "/own.txt")]:
            self.remember(relative)
            self.config["own_tests"].append(dict(
                id=identifier, path=relative,
                first="BOTRBLX_DIAGNOSTIC:" + self.nonce + ":FIRST",
                second="BOTRBLX_DIAGNOSTIC:" + self.nonce + ":SECOND"))
        for generation in (1, 2):
            item = dict(id=generation,
                        expected=f"BOTRBLX_DIAGNOSTIC:{self.nonce}:GENERATION:{generation}", paths=[])
            for level, folder in [("root", ""), ("one", self.prefix + "/"),
                                  ("deep", self.prefix + "/deep/")]:
                for method in ("inplace", "atomic", "fresh"):
                    name = (self.prefix + "_" if level == "root" else "") + method
                    if method == "fresh":
                        name += "_g" + str(generation)
                    relative = folder + name + ".json"
                    identifier = level + "_" + method
                    item["paths"].append(dict(id=identifier, path=relative))
                    self.generation_methods[(generation, identifier)] = method
                    if method != "fresh" and generation == 1:
                        self.write(relative, "BOTRBLX_DIAGNOSTIC:" + self.nonce + ":GENERATION:0", method)
                    else:
                        self.remember(relative)
            self.config["generations"].append(item)
        for name in ("control_path", "report_path"):
            self.remember(self.config[name])
        self.event("fixtures_prepared", static_cases=len(self.config["cases"]), generations=2)
        return self.config

    def install(self):
        template = (self.app_dir / "JJSploit_Diagnose.lua").read_text(encoding="utf-8")
        if template.count(PLACEHOLDER) != 1:
            raise ValueError("Diagnostic Lua template must contain exactly one config placeholder")
        encoded = json.dumps(self.config, separators=(",", ":"), ensure_ascii=True)
        if "]====]" in encoded:
            raise ValueError("Invalid Lua config delimiter")
        contents = template.replace(PLACEHOLDER, encoded).encode("utf-8")
        path = self.workspace / "botrblx_diagnose.lua"
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise ValueError("botrblx_diagnose.lua is not a file in the executor workspace")
        self.installed_before = path.read_bytes() if path.exists() else None
        self.installed, self.installed_bytes = path, contents
        path.write_bytes(contents)
        self.event("lua_installed", path=path.name, sha256=hashlib.sha256(contents).hexdigest())

    def process_control(self):
        try:
            control = read_json(self.local_path(self.config["control_path"]), 4096)
        except (OSError, ValueError, UnicodeError):
            return False
        if not isinstance(control, dict) or control.get("nonce") != self.nonce:
            return False
        seq, generation = control.get("seq"), control.get("generation")
        if type(seq) is not int or seq < 0 or seq <= self.last_seq:
            return False
        if control.get("kind") != "generation" or type(generation) is not int or generation not in (1, 2):
            return False
        self.last_seq = seq
        if generation in self.generation_ids:
            return False
        if generation == 2 and 1 not in self.generation_ids:
            self.event("control_ignored", reason="generation 2 arrived before generation 1", seq=seq)
            return False
        self.generation_ids.add(generation)
        item = self.config["generations"][generation - 1]
        started = self.clock()
        published = []
        for test in item["paths"]:
            method = self.generation_methods[(generation, test["id"])]
            record = dict(id=test["id"], path=test["path"], method=method)
            try:
                path = self.write(test["path"], item["expected"], method)
                record.update(published=True, filesystem_kind=path_kind(path),
                              mtime_ns=path.stat().st_mtime_ns)
            except (OSError, ValueError) as error:
                record.update(published=False, error=str(error))
            published.append(record)
        self.event("generation_published", generation=generation, seq=seq,
                   elapsed_ms=round((self.clock() - started) * 1000, 2), paths=published)
        return True

    def receive_report(self):
        try:
            report = read_json(self.local_path(self.config["report_path"]))
        except (OSError, ValueError, UnicodeError):
            return None
        if not isinstance(report, dict) or type(report.get("schema")) is not int or report["schema"] != SCHEMA:
            return None
        if report.get("nonce") != self.nonce:
            return None
        self.event("lua_report_received")
        return sanitize(report)

    def filesystem_snapshot(self):
        items = []
        for case in self.config["cases"]:
            path = self.local_path(case["path"])
            items.append(dict(id=case["id"], path=case["path"], expected_kind=case["kind"],
                              actual_kind=path_kind(path)))
        own = []
        for test in self.config["own_tests"]:
            path = self.local_path(test["path"])
            kind = path_kind(path)
            matches = False
            if kind == "file":
                try:
                    with path.open("rb") as stream:
                        matches = stream.read(4097) == test["second"].encode("utf-8")
                except OSError:
                    pass
            own.append(dict(id=test["id"], path=test["path"], actual_kind=kind,
                            python_observed_final_write=matches))
        return dict(static=items, own=own)

    def cleanup(self):
        # Lua owns only these fixed paths; never traverse or remove unknown files.
        for relative in [self.config["control_path"], self.config["report_path"]] + [
                test["path"] for test in self.config["own_tests"]]:
            path = self.local_path(relative)
            if self.first_seen.get(path) == "missing":
                self.owned_files.add(path)
        for path in self.owned_files:
            try:
                if path.is_file() and not path.is_symlink():
                    path.unlink()
            except OSError:
                pass
        for directory in sorted(self.owned_dirs, key=lambda item: len(item.parts), reverse=True):
            try:
                if not directory.is_symlink():
                    directory.rmdir()
            except OSError:
                pass  # Preserve unexpected user files.
        if self.installed is not None:
            try:
                if self.installed.read_bytes() == self.installed_bytes:
                    if self.installed_before is None:
                        self.installed.unlink()
                    else:
                        self.installed.write_bytes(self.installed_before)
            except OSError:
                pass


def process_census():
    """Bounded read-only census. Command lines never leave the local filter."""
    if sys.platform != "win32":
        return {"status": "not_checked", "reason": "Windows process census only", "processes": []}
    script = r'''
$ErrorActionPreference = 'Stop'
$items = @(Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" | ForEach-Object {
    $kind = $null
    if ($_.CommandLine -match 'bridge271\.py') { $kind = 'bridge' }
    elseif ($_.CommandLine -match 'diagnostics\.py') { $kind = 'diagnostic' }
    if ($kind) { [pscustomobject]@{pid=[int]$_.ProcessId;kind=$kind} }
})
ConvertTo-Json -InputObject $items -Compress
'''
    try:
        result = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
                                capture_output=True, encoding="utf-8", errors="replace", timeout=4,
                                check=False)
        if result.returncode != 0:
            return {"status": "not_checked", "reason": "Windows process query failed", "processes": []}
        data = json.loads(result.stdout)
        if not isinstance(data, list):
            data = [data]
        filtered = [{"pid": item["pid"], "kind": item["kind"]} for item in data
                    if isinstance(item, dict) and type(item.get("pid")) is int
                    and item.get("kind") in ("bridge", "diagnostic")]
        return {"status": "checked", "processes": filtered[:30]}
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return {"status": "not_checked", "reason": "Windows process query unavailable or timed out",
                "processes": []}


def bridge_metadata(app_dir, project_root, workspace=None):
    """Fingerprints and whitelisted values only; never read session mailboxes."""
    app_dir, project_root = Path(app_dir), Path(project_root)
    result = {"python": sys.version.split()[0], "platform": sys.platform,
              "diagnostic_schema": SCHEMA, "sources": {}, "project": {}}
    for relative in ("bridge271.py", "file_transport.py", "client271.lua", "JJSploit_File_Client.lua",
                     "templates/file_transport.lua", "diagnostics.py", "JJSploit_Diagnose.lua"):
        path = app_dir / relative
        if path.is_file():
            contents = path.read_bytes()
            item = dict(sha256=hashlib.sha256(contents).hexdigest(), bytes=len(contents))
            if relative in ("file_transport.py", "templates/file_transport.lua"):
                versions = sorted(set(re.findall(rb"file_protocol\s*[=:]\s*(\d+)", contents)))
                item["file_protocols"] = [int(version) for version in versions]
            result["sources"][relative] = item
    for key, relative in {
            "project_python": ".venv/Scripts/python.exe",
            "model_271": "data/isolated/mechanics_curriculum/selected7_mechanics01/update_000271.pt",
            "nexto_base": "vendor/nexto/nexto-model.pt"}.items():
        path = project_root / relative
        result["project"][key] = {"kind": path_kind(path)}
        if path.is_file():
            result["project"][key]["bytes"] = path.stat().st_size
            if key != "project_python":
                digest = hashlib.sha256()
                with path.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)
                result["project"][key]["sha256"] = digest.hexdigest()
    result["model_validation"] = {"status": "not rerun; no Torch imported"}
    log_path = app_dir / "bridge.log"
    if log_path.is_file():
        with log_path.open("rb") as stream:
            stream.seek(max(0, log_path.stat().st_size - 65536))
            tail = stream.read(65536).decode("utf-8", errors="replace")
        # Only keep fixed known markers and timestamps, not arbitrary log text.
        for line in tail.splitlines():
            marker = next((name for name in ("MODEL_READY", "SELF_CHECK_OK") if name + ":" in line), None)
            if marker:
                timestamp = re.search(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d[,\.]\d+", line)
                result["model_validation"] = {"status": "previous bridge log contains " + marker,
                                              "log_timestamp": timestamp.group() if timestamp else None,
                                              "fresh_validation": False}
            ready = re.search(r"READY FILE MODE v(\d+)", line)
            if ready:
                result["last_logged_file_protocol"] = int(ready.group(1))
    result["input_testing"] = "not performed; no game controls or model inference started"
    result["relevant_processes"] = process_census()
    if workspace is not None:
        installed = Path(workspace) / "botrblx_client.lua"
        result["installed_client"] = {"kind": path_kind(installed)}
        if installed.is_file():
            source = installed.read_bytes()
            result["installed_client"].update(sha256=hashlib.sha256(source).hexdigest(), bytes=len(source))
            result["installed_client"]["file_protocols"] = [int(value) for value in sorted(set(
                re.findall(rb"file_protocol\s*[=:]\s*(\d+)", source)))]
            revision = re.search(rb"file client v(\d+(?:\.\d+)*)", source)
            if revision:
                result["installed_client"]["revision"] = revision.group(1).decode("ascii")
    return result


def conclusions(report):
    lua = report.get("lua") or {}
    lines = []
    static = lua.get("static", [])
    if isinstance(static, list):
        files = {item.get("id"): item for item in static if isinstance(item, dict)}
        working = [key for key, item in files.items() if item.get("matches") is True]
        failed = [key for key, item in files.items() if item.get("matches") is False
                  and key not in ("directory_control", "missing_control")]
        if working:
            lines.append("Executor read verified for: " + ", ".join(working))
        if failed:
            lines.append("Executor read failed/mismatched for: " + ", ".join(failed))
        root_ok = files.get("root_txt", {}).get("matches") is True
        nested_ok = files.get("one_txt", {}).get("matches") is True
        if root_ok and not nested_ok:
            lines.append("Flat files work while nested files fail: prefer a flat mailbox after reviewing this report.")
        if not root_ok and not nested_ok and files:
            lines.append("Python-created files were not readable through tested paths; no transport fix is proven.")
        by_id = {item["id"]: item for item in report.get("filesystem", {}).get("static", [])}
        directory_errors = [key for key, item in files.items()
                            if by_id.get(key, {}).get("actual_kind") == "file"
                            and "got directory" in str(item.get("error", "")).lower()]
        if directory_errors:
            lines.append("Executor reports a directory where Python confirms a file: "
                         + ", ".join(directory_errors))
        if nested_ok and files.get("one_backslash", {}).get("matches") is False:
            lines.append("Forward slash works for the one-folder fixture; backslash does not.")
    generations = lua.get("generations", [])
    if isinstance(generations, list):
        second = next((item for item in generations if isinstance(item, dict) and item.get("id") == 2), {})
        values = {item.get("id"): item for item in second.get("results", []) if isinstance(item, dict)}
        fresh = [name for name, item in values.items() if name.endswith("fresh") and item.get("matches") is True]
        stale = [name for name, item in values.items() if name.endswith(("inplace", "atomic"))
                 and item.get("matches") is False]
        if fresh and stale:
            lines.append("Generation 2 fresh paths work while some reused paths fail; stale-read/cache behavior is possible. "
                         "Fresh: " + ", ".join(fresh) + "; failed reused: " + ", ".join(stale))
        delays = [item.get("latency_ms") for item in values.values()
                  if item.get("matches") is True and isinstance(item.get("latency_ms"), (int, float))]
        if delays:
            lines.append("Generation 2 successful reads took %.1f–%.1f ms after signaling publication." %
                         (min(delays), max(delays)))
    if report.get("status") != "COMPLETE":
        lines.append("Report transfer incomplete. Copy the diagnostic panel's report text into chat as a fallback.")
    own = report.get("filesystem", {}).get("own", [])
    if any(item.get("python_observed_final_write") for item in own):
        lines.append("Python verified at least one executor-written file in the selected workspace.")
    own_lua = {item.get("id"): item for item in lua.get("own", []) if isinstance(item, dict)}
    if any(item.get("python_observed_final_write") and own_lua.get(item.get("id"), {}).get("second_ok") is False
           for item in own):
        lines.append("Python sees a completed executor overwrite that the executor did not read back correctly.")
    processes = report.get("metadata", {}).get("relevant_processes", {}).get("processes", [])
    bridges = [item["pid"] for item in processes if item.get("kind") == "bridge"]
    if len(bridges) > 1:
        lines.append("Multiple bridge processes are running (PIDs " + ", ".join(map(str, bridges))
                     + "); they may clear each other's replies. No process was stopped.")
    if not lines:
        lines.append("Inspect individual test results below; no automatic transport change was made.")
    return lines


def save_report(session, status, lua_report, project_root, output_dir=None, error=None):
    output_dir = session.app_dir if output_dir is None else Path(output_dir)
    report = sanitize(dict(schema=SCHEMA, nonce=session.nonce, status=status,
                          started_utc=session.started_utc, finished_utc=utc_now(),
                          workspace=str(session.workspace), lua=lua_report,
                          filesystem=session.filesystem_snapshot(), python_events=session.events,
                          metadata=bridge_metadata(session.app_dir, project_root, session.workspace), error=error))
    report["findings"] = conclusions(report)
    output_dir.mkdir(parents=True, exist_ok=True)
    text_path = output_dir / "DIAGNOSTIC_REPORT.txt"
    json_path = output_dir / "DIAGNOSTIC_REPORT.json"
    text = ["BOTRBLX FILESYSTEM DIAGNOSTIC — schema 1", "Status: " + status,
            "Run: " + session.nonce, "Workspace: " + str(session.workspace),
            "No game controls, module requires, identity changes, or live mailbox contents.", ""]
    text.extend(report["findings"])
    text.extend(["", "DETAILS (sanitized)", json.dumps(report, indent=2, ensure_ascii=True, allow_nan=False)])
    text_path.write_text("\n".join(text) + "\n", encoding="utf-8")
    json_path.write_text(json.dumps(report, indent=2, ensure_ascii=True, allow_nan=False) + "\n", encoding="utf-8")
    return text_path, report


def run(args, app_dir=APP_DIR):
    app_dir = Path(app_dir)
    workspace = resolve_workspace(args.workspace, app_dir / "file_connection.json")
    project_root = Path(args.project_root).expanduser().resolve()
    session = DiagnosticSession(workspace, app_dir)
    result, lua_report, failure = "TIMEOUT", None, None
    with DiagnosticLock(app_dir / "diagnostics.lock"):
        try:
            session.prepare()
            session.install()
            print("READY DIAGNOSTIC | workspace " + str(workspace), flush=True)
            print("Close the bot panel and stop its bridge first. This diagnostic does not send game controls.", flush=True)
            print('Execute in JJSploit: loadstring(readfile("botrblx_diagnose.lua"))()', flush=True)
            print("Then wait for DIAGNOSTIC COMPLETE. Run: " + session.nonce, flush=True)
            deadline, next_progress = time.monotonic() + args.timeout, time.monotonic() + 15
            while time.monotonic() < deadline:
                if session.process_control():
                    print("GENERATION PUBLISHED: " + str(max(session.generation_ids)), flush=True)
                lua_report = session.receive_report()
                if lua_report is not None:
                    result = "COMPLETE"
                    break
                if time.monotonic() >= next_progress:
                    print("Waiting for executor diagnostic/report; "
                          + str(max(0, int(deadline - time.monotonic()))) + "s remaining...", flush=True)
                    next_progress = time.monotonic() + 15
                time.sleep(.01)
        except KeyboardInterrupt:
            result = "INTERRUPTED"
        except Exception as error:
            result, failure = "ERROR", str(error)
            session.event("error", message=str(error))
        finally:
            try:
                path, report = save_report(session, result, lua_report, project_root, error=failure)
                print("DIAGNOSTIC " + result + " | report: " + str(path), flush=True)
                for finding in report["findings"]:
                    print(finding, flush=True)
            finally:
                session.cleanup()
    return 0 if result == "COMPLETE" else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--project-root", type=Path, default=APP_DIR.parent)
    parser.add_argument("--timeout", type=float, default=300,
                        help="Maximum seconds to wait for Lua and its report (default: 300)")
    args = parser.parse_args(argv)
    if not 10 <= args.timeout <= 900:
        parser.error("--timeout must be between 10 and 900 seconds")
    try:
        return run(args)
    except (OSError, ValueError, RuntimeError) as error:
        print("DIAGNOSTIC ERROR: " + str(sanitize(str(error))), file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
