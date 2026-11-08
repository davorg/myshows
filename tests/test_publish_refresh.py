"""Exercise publication against local git remotes; never contact GitHub."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parent.parent / ".github/scripts/publish-refresh.sh"


class PublishRefreshTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.remote = self.root / "remote.git"
        self.work = self.root / "work"
        self.git(self.root, "init", "--bare", "--initial-branch=main", str(self.remote))
        self.git(self.root, "clone", str(self.remote), str(self.work))
        self.git(self.work, "config", "user.name", "Test")
        self.git(self.work, "config", "user.email", "test@example.invalid")
        (self.work / "data").mkdir()
        for name in ("watchlist", "statuses"):
            (self.work / f"data/{name}.json").write_text('{"version":1}\n')
        (self.work / ".gitignore").write_text('.myshows/\n')
        self.git(self.work, "add", "data/watchlist.json", "data/statuses.json", ".gitignore")
        self.git(self.work, "commit", "-m", "Fixture")
        self.git(self.work, "push", "-u", "origin", "main")
        self.initial = self.git(self.work, "rev-parse", "HEAD")
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.log = self.root / "operations"
        self.output = self.root / "outputs"
        self.output.touch()
        self.stub(self.bin / "python3", 'echo tests >> "$PUBLISH_TEST_LOG"\n[ "${PUBLISH_TEST_FAIL:-}" != tests ]\n')
        self.stub(self.bin / "gh", 'echo "gh $*" >> "$PUBLISH_TEST_LOG"\n')
        (self.work / "scripts").mkdir()
        self.stub(self.work / "scripts/rebuild-site", 'echo build >> "$PUBLISH_TEST_LOG"\n[ "${PUBLISH_TEST_FAIL:-}" != build ]\n')
        self.environment = {**os.environ, "PATH": str(self.bin) + os.pathsep + os.environ["PATH"],
                            "GITHUB_OUTPUT": str(self.output), "GH_TOKEN": "fake-token", "GH_REPO": "example/test",
                            "PUBLISH_TEST_LOG": str(self.log)}

    def git(self, cwd, *args):
        return subprocess.check_output(["git", "-c", "core.fsmonitor=false", *args], cwd=cwd, text=True, stderr=subprocess.PIPE).strip()

    def stub(self, path, body):
        path.write_text("#!/bin/sh\nset -eu\n" + body)
        path.chmod(0o700)

    def publish(self, filename, failure=""):
        return subprocess.run([str(SCRIPT), filename], cwd=self.work, env={**self.environment, "PUBLISH_TEST_FAIL": failure},
                              capture_output=True, text=True)

    def test_no_change_skips_tests_build_commit_and_dispatch(self):
        for filename in ("data/watchlist.json", "data/statuses.json"):
            self.assertEqual(self.publish(filename).returncode, 0)
        self.assertFalse(self.log.exists())
        self.assertEqual(self.git(self.work, "rev-parse", "HEAD"), self.initial)
        self.assertEqual(self.output.read_text().splitlines(), ["changed=false", "changed=false"])

    def test_both_public_inputs_trigger_validation_and_pages_on_changes(self):
        (self.work / ".myshows").mkdir()
        (self.work / ".myshows/credentials.json").write_text("fake-private-credentials")
        for filename in ("data/watchlist.json", "data/statuses.json"):
            with self.subTest(filename=filename):
                self.log.write_text("")
                self.output.write_text("")
                (self.work / filename).write_text('{"version":2}\n')
                result = self.publish(filename)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(self.log.read_text().splitlines(), ["tests", "build", "gh workflow run pages.yml --ref main"])
                self.assertEqual(self.git(self.work, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"), filename)
                self.assertEqual(self.git(self.remote, "show", "main:" + filename), '{"version":2}')
                self.assertEqual(self.output.read_text().strip(), "changed=true")
        self.assertNotIn(".myshows", self.git(self.work, "ls-files"))

    def test_failed_validation_never_pushes_or_dispatches(self):
        for failure in ("tests", "build"):
            with self.subTest(failure=failure):
                self.log.write_text("")
                (self.work / "data/statuses.json").write_text('{"version":2}\n')
                self.assertNotEqual(self.publish("data/statuses.json", failure).returncode, 0)
                self.assertNotIn("gh ", self.log.read_text())
                self.assertEqual(self.git(self.remote, "rev-parse", "main"), self.initial)
                self.assertEqual(self.git(self.work, "rev-parse", "HEAD"), self.initial)

    def test_concurrent_unrelated_main_change_survives_rebase(self):
        other = self.root / "other"
        self.git(self.root, "clone", str(self.remote), str(other))
        self.git(other, "config", "user.name", "Other")
        self.git(other, "config", "user.email", "other@example.invalid")
        (other / "concurrent.md").write_text("concurrent change")
        self.git(other, "add", "concurrent.md")
        self.git(other, "commit", "-m", "Concurrent update")
        self.git(other, "push", "origin", "main")
        (self.work / "data/watchlist.json").write_text('{"version":2}\n')
        result = self.publish("data/watchlist.json")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.git(self.remote, "show", "main:concurrent.md"), "concurrent change")

    def test_arbitrary_files_cannot_be_published(self):
        self.assertNotEqual(self.publish(".myshows/credentials.json").returncode, 0)
        self.assertFalse(self.log.exists())
        self.assertEqual(self.git(self.remote, "rev-parse", "main"), self.initial)


if __name__ == "__main__":
    unittest.main()
