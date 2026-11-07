"""Offline integration tests; every API response below is synthetic test data."""

from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from io import BytesIO, StringIO
from http.client import IncompleteRead
import json
from pathlib import Path
import stat
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from myshows.__main__ import main
from myshows.progress import overview, summarize
from myshows.state import AppError, Cache, State
from myshows.trakt import ApiError, Trakt


def token(**changes):
    return {"access_token": "test-access", "refresh_token": "test-refresh", "created_at": int(time.time()),
            "expires_in": 3600, **changes}


def progress():
    return {"aired": 4, "completed": 2, "reset_at": None, "seasons": [{
        "number": 1, "episodes": [
            {"number": 1, "completed": True, "last_watched_at": "2026-11-03T10:00:00Z"},
            {"number": 2, "completed": False, "last_watched_at": None},
            {"number": 3, "completed": True, "last_watched_at": "2026-10-01T10:00:00Z"},
            {"number": 4, "completed": False, "last_watched_at": None}]}]}


def item(show_id=42, title="Test Show"):
    return {"type": "show", "show": {"title": title, "year": 2026,
            "ids": {"trakt": show_id, "slug": f"test-show-{show_id}", "tmdb": 100 + show_id}}}


class Response(BytesIO):
    def __init__(self, value, headers=None):
        super().__init__(json.dumps(value).encode())
        self.headers = headers or {}


class Transport:
    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def open(self, request, timeout):
        self.requests.append(request)
        if not self.responses:
            raise AssertionError("Unexpected network request")
        result = self.responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def http_error(status, headers=None):
    return HTTPError("https://api.trakt.tv/test", status, "test", headers or {}, BytesIO(b"sensitive-body"))


class Clock:
    def __init__(self):
        self.now = 0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.sleeps.append(seconds)
        self.now += seconds


class PrototypeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = State(Path(self.temp.name) / "private")
        self.credentials = {"client_id": "test-client", "redirect_uri": "https://example.com/callback",
                            "tokens": token(), "account": {"username": "test", "slug": "test"}}
        self.state.save(self.credentials)

    def client(self, responses, clock=None):
        transport = Transport(responses)
        kwargs = {"sleep": clock.sleep, "clock": clock} if clock else {}
        return Trakt(self.state, deepcopy(self.credentials), opener=transport, **kwargs), transport

    def cache(self, account="test"):
        cache = Cache(self.state, account)
        self.addCleanup(cache.close)
        return cache

    def test_device_flow_pending_slowdown_and_token_storage(self):
        clock = Clock()
        client, transport = self.client([
            Response({"device_code": "test-device", "user_code": "TEST-CODE", "verification_url": "https://auth.trakt.tv/activate",
                      "interval": 2, "expires_in": 60}),
            http_error(400), http_error(429, {"Retry-After": "10"}), Response(token()),
        ], clock)
        messages = []
        client.authenticate(messages.append)
        self.assertEqual(clock.sleeps, [2, 2, 10])
        self.assertIn("TEST-CODE", messages[0])
        self.assertNotIn("test-access", " ".join(messages))
        self.assertEqual(self.state.load()["tokens"]["refresh_token"], "test-refresh")
        self.assertNotIn("account", self.state.load())
        self.assertTrue(all(r.full_url.startswith("https://auth.trakt.tv/oauth/") for r in transport.requests))
        self.assertNotIn("client_secret", json.loads(transport.requests[-1].data))

    def test_device_denial_does_not_overwrite_existing_tokens(self):
        client, _ = self.client([
            Response({"device_code": "x", "user_code": "X", "verification_url": "https://auth.trakt.tv/activate",
                      "interval": 2, "expires_in": 30}), http_error(418)], Clock())
        with self.assertRaisesRegex(AppError, "denied"):
            client.authenticate(lambda _: None)
        self.assertEqual(self.state.load()["tokens"], self.credentials["tokens"])

    def test_device_expiry_stops_polling(self):
        clock = Clock()
        client, transport = self.client([Response({"device_code": "x", "user_code": "X",
            "verification_url": "https://auth.trakt.tv/activate", "interval": 2, "expires_in": 5}),
            http_error(400), http_error(400)], clock)
        with self.assertRaisesRegex(AppError, "expired"):
            client.authenticate(lambda _: None)
        self.assertEqual(len(transport.requests), 3)
        self.assertLess(clock.now, 5)

    def test_refresh_rotates_tokens_before_data_request(self):
        self.credentials["tokens"] = token(created_at=0)
        client, transport = self.client([Response(token(access_token="new-access", refresh_token="new-refresh")),
                                       Response({"value": True})])
        data, _ = client.get("/users/settings")
        self.assertEqual(data, {"value": True})
        self.assertEqual(self.state.load()["tokens"]["refresh_token"], "new-refresh")
        body = json.loads(transport.requests[0].data)
        self.assertEqual(body["grant_type"], "refresh_token")
        self.assertEqual(body["redirect_uri"], "https://example.com/callback")
        self.assertEqual(transport.requests[1].get_header("Authorization"), "Bearer new-access")

    def test_unauthorized_refreshes_once(self):
        client, transport = self.client([http_error(401), Response(token(access_token="new")), http_error(401)])
        with self.assertRaises(ApiError):
            client.get("/users/settings")
        with self.assertRaises(ApiError):
            client.get("/users/settings")
        self.assertEqual(len(transport.requests), 3)

    def test_failed_refresh_does_not_destroy_saved_tokens(self):
        self.credentials["tokens"] = token(created_at=0)
        self.state.save(self.credentials)
        client, _ = self.client([http_error(400)])
        with self.assertRaisesRegex(AppError, "refresh was rejected"):
            client.get("/users/settings")
        self.assertEqual(self.state.load()["tokens"], self.credentials["tokens"])

    def test_paginated_list_complete_and_get_headers(self):
        client, transport = self.client([Response([item()], {"X-Pagination-Page-Count": "2"}),
                                       Response([item(43)], {"X-Pagination-Page-Count": "2"})])
        result = client.pages("/users/me/lists/123/items/show")
        self.assertEqual(len(result), 2)
        self.assertIn("page=2", transport.requests[1].full_url)
        self.assertEqual(transport.requests[0].get_header("Trakt-api-key"), "test-client")
        self.assertEqual(transport.requests[0].get_header("Trakt-api-version"), "2")

    def test_progress_handles_rewatch_gap_and_specials(self):
        raw = progress()
        raw["seasons"].append({"number": 0, "episodes": [{"number": 99, "completed": True,
                                    "last_watched_at": "2026-11-06T10:00:00Z"}]})
        result = summarize(raw)
        self.assertEqual(result["aired_unwatched"], 2)
        self.assertEqual(result["most_recently_watched"]["episode"], 1)
        self.assertEqual(result["furthest_watched"]["episode"], 3)
        self.assertFalse(result["specials_included"])

    def test_unknown_watch_time_does_not_invent_most_recent(self):
        raw = progress()
        for e in raw["seasons"][0]["episodes"]:
            e["last_watched_at"] = None
        result = summarize(raw)
        self.assertIsNone(result["most_recently_watched"])
        self.assertEqual(result["furthest_watched"]["episode"], 3)

    def test_progress_uses_timestamps_rather_than_lexical_date_order(self):
        raw = progress()
        raw["seasons"][0]["episodes"][0]["last_watched_at"] = "2026-11-03T10:00:00+02:00"
        raw["seasons"][0]["episodes"][2]["last_watched_at"] = "2026-11-03T09:00:00Z"
        self.assertEqual(summarize(raw)["most_recently_watched"]["episode"], 3)

    def test_invalid_progress_is_not_silently_zero(self):
        for changes in ({"completed": 10}, {"aired": True}, {"seasons": None}, {"aired": None}):
            with self.subTest(changes=changes), self.assertRaises(AppError):
                summarize({**progress(), **changes})

    def test_never_watched_and_caught_up(self):
        for count in (0, 4):
            raw = progress()
            raw["completed"] = count
            for e in raw["seasons"][0]["episodes"]:
                e["completed"] = count == 4
                e["last_watched_at"] = "2026-11-03T10:00:00Z" if count else None
            result = summarize(raw)
            self.assertEqual(result["aired_unwatched"], 4 - count)
            if count == 0:
                self.assertIsNone(result["furthest_watched"])

    def test_snapshot_survives_restart_then_failed_refresh(self):
        cache = self.cache()
        client, _ = self.client([Response([item()]), Response(progress())])
        fresh = overview(client, cache, "123")
        restarted = self.cache()
        client, transport = self.client([])
        offline = overview(client, restarted, "123", offline=True)
        self.assertEqual(offline["shows"][0]["progress"]["data"], fresh["shows"][0]["progress"]["data"])
        self.assertEqual(len(transport.requests), 0)
        client, _ = self.client([http_error(503), http_error(503)])
        stale = overview(client, restarted, "123")
        self.assertEqual(stale["list"]["state"], "stale")
        old, new = fresh["shows"][0]["progress"], stale["shows"][0]["progress"]
        self.assertEqual(new["state"], "stale")
        self.assertEqual(old["data"], new["data"])
        self.assertEqual(old["last_success_at"], new["last_success_at"])
        self.assertIsNotNone(new["error"])

    def test_partial_pagination_failure_does_not_replace_complete_list(self):
        cache = self.cache()
        client, _ = self.client([Response([item(), item(43)]), Response(progress()), Response(progress())])
        overview(client, cache, "123")
        client, _ = self.client([Response([item()], {"X-Pagination-Page-Count": "2"}),
                                http_error(503), Response(progress()), Response(progress())])
        stale = overview(client, cache, "123")
        self.assertEqual(len(stale["shows"]), 2)
        self.assertEqual(stale["list"]["state"], "stale")

    def test_partial_provider_failure_preserves_other_show_success(self):
        cache = self.cache()
        client, _ = self.client([Response([item(), item(43)]), Response(progress()), http_error(503)])
        report = overview(client, cache, "123")
        self.assertEqual(report["shows"][0]["progress"]["state"], "fresh")
        self.assertEqual(report["shows"][1]["progress"]["state"], "unknown")
        self.assertIsNone(report["shows"][1]["progress"]["data"])

    def test_empty_success_removes_old_items(self):
        cache = self.cache()
        client, _ = self.client([Response([item()]), Response(progress()), Response([])])
        overview(client, cache, "123")
        empty = overview(client, cache, "123")
        self.assertEqual(empty["shows"], [])
        self.assertEqual(empty["list"]["state"], "fresh")

    def test_accounts_do_not_share_cache(self):
        client, _ = self.client([Response([item()]), Response(progress())])
        overview(client, self.cache("first-account"), "123")
        offline = overview(client, self.cache("second-account"), "123", offline=True)
        self.assertEqual(offline["shows"], [])
        self.assertEqual(offline["list"]["state"], "unknown")

    def test_rate_limit_stops_remaining_requests(self):
        client, transport = self.client([Response([item(), item(43)]), http_error(429, {"Retry-After": "60"})])
        report = overview(client, self.cache(), "123")
        self.assertEqual(len(transport.requests), 2)
        self.assertIn("60 seconds", report["shows"][0]["progress"]["error"])
        self.assertEqual(report["shows"][1]["progress"]["state"], "unknown")

    def test_invalid_json_and_network_errors_are_safe(self):
        for response in (BytesIO(b"invalid sensitive-body"), URLError("sensitive-body"), IncompleteRead(b"partial")):
            if isinstance(response, BytesIO):
                response.headers = {}
            client, _ = self.client([response])
            with self.assertRaises(AppError) as caught:
                client.get("/users/settings")
            self.assertNotIn("sensitive-body", str(caught.exception))

    def test_invalid_fresh_progress_keeps_previous_snapshot(self):
        cache = self.cache()
        client, _ = self.client([Response([item()]), Response(progress())])
        fresh = overview(client, cache, "123")
        client, _ = self.client([Response([item()]), Response({"aired": None})])
        report = overview(client, cache, "123")
        self.assertEqual(report["shows"][0]["progress"]["state"], "stale")
        self.assertEqual(report["shows"][0]["progress"]["data"], fresh["shows"][0]["progress"]["data"])

    def test_cli_setup_identity_and_list_discovery(self):
        directory = Path(self.temp.name) / "new-account"
        args = ["--state-dir", str(directory)]
        output = StringIO()
        with patch("myshows.__main__.getpass", return_value="new-client"), patch("builtins.input", return_value=""), redirect_stdout(output):
            self.assertEqual(main(args + ["configure"]), 0)
        new_state = State(directory)
        self.assertEqual(new_state.load()["redirect_uri"], "http://localhost")
        client, _ = self.client([
            Response({"device_code": "x", "user_code": "X", "verification_url": "https://auth.trakt.tv/activate",
                      "interval": 1, "expires_in": 30}), Response(token()),
            Response({"user": {"username": "New User", "ids": {"slug": "new-user"}}})], Clock())
        client.state = new_state
        client.credentials = new_state.load()
        with patch("myshows.__main__.Trakt", return_value=client), redirect_stdout(output):
            self.assertEqual(main(args + ["auth"]), 0)
        self.assertIn("Connected as New User", output.getvalue())
        self.assertNotIn("test-access", output.getvalue())
        self.assertEqual(new_state.load()["account"]["slug"], "new-user")
        client, _ = self.client([
            Response({"user": {"username": "New User", "ids": {"slug": "new-user"}}}),
            Response([{"name": "Following", "ids": {"trakt": 123, "slug": "following"}}])])
        client.state = new_state
        client.credentials = new_state.load()
        with patch("myshows.__main__.Trakt", return_value=client), redirect_stdout(output):
            self.assertEqual(main(args + ["lists"]), 0)
        self.assertIn("Following\tID: 123\tslug: following", output.getvalue())

    def test_configure_accepts_development_and_https_callbacks(self):
        callbacks = ["http://localhost", "http://localhost:8080/oauth/callback",
                     "http://127.0.0.1:8080/callback", "http://[::1]:8080/callback",
                     "https://myshows.davecross.co.uk/oauth/callback"]
        for index, uri in enumerate(callbacks):
            with self.subTest(uri=uri):
                directory = Path(self.temp.name) / f"callback-{index}"
                with patch("myshows.__main__.getpass", return_value="test-client"), \
                        patch("builtins.input", return_value=uri), redirect_stdout(StringIO()):
                    self.assertEqual(main(["--state-dir", str(directory), "configure"]), 0)
                self.assertEqual(State(directory).load()["redirect_uri"], uri)

    def test_configure_rejects_unsafe_and_malformed_callbacks_without_saving(self):
        callbacks = ["http://example.com/callback", "http://localhost.example.com/callback",
                     "http://192.168.1.2/callback", "file:///callback", "https://",
                     "https://user:password@example.com/callback", "http://localhost#fragment",
                     "http://localhost:invalid/callback", "http://[broken", "http://localhost:0",
                     "http://localhost\n/callback"]
        for index, uri in enumerate(callbacks):
            with self.subTest(uri=uri):
                directory = Path(self.temp.name) / f"bad-callback-{index}"
                error = StringIO()
                with patch("myshows.__main__.getpass", return_value="test-client"), \
                        patch("builtins.input", return_value=uri), redirect_stderr(error):
                    self.assertEqual(main(["--state-dir", str(directory), "configure"]), 1)
                self.assertIn("Use HTTPS, or HTTP on localhost", error.getvalue())
                self.assertFalse((directory / "credentials.json").exists())

    def test_remote_data_writes_are_rejected(self):
        client, transport = self.client([])
        with self.assertRaises(AppError):
            client.request("/sync/history", payload={"shows": []})
        self.assertEqual(len(transport.requests), 0)

    def test_private_permissions_and_lock(self):
        self.cache()
        for path, expected in ((self.state.directory, 0o700), (self.state.credentials, 0o600),
                               (self.state.directory / "cache.sqlite3", 0o600)):
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), expected)
        with self.state.lock():
            with self.assertRaises(AppError):
                with self.state.lock():
                    self.fail("Lock should not be acquired twice")

    def test_cli_offline_report_and_missing_config(self):
        client, _ = self.client([Response([item()]), Response(progress())])
        overview(client, self.cache("test-client:test"), "123")
        out = StringIO()
        with redirect_stdout(out), patch.object(Trakt, "request", side_effect=AssertionError("network")):
            result = main(["--state-dir", str(self.state.directory), "report", "--list", "123", "--json"])
        self.assertEqual(result, 0)
        report = json.loads(out.getvalue())
        self.assertEqual(report["shows"][0]["title"], "Test Show")
        self.assertNotIn("test-access", out.getvalue())
        error = StringIO()
        with redirect_stderr(error):
            result = main(["--state-dir", str(Path(self.temp.name) / "empty"), "whoami"])
        self.assertEqual(result, 1)
        self.assertIn("configure first", error.getvalue())


if __name__ == "__main__":
    unittest.main()
