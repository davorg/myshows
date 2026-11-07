"""Small Trakt client: only GET data requests and OAuth POST requests."""

import json
from http.client import HTTPException
import socket
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .state import AppError

API_URL = "https://api.trakt.tv"
AUTH_URL = "https://auth.trakt.tv"


class ApiError(AppError):
    def __init__(self, status, headers=None):
        self.status = status
        self.headers = headers or {}
        message = {
            401: "Trakt authorization expired or was revoked; run auth again.",
            403: "Trakt denied access; check app approval and account permissions.",
            404: "Trakt resource not found; check the list ID and account.",
            429: "Trakt rate limit reached; stop and retry later.",
        }.get(status, f"Trakt returned HTTP {status}.")
        delay = self.headers.get("Retry-After")
        if status == 429 and delay and str(delay).isdigit():
            message += f" Retry after at least {delay} seconds."
        super().__init__(message)


class NoRedirect(HTTPRedirectHandler):
    # Never forward API credentials to a redirected host.
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Trakt:
    def __init__(self, state, credentials, opener=None, sleep=time.sleep, clock=time.monotonic):
        self.state = state
        self.credentials = credentials
        self.opener = opener or build_opener(NoRedirect())
        self.sleep = sleep
        self.clock = clock
        self.blocked = None

    def request(self, path, params=None, payload=None, token=None):
        oauth = path in {"/oauth/device/code", "/oauth/device/token", "/oauth/token"}
        if payload is not None and not oauth:
            raise AppError("Only OAuth requests may modify remote state.")
        if not path.startswith("/") or path.startswith("//") or "?" in path:
            raise AppError("Invalid API path.")
        url = (AUTH_URL if oauth else API_URL) + path
        if params:
            url += "?" + urlencode(params)
        headers = {"Content-Type": "application/json", "Accept": "application/json",
                   "trakt-api-key": self.credentials["client_id"],
                   "trakt-api-version": "2", "User-Agent": "MyShows/0.1 (personal dashboard)"}
        if token:
            headers["Authorization"] = "Bearer " + token
        request = Request(url, headers=headers, method="POST" if payload is not None else "GET",
                          data=json.dumps(payload).encode() if payload is not None else None)
        try:
            with self.opener.open(request, timeout=30) as response:
                return json.load(response), response.headers
        except HTTPError as exc:
            # Never echo bodies: OAuth errors can contain sensitive values.
            error = ApiError(exc.code, exc.headers)
            exc.close()
            raise error from None
        except (URLError, TimeoutError, socket.timeout, OSError, HTTPException):
            raise AppError("Unable to reach Trakt; check the network and retry later.") from None
        except (ValueError, UnicodeError):
            raise AppError("Trakt returned an invalid JSON response.") from None

    def save_tokens(self, tokens):
        required = {"access_token", "refresh_token", "created_at", "expires_in"}
        if not isinstance(tokens, dict) or not required <= tokens.keys():
            raise AppError("Trakt returned an incomplete token response; run auth again.")
        if (not all(isinstance(tokens[k], str) and tokens[k] for k in ("access_token", "refresh_token"))
                or not all(type(tokens[k]) is int for k in ("created_at", "expires_in"))):
            raise AppError("Trakt returned an invalid token response; run auth again.")
        self.credentials["tokens"] = tokens
        self.state.save(self.credentials)

    def access_token(self, refresh=False):
        tokens = self.credentials.get("tokens")
        if not tokens:
            raise AppError("Run python3 -m myshows auth first.")
        if refresh or time.time() >= tokens["created_at"] + tokens["expires_in"] - 60:
            try:
                value, _ = self.request("/oauth/token", payload={
                    "client_id": self.credentials["client_id"],
                    "redirect_uri": self.credentials["redirect_uri"],
                    "grant_type": "refresh_token", "refresh_token": tokens["refresh_token"]})
            except ApiError as exc:
                if exc.status in (400, 401):
                    raise AppError("Trakt token refresh was rejected; run auth again.") from None
                raise
            self.save_tokens(value)
        return self.credentials["tokens"]["access_token"]

    def get(self, path, params=None):
        if self.blocked:
            raise self.blocked
        try:
            token = self.access_token()
            try:
                return self.request(path, params=params, token=token)
            except ApiError as exc:
                if exc.status != 401:
                    raise
            return self.request(path, params=params, token=self.access_token(refresh=True))
        except AppError as exc:
            # Do not hammer a failing authentication service or continue after 429.
            if not isinstance(exc, ApiError) or exc.status in (401, 403, 429):
                self.blocked = exc
            raise

    def pages(self, path):
        items, page = [], 1
        while True:
            data, headers = self.get(path, {"page": page, "limit": 100})
            if not isinstance(data, list):
                raise AppError("Trakt returned an invalid list response.")
            items.extend(data)
            total = headers.get("X-Pagination-Page-Count")
            try:
                total = int(total) if total is not None else None
            except ValueError:
                raise AppError("Trakt returned invalid pagination headers.") from None
            if total is not None and page >= total:
                return items
            if total is None and len(data) < 100:
                return items
            if not data or page >= 1000:
                raise AppError("Trakt pagination did not finish; cached data was preserved.")
            page += 1

    def authenticate(self, output=print):
        value, _ = self.request("/oauth/device/code", payload={"client_id": self.credentials["client_id"]})
        try:
            interval = max(1, int(value["interval"]))
            deadline = self.clock() + int(value["expires_in"])
            code = value["device_code"]
            output(f"Visit {value['verification_url']} and enter {value['user_code']}.")
        except (KeyError, TypeError, ValueError):
            raise AppError("Trakt returned an invalid device-code response.") from None
        while self.clock() + interval < deadline:
            self.sleep(interval)
            if self.clock() >= deadline:
                break
            try:
                tokens, _ = self.request("/oauth/device/token", payload={
                    "code": code, "client_id": self.credentials["client_id"]})
            except ApiError as exc:
                if exc.status == 400:
                    continue
                if exc.status == 429:
                    delay = exc.headers.get("Retry-After", "0")
                    interval = max(interval + 5, int(delay) if str(delay).isdigit() else 0)
                    continue
                messages = {404: "Invalid device code.", 409: "Device code was already used.",
                            410: "Device code expired.", 418: "Authorization was denied."}
                if exc.status in messages:
                    raise AppError(messages[exc.status] + " Run auth again.") from None
                raise
            self.credentials.pop("account", None)
            self.save_tokens(tokens)
            return
        raise AppError("Device code expired. Run auth again.")

    def identity(self):
        value, _ = self.get("/users/settings")
        try:
            user = value["user"]
            account = {"username": user["username"], "slug": user["ids"]["slug"]}
            if not all(isinstance(v, str) and v for v in account.values()):
                raise ValueError
        except (KeyError, TypeError, ValueError):
            raise AppError("Trakt returned invalid account identity.") from None
        self.credentials["account"] = account
        self.state.save(self.credentials)
        return account
