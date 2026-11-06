"""Source identity and publication failures must not admit substitute FreeType bytes."""

import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_freetype as producer
from dependency_archive import digest, write_archive
import release_dependencies
import test_kai_link_inputs as kai_fixtures
import tarfile


class FreeTypeDependencyTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.bytes = b"reviewed source bytes"
        self.source = {"url": "https://example.invalid/source.tar.xz",
                       "size": len(self.bytes), "sha256": digest(self.bytes)}

    def test_sandbox_source_bytes_still_require_the_reviewed_identity(self):
        source = self.root / "source.tar"
        source.write_bytes(self.bytes)
        producer.verify_source(source, self.source)
        for data in (self.bytes[:-1], self.bytes + b"x", b"x" * len(self.bytes)):
            source.write_bytes(data)
            with self.assertRaisesRegex(ValueError, "reviewed recipe"):
                producer.verify_source(source, self.source)

    def test_kai_source_follows_the_store_link_to_the_reviewed_bytes(self):
        store = self.root / "store"
        store.mkdir()
        (store / "source").write_bytes(self.bytes)
        inputs = self.root / "inputs"
        inputs.mkdir()
        (inputs / "freetype-source").symlink_to(store / "source")
        source = producer.kai_source(inputs)
        self.assertFalse(source.is_symlink())
        producer.verify_source(source, self.source)
        (inputs / "freetype-source").unlink()
        (inputs / "freetype-source").symlink_to(store)
        with self.assertRaisesRegex(ValueError, "not a regular file"):
            producer.kai_source(inputs)
        (inputs / "freetype-source").unlink()
        with self.assertRaisesRegex(ValueError, "no FreeType source"):
            producer.kai_source(inputs)

    def make_archive(self, missing_license=False):
        policy = release_dependencies.KINDS["freetype"]
        fixture = kai_fixtures.KaiLinkInputTests()
        fixture.root = self.root
        draft = fixture.make_source_archive()
        with tarfile.open(draft) as archive:
            metadata = json.load(archive.extractfile("dependency.json"))
            files = {name: archive.extractfile(name).read() for name in metadata.pop("files")}
        draft.unlink()
        for name in policy["licenses"]:
            files["licenses/freetype/" + name] = b"license text"
        if missing_license:
            del files["licenses/freetype/NOTICE"]
        return write_archive(self.root / producer.ARCHIVE_NAME, metadata, files)

    def prepare(self):
        environment = {"GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_REF": "refs/heads/main",
                       "GITHUB_REPOSITORY": release_dependencies.REPOSITORY, "GITHUB_SHA": "a" * 40}
        with patch.object(release_dependencies.subprocess, "check_output", return_value="a" * 40), patch.object(
                release_dependencies, "verify_archive") as verifier:
            release_dependencies.prepare(self.root, "deps-freetype-1", environment, "freetype")
        return verifier

    def test_release_lock_binds_the_freetype_producer(self):
        archive = self.make_archive()
        verifier = self.prepare()
        lock = json.loads((self.root / "dependencies.lock.json").read_text())
        entry = lock["artifacts"]["freetype-x64glibc"]
        self.assertTrue(entry["signer_workflow"].endswith("/.github/workflows/freetype-dependencies.yml"))
        self.assertEqual(entry["sha256"], digest(archive.read_bytes()))
        verifier.assert_called_once_with(archive, entry)

    def test_missing_license_refuses_publication(self):
        self.make_archive(missing_license=True)
        with self.assertRaisesRegex(ValueError, "incomplete or unexpected"):
            self.prepare()
        self.assertFalse((self.root / "dependencies.lock.json").exists())


if __name__ == "__main__":
    unittest.main()
