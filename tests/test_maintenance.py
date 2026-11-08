from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from datetime import date
from io import BytesIO, StringIO
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from myshows.__main__ import main
from myshows.maintenance import merge_record
from myshows.production import parse_research, ProviderError, Researcher
from myshows.snapshot import load_snapshot, watchlist_snapshot
from myshows.state import AppError, State
from test_dashboard import report
from test_status import document


def response():
    record = deepcopy(document()["shows"]["123"])
    for fact in record["facts"]:
        fact.pop("checked_on")
        fact.setdefault("release", None)
    record["lead_index"] = 0
    record.pop("lead")
    return {"status": "completed", "output": [
        {"type": "web_search_call", "status": "completed", "action": {"sources": [
            {"url": "https://example.com/news"}, {"url": "https://example.com/ending"}]}},
        {"type": "message", "content": [{"type": "output_text", "text": json.dumps({"trakt_id": 123, **record})}]},
        {"type": "web_search_call", "status": "completed", "action": {"type": "open_page", "url": "https://example.com/news"}},
        {"type": "web_search_call", "status": "completed", "action": {"type": "open_page", "url": "https://example.com/ending"}}]}


class ResearchTests(unittest.TestCase):
    def test_independent_unchecked_facts_keep_original_dates_when_other_facts_refresh(self):
        previous = document()["shows"]["123"]
        refreshed = deepcopy(previous)
        refreshed["facts"] = refreshed["facts"][:1]
        refreshed["facts"][0]["id"] = "new-release-id"
        refreshed["facts"][0]["checked_on"] = date.today().isoformat()
        refreshed["lead"] = "new-release-id"
        merged = merge_record(previous, refreshed)
        self.assertEqual(len(merged["facts"]), 2)
        self.assertEqual(merged["facts"][1], previous["facts"][1])
        self.assertEqual(previous["facts"][0]["id"], "release")

    def test_research_requires_live_search_correct_identity_and_actual_source_urls(self):
        mutations = [lambda r: r.update(status="incomplete"),
                     lambda r: r.update(output=[r["output"][1]]),
                     lambda r: r.update(output=[r["output"][1], {"type": "web_search_call", "status": "completed", "action": {}}]),
                     lambda r: r["output"][1]["content"][0].update(text="not JSON"),
                     lambda r: r["output"][1]["content"][0].update(text=json.dumps({"trakt_id": 999, "facts": [], "lead_index": None})),
                     lambda r: r["output"][1].update(content=[{"type": "refusal", "refusal": "No"}])]
        for mutation in mutations:
            value = response()
            mutation(value)
            with self.subTest(value=value), self.assertRaises(AppError):
                parse_research(value, 123, date.today())

    def test_validated_records_keep_precision_and_program_sets_check_date(self):
        result = parse_research(response(), 123, date.today())
        self.assertEqual(result["lead"], "release")
        self.assertEqual(result["facts"][0]["release"]["value"], "2027-03")
        self.assertEqual(result["facts"][0]["checked_on"], date.today().isoformat())
        self.assertNotIn("release", result["facts"][1])

    def test_old_premiere_cannot_hide_supported_next_season_facts(self):
        value = response()
        content = value["output"][1]["content"][0]
        result = json.loads(content["text"])
        result["facts"][0]["release"] = {"precision": "month", "value": "2010-01", "region": "US"}
        result["facts"][1]["season"] = 3
        content["text"] = json.dumps(result)
        with self.assertRaisesRegex(AppError, "passed premiere"):
            parse_research(value, 123, date.today())

    def test_unretrieved_fact_is_dropped_without_discarding_independent_supported_evidence(self):
        value = response()
        value["output"].pop(2)
        value["output"][0]["action"]["sources"].pop(0)
        warnings = []
        result = parse_research(value, 123, date.today(), warnings)
        self.assertEqual(result["lead"], "ending")
        self.assertEqual([f["id"] for f in result["facts"]], ["ending"])
        self.assertEqual(len(warnings), 1)

    def test_opened_sources_are_accepted_but_unsearched_unknown_is_rejected(self):
        value = response()
        value["output"][0]["action"] = {}
        value["output"][1]["content"][0]["annotations"] = [
            {"type": "url_citation", "url": "https://example.com/news"},
            {"type": "url_citation", "url": "https://example.com/ending"}]
        self.assertIsNotNone(parse_research(value, 123, date.today()))
        value["output"][1]["content"][0]["text"] = json.dumps({"trakt_id": 123, "lead_index": None, "facts": []})
        self.assertIsNone(parse_research(value, 123, date.today()))
        value["output"] = [value["output"][1]]
        with self.assertRaises(AppError):
            parse_research(value, 123, date.today())

    def test_request_omits_private_viewing_data_and_requires_bounded_search(self):
        class Transport:
            def open(self, request, timeout):
                self.request = request
                return BytesIO(json.dumps(response()).encode())
        transport = Transport()
        researcher = Researcher(api_key="secret-key", opener=transport)
        researcher.research(report()["shows"][0])
        payload = json.loads(transport.request.data)
        self.assertEqual(payload["model"], "gpt-6.1-sol")
        self.assertEqual(payload["reasoning"], {"effort": "low"})
        self.assertNotIn("private-", json.dumps(payload))
        self.assertNotIn("secret-key", json.dumps(payload))
        self.assertEqual(payload["tool_choice"], "required")
        self.assertFalse(payload["store"])
        self.assertLessEqual(payload["max_tool_calls"], 8)
        self.assertEqual(payload["text"]["format"]["type"], "json_schema")

    def test_provider_errors_never_expose_response_bodies_or_credentials(self):
        class Transport:
            def open(self, request, timeout):
                raise HTTPError(request.full_url, 401, "secret-error", {}, BytesIO(b"secret-body"))
        with self.assertRaises(ProviderError) as caught:
            Researcher(api_key="secret-key", opener=Transport()).research(report()["shows"][0])
        self.assertTrue(caught.exception.stop)
        self.assertNotIn("secret", str(caught.exception))
        with patch.dict("os.environ", {}, clear=True), self.assertRaises(AppError):
            Researcher()


class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = self.root / "private"
        self.watchlist = self.root / "watchlist.json"
        self.statuses = self.root / "statuses.json"
        self.watchlist.write_text(json.dumps(watchlist_snapshot(report())))
        self.statuses.write_text(json.dumps(document()))
        self.output = StringIO()
        self.enterContext(redirect_stdout(self.output))
        self.enterContext(redirect_stderr(self.output))

    def research(self, *extra):
        return main(["refresh-production", "--state-dir", str(self.state), "--snapshot", str(self.watchlist),
                     "--statuses", str(self.statuses), *extra])

    def test_dry_run_needs_no_key_state_or_network_and_unknown_id_rejected(self):
        with patch("myshows.maintenance.Researcher", side_effect=AssertionError("No calls")):
            self.assertEqual(self.research("--dry-run"), 0)
            self.assertEqual(self.research("--missing-only"), 0)
            self.assertEqual(self.research("--show", "999"), 1)
        self.assertFalse(self.state.exists())

    def test_partial_failure_saves_success_and_preserves_other_show_dates(self):
        original = document()
        original["shows"]["456"] = deepcopy(original["shows"]["123"])
        self.statuses.write_text(json.dumps(original))
        snapshot = json.loads(self.watchlist.read_text())
        snapshot["shows"].append({**deepcopy(snapshot["shows"][0]), "trakt_id": 456, "title": "Another Show"})
        self.watchlist.write_text(json.dumps(snapshot))
        changed = parse_research(response(), 123, date.today())
        with patch("myshows.maintenance.Researcher") as cls:
            cls.return_value.research.side_effect = [changed, AppError("Service unavailable")]
            self.assertEqual(self.research(), 1)
        saved = json.loads(self.statuses.read_text())
        self.assertEqual(saved["shows"]["123"]["facts"][0]["checked_on"], date.today().isoformat())
        self.assertEqual(saved["shows"]["456"], original["shows"]["456"])
        self.assertEqual(json.loads((self.state / "statuses-before-refresh.json").read_text()), original)

    def test_unknown_and_invalid_evidence_preserve_previous_file_byte_for_byte(self):
        original = self.statuses.read_bytes()
        for result, code in ((None, 0), ({"lead": "invalid", "facts": []}, 1), (ProviderError(429), 1)):
            with patch("myshows.maintenance.Researcher") as cls:
                if isinstance(result, Exception):
                    cls.return_value.research.side_effect = result
                else:
                    cls.return_value.research.return_value = result
                self.assertEqual(self.research(), code)
            self.assertEqual(self.statuses.read_bytes(), original)

    def test_rebuild_is_offline_and_does_not_create_private_state(self):
        with patch.object(State, "load", side_effect=AssertionError("No credentials")):
            result = main(["rebuild-site", "--state-dir", str(self.state), "--snapshot", str(self.watchlist),
                           "--statuses", str(self.statuses), "--output", str(self.root / "public")])
        self.assertEqual(result, 0)
        self.assertFalse(self.state.exists())

    def refresh(self, value):
        with patch.object(State, "load", return_value={"client_id": "test", "account": {"slug": "test"}}), \
                patch("myshows.maintenance.overview", return_value=value):
            return main(["refresh-shows", "--state-dir", str(self.state), "--output", str(self.watchlist)])

    def test_refresh_without_cached_list_preserves_existing_public_snapshot(self):
        original = self.watchlist.read_bytes()
        value = report()
        value["list"]["last_success_at"] = None
        value["shows"] = []
        self.assertEqual(self.refresh(value), 1)
        self.assertEqual(self.watchlist.read_bytes(), original)

    def test_partial_refresh_exports_cached_values_with_failure_flags(self):
        self.assertEqual(self.refresh(report()), 1)
        saved = load_snapshot(self.watchlist)
        self.assertEqual(saved["shows"][0]["progress"]["data"]["watched"], 5)
        self.assertEqual(saved["shows"][0]["progress"]["last_success_at"], "2026-11-07T10:00:00+00:00")
        self.assertTrue(saved["list"]["error"])

    def test_successfully_empty_list_removes_previous_shows(self):
        value = report()
        value["list"]["error"] = None
        value["shows"] = []
        self.assertEqual(self.refresh(value), 0)
        self.assertEqual(load_snapshot(self.watchlist)["shows"], [])
        self.assertIn("Removed: A Test Show", self.output.getvalue())


if __name__ == "__main__":
    unittest.main()
