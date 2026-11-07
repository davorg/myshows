"""Validate dated, sourced status assertions independently of watched history."""

from datetime import date
import json
from pathlib import Path
import re
from urllib.parse import urlsplit

from .state import AppError

DEFAULT_STATUSES = Path(__file__).resolve().parent.parent / "data" / "statuses.json"
KINDS = {"renewal", "production", "release", "outcome"}


def text(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError
    return value


def source_url(value):
    url = urlsplit(text(value))
    if url.scheme != "https" or not url.hostname or url.username is not None:
        raise ValueError
    return value


def release_value(value, precision):
    text(value)
    if precision == "day":
        if date.fromisoformat(value).isoformat() != value:
            raise ValueError
    elif precision == "month":
        if not re.fullmatch(r"\d{4}-\d{2}", value):
            raise ValueError
        date.fromisoformat(value + "-01")
    elif precision == "year":
        if not re.fullmatch(r"\d{4}", value):
            raise ValueError
        date.fromisoformat(value + "-01-01")
    elif precision != "window":
        raise ValueError
    return value


def validate_statuses(document):
    try:
        if type(document["schema_version"]) is not int or document["schema_version"] != 1 or not isinstance(document["shows"], dict):
            raise ValueError
        validated = {}
        for trakt_id, record in document["shows"].items():
            if not trakt_id.isdigit() or not isinstance(record["facts"], list):
                raise ValueError
            facts, identifiers = [], set()
            for fact in record["facts"]:
                identifier = text(fact["id"])
                checked = date.fromisoformat(fact["checked_on"])
                if (identifier in identifiers or fact["kind"] not in KINDS
                        or fact["confidence"] not in {"confirmed", "reported"}
                        or type(fact["season"]) is not int or fact["season"] < 1
                        or checked > date.today()):
                    raise ValueError
                identifiers.add(identifier)
                sources = []
                for source in fact["sources"]:
                    published = source.get("published_on")
                    if published and date.fromisoformat(published) > checked:
                        raise ValueError
                    sources.append({"name": text(source["name"]), "url": source_url(source["url"]),
                                    "published_on": published})
                if not sources:
                    raise ValueError
                value = {"id": identifier, "kind": fact["kind"], "season": fact["season"],
                         "headline": text(fact["headline"]), "detail": text(fact["detail"]),
                         "confidence": fact["confidence"], "checked_on": checked.isoformat(), "sources": sources}
                if fact["kind"] == "release":
                    release = fact["release"]
                    value["release"] = {"precision": release["precision"],
                        "value": release_value(release["value"], release["precision"]),
                        "region": text(release["region"])}
                facts.append(value)
            lead = record["lead"]
            if lead not in identifiers:
                raise ValueError
            validated[trakt_id] = {"lead": next(f for f in facts if f["id"] == lead), "facts": facts}
        return validated
    except (ValueError, KeyError, TypeError, AttributeError):
        raise AppError("Invalid status data. Every status needs a stable show ID, dated evidence and HTTPS sources; release precision must match its value.") from None


def load_statuses(path=DEFAULT_STATUSES):
    try:
        document = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        raise AppError("Unable to read the sourced status file; the existing dashboard was preserved.") from None
    return validate_statuses(document)
