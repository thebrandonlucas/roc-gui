import json
from pathlib import Path
import sys
import subprocess
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dependency_archive import write_archive, digest
from test_native_archive_fixture import current_native
from dependency_artifacts import unpack_verified
import test_kai_link_inputs as fixtures
import link_input_artifacts as links


class LinkInputArtifactsTests(unittest.TestCase):
    def component(self, directory, name, target, files):
        metadata = {"schema_version": 1, "name": name, "target": target}
        if name in {"alsa", "glibc", "unwind", "xkbcommon"}:
            metadata, files = current_native(name, files)
        elif name == "windows-gnu-runtime":
            recipe = "dependencies/windows-gnu-runtime.json"
            files["sources/windows-gnu-runtime/" + recipe] = b"recipe"
            identity = digest(b"recipe")
            metadata.update(schema_version=3, source={"native_toolchain": {"sha256": "c" * 64}},
                            build={"builder_kind": "native-windows-zig", "toolchain_sha256": "c" * 64,
                                   "recipe_sha256": identity, "reproduction_sha256": {recipe: identity}})
        write_archive(directory / f"{name}-{target}.tar", metadata, files)

    def candidates(self, directory):
        for name, target in sum((list(value) for value in links.COMPONENTS.values()), []):
            if name == "macos-interfaces":
                files = {f"targets/{target}/usr/lib/libSystem.tbd": b"system",
                         f"sources/{name}/catalog.json": b"catalog"}
            else:
                files = {f"targets/{target}/{name}.a": name.encode(),
                         f"licenses/{name}/LICENSE": b"terms",
                         f"sources/{name}/recipe": b"recipe"}
            if name == "freetype":
                fixture = fixtures.KaiLinkInputTests()
                fixture.root = directory
                fixture.make_source_archive().rename(directory / "freetype-x64glibc.tar")
            else:
                self.component(directory, name, target, files)

    def test_composes_safe_target_archives_and_content_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            components = root / "components"
            components.mkdir()
            self.candidates(components)
            resource = root / "roc-gui.res"
            resource.write_bytes(b"resource")
            source = {"repository": links.REPOSITORY, "sha": "a" * 40,
                      "ref": "refs/heads/change", "workflow": links.REPOSITORY +
                      "/.github/workflows/link-inputs.yml", "input_fingerprint": "f" * 64}
            with patch.object(links, "source_fingerprint", return_value="f" * 64), patch.object(
                    links.kai_admission, "read_record", return_value={"reviewed": True}), patch.object(
                    links.kai_admission, "verify_bytes"), patch.object(links.kai_admission, "check_current"):
                manifest = links.compose(components, root / "release", resource,
                                         root=links.ROOT, source=source)
            self.assertEqual(set(manifest["assets"]), set(links.TARGETS))
            self.assertEqual(manifest["schema_version"], 2)
            self.assertEqual(manifest["component_builds"], {"freetype": {"reviewed": True}})
            extracted = root / "extracted"
            archive = root / "release/link-inputs-x64mingw.tar"
            unpack_verified(archive, {"name": "link-inputs", "target": "x64mingw"}, extracted)
            self.assertEqual((extracted / "targets/x64mingw/roc-gui.res").read_bytes(), b"resource")
            self.assertTrue((extracted / "licenses/link-inputs/windows-gnu-runtime/LICENSE").is_file())
            mac = root / "mac"
            unpack_verified(root / "release/link-inputs-arm64mac.tar",
                            {"name": "link-inputs", "target": "arm64mac"}, mac)
            self.assertEqual(
                (mac / "targets/arm64mac/macos-sysroot/usr/lib/libSystem.tbd").read_bytes(),
                b"system",
            )

    def test_component_fingerprint_excludes_only_migrated_freetype_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = (*links.FREETYPE_ONLY, "dependencies/nixpkgs-pin.nix", "scripts/dependency_artifacts.py")
            for relative in paths:
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("reviewed")
            subprocess.run(["git", "init", "--quiet"], cwd=root, check=True)
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "-c", "user.name=Test", "-c", "user.email=test@example.invalid",
                            "-c", "commit.gpgsign=false", "commit", "--quiet", "-m", "fixture"], cwd=root, check=True)
            before = links.source_fingerprint(root)
            (root / "scripts/build_freetype.py").write_text("changed producer")
            self.assertEqual(links.source_fingerprint(root), before)
            (root / "dependencies/nixpkgs-pin.nix").write_text("changed shared pins")
            with self.assertRaises(links.UncommittedLinkInputs):
                links.source_fingerprint(root)

    def test_new_lock_requires_fresh_component_binding(self):
        from test_kai_admission import KaiAdmissionTests
        fixture = KaiAdmissionTests()
        fixture.setUp()
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "link-inputs.lock.json"
            lock = {"schema_version": 2, "kind": "roc-gui-link-inputs", "repository": links.REPOSITORY,
                    "release": "link-inputs-sha256-" + "a" * 64,
                    "manifest": {"asset": "build-input-release.json", "sha256": "b" * 64},
                    "source": {"repository": links.REPOSITORY, "sha": "a" * 40,
                               "ref": "refs/heads/change", "workflow": links.REPOSITORY +
                               "/.github/workflows/link-inputs.yml", "input_fingerprint": "f" * 64},
                    "targets": {target: {"asset": f"link-inputs-{target}.tar", "sha256": "c" * 64, "size": 1}
                                for target in links.TARGETS}, "component_builds": {"freetype": fixture.record}}
            path.write_text(json.dumps(lock))
            with patch.object(links, "source_fingerprint", return_value="f" * 64), patch.object(
                    links.kai_admission.kai_link_inputs, "plan", return_value=fixture.current) as plan:
                self.assertEqual(links.read_lock(path)["component_builds"], lock["component_builds"])
                self.assertNotIn("prepare", plan.call_args.kwargs)
                changed = dict(fixture.current, snapshot="/nix/store/" + "c" * 32 + "-kai-project")
                plan.return_value = changed
                with self.assertRaises(links.StaleLinkInputs):
                    links.read_lock(path)
                plan.return_value = {"schema_version": 99}
                with self.assertRaisesRegex(ValueError, "invalid Kai") as raised:
                    links.read_lock(path)
                self.assertNotIsInstance(raised.exception, links.StaleLinkInputs)

    def test_lock_requires_all_targets_and_current_fingerprint(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "link-inputs.lock.json"
            lock = {"schema_version": 2, "kind": "roc-gui-link-inputs",
                    "repository": links.REPOSITORY, "release": "link-inputs-sha256-" + "a" * 64,
                    "manifest": {"asset": "build-input-release.json", "sha256": "b" * 64},
                    "source": {"repository": links.REPOSITORY, "sha": "a" * 40,
                               "ref": "refs/heads/change", "workflow": links.REPOSITORY +
                               "/.github/workflows/link-inputs.yml", "input_fingerprint": "f" * 64},
                    "targets": {target: {"asset": f"link-inputs-{target}.tar",
                                         "sha256": "c" * 64, "size": 1}
                                for target in links.TARGETS}}
            from test_kai_admission import KaiAdmissionTests
            fixture = KaiAdmissionTests()
            fixture.setUp()
            lock["component_builds"] = {"freetype": fixture.record}
            self.admission_patch = patch.object(links.kai_admission, "check_current")
            self.admission_patch.start()
            self.addCleanup(self.admission_patch.stop)
            path.write_text(json.dumps(lock))
            with patch.object(links, "source_fingerprint", return_value="f" * 64):
                self.assertEqual(links.read_lock(path)["release"], lock["release"])
                self.assertFalse(links.development_requires_source_inputs(path.parent))
            with patch.object(links, "source_fingerprint", return_value="e" * 64):
                with self.assertRaises(links.StaleLinkInputs):
                    links.development_requires_source_inputs(path.parent)
                with self.assertRaisesRegex(links.StaleLinkInputs, "stale"):
                    links.read_lock(path)
            with patch.object(links, "source_fingerprint", side_effect=links.UncommittedLinkInputs("dirty")):
                with self.assertRaises(links.UncommittedLinkInputs):
                    links.development_requires_source_inputs(path.parent)
                with self.assertRaises(links.UncommittedLinkInputs):
                    links.read_lock(path)
            with patch.object(links, "source_fingerprint", side_effect=ValueError("cannot inspect producer")):
                with self.assertRaisesRegex(ValueError, "cannot inspect"):
                    links.development_requires_source_inputs(path.parent)
            lock["targets"].pop("x64glibc")
            path.write_text(json.dumps(lock))
            with self.assertRaisesRegex(ValueError, "invalid"):
                links.development_requires_source_inputs(path.parent)
            path.write_text("not json")
            with self.assertRaises(json.JSONDecodeError):
                links.development_requires_source_inputs(path.parent)
            old = dict(lock, schema_version=1)
            old.pop("component_builds")
            path.write_text(json.dumps(old))
            with self.assertRaisesRegex(ValueError, "invalid unified"):
                links.read_lock(path)
            path.unlink()
            with self.assertRaises(FileNotFoundError):
                links.development_requires_source_inputs(path.parent)


if __name__ == "__main__":
    unittest.main()
