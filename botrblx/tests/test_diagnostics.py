import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


APP = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("botrblx_diagnostics", APP / "diagnostics.py")
d = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(d)


class DiagnosticTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.app = self.root / "app"
        self.app.mkdir()
        self.session = d.DiagnosticSession(self.workspace, self.app, nonce="test123456")
        self.addCleanup(self.session.cleanup)

    def prepare(self):
        return self.session.prepare()

    def control(self, generation, seq=None, **extra):
        value = {"nonce": self.session.nonce, "kind": "generation", "generation": generation,
                 "seq": generation if seq is None else seq}
        value.update(extra)
        self.session.local_path(self.session.config["control_path"]).write_text(json.dumps(value))

    def test_workspace_explicit_saved_default_and_missing(self):
        config = self.app / "file_connection.json"
        config.write_text(json.dumps({"workspace": str(self.workspace), "token": "ignored"}))
        self.assertEqual(d.resolve_workspace(None, config), self.workspace)
        self.assertEqual(d.resolve_workspace(self.workspace, config), self.workspace)
        default = self.root / "jjsploit" / "workspace"
        default.mkdir(parents=True)
        self.assertEqual(d.resolve_workspace(None, self.app / "absent", {"APPDATA": str(self.root)}), default)
        with self.assertRaises(ValueError):
            d.resolve_workspace(self.root / "missing", config)

    def test_namespace_paths_and_symlinks_are_guarded(self):
        for relative in ("../outside", "/tmp/foo", "C:\\outside", "other_file", "test123456"):
            with self.subTest(relative=relative), self.assertRaises(ValueError):
                self.session.local_path(relative)
        self.assertEqual(self.session.local_path(".\\botrblx_diag_test123456_root.txt"),
                         self.workspace / "botrblx_diag_test123456_root.txt")
        outside = self.root / "outside"
        outside.mkdir()
        (self.workspace / self.session.prefix).symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            self.session.local_path(self.session.prefix + "/foo.txt")
        (self.workspace / self.session.prefix).unlink()

    def test_fixture_layout_has_aliases_and_negative_controls(self):
        config = self.prepare()
        self.assertEqual(config["schema"], 1)
        self.assertEqual(len(config["generations"]), 2)
        self.assertEqual(len(config["generations"][0]["paths"]), 9)
        for case in config["cases"]:
            path = self.session.local_path(case["path"])
            self.assertEqual(d.path_kind(path), case["kind"])
            if case["kind"] == "file":
                self.assertEqual(path.read_text(), case["expected"])
        for gen in config["generations"]:
            for case in gen["paths"]:
                kind = d.path_kind(self.session.local_path(case["path"]))
                self.assertEqual(kind, "missing" if case["id"].endswith("fresh") else "file")

    def test_generation_publishing_strict_nonce_seq_order_and_duplicates(self):
        config = self.prepare()
        self.control(1, nonce="wrong")
        self.assertFalse(self.session.process_control())
        self.control(2)
        self.assertFalse(self.session.process_control())
        self.control(1, seq=3)
        self.assertTrue(self.session.process_control())
        times = [self.session.local_path(item["path"]).stat().st_mtime_ns
                 for item in config["generations"][0]["paths"]]
        self.assertFalse(self.session.process_control())
        self.control(1, seq=4)
        self.assertFalse(self.session.process_control())
        self.assertEqual(times, [self.session.local_path(item["path"]).stat().st_mtime_ns
                                for item in config["generations"][0]["paths"]])
        self.control(2, seq=5)
        self.assertTrue(self.session.process_control())
        for case in config["generations"][1]["paths"]:
            self.assertEqual(self.session.local_path(case["path"]).read_text(),
                             config["generations"][1]["expected"])
        self.assertEqual(len([event for event in self.session.events
                              if event["event"] == "generation_published"]), 2)

    def test_partial_and_oversized_control_and_report_are_ignored(self):
        config = self.prepare()
        control = self.session.local_path(config["control_path"])
        for data in ("{", "[]", "x" * 5000):
            control.write_text(data)
            self.assertFalse(self.session.process_control())
        report = self.session.local_path(config["report_path"])
        for value in ({"schema": 1, "nonce": "old"}, {"schema": True, "nonce": self.session.nonce},
                      {"schema": 2, "nonce": self.session.nonce}, []):
            report.write_text(json.dumps(value))
            self.assertIsNone(self.session.receive_report())
        report.write_text("{")
        self.assertIsNone(self.session.receive_report())

    def test_one_failed_publication_does_not_abort_other_variants(self):
        self.prepare()
        self.control(1)
        original = self.session.write

        def blocked_atomic(relative, contents, method="inplace"):
            if method == "atomic":
                raise PermissionError("test simulated locked publication")
            return original(relative, contents, method)

        with mock.patch.object(self.session, "write", side_effect=blocked_atomic):
            self.assertTrue(self.session.process_control())
        published = self.session.events[-1]["paths"]
        self.assertEqual(sum(item["published"] for item in published), 6)
        self.assertEqual(sum(not item["published"] for item in published), 3)

    def test_findings_explain_generation_cache_and_directory_mismatch(self):
        result = {"status": "COMPLETE", "lua": {
            "static": [{"id": "root_txt", "matches": True},
                       {"id": "one_txt", "matches": False, "error": "Expected File But Got Directory"}],
            "generations": [{"id": 2, "results": [
                {"id": "root_fresh", "matches": True, "latency_ms": 12},
                {"id": "root_inplace", "matches": False}]}]},
            "filesystem": {"static": [{"id": "one_txt", "actual_kind": "file"}], "own": []}}
        findings = "\n".join(d.conclusions(result))
        self.assertIn("confirms a file", findings)
        self.assertIn("stale-read/cache", findings)
        self.assertIn("12.0", findings)

    def test_report_validated_verified_merged_and_sanitized(self):
        config = self.prepare()
        for case in config["own_tests"]:
            self.session.local_path(case["path"]).write_text(case["second"])
        supplied = {"schema": 1, "nonce": self.session.nonce, "capabilities": {"readfile": "function"},
                    "static": [{"id": "root_txt", "matches": True},
                               {"id": "one_txt", "matches": False,
                                "error": "Expected File But Got Directory token=hidden"}],
                    "token": "credential", "authorization": "Bearer hidden"}
        self.session.local_path(config["report_path"]).write_text(json.dumps(supplied))
        lua = self.session.receive_report()
        self.assertEqual(lua["token"], "[REDACTED]")
        path, report = d.save_report(self.session, "COMPLETE", lua, self.root)
        self.assertTrue(path.is_file())
        self.assertTrue(path.with_suffix(".json").is_file())
        self.assertTrue(all(item["python_observed_final_write"] for item in report["filesystem"]["own"]))
        self.assertTrue(any("Flat files" in item for item in report["findings"]))
        self.assertNotIn("credential", path.read_text())
        self.assertNotIn("hidden", path.read_text())
        self.assertEqual(report["metadata"]["model_validation"]["status"], "not rerun; no Torch imported")

    def test_source_metadata_reads_only_fixed_markers_from_logs(self):
        (self.app / "bridge.log").write_text(
            '2026-10-16 00:00:00,001 MODEL_READY: policy returned 90 finite logits\n'
            'SECRET token=not-for-report\nREADY FILE MODE v3\n')
        model = self.root / "vendor/nexto/nexto-model.pt"
        model.parent.mkdir(parents=True)
        model.write_bytes(b"test-model-only")
        data = d.bridge_metadata(self.app, self.root)
        self.assertEqual(data["last_logged_file_protocol"], 3)
        self.assertFalse(data["model_validation"]["fresh_validation"])
        self.assertEqual(data["project"]["nexto_base"]["sha256"], d.hashlib.sha256(model.read_bytes()).hexdigest())
        self.assertNotIn("not-for-report", json.dumps(data))

    def test_process_census_only_returns_whitelisted_fields(self):
        output = '[{"pid":12,"kind":"bridge","CommandLine":"token=hide"},'
        output += '{"pid":13,"kind":"diagnostic"},{"pid":14,"kind":"other"}]'
        fake = d.subprocess.CompletedProcess([], 0, output, "")
        with mock.patch.object(d.sys, "platform", "win32"), mock.patch.object(d.subprocess, "run", return_value=fake):
            data = d.process_census()
        self.assertEqual(data["processes"], [{"pid": 12, "kind": "bridge"},
                                             {"pid": 13, "kind": "diagnostic"}])
        self.assertNotIn("CommandLine", json.dumps(data))
        with mock.patch.object(d.sys, "platform", "linux"):
            self.assertEqual(d.process_census()["status"], "not_checked")

    def test_installed_client_is_fingerprinted_without_dumping_contents(self):
        installed = self.workspace / "botrblx_client.lua"
        source = 'label.Text="Update271 file client v3.1"\nfile_protocol=3\n-- secret body'
        installed.write_text(source)
        data = d.bridge_metadata(self.app, self.root, self.workspace)
        self.assertEqual(data["installed_client"]["revision"], "3.1")
        self.assertEqual(data["installed_client"]["file_protocols"], [3])
        self.assertEqual(data["installed_client"]["sha256"], d.hashlib.sha256(source.encode()).hexdigest())
        self.assertNotIn("secret body", json.dumps(data))

    def test_install_substitution_and_previous_file_restored(self):
        self.prepare()
        template = 'local config = [[__BOTRBLX_DIAGNOSTIC_CONFIG_JSON__]]'
        (self.app / "JJSploit_Diagnose.lua").write_text(template)
        installed = self.workspace / "botrblx_diagnose.lua"
        installed.write_text("prior-user-text")
        self.session.install()
        self.assertNotIn(d.PLACEHOLDER, installed.read_text())
        self.assertIn(self.session.nonce, installed.read_text())
        self.session.cleanup()
        self.assertEqual(installed.read_text(), "prior-user-text")

    def test_existing_fixtures_preserved_and_unknown_files_not_removed(self):
        root_file = self.session.local_path(self.session.prefix + "_root.txt")
        root_file.write_text("prior-file")
        with self.assertRaises(FileExistsError):
            self.prepare()
        self.session.cleanup()
        self.assertEqual(root_file.read_text(), "prior-file")
        root_file.unlink()
        self.session = d.DiagnosticSession(self.workspace, self.app, nonce="other12345")
        self.addCleanup(self.session.cleanup)
        config = self.prepare()
        unknown = self.workspace / self.session.prefix / "not-a-fixture.txt"
        unknown.write_text("keep")
        for case in config["own_tests"]:
            self.session.local_path(case["path"]).write_text(case["second"])
        self.session.cleanup()
        self.assertTrue(unknown.is_file())
        self.assertFalse(self.session.local_path(config["own_tests"][0]["path"]).exists())

    def test_concurrent_runner_lock_is_exclusive_and_released(self):
        path = self.app / "diagnostics.lock"
        with d.DiagnosticLock(path):
            with self.assertRaises(RuntimeError):
                with d.DiagnosticLock(path):
                    pass
        self.assertFalse(path.exists())

    def test_redaction_handles_nested_errors_bearers_and_nonfinite(self):
        value = d.sanitize({"nested": {"api_key": "hide", "error":
                            'token="very secret" Authorization: Bearer abc.def password=oops'},
                            "value": float("nan")})
        encoded = json.dumps(value, allow_nan=False)
        for secret in ("very secret", "abc.def", "oops", '"hide"'):
            self.assertNotIn(secret, encoded)

    def test_no_torch_dependency_and_cli_help(self):
        result = subprocess.run([sys.executable, "-S", str(APP / "diagnostics.py"), "--help"],
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--workspace", result.stdout)
        self.assertNotIn("torch", result.stderr.lower())

    def test_timeout_and_interrupt_save_partial_report_and_release_lock(self):
        (self.app / "JJSploit_Diagnose.lua").write_text("__BOTRBLX_DIAGNOSTIC_CONFIG_JSON__")
        args = d.argparse.Namespace(workspace=self.workspace, project_root=self.root, timeout=.01)
        with mock.patch.object(d.time, "sleep", side_effect=KeyboardInterrupt), mock.patch("builtins.print"):
            self.assertEqual(d.run(args, self.app), 1)
        report = json.loads((self.app / "DIAGNOSTIC_REPORT.json").read_text())
        self.assertEqual(report["status"], "INTERRUPTED")
        self.assertIsNone(report["lua"])
        self.assertFalse((self.app / "diagnostics.lock").exists())
        self.assertFalse((self.workspace / "botrblx_diagnose.lua").exists())


if __name__ == "__main__":
    unittest.main()
