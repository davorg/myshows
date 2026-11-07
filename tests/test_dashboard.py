from copy import deepcopy
from html.parser import HTMLParser
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from contextlib import redirect_stdout
from io import StringIO

from myshows.__main__ import main
from myshows.dashboard import PUBLIC_FILES, export_dashboard, public_snapshot
from myshows.progress import overview
from myshows.state import AppError, Cache, State
from myshows.trakt import Trakt


def report():
    return {"list_id": "private-list-slug", "list": {"last_success_at": "2026-11-07T10:00:00+00:00",
            "source": "private-api-url", "last_attempt_at": "2026-11-07T11:00:00+00:00", "error": "private-list-error"},
        "shows": [{"title": "A Test Show", "year": 2026, "ids": {"trakt": 123},
            "url": "https://trakt.tv/shows/a-test-show", "private_note": "private-note",
            "progress": {"data": {"aired": 8, "watched": 5, "aired_unwatched": 3,
                "most_recently_watched": {"season": 1, "episode": 2, "watched_at": "2026-11-07T09:00:00Z"},
                "furthest_watched": {"season": 1, "episode": 6, "watched_at": "2026-11-01T09:00:00Z"}, "reset_at": None},
                "last_success_at": "2026-11-07T10:00:00+00:00", "error": "private-error", "source": "private-source"}}]}


class SnapshotParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_snapshot = False
        self.data = ""
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "script":
            self.scripts.append(attrs)
            self.in_snapshot = attrs.get("id") == "watchlist-data"

    def handle_endtag(self, tag):
        if tag == "script":
            self.in_snapshot = False

    def handle_data(self, data):
        if self.in_snapshot:
            self.data += data


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_public_snapshot_omits_private_metadata_and_preserves_uncertainty(self):
        snapshot = public_snapshot(report())
        text = json.dumps(snapshot)
        self.assertNotIn("private-", text)
        self.assertNotIn("ids", snapshot["shows"][0])
        self.assertTrue(snapshot["list_refresh_failed"])
        self.assertTrue(snapshot["shows"][0]["refresh_failed"])
        self.assertEqual(snapshot["shows"][0]["progress"]["aired_unwatched"], 3)
        missing = report()
        missing["shows"][0]["progress"]["data"] = None
        self.assertIsNone(public_snapshot(missing)["shows"][0]["progress"])

    def test_export_does_not_allow_titles_to_escape_json_script(self):
        value = report()
        title = '</script><script>alert("injection")</script> & <img src=x>'
        value["shows"][0]["title"] = title
        output = self.root / "public"
        export_dashboard(value, output, self.root / "private")
        parser = SnapshotParser()
        parser.feed((output / "index.html").read_text())
        self.assertEqual(len(parser.scripts), 2)
        self.assertEqual(json.loads(parser.data)["shows"][0]["title"], title)
        self.assertEqual({p.name for p in output.iterdir()}, PUBLIC_FILES)
        self.assertNotIn("__MYSHOWS_DATA__", (output / "index.html").read_text())

    def test_export_rejects_private_and_unrelated_output_directories(self):
        private = self.root / "private"
        private.mkdir()
        (private / "credentials.json").write_text("secret")
        for output in (private, private / "public", self.root):
            with self.subTest(output=output), self.assertRaises(AppError):
                export_dashboard(report(), output, private)
        unrelated = self.root / "unrelated"
        unrelated.mkdir()
        (unrelated / "notes.txt").write_text("retain me")
        with self.assertRaises(AppError):
            export_dashboard(report(), unrelated, private)
        self.assertEqual((unrelated / "notes.txt").read_text(), "retain me")

    def test_build_cli_only_reads_cache_and_exports_no_credentials(self):
        state = State(self.root / "private")
        state.save({"client_id": "secret-client-id", "account": {"slug": "private-account"}})
        cache = Cache(state, "secret-client-id:private-account")
        self.addCleanup(cache.close)
        cache.fetch("list:following", "source", lambda: [{"type": "show", "show": {
            "title": "A Real Cached Show", "year": 2026, "ids": {"trakt": 123, "slug": "cached-show"}}}])
        cache.fetch("progress:123", "source", lambda: report()["shows"][0]["progress"]["data"])
        output = self.root / "public"
        with patch.object(Trakt, "request", side_effect=AssertionError("No network allowed")), redirect_stdout(StringIO()):
            result = main(["--state-dir", str(state.directory), "build", "--list", "following", "--output", str(output)])
        self.assertEqual(result, 0)
        html = (output / "index.html").read_text()
        self.assertIn("A Real Cached Show", html)
        self.assertNotIn("secret-client-id", html)
        self.assertNotIn("private-account", html)

    def test_export_replaces_snapshot_after_empty_success_and_rejects_bad_urls(self):
        output = self.root / "public"
        value = report()
        value["shows"][0]["url"] = "javascript:alert(1)"
        self.assertEqual(public_snapshot(value)["shows"][0]["url"], "https://trakt.tv")
        export_dashboard(value, output, self.root / "private")
        value["shows"] = []
        export_dashboard(value, output, self.root / "private")
        parser = SnapshotParser()
        parser.feed((output / "index.html").read_text())
        self.assertEqual(json.loads(parser.data)["shows"], [])


if __name__ == "__main__":
    unittest.main()
