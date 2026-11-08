from argparse import Namespace
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from myshows.github_trakt import credentials_from_json, GitHubState, main
from myshows.maintenance import refresh_shows, seed_progress
from myshows.snapshot import load_snapshot, watchlist_snapshot
from myshows.state import AppError, Cache, State
from myshows.trakt import Trakt
from test_dashboard import report
from test_myshows import Response, Transport, token


def credentials():
    return {"client_id": "fake-client", "redirect_uri": "http://localhost", "tokens": token(),
            "account": {"username": "test", "slug": "test"}}


class GitHubTraktTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.commands = []
        self.state = GitHubState(self.root / "private", "example/myshows", "fake-github-token", run=self.run_secret)

    def run_secret(self, command, **kwargs):
        self.commands.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, "", "")

    def test_credentials_validate_and_allowlist_before_restore(self):
        value = credentials()
        value["private_note"] = "unrelated secret"
        self.assertNotIn("private_note", credentials_from_json(json.dumps(value)))
        invalid = ["", "not JSON", "[]", "{}"]
        for field in ("tokens", "account", "client_id", "redirect_uri"):
            changed = credentials()
            changed[field] = None
            invalid.append(json.dumps(changed))
        changed = credentials()
        changed["tokens"]["expires_in"] = True
        invalid.append(json.dumps(changed))
        for raw in invalid:
            with self.subTest(raw=raw), self.assertRaises(AppError):
                credentials_from_json(raw)

    def test_secret_update_uses_stdin_and_environment_not_arguments_or_logs(self):
        value = credentials()
        captured = StringIO()
        with redirect_stdout(captured), redirect_stderr(captured):
            self.state.save(value)
        command, options = self.commands[0]
        self.assertEqual(command, ["gh", "secret", "set", "TRAKT_CREDENTIALS_JSON", "--env", "trakt-refresh", "--repo", "example/myshows"])
        self.assertEqual(json.loads(options["input"]), value)
        self.assertEqual(options["env"]["GH_TOKEN"], "fake-github-token")
        self.assertNotIn("TRAKT_CREDENTIALS_JSON", options["env"])
        self.assertNotIn("fake-github-token", " ".join(command))
        self.assertNotIn(value["tokens"]["access_token"], " ".join(command))
        self.assertEqual(captured.getvalue(), "")
        self.assertEqual(self.state.credentials.stat().st_mode & 0o777, 0o600)

    def test_failed_secret_write_preserves_local_rotation_and_hides_diagnostics(self):
        def failure(command, **kwargs):
            return subprocess.CompletedProcess(command, 1, "sensitive output", "sensitive diagnostic")
        self.state.run = failure
        value = credentials()
        with self.assertRaises(AppError) as caught:
            self.state.save(value)
        self.assertNotIn("sensitive", str(caught.exception))
        self.assertEqual(self.state.load()["tokens"], value["tokens"])
        self.state.run = lambda *a, **k: (_ for _ in ()).throw(subprocess.TimeoutExpired("gh", 30))
        with self.assertRaisesRegex(AppError, "no further Trakt"):
            self.state.save(credentials())

    def test_rotated_tokens_persist_before_the_first_authenticated_get(self):
        value = credentials()
        value["tokens"] = token(created_at=0, expires_in=1)
        events = []
        class OrderedTransport(Transport):
            def open(self, request, timeout):
                events.append("oauth" if request.method == "POST" else "get")
                return super().open(request, timeout)
        def save_secret(command, **kwargs):
            events.append("persist")
            self.assertEqual(json.loads(kwargs["input"])["tokens"]["refresh_token"], "new-refresh")
            return subprocess.CompletedProcess(command, 0)
        self.state.run = save_secret
        client = Trakt(self.state, value, opener=OrderedTransport([
            Response(token(access_token="new-access", refresh_token="new-refresh")), Response({"ok": True})]))
        self.assertEqual(client.get("/users/settings")[0], {"ok": True})
        self.assertEqual(events, ["oauth", "persist", "get"])

    def test_failed_rotation_persistence_stops_further_trakt_requests(self):
        value = credentials()
        value["tokens"] = token(created_at=0, expires_in=1)
        self.state.run = lambda command, **kwargs: subprocess.CompletedProcess(command, 1)
        transport = Transport([Response(token(refresh_token="rotated-refresh"))])
        client = Trakt(self.state, value, opener=transport)
        for _ in range(2):
            with self.assertRaises(AppError):
                client.get("/users/settings")
        self.assertEqual(len(transport.requests), 1)
        self.assertEqual(self.state.load()["tokens"]["refresh_token"], "rotated-refresh")

    def test_missing_or_unwritable_initial_secret_stops_before_trakt(self):
        variables = {"TRAKT_CREDENTIALS_JSON": json.dumps(credentials()), "GH_REPO": "example/myshows",
                     "TRAKT_SECRET_UPDATE_TOKEN": "fake-token", "MYSHOWS_STATE_DIR": str(self.root / "new-state")}
        with patch.dict("os.environ", variables), patch("myshows.github_trakt.refresh_shows", side_effect=AssertionError("No Trakt calls")), \
                patch("myshows.github_trakt.subprocess.run", return_value=subprocess.CompletedProcess([], 1)), redirect_stderr(StringIO()):
            self.assertEqual(main(), 1)
        with patch.dict("os.environ", {"TRAKT_CREDENTIALS_JSON": ""}), redirect_stderr(StringIO()):
            self.assertEqual(main(), 1)

    def test_cloud_failure_restores_public_progress_without_changing_success_dates(self):
        value = report()
        value["list"]["error"] = None
        value["shows"][0]["progress"]["error"] = None
        snapshot = self.root / "watchlist.json"
        snapshot.write_text(json.dumps(watchlist_snapshot(value)))
        State.save(self.state, credentials())
        args = Namespace(state_dir=self.state.directory, output=snapshot, list_id="following")
        client = unittest.mock.Mock()
        client.pages.side_effect = AppError("Trakt unavailable")
        client.get.side_effect = AppError("Trakt unavailable")
        with patch("myshows.maintenance.Trakt", return_value=client), redirect_stdout(StringIO()), redirect_stderr(StringIO()):
            result = refresh_shows(args, state=self.state, seed_from_snapshot=True)
        self.assertEqual(result, 1)
        restored = load_snapshot(snapshot)
        self.assertEqual(restored["shows"][0]["progress"]["data"]["watched"], 5)
        self.assertEqual(restored["shows"][0]["progress"]["last_success_at"], value["shows"][0]["progress"]["last_success_at"])
        self.assertTrue(restored["shows"][0]["progress"]["error"])
        self.assertTrue(restored["list"]["error"])

    def test_snapshot_seeding_never_replaces_newer_local_cache(self):
        cache = Cache(self.state, "test-account")
        self.addCleanup(cache.close)
        cache.fetch("progress:123", "new source", lambda: {"watched": 99})
        before = cache.read("progress:123")
        seed_progress(cache, report(), "following")
        self.assertEqual(cache.read("progress:123"), before)


if __name__ == "__main__":
    unittest.main()
