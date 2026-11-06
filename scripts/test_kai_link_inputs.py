"""Exercise the production adapter and selected-source archive trust boundary."""

import base64
import json
import os
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import kai_link_inputs as adapter
import check_linux_reproduction as reproduction
from dependency_archive import digest, write_archive
from dependency_artifacts import unpack_verified


class KaiLinkInputTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_producer_runs_with_only_declared_project_files(self):
        for relative in adapter.SELECTED_FILES:
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((adapter.ROOT / relative).read_bytes())
        completed = subprocess.run([sys.executable, "-E", "-s", "scripts/build_freetype.py", "--help"],
                                   cwd=self.root, capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("--rebuild", completed.stdout)

    def output(self):
        output = self.root / "store"
        output.mkdir(exist_ok=True)
        (output / "freetype-x64glibc.tar").write_bytes(b"tested archive")
        return output

    def result(self, output=None):
        """A plan of the FreeType build, as `kai build freetype --plan` prints it."""
        return {"schema_version": 1, "backend": "nix", "name": "freetype", "system": "x86_64-linux",
                "environment": "freetype-producer", "output": "dist", "files": list(adapter.SELECTED_FILES),
                "inputs": [], "needs": [], "snapshot": "/nix/store/" + "b" * 32 + "-kai-project",
                "derivation": "/nix/store/" + "a" * 32 + "-kai-freetype.drv",
                "output_path": str(output) if output else "/nix/store/" + "c" * 32 + "-kai-freetype"}

    def test_build_binds_the_planned_snapshot_and_identity(self):
        output = self.output()
        planned = self.result()
        with patch.object(adapter, "kai", return_value=planned["output_path"] + "\n") as kai, patch.object(
                adapter, "plan", return_value=planned), patch.object(adapter, "STORE_PATH") as store:
            store.fullmatch.return_value = True
            with patch.object(adapter, "Path", side_effect=lambda value: output if value == planned["output_path"] else Path(value)):
                archive = adapter.build(self.root / "candidate", rebuild=True)
        self.assertEqual(kai.call_args.args[0], ["build", "freetype", "--rebuild"])
        record = json.loads(archive.with_suffix(".tar.kai.json").read_text())
        self.assertEqual(record["derivation"], planned["derivation"])
        self.assertEqual(record["snapshot"], planned["snapshot"])
        self.assertEqual(record["artifact"], {"name": archive.name, "size": 14,
                                             "sha256": digest(b"tested archive")})
        with self.assertRaises(FileExistsError):
            adapter.build(archive.parent)

    def test_wrong_plan_never_publishes_candidate(self):
        for field, value in (("schema_version", 2), ("backend", "guix"), ("derivation", "opaque"),
                             ("snapshot", "sha256:" + "b" * 64), ("files", None)):
            plan = self.result()
            plan[field] = value
            with self.subTest(field=field), patch.object(adapter, "command", return_value=plan):
                with self.assertRaises(ValueError):
                    adapter.plan()

    def test_plan_runs_kai_build_plan(self):
        with patch.object(adapter, "command", return_value=self.result()) as command:
            adapter.plan(root=self.root)
        command.assert_called_once_with(["build", "freetype", "--plan"], root=self.root)

    def evidence(self):
        return {"format": 2,
                "packages": [{"name": "nix", "provider": "nix", "rev": "a" * 40,
                              "narHash": "sha256-" + "A" * 43 + "="}],
                "files": [{"name": "freetype-source", "provider": "file", "sha256": digest(b"source")}],
                "tools": [{"name": "nix#python3", "path": "/nix/store/" + "c" * 32 + "-python"}]}

    def test_compile_discovery_preserves_zig_target_libc(self):
        with patch.dict(os.environ, {"KAI_TOOLS": "/declared-tools"}, clear=True):
            adapter.configure_environment(self.root / "work")
            self.assertNotIn("glibc", os.environ["C_INCLUDE_PATH"])
            self.assertNotIn("glibc", os.environ["LIBRARY_PATH"])
            self.assertIn("nix#bzip2.out/lib", os.environ["LIBRARY_PATH"])
            self.assertIn("nix#brotli.lib/lib", os.environ["LIBRARY_PATH"])
            command = adapter.probe_command(self.root / "probe")
            self.assertEqual(command[0], "/declared-tools/nix#glibc/lib/ld-linux-x86-64.so.2")

    def test_evidence_is_collected_from_kai_records_and_the_nixpkgs_pin(self):
        inputs, tools = self.root / "inputs", self.root / "tools"
        inputs.mkdir()
        tools.mkdir()
        value = "sha256-" + base64.b64encode(bytes.fromhex(digest(b"source"))).decode()
        (inputs / ".kai-inputs.json").write_text(json.dumps({"schema_version": 1, "inputs": [
            {"name": "freetype-source", "kind": "fetch", "url": "https://example.test/ft.tar.xz", "revision": None,
             "hash": {"algorithm": "sha256", "of": "file", "encoding": "sri", "value": value}}]}))
        (tools / "nix#python3").symlink_to("/nix/store/" + "c" * 32 + "-python")
        with patch.dict(os.environ, {"KAI_INPUTS": str(inputs), "KAI_TOOLS": str(tools)}):
            evidence, encoded = adapter.collect_evidence()
        self.assertEqual(evidence["files"], self.evidence()["files"])
        self.assertEqual(evidence["tools"], self.evidence()["tools"])
        self.assertEqual(evidence["packages"][0]["rev"],
                         adapter.nixpkgs_pin((adapter.ROOT / "dependencies/nixpkgs-pin.nix").read_text())["rev"])
        self.assertEqual(json.loads(encoded), evidence)

    def test_native_evidence_rejects_extra_categories_and_non_store_paths(self):
        path = self.root / "evidence"
        evidence = self.evidence()
        path.write_text(json.dumps(evidence))
        self.assertEqual(adapter.input_evidence(path)[0], evidence)
        for mutation in ({"derivation": "self"}, {"lock": "whole lock"},
                         {"tools": [{"name": "python3", "path": "/home/user/python"}]},
                         {"format": 1}):
            path.write_text(json.dumps(dict(evidence, **mutation)))
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                adapter.input_evidence(path)

    def make_source_archive(self, *, changed_evidence=False, source_mismatch=False):
        evidence = self.evidence()
        if source_mismatch:
            evidence["files"][0]["sha256"] = "f" * 64
        encoded = (json.dumps(evidence) + "\n").encode()
        files = {"sources/freetype/" + name: b"selected source" for name in adapter.SELECTED_FILES}
        files.update({"sources/freetype/source.tar.xz": b"source",
                      "sources/freetype/kai-input-evidence.json": encoded,
                      "targets/x64glibc/libfreetype.so": b"library"})
        metadata = {"schema_version": 6, "name": "freetype", "target": "x64glibc",
                    "source": {"sha256": digest(b"source")},
                    "build": {"builder_kind": "kai-nix",
                              "input_evidence_sha256": "e" * 64 if changed_evidence else digest(encoded),
                              "reproduction_sha256": {name: digest(b"selected source") for name in adapter.SELECTED_FILES},
                              "reproduction_modes": {name: 0o644 for name in adapter.SELECTED_FILES}}}
        return write_archive(self.root / "candidate.tar", metadata, files)

    def test_reproduction_restores_modes_and_checks_exact_native_identity(self):
        archive = self.make_source_archive()
        manifest = unpack_verified(archive, {"name": "freetype", "target": "x64glibc"}, self.root / "contents")
        source = self.root / "contents/sources/freetype"
        expected = self.evidence()["packages"][0]
        pin = {"schema_version": 1, "inputs": [{"section": "nix", "name": "nix", "revision": expected["rev"],
                                                "hash": {"value": expected["narHash"]}}]}
        with patch.object(adapter, "plan", return_value=self.result()) as plan, patch.object(
                adapter, "command", return_value=pin), patch.object(reproduction.subprocess, "run") as run:
            reproduction.check_kai_freetype(source, manifest)
        run.assert_called_once()
        self.assertEqual(plan.call_count, 2)
        self.assertIn("FreeType.settings", (source / "Kaifile.roc").read_text())
        self.assertNotIn('"/', (source / "Kaifile.roc").read_text())
        self.assertEqual((source / "scripts/build_freetype.py").stat().st_mode & 0o777, 0o644)
        pin["inputs"][0]["hash"]["value"] = "sha256-" + "B" * 43 + "="
        with patch.object(adapter, "plan", return_value=self.result()) as plan, patch.object(
                adapter, "command", return_value=pin), patch.object(reproduction.subprocess, "run"):
            with self.assertRaisesRegex(ValueError, "package pin differs"):
                reproduction.check_kai_freetype(source, manifest)
        self.assertEqual(plan.call_count, 1)

    def test_only_kai_schema_six_is_accepted_for_freetype(self):
        for version in (1, 2, 3, 4, 5):
            archive = write_archive(self.root / f"old-{version}.tar",
                                    {"schema_version": version, "name": "freetype", "target": "x64glibc"},
                                    {"targets/x64glibc/libfreetype.so": b"library"})
            with self.subTest(version=version), self.assertRaisesRegex(ValueError, "schema 6"):
                unpack_verified(archive, {"name": "freetype", "target": "x64glibc"}, self.root / "contents")
            self.assertFalse((self.root / "contents").exists())

    def test_new_archive_validates_selected_evidence_and_sources(self):
        archive = self.make_source_archive()
        manifest = unpack_verified(archive, {"name": "freetype", "target": "x64glibc"}, self.root / "contents")
        self.assertEqual(manifest["schema_version"], 6)
        self.assertNotIn("builder_derivation", manifest["build"])

    def test_tampered_evidence_or_mismatched_upstream_fails_before_extraction(self):
        for change in ("changed_evidence", "source_mismatch"):
            with self.subTest(change=change):
                archive = self.make_source_archive(**{change: True})
                with self.assertRaisesRegex(ValueError, "Kai"):
                    unpack_verified(archive, {"name": "freetype", "target": "x64glibc"}, self.root / "contents")
                self.assertFalse((self.root / "contents").exists())
                archive.unlink()


if __name__ == "__main__":
    unittest.main()
