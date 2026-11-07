"""Normalize source progress without inferring watches across episode gaps."""

from datetime import datetime
from urllib.parse import quote

from .state import AppError
from .trakt import API_URL


def segment(value):
    return quote(str(value), safe="")


def validate_shows(items):
    for item in items:
        try:
            show = item["show"]
            if item["type"] != "show" or type(show["ids"]["trakt"]) is not int or not isinstance(show["title"], str):
                raise ValueError
        except (KeyError, TypeError, ValueError):
            raise AppError("Trakt returned an invalid show list; cached data was preserved.") from None
    return items


def summarize(value):
    try:
        aired, completed = value["aired"], value["completed"]
        if any(type(n) is not int or n < 0 for n in (aired, completed)) or completed > aired:
            raise ValueError
        watches = []
        for season in value["seasons"]:
            number = season["number"]
            if type(number) is not int or number < 0:
                raise ValueError
            for episode in season["episodes"]:
                if type(episode["completed"]) is not bool or type(episode["number"]) is not int:
                    raise ValueError
                if number == 0 or not episode["completed"]:
                    continue
                watched_at = episode.get("last_watched_at")
                if watched_at:
                    dt = datetime.fromisoformat(watched_at.replace("Z", "+00:00"))
                    if dt.tzinfo is None:
                        raise ValueError
                else:
                    dt = None
                watches.append((number, episode["number"], watched_at, dt))
        recent = max((w for w in watches if w[3]), key=lambda w: w[3], default=None)
        furthest = max(watches, key=lambda w: (w[0], w[1]), default=None)
        def episode_ref(watch):
            return {"season": watch[0], "episode": watch[1], "watched_at": watch[2]} if watch else None
        return {"aired": aired, "watched": completed, "aired_unwatched": aired - completed,
                "most_recently_watched": episode_ref(recent), "furthest_watched": episode_ref(furthest),
                "reset_at": value.get("reset_at"), "specials_included": False,
                "basis": "Trakt aired-episode totals; no local rewatch reset applied"}
    except (KeyError, TypeError, ValueError, AttributeError):
        raise AppError("Trakt returned invalid watched progress; cached data was preserved.") from None


def overview(client, cache, list_id, offline=False):
    list_path = f"/users/me/lists/{segment(list_id)}/items/show"
    listing = cache.fetch("list:" + list_id, API_URL + list_path,
                          lambda: validate_shows(client.pages(list_path)), offline=offline)
    rows, seen = [], set()
    for item in listing["data"] or []:
        show = item["show"]
        trakt_id = show["ids"]["trakt"]
        if trakt_id in seen:
            continue
        seen.add(trakt_id)
        path = f"/shows/{trakt_id}/progress/watched"
        def load_progress():
            raw, _ = client.get(path, {"hidden": "true", "specials": "false"})
            return summarize(raw)
        progress = cache.fetch(f"progress:{trakt_id}", API_URL + path + "?hidden=true&specials=false",
                               load_progress, offline=offline)
        rows.append({"title": show["title"], "year": show.get("year"), "ids": show["ids"],
                     "url": f"https://trakt.tv/shows/{segment(show['ids'].get('slug') or trakt_id)}",
                     "progress": progress, "renewal": None, "production": None})
    return {"list_id": list_id, "list": {k: v for k, v in listing.items() if k != "data"}, "shows": rows}


def display(report):
    listing = report["list"]
    print(f"List {report['list_id']}: {listing['state']}; last successful update: {listing['last_success_at'] or 'never'}")
    if listing["source"]:
        print("Source: " + listing["source"])
    if listing["error"]:
        print("  " + listing["error"])
    if not report["shows"]:
        print("No shows in this list." if listing["last_success_at"] else "Show list is unknown.")
    for show in report["shows"]:
        progress = show["progress"]
        data = progress["data"]
        print(f"\n{show['title']} ({show['year'] or 'year unknown'}) [{progress['state']}]")
        if data:
            print(f"  Aired episodes: {data['watched']} watched; {data['aired_unwatched']} unwatched")
            for key, label in (("most_recently_watched", "Most recently watched"), ("furthest_watched", "Furthest watched")):
                ref = data[key]
                text = f"S{ref['season']:02}E{ref['episode']:02}" if ref else "unknown"
                print(f"  {label}: {text}")
            if data["reset_at"]:
                print("  Trakt rewatch reset exists; counts use Trakt totals without a local reset.")
        else:
            print("  Watched progress: unknown")
        print(f"  Last successful update: {progress['last_success_at'] or 'never'}")
        print(f"  Source: {progress['source'] or show['url']}")
        if progress["error"]:
            print("  " + progress["error"])
    print("\nProgress covers aired regular episodes; specials excluded. UK streaming access is unknown.")
