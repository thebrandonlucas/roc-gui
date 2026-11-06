import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import kai_admission as admission
import kai_link_inputs


class KaiAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = "/nix/store/" + "b" * 32 + "-kai-project"
        self.record = {"schema_version": 2, "backend": "nix",
                       "derivation": "/nix/store/" + "a" * 32 + "-kai-freetype.drv",
                       "snapshot": self.snapshot,
                       "artifact": {"name": "freetype-x64glibc.tar", "sha256": hashlib.sha256(b"archive").hexdigest(), "size": 7}}
        self.current = {"schema_version": 1, "name": "freetype", "system": "x86_64-linux",
                        "backend": "nix", "environment": "freetype-producer", "output": "dist",
                        "files": list(kai_link_inputs.SELECTED_FILES), "inputs": [], "needs": [],
                        "derivation": self.record["derivation"], "snapshot": self.snapshot,
                        "output_path": "/nix/store/" + "c" * 32 + "-kai-freetype"}

    def test_exact_admission_can_refresh_a_binding_only_when_build_is_identical(self):
        current = dict(self.current, snapshot="/nix/store/" + "e" * 32 + "-kai-project")
        refreshed = admission.match_current(self.record, current, exact=True)
        self.assertEqual(refreshed["snapshot"], current["snapshot"])
        self.assertEqual(refreshed["artifact"], self.record["artifact"])
        with self.assertRaisesRegex(ValueError, "build identity differs"):
            admission.match_current(self.record, dict(current, derivation="/nix/store/" + "d" * 32 + "-changed.drv"), exact=True)

    def test_structural_check_compares_the_planned_snapshot(self):
        with patch.object(admission.kai_link_inputs, "plan", return_value=self.current) as plan:
            admission.check_current(self.record)
        plan.assert_called_once()

    def test_changed_snapshot_cannot_reuse_admission(self):
        with self.assertRaisesRegex(ValueError, "stale"):
            admission.match_current(self.record, dict(self.current, snapshot="/nix/store/" + "f" * 32 + "-kai-project"), exact=False)

    def test_a_record_from_before_kai_is_stale(self):
        older = {"schema_version": 1, "provider": "nix", "build_identity": self.record["derivation"],
                 "snapshot_digest": "sha256:" + "b" * 64, "snapshot": {}, "artifact": self.record["artifact"]}
        with patch.object(admission.kai_link_inputs, "plan") as plan:
            with self.assertRaisesRegex(admission.StaleAdmission, "publish new linker inputs"):
                admission.check_current(older)
            plan.assert_not_called()

    def test_malformed_records_cannot_establish_exact_equivalence(self):
        for change in ({"backend": "another"}, {"derivation": ""},
                       {"snapshot": "sha256:" + "b" * 64}, {"schema_version": 1}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                admission.match_current(dict(self.record, **change), self.current, exact=True)

    def test_archive_bytes_are_verified_before_planning(self):
        with tempfile.TemporaryDirectory() as directory:
            archive = Path(directory) / "freetype-x64glibc.tar"
            archive.write_bytes(b"archive")
            sidecar = archive.with_suffix(".tar.kai.json")
            sidecar.write_text(json.dumps(self.record))
            with patch.object(admission.kai_link_inputs, "plan", return_value=self.current) as plan:
                admission.admit(archive)
                plan.assert_called_once()
            archive.write_bytes(b"changed")
            with patch.object(admission.kai_link_inputs, "plan") as plan:
                with self.assertRaisesRegex(ValueError, "admitted digest"):
                    admission.admit(archive)
                plan.assert_not_called()


if __name__ == "__main__":
    unittest.main()
