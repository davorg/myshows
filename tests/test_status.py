from copy import deepcopy
from datetime import date, timedelta
import json
from pathlib import Path
import tempfile
import unittest

from myshows.dashboard import public_snapshot, export_dashboard
from myshows.state import AppError
from myshows.status import load_statuses, validate_statuses
from test_dashboard import report, SnapshotParser


def document():
    return {"schema_version": 1, "shows": {"123": {"lead": "release", "facts": [
        {"id": "release", "kind": "release", "season": 2, "headline": "Season 2: March 2027",
         "detail": "A month has been announced; an exact day is unknown.", "confidence": "confirmed",
         "checked_on": "2026-11-07", "sources": [{"name": "Test publisher", "url": "https://example.com/news", "published_on": "2026-10-01"}],
         "release": {"precision": "month", "value": "2027-03", "region": "UK timing unverified"}},
        {"id": "ending", "kind": "outcome", "season": 2, "headline": "Cancelled after season 2",
         "detail": "The final season is still due to air.", "confidence": "reported", "checked_on": "2026-11-07",
         "sources": [{"name": "Trade reporting", "url": "https://example.com/ending", "published_on": "2026-03-01"}]}
    ]}}}


class StatusTests(unittest.TestCase):
    def test_independent_ending_and_release_survive_export(self):
        statuses = validate_statuses(document())
        public = public_snapshot(report(), statuses)["shows"][0]["status"]
        self.assertEqual(public["lead"]["release"]["value"], "2027-03")
        self.assertEqual(public["lead"]["release"]["precision"], "month")
        self.assertEqual(public["facts"][1]["kind"], "outcome")
        self.assertEqual(public["facts"][1]["confidence"], "reported")
        self.assertNotIn("2027-03-01", json.dumps(public))

    def test_ids_control_matching_and_unknown_remains_unknown(self):
        statuses = validate_statuses(document())
        value = report()
        value["shows"][0]["ids"]["trakt"] = 999
        status = public_snapshot(value, statuses)["shows"][0]["status"]
        self.assertIsNone(status["lead"])
        self.assertEqual(status["facts"], [])

    def test_missing_or_bad_evidence_and_invalid_release_precision_are_rejected(self):
        mutations = [
            lambda d: d["shows"]["123"]["facts"][0].update(sources=[]),
            lambda d: d["shows"]["123"]["facts"][0]["sources"][0].update(url="javascript:alert(1)"),
            lambda d: d["shows"]["123"]["facts"][0]["sources"][0].update(url="http://example.com"),
            lambda d: d["shows"]["123"]["facts"][0].update(checked_on=(date.today()+timedelta(days=1)).isoformat()),
            lambda d: d["shows"]["123"]["facts"][0]["release"].update(precision="day",value="2027-03"),
            lambda d: d["shows"]["123"]["facts"][0]["release"].update(value="2027-13"),
            lambda d: d["shows"]["123"].update(lead="missing"),
            lambda d: d["shows"]["123"]["facts"][1].update(id="release"),
            lambda d: d["shows"]["123"]["facts"][0].update(confidence="speculation"),
        ]
        for mutate in mutations:
            value = document()
            mutate(value)
            with self.subTest(value=value), self.assertRaises(AppError):
                validate_statuses(value)

    def test_build_does_not_advance_evidence_dates_and_escapes_status_html(self):
        value = document()
        value["shows"]["123"]["facts"][0]["headline"] = '</script><script>alert("status")</script>'
        statuses = validate_statuses(value)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            export_dashboard(report(), root/"public", root/"private", statuses)
            parser = SnapshotParser()
            parser.feed((root/"public/index.html").read_text())
            self.assertEqual(len(parser.scripts), 2)
            status = json.loads(parser.data)["shows"][0]["status"]
            self.assertEqual(status["lead"]["checked_on"], "2026-11-07")
            self.assertEqual(status["lead"]["headline"], value["shows"]["123"]["facts"][0]["headline"])

    def test_checked_in_records_have_valid_evidence_without_a_fixed_watchlist(self):
        statuses = load_statuses()
        self.assertTrue(statuses)
        self.assertEqual(statuses["206790"]["lead"]["confidence"], "reported")
        self.assertEqual(statuses["169972"]["lead"]["release"]["precision"], "year")
        self.assertEqual(statuses["205398"]["lead"]["season"], 2)
        self.assertTrue(any(f["kind"] == "renewal" and f["season"] == 3 for f in statuses["205398"]["facts"]))

    def test_unreadable_status_file_fails_instead_of_publishing_empty_updates(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(AppError):
                load_statuses(Path(temporary)/"missing.json")


if __name__ == "__main__":
    unittest.main()
