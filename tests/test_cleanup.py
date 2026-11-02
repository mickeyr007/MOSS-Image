import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "recovery"))
import cleanup


class CleanupAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        subprocess.run(("git", "init", "-q", str(self.root)), check=True)
        (self.root / "Makefile").write_text("all:\n\t@true\n")
        (self.root / ".gitignore").write_text("ignored/\n")
        (self.root / "source.txt").write_text("original\n")
        subprocess.run(("git", "add", "Makefile", ".gitignore", "source.txt"), cwd=self.root, check=True)
        subprocess.run(("git", "-c", "user.name=Test", "-c", "user.email=test@example.com",
                        "commit", "-qm", "initial"), cwd=self.root, check=True)
        self.commit = cleanup.git(self.root, "rev-parse", "HEAD").strip()

    def approval(self, names):
        separate = tempfile.TemporaryDirectory()
        self.addCleanup(separate.cleanup)
        path = Path(separate.name) / "approval.json"
        path.write_text(json.dumps({"directory": str(self.root.resolve()),
                                    "remote_commit": self.commit,
                                    "delete": [{"name": name, "size_kib": 999} for name in names]}))
        return path

    def test_changed_sizes_and_missing_names_are_allowed(self):
        approval = self.approval([".git", ".gitignore", "source.txt", "missing"])
        self.assertEqual(set(cleanup.approved_entries(self.root, approval, self.commit)),
                         {".git", ".gitignore", "source.txt"})

    def test_new_top_level_entry_is_rejected(self):
        approval = self.approval([".git", ".gitignore", "source.txt"])
        (self.root / "surprise").write_text("data")
        with self.assertRaises(SystemExit):
            cleanup.approved_entries(self.root, approval, self.commit)

    def test_recursive_ignored_unknown_aborts(self):
        ignored = self.root / "ignored" / "asset.png"
        ignored.parent.mkdir()
        ignored.write_bytes(b"irreplaceable")
        self.assertIn("ignored/asset.png", cleanup.audit(self.root, {}, [], {}, set()))

    def test_modified_and_untracked_need_encrypted_backup(self):
        (self.root / "source.txt").write_text("changed\n")
        (self.root / "new.txt").write_text("new\n")
        unknown = cleanup.audit(self.root, {}, [], {}, set())
        self.assertIn("source.txt", unknown)
        self.assertIn("new.txt", unknown)
        self.assertEqual(cleanup.audit(self.root, {}, [], {}, {"source.txt", "new.txt"}), [])

    def test_symlink_outside_root_is_reported_without_following(self):
        separate = tempfile.TemporaryDirectory()
        self.addCleanup(separate.cleanup)
        outside = Path(separate.name) / "outside.txt"
        outside.write_text("keep\n")
        (self.root / "outside-link").symlink_to(outside)
        self.assertIn("outside-link", cleanup.audit(self.root, {}, [], {}, set()))
        self.assertEqual(outside.read_text(), "keep\n")


if __name__ == "__main__":
    unittest.main()
