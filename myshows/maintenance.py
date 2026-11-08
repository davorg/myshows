"""Independent refresh operations; publication remains a separate git push."""

from copy import deepcopy
import argparse
import os
from pathlib import Path
import sys

from .dashboard import export_dashboard
from .production import DEFAULT_MODEL, Researcher, ProviderError
from .progress import overview
from .snapshot import load_snapshot, write_snapshot
from .state import AppError, Cache, State
from .status import DEFAULT_STATUSES, load_statuses, validate_statuses
from .storage import write_json
from .trakt import Trakt


def positive(value):
    try:
        number = int(value)
        if number > 0:
            return number
    except ValueError:
        pass
    raise argparse.ArgumentTypeError("Use a positive integer.")


def add_commands(commands):
    refresh = commands.add_parser("refresh-shows", help="Refresh Following and save the public watchlist.")
    refresh.add_argument("--state-dir", default=argparse.SUPPRESS, help="Private state directory.")
    refresh.add_argument("--list", dest="list_id", default="following", help="Trakt list ID or slug (default: following).")
    refresh.add_argument("--output", default="data/watchlist.json")
    for name, description in (("refresh-production", "Research sourced production updates using the OpenAI API (billable)."),
                              ("rebuild-site", "Rebuild the website from saved public files, offline.")):
        command = commands.add_parser(name, help=description)
        command.add_argument("--state-dir", default=argparse.SUPPRESS, help="Private state directory.")
        command.add_argument("--snapshot", default="data/watchlist.json")
        command.add_argument("--statuses", default=str(DEFAULT_STATUSES))
        if name == "rebuild-site":
            command.add_argument("--output", default="site/dist")
        else:
            command.add_argument("--model", default=os.environ.get("MYSHOWS_RESEARCH_MODEL", DEFAULT_MODEL))
            command.add_argument("--show", type=positive, action="append", help="Only research this Trakt show ID; repeatable.")
            command.add_argument("--limit", type=positive, help="Maximum shows to research this run.")
            command.add_argument("--missing-only", action="store_true", help="Only research shows without saved status facts.")
            command.add_argument("--dry-run", action="store_true", help="List selected shows without an API key or any network requests.")


def run_command(args):
    if args.command == "rebuild-site":
        result = export_dashboard(load_snapshot(args.snapshot), args.output, args.state_dir, load_statuses(args.statuses))
        print(f"Built public dashboard with {len(result['shows'])} shows in {args.output}.")
        return 0
    if args.command == "refresh-production":
        return refresh_production(args)
    state = State(args.state_dir)
    with state.lock():
        destination = Path(args.output)
        previous = load_snapshot(destination) if destination.exists() else {"shows": []}
        credentials = state.load()
        client = Trakt(state, credentials)
        account = credentials.get("account") or client.identity()
        cache = Cache(state, credentials["client_id"] + ":" + account["slug"])
        try:
            report = overview(client, cache, args.list_id)
        finally:
            cache.close()
        if report["list"]["last_success_at"] is None:
            raise AppError("Following refresh failed with no cached list; the existing public snapshot was preserved.")
        snapshot = write_snapshot(report, destination, state.directory)
        old = {s["ids"]["trakt"]: s["title"] for s in previous["shows"]}
        new = {s["ids"]["trakt"]: s["title"] for s in report["shows"]}
        for identifier in new.keys() - old.keys():
            print(f"Added: {new[identifier]}")
        for identifier in old.keys() - new.keys():
            print(f"Removed: {old[identifier]}")
        print(f"Saved {len(snapshot['shows'])} shows to {destination}.")
        failed = bool(report["list"]["error"] or any(s["progress"]["error"] for s in report["shows"]))
        if failed:
            print("Some Trakt requests failed; last successful values and dates were retained where available.", file=sys.stderr)
        return int(failed)


def status_document(statuses):
    return {"schema_version": 1, "shows": {key: {"lead": record["lead"]["id"], "facts": record["facts"]}
                                          for key, record in statuses.items()}}


def merge_record(previous, refreshed):
    """Keep independent facts not rechecked, without advancing their dates."""
    result = deepcopy(refreshed)
    identifiers = {f["id"] for f in result["facts"]}
    assertions = {(f["kind"], f["season"]) for f in result["facts"]}
    for fact in (previous or {}).get("facts", []):
        if fact["id"] not in identifiers and (fact["kind"], fact["season"]) not in assertions:
            result["facts"].append(deepcopy(fact))
    return result


def refresh_production(args):
    # Dry runs and no-op selections need neither private state nor credentials.
    report = load_snapshot(args.snapshot)
    statuses = load_statuses(args.statuses)
    identifiers = {s["ids"]["trakt"] for s in report["shows"]}
    if args.show and not set(args.show) <= identifiers:
        raise AppError("A requested show ID is absent from the watchlist snapshot.")
    shows = [s for s in report["shows"] if (not args.show or s["ids"]["trakt"] in args.show)
             and (not args.missing_only or str(s["ids"]["trakt"]) not in statuses)]
    if args.limit:
        shows = shows[:args.limit]
    print(f"Selected {len(shows)} shows for research ({args.model}).")
    for show in shows:
        print(f"  {show['ids']['trakt']}: {show['title']}")
    if args.dry_run or not shows:
        return 0
    researcher = Researcher(model=args.model)
    state = State(args.state_dir)
    with state.lock():
        researcher.on_response = lambda identifier, result: write_json(
            state.directory / "research" / f"{identifier}.json", result)
        # Reload under the lock so another completed refresh cannot be lost.
        document = status_document(load_statuses(args.statuses))
        write_json(state.directory / "statuses-before-refresh.json", document)
        failed = False
        for show in shows:
            identifier = str(show["ids"]["trakt"])
            print(f"Researching: {show['title']}…", flush=True)
            try:
                record = researcher.research(show, document["shows"].get(identifier))
                for warning in researcher.warnings:
                    print(f"  {warning}")
                if record is None:
                    print("  No supported update found; previous facts and check dates retained.")
                    continue
                updated = deepcopy(document)
                updated["shows"][identifier] = merge_record(document["shows"].get(identifier), record)
                validate_statuses(updated)
                # Save each success: a later failure or interruption cannot lose it.
                write_json(args.statuses, updated)
                document = updated
                print(f"  Saved: {next(f['headline'] for f in record['facts'] if f['id'] == record['lead'])}")
            except AppError as exc:
                failed = True
                print(f"  {exc} Previous facts and dates retained.", file=sys.stderr)
                if isinstance(exc, ProviderError) and exc.stop:
                    break
    print("Research complete. Review the source links and JSON diff before committing and publishing.")
    return int(failed)
