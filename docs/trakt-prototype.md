# Trakt prototype

The local command-line tool connects a single Trakt account, lists its custom lists, and retrieves aired-episode progress for the shows on a selected list. It does not change lists or viewing history. It can also [build the static dashboard](dashboard.md) from saved data without contacting Trakt.

## Run it

Use Python 3.11 or newer on Linux or macOS, from the repository root. There are no third-party packages to install. State-file locking uses POSIX `fcntl`.

1. [Register a Trakt API app](https://developer.trakt.tv/docs/create-an-app). Trakt currently requires a verified GitHub account to create an app. Name it **My Shows** and describe the personal read-only dashboard. For a development app restricted to localhost callbacks, register `http://localhost` (or the exact localhost URL accepted by the registration form). The device-code flow does not receive a callback, so no local HTTP server needs to be running. The registered URI is retained for token refresh requests.
2. Enter the Client ID locally:

   ```sh
   python3 -m myshows configure
   ```

   The default redirect URI is `http://localhost`. Accept it only if it exactly matches the app registration; otherwise enter the registered URI, including any port and path. HTTP is accepted for `localhost` and loopback IP addresses such as `127.0.0.1` or `[::1]`; other hosts require HTTPS. A production app can use a registered HTTPS callback such as `https://myshows.davecross.co.uk/oauth/callback`. The Client ID prompt hides input. The current device-token contract does not require a Client Secret; no Trakt password or secret needs to be entered into this tool or chat.

   If an earlier `configure` attempt failed validation, simply run it again; failed validation does not save credentials.
3. Start authorization:

   ```sh
   python3 -m myshows auth
   ```

   Visit the displayed Trakt verification URL, enter the short code, and approve the connection. The command waits for approval until the code expires, then verifies the account and prints its username. The authorization grant may permit more than this prototype uses; the tool only reads account data. The only POST requests are OAuth code/token operations.
4. Check the account and discover your list:

   ```sh
   python3 -m myshows whoami
   python3 -m myshows lists
   ```

   If necessary, create a custom **Following** list in Trakt and add shows there. Copy its numeric ID or slug from the command output. Neither the list name nor its programmes are hard-coded.
5. Fetch and print progress (replace `following` if your list has a different slug, or use its numeric ID):

   ```sh
   python3 -m myshows sync --list following
   python3 -m myshows report --list following
   python3 -m myshows report --list following --json
   ```

   `sync` makes network requests and persists each complete successful result. `report` only reads local storage, including after a restart, and makes no network requests. The JSON output contains source links, last attempt/success times, freshness/error states, stable show IDs, and progress. There are no tokens in report output. Treat reports as personal data even though the eventual dashboard is intended to be public.

## Progress semantics

- Counts come from Trakt's aired-episode totals, including hidden seasons and excluding specials. Episodes without an air date and future episodes are excluded by that endpoint. An aired episode is not necessarily available in the UK.
- Most recently watched means the aired regular episode with the latest supplied viewing timestamp. Furthest watched means the highest season/episode pair marked completed. Rewatches can make these different, and gaps do not imply completion of earlier episodes. These references use Trakt's episode numbering; no cross-provider episode matching is implemented.
- Missing timestamps leave the most recent viewing unknown. Zero counts from a successful response are distinct from missing progress.
- The prototype uses the supplied progress totals without applying a local rewatch reset. If Trakt supplies `reset_at`, the report retains it and the text output explains this limitation. A separate current-rewatch view can be added later.
- Trakt progress does not determine renewal or production status. The dashboard supplements it with [dated, sourced editorial assertions](status-updates.md), approved for the MVP. UK streaming availability remains unimplemented.

## Storage and failed refreshes

By default, `.myshows/` holds a `credentials.json` file and `cache.sqlite3`. Both are excluded from Git; the directory uses mode `0700` and files use `0600`. These are plaintext files protected by local filesystem permissions, not an encrypted credential vault. Keep the directory outside any public document root and protect backups. The CLI creates state in the current working directory, so run it from the repository root or choose a fixed absolute path:

```sh
python3 -m myshows --state-dir /absolute/private/path auth
python3 -m myshows --state-dir /absolute/private/path sync --list following
```

`MYSHOWS_STATE_DIR` also overrides the default. Each command takes an exclusive lock to prevent simultaneous refreshes from consuming the same single-use refresh token. New tokens are written atomically before subsequent data requests.

The SQLite cache is scoped by Client ID and verified account slug. List contents are replaced only after all pages load and validate. Each show's progress is cached separately, so one show's failure does not erase another show's success. An explicitly empty successful list removes its old entries from the report. A failed refresh retains old values and their original success timestamps, adds the new attempt/error, and marks retained values stale. Without an earlier value, it reports unknown.

`fresh` means verified during this sync, not a promise of real-time accuracy. `cached` means read offline without a new check; `stale` means a known refresh failed. Retention has no automatic age limit in this prototype. A nonzero exit status from `sync` indicates at least one failed retrieval even when a useful cached report was printed. `report` can be used without a valid access token as long as a verified account and cached data remain on disk.

On ordinary HTTP 429 responses the command stops further network calls and prints the documented `Retry-After` delay when supplied; rerun after that delay. Device authorization handles pending responses, increases its polling interval after throttling, and stops on denial or expiry. Other source failures retain cached values. There is no unattended retry scheduler yet.

If access is revoked or token refresh is rejected, run `auth` again. To disconnect, stop any scheduled commands and revoke the app in Trakt's connected-app settings. Remove the private state directory if you also want to erase local credentials and cached data. A newly authorized account does not read another account's cached rows.

## Development checks

```sh
python3 -m unittest discover -s tests -v
python3 -m compileall -q myshows tests
git diff --check
```

Tests use synthetic fixtures and an in-memory HTTP transport, never real credentials. They cover token rotation, authorization denial/expiry/throttling, pagination, rewatches/gaps, account isolation, and persistent fallback after partial failures. Passing them does not establish real API access. On 7 November 2026, the owner separately confirmed successful live authorization, list retrieval and progress after checking the output against Trakt. This does not imply that every failure case has been exercised live.

## Initial technology decision

Python's standard library supplies HTTPS, CLI parsing, SQLite, locking and tests, so this investigation needs no dependency installation or framework. SQLite provides persistent fallback for a single local process and gives us real data before deciding on the hosted architecture. It needs a persistent volume if retained for deployment; it is not a choice of Firebase or a commitment to a particular hosting service. A later web layer can consume the normalized progress data while keeping all OAuth operations private.

## API references

Checked on 7 November 2026:

- [Authentication](https://developer.trakt.tv/docs/authentication-oauth) and the [current OAuth contract](https://github.com/trakt/trakt-api/blob/master/projects/api/src/contracts/oauth/index.ts): device authorization and refresh use `https://auth.trakt.tv`. The contract makes Client Secret optional. Access tokens expire according to their returned expiry; refresh tokens rotate after a successful exchange.
- [Trakt's own local development setup](https://github.com/trakt/trakt-web/blob/main/README.md) includes HTTP localhost callbacks. This prototype permits those development callbacks while keeping remote callbacks on HTTPS.
- [Personal-list contract](https://github.com/trakt/trakt-api/blob/master/projects/api/src/contracts/users/subroutes/userLists.ts): custom lists and paginated show items.
- [Show contract](https://github.com/trakt/trakt-api/blob/master/projects/api/src/contracts/shows/index.ts): watched progress and its aired-episode/specials semantics.
- [Rate limits](https://developer.trakt.tv/docs/rate-limiting): handle returned HTTP 429 and `Retry-After`; do not assume a permanent request quota.
- [API use policy](https://developer.trakt.tv/docs/api-use-policy): caching for chosen app features and branding requirements. Live access has been confirmed for this prototype's authentication, list and progress flow; other endpoints remain unverified.

My Shows uses Trakt but is not endorsed or certified by Trakt.
