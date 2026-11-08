"""Export an allowlisted public snapshot, without contacting Trakt."""

from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import tempfile
from urllib.parse import urlsplit

from .state import AppError
from .status import display_status

ASSETS = Path(__file__).with_name("web")
PUBLIC_FILES = {"index.html", "dashboard.css", "dashboard.js", "robots.txt"}


def public_time(value):
    if not value:
        return None
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return result.isoformat() if result.tzinfo else None
    except (ValueError, TypeError, AttributeError):
        return None


def public_episode(value):
    if not isinstance(value, dict):
        return None
    if any(type(value.get(k)) is not int or value[k] < 0 for k in ("season", "episode")):
        return None
    return {"season": value["season"], "episode": value["episode"],
            "watched_at": public_time(value.get("watched_at"))}


def public_snapshot(report, statuses=None):
    """Do not export account IDs, private notes, API URLs, or raw errors."""
    listing = report["list"]
    shows = []
    for show in report["shows"]:
        stored = show["progress"]
        data = stored["data"]
        url = show.get("url", "")
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.netloc != "trakt.tv" or not parsed.path.startswith("/shows/"):
            url = "https://trakt.tv"
        progress = None
        if data is not None:
            counts = {k: data.get(k) for k in ("aired", "watched", "aired_unwatched")}
            if (all(type(v) is int and v >= 0 for v in counts.values())
                    and counts["aired"] == counts["watched"] + counts["aired_unwatched"]):
                progress = {**counts, "recent": public_episode(data.get("most_recently_watched")),
                            "furthest": public_episode(data.get("furthest_watched")),
                            "rewatch_reset": bool(data.get("reset_at"))}
        shows.append({"title": show["title"], "year": show.get("year"), "url": url,
                      "progress": progress, "checked_at": public_time(stored["last_success_at"]),
                      "refresh_failed": bool(stored["error"]),
                      "status": display_status((statuses or {}).get(str(show["ids"]["trakt"])))})
    return {"generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "list_checked_at": public_time(listing["last_success_at"]),
            "list_refresh_failed": bool(listing["error"]), "shows": shows}


def export_dashboard(report, directory, private_directory, statuses=None):
    destination = Path(directory).expanduser().resolve()
    private = Path(private_directory).resolve()
    if destination == private or destination.is_relative_to(private) or private.is_relative_to(destination):
        raise AppError("Export to a separate public directory outside the private state directory.")
    if destination.exists():
        if not destination.is_dir() or any(p.name not in PUBLIC_FILES or not p.is_file() or p.is_symlink()
                                           for p in destination.iterdir()):
            raise AppError("Dashboard output must be empty or contain only previously exported dashboard files.")
    snapshot = public_snapshot(report, statuses)
    # JSON lives inside an inert script element; escape HTML delimiters as well as JSON.
    payload = json.dumps(snapshot, ensure_ascii=True).replace("<", "\\u003c").replace(
        ">", "\\u003e").replace("&", "\\u0026")
    template = (ASSETS / "index.html").read_text()
    html = template.replace("__MYSHOWS_DATA__", payload)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as temporary:
        staging = Path(temporary)
        (staging / "index.html").write_text(html)
        for name in PUBLIC_FILES - {"index.html"}:
            shutil.copyfile(ASSETS / name, staging / name)
        destination.mkdir(exist_ok=True)
        # Install index last, so visitors never see a page without its assets.
        for name in ("dashboard.css", "dashboard.js", "robots.txt", "index.html"):
            (staging / name).replace(destination / name)
    return snapshot
