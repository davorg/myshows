from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from myshows.__main__ import main
from myshows.dashboard import public_snapshot
from myshows.snapshot import load_snapshot, report_from_snapshot, watchlist_snapshot, write_snapshot
from myshows.state import AppError, State
from myshows.trakt import Trakt
from test_dashboard import report, SnapshotParser


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_round_trip_preserves_progress_and_freshness_without_private_fields(self):
        original = report()
        snapshot = watchlist_snapshot(original)
        self.assertNotIn("private-", json.dumps(snapshot))
        self.assertNotIn("status", snapshot["shows"][0])
        self.assertEqual(snapshot["shows"][0]["trakt_id"], 123)
        first = public_snapshot(original)
        restored = public_snapshot(report_from_snapshot(snapshot))
        first.pop("generated_at")
        restored.pop("generated_at")
        self.assertEqual(first, restored)

    def test_clean_checkout_build_needs_no_credentials_state_or_network(self):
        path = self.root / "watchlist.json"
        path.write_text(json.dumps(watchlist_snapshot(report())))
        state = self.root / "must-not-exist"
        output = self.root / "public"
        with patch.object(State, "load", side_effect=AssertionError("No credentials")), \
                patch.object(Trakt, "request", side_effect=AssertionError("No network")), redirect_stdout(StringIO()):
            result = main(["--state-dir", str(state), "build", "--snapshot", str(path), "--output", str(output)])
        self.assertEqual(result, 0)
        self.assertFalse(state.exists())
        parser = SnapshotParser()
        parser.feed((output / "index.html").read_text())
        self.assertEqual(json.loads(parser.data)["shows"][0]["title"], "A Test Show")

    def test_invalid_snapshot_leaves_existing_export_untouched(self):
        output = self.root / "public"
        output.mkdir()
        (output / "index.html").write_text("previous successful dashboard")
        path = self.root / "invalid.json"
        value = watchlist_snapshot(report())
        value["shows"][0]["progress"]["watched"] = 999
        path.write_text(json.dumps(value))
        with redirect_stderr(StringIO()):
            result = main(["build", "--snapshot", str(path), "--output", str(output)])
        self.assertEqual(result, 1)
        self.assertEqual((output / "index.html").read_text(), "previous successful dashboard")

    def test_invalid_identifiers_dates_counts_and_links_are_rejected(self):
        mutations = [
            lambda s: s["shows"][0].update(trakt_id=True),
            lambda s: s["shows"].append(deepcopy(s["shows"][0])),
            lambda s: s.update(list_checked_at="not-a-date"),
            lambda s: s["shows"][0].update(refresh_failed="false"),
            lambda s: s["shows"][0].update(url="https://example.com/private"),
            lambda s: s["shows"][0]["progress"].update(aired_unwatched=-1),
        ]
        for mutation in mutations:
            value = watchlist_snapshot(report())
            mutation(value)
            with self.subTest(value=value), self.assertRaises(AppError):
                report_from_snapshot(value)

    def test_unknown_and_empty_success_are_distinct(self):
        value = watchlist_snapshot(report())
        value["shows"][0]["progress"] = None
        restored = report_from_snapshot(value)
        self.assertIsNone(restored["shows"][0]["progress"]["data"])
        value["shows"] = []
        restored = report_from_snapshot(value)
        self.assertEqual(restored["shows"], [])
        self.assertIsNotNone(restored["list"]["last_success_at"])

    def test_extra_input_fields_cannot_reach_public_html(self):
        value = watchlist_snapshot(report())
        value["account"] = "do-not-publish-account"
        value["shows"][0]["private_note"] = "do-not-publish-note"
        restored = report_from_snapshot(value)
        self.assertNotIn("do-not-publish", json.dumps(public_snapshot(restored)))

    def test_snapshot_writer_preserves_dates_and_protects_private_directory(self):
        private = self.root / "private"
        private.mkdir()
        with self.assertRaises(AppError):
            write_snapshot(report(), private / "credentials.json", private)
        destination = self.root / "data/watchlist.json"
        write_snapshot(report(), destination, private)
        restored = load_snapshot(destination)
        self.assertEqual(restored["shows"][0]["progress"]["last_success_at"], "2026-11-07T10:00:00+00:00")
        with self.assertRaises(AppError):
            load_snapshot(self.root / "missing.json")


if __name__ == "__main__":
    unittest.main()
