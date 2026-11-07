import argparse
from getpass import getpass
from ipaddress import ip_address
import json
import os
import sqlite3
import sys
from urllib.parse import urlsplit

from .dashboard import export_dashboard
from .progress import display, overview
from .state import AppError, Cache, State
from .status import DEFAULT_STATUSES, load_statuses
from .trakt import Trakt


def valid_redirect_uri(uri):
    """Allow HTTPS callbacks and HTTP loopback callbacks for development apps."""
    try:
        parsed = urlsplit(uri)
        if (not parsed.hostname or parsed.username is not None or parsed.fragment
                or any(c.isspace() or ord(c) < 32 for c in uri)
                or (parsed.port is not None and parsed.port == 0)):
            return False
        if parsed.scheme == "https":
            return True
        if parsed.scheme != "http":
            return False
        if parsed.hostname == "localhost":
            return True
        return ip_address(parsed.hostname).is_loopback
    except ValueError:
        return False


def main(argv=None):
    parser = argparse.ArgumentParser(description="Read-only Trakt list and progress prototype.")
    parser.add_argument("--state-dir", default=os.environ.get("MYSHOWS_STATE_DIR", ".myshows"),
                        help="Private state directory (default: .myshows; never serve this directory).")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("configure", help="Enter Trakt app configuration locally.")
    commands.add_parser("auth", help="Authorize via Trakt's device-code flow.")
    commands.add_parser("whoami", help="Fetch and verify the connected account.")
    commands.add_parser("lists", help="List your custom lists and their IDs.")
    for name in ("sync", "report", "build"):
        descriptions = {"sync": "Refresh progress.", "report": "Read cached progress without network access.",
                        "build": "Build a public static dashboard from cached progress."}
        command = commands.add_parser(name, help=descriptions[name])
        command.add_argument("--list", required=True, dest="list_id", help="Trakt custom list ID or slug.")
        if name == "build":
            command.add_argument("--output", default="site/dist", help="Public output directory (default: site/dist).")
            command.add_argument("--statuses", default=str(DEFAULT_STATUSES), help="Sourced status JSON file.")
        else:
            command.add_argument("--json", action="store_true", help="Print structured output.")
    args = parser.parse_args(argv)
    try:
        state = State(args.state_dir)
        with state.lock():
            if args.command == "configure":
                if state.credentials.exists():
                    raise AppError("Configuration already exists. Use a different --state-dir for another app.")
                client_id = getpass("Trakt Client ID (hidden input): ").strip()
                redirect_uri = input("Registered redirect URI [http://localhost]: ").strip()
                redirect_uri = redirect_uri or "http://localhost"
                if not client_id or not valid_redirect_uri(redirect_uri):
                    raise AppError("A Client ID and a valid registered redirect URI are required. "
                                   "Use HTTPS, or HTTP on localhost/a loopback address for development.")
                state.save({"client_id": client_id, "redirect_uri": redirect_uri})
                print("Configuration saved privately. Run python3 -m myshows auth next.")
                return 0
            credentials = state.load()
            client = Trakt(state, credentials)
            if args.command == "auth":
                client.authenticate()
                account = client.identity()
                print(f"Connected as {account['username']}. Tokens saved privately.")
            elif args.command == "whoami":
                print(client.identity()["username"])
            elif args.command == "lists":
                client.identity()
                lists = client.pages("/users/me/lists")
                for item in lists:
                    if not isinstance(item, dict) or not isinstance(item.get("ids"), dict):
                        raise AppError("Trakt returned an invalid custom-list response.")
                    print(f"{item.get('name', '(unnamed)')}\tID: {item['ids'].get('trakt')}\tslug: {item['ids'].get('slug')}")
                if not lists:
                    print("No custom lists found. Create a Following list in Trakt and add shows.")
            else:
                account = credentials.get("account")
                if not account:
                    if args.command in ("report", "build"):
                        raise AppError("No verified account cached. Run auth or whoami first.")
                    account = client.identity()
                cache = Cache(state, credentials["client_id"] + ":" + account["slug"])
                try:
                    report = overview(client, cache, args.list_id, offline=args.command != "sync")
                finally:
                    cache.close()
                if args.command == "build":
                    snapshot = export_dashboard(report, args.output, state.directory, load_statuses(args.statuses))
                    print(f"Built public dashboard with {len(snapshot['shows'])} shows in {args.output}.")
                elif args.json:
                    print(json.dumps(report, indent=2, ensure_ascii=False))
                else:
                    display(report)
                if args.command == "sync" and (report["list"]["error"] or any(s["progress"]["error"] for s in report["shows"])):
                    return 1
        return 0
    except (AppError, OSError, sqlite3.Error) as exc:
        # OSError and database diagnostics may contain local paths, not token bodies.
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        print("Cancelled.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
