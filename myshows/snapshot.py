"""Portable public watchlist input for credential-free builds."""

import json
import os
from pathlib import Path
import tempfile
from urllib.parse import urlsplit

from .dashboard import public_episode, public_snapshot, public_time
from .state import AppError


def watchlist_snapshot(report):
    exported = public_snapshot(report)
    shows = []
    for original, show in zip(report["shows"], exported["shows"]):
        shows.append({"trakt_id": original["ids"]["trakt"],
                      **{key: value for key, value in show.items() if key != "status"}})
    return {"schema_version": 1, "list_checked_at": exported["list_checked_at"],
            "list_refresh_failed": exported["list_refresh_failed"], "shows": shows}


def write_snapshot(report, filename, private_directory):
    destination = Path(filename).expanduser().resolve()
    private = Path(private_directory).resolve()
    if destination == private or destination.is_relative_to(private):
        raise AppError("Write the public snapshot outside the private state directory.")
    value = watchlist_snapshot(report)
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=destination.parent)
    try:
        with os.fdopen(fd, "w") as handle:
            json.dump(value, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return value


def checked_time(value):
    result = public_time(value)
    if value is not None and result is None:
        raise ValueError
    return result


def report_from_snapshot(value):
    """Validate and restore only the fields needed by the public renderer."""
    try:
        if type(value["schema_version"]) is not int or value["schema_version"] != 1:
            raise ValueError
        if type(value["list_refresh_failed"]) is not bool or not isinstance(value["shows"], list):
            raise ValueError
        shows, identifiers = [], set()
        for item in value["shows"]:
            identifier = item["trakt_id"]
            if type(identifier) is not int or identifier < 1 or identifier in identifiers:
                raise ValueError
            identifiers.add(identifier)
            if not isinstance(item["title"], str) or not item["title"].strip():
                raise ValueError
            year = item["year"]
            if year is not None and (type(year) is not int or not 1800 <= year <= 9999):
                raise ValueError
            url = urlsplit(item["url"])
            if url.scheme != "https" or url.netloc != "trakt.tv" or not url.path.startswith("/shows/"):
                raise ValueError
            if type(item["refresh_failed"]) is not bool:
                raise ValueError
            progress = item["progress"]
            data = None
            if progress is not None:
                counts = {key: progress[key] for key in ("aired", "watched", "aired_unwatched")}
                if (not all(type(n) is int and n >= 0 for n in counts.values())
                        or counts["aired"] != counts["watched"] + counts["aired_unwatched"]
                        or type(progress["rewatch_reset"]) is not bool):
                    raise ValueError
                references = {}
                for key in ("recent", "furthest"):
                    reference = progress[key]
                    normalized = public_episode(reference)
                    if reference is not None and normalized is None:
                        raise ValueError
                    references[key] = normalized
                data = {**counts, "most_recently_watched": references["recent"],
                        "furthest_watched": references["furthest"], "reset_at": progress["rewatch_reset"]}
            shows.append({"title": item["title"], "year": year, "ids": {"trakt": identifier}, "url": item["url"],
                          "progress": {"data": data, "last_success_at": checked_time(item["checked_at"]),
                                       "error": "Previous refresh failed" if item["refresh_failed"] else None}})
        return {"list": {"last_success_at": checked_time(value["list_checked_at"]),
                         "error": "Previous refresh failed" if value["list_refresh_failed"] else None},
                "shows": shows}
    except (KeyError, ValueError, TypeError, AttributeError):
        raise AppError("Invalid public watchlist snapshot; the existing dashboard was preserved.") from None


def load_snapshot(filename):
    try:
        value = json.loads(Path(filename).read_text())
    except (OSError, ValueError):
        raise AppError("Unable to read the public watchlist snapshot.") from None
    return report_from_snapshot(value)
