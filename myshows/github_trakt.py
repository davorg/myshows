"""Trakt refresh on ephemeral Actions runners, with durable token rotation."""

from argparse import Namespace
import json
import os
import re
import sqlite3
import subprocess
import sys

from .maintenance import refresh_shows
from .state import AppError, State

ENVIRONMENT = "trakt-refresh"
SECRET_NAME = "TRAKT_CREDENTIALS_JSON"


def credentials_from_json(raw):
    try:
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError
        tokens, account = value["tokens"], value["account"]
        if (not all(isinstance(value.get(k), str) and value[k] for k in ("client_id", "redirect_uri"))
                or not all(isinstance(tokens.get(k), str) and tokens[k] for k in ("access_token", "refresh_token"))
                or not all(type(tokens.get(k)) is int and tokens[k] >= 0 for k in ("created_at", "expires_in"))
                or not all(isinstance(account.get(k), str) and account[k] for k in ("username", "slug"))):
            raise ValueError
        # Restore only fields used by this client; do not retain arbitrary secret payload fields.
        result = {k: value[k] for k in ("client_id", "redirect_uri")}
        result["tokens"] = {k: tokens[k] for k in ("access_token", "refresh_token", "created_at", "expires_in")}
        result["account"] = {k: account[k] for k in ("username", "slug")}
        return result
    except (ValueError, KeyError, TypeError, AttributeError):
        raise AppError("Invalid TRAKT_CREDENTIALS_JSON; use the credentials from a verified, dedicated Trakt authorization.") from None


class GitHubState(State):
    def __init__(self, directory, repository, update_token, run=None):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository or "") or not update_token:
            raise AppError("Set GH_REPO and TRAKT_SECRET_UPDATE_TOKEN for the Actions Trakt refresh.")
        super().__init__(directory)
        self.repository = repository
        self.update_token = update_token
        self.run = run or subprocess.run

    def save(self, credentials):
        super().save(credentials)
        # Trakt calls State.save immediately after OAuth rotation, before any GET.
        # gh encrypts stdin using the environment's public key. Never put secrets in argv/logs.
        environment = {**os.environ, "GH_TOKEN": self.update_token, "GH_PROMPT_DISABLED": "1"}
        environment.pop(SECRET_NAME, None)
        environment.pop("TRAKT_SECRET_UPDATE_TOKEN", None)
        try:
            result = self.run(["gh", "secret", "set", SECRET_NAME, "--env", ENVIRONMENT,
                               "--repo", self.repository], input=json.dumps(credentials),
                              text=True, capture_output=True, env=environment, timeout=30)
            if result.returncode:
                raise AppError("Unable to save Trakt credentials to the Actions environment; check the update token's Environments permission and expiry.")
        except (OSError, subprocess.SubprocessError):
            raise AppError("Unable to save Trakt credentials to the Actions environment; no further Trakt requests will be made.") from None


def main():
    try:
        credentials = credentials_from_json(os.environ.get(SECRET_NAME, ""))
        directory = os.environ.get("MYSHOWS_STATE_DIR", ".myshows")
        state = GitHubState(directory, os.environ.get("GH_REPO"), os.environ.get("TRAKT_SECRET_UPDATE_TOKEN"))
        # Verify write access before a network request can consume a rotating token.
        with state.lock():
            state.save(credentials)
        args = Namespace(state_dir=directory, output="data/watchlist.json", list_id="following")
        return refresh_shows(args, state=state, seed_from_snapshot=True)
    except (AppError, OSError, sqlite3.Error) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        print("Cancelled.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
