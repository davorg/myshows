# Dashboard

The public snapshot is live at [My Shows](https://davorg.dev/myshows/). It uses real shows from the owner's Trakt list, plus dated, sourced status updates. There is no sample-show fallback and no live Trakt/news access from the browser.

## Build and preview

From the repository root:

```sh
python3 -m myshows build --snapshot data/watchlist.json
python3 -m http.server 8000 --bind 127.0.0.1 --directory site/dist
```

Open `http://127.0.0.1:8000`. The public-snapshot build works in a clean checkout without Trakt credentials, a SQLite cache or network access. `build --list following` remains available when building directly from a local private cache; replace `following` with the actual list slug/ID if different. Use `--output /path/to/public-directory` to choose another output folder. It rejects the private state directory, its ancestors/descendants, and output folders containing unrelated files. Only the four dashboard files are exported.

Serve **only `site/dist`**, rather than the repository root. The source assets live in `myshows/web/`; the exporter is `myshows/dashboard.py`. Generated assets are ignored by Git. The committed `data/watchlist.json` contains only the public viewing-progress fields already shown on the dashboard; it is not a private backup. The deployed snapshot is public; no Trakt credentials, account identifiers, list notes, raw API URLs or error bodies are exported.

## What the page shows

- Programme names, years and links to Trakt.
- Prominent renewal/production/release/ending headlines, with confirmed versus reported labels, evidence links and independent check dates.
- Watched/aired progress, most recent episode, and aired-but-unwatched counts.
- Separate furthest-watched references in expandable progress/source details.
- Watchlist and per-show last-successful-check timestamps.
- Search, filters for progress and status facts, and release-window/title/unwatched-count sorting.
- Explicit unknown, empty, old and failed-refresh states.

The modernist layout uses sans-serif type, bold headings, flat colour blocks and a two-column card grid that becomes one column on narrow screens. Controls are labelled, filter state uses `aria-pressed`, source details use native expandable elements, and a live region announces result counts. Font and graphic assets are local; there are no external fonts, trackers or image requests.

Counts exclude specials, future episodes and episodes without air dates. A show with zero aired episodes is not counted as caught up. Unknown progress is excluded from episode totals and identified in the summary. Existing rewatch-reset limitations remain visible. Statuses come from [separate sourced assertions](status-updates.md), not from viewing progress. UK subscription availability remains unknown.

Freshness is evaluated when the page opens. Watched information checked more than 24 hours ago gets an “Older snapshot” label. A failed refresh retains the original successful timestamp and has a separate warning. Status evidence has its own publication/check dates, a 30-day review indicator, and warnings after announced release windows pass. A new export never advances these dates. Progress timestamps use the browser's timezone; date-only announcements retain their stated region.

## Refresh the snapshot

```sh
scripts/refresh-shows
scripts/refresh-production
scripts/rebuild-site
```

The [maintenance guide](maintenance.md) explains each independent operation, credentials and research charges, selections and failure handling. `refresh-shows` saves retained data with failure indicators even after a partial Trakt failure; the lower-level `sync` and offline `snapshot` commands also remain available separately. Local changes can be reviewed, committed and pushed to `main` for publication. Actions also provides a six-hourly Trakt refresh after environment-secret setup, and a weekly production refresh whose schedule remains commented out. Both rebuild and publish changed public data, including successful-check times. A visitor cannot trigger refresh or publication.

`build` also reads `data/statuses.json`. Research and edit that file separately to refresh status information; Trakt sync does not check those sources. Unknown shows remain unknown, and invalid status data aborts the build before replacing the previous export.

## GitHub Pages publication

The workflow is `.github/workflows/pages.yml`. It runs on pushes to `main`, pull requests, and manual dispatch. Both push and PR runs execute the offline tests, syntax checks and a credential-free build. Only a main-branch push or manual main-branch run uploads the four files in `site/dist` and deploys them. PRs have no Pages deployment permissions.

Actions are pinned to verified commit SHAs. Build jobs have read-only repository access. Only the deployment job receives `pages: write` and `id-token: write`, using the `github-pages` environment and GitHub's standard upload/deploy actions. There are no Trakt secrets or private-cache artifacts in Actions. A failed test or invalid snapshot leaves the previous successful deployment intact.

The repository's Pages source is **GitHub Actions** (`build_type: workflow`). The site inherits the account's existing `davorg.dev` domain, so the project URL is `https://davorg.dev/myshows/`. Do not add a repository `CNAME` file for `davorg.dev`; that domain belongs to the existing account site. Relative asset/home links work below `/myshows/` as well as in a local root preview.

Publication happens automatically after a user push. The Actions run and the `github-pages` environment report the deployment URL and failures. Both refresh workflows explicitly dispatch Pages after saving changed public data, because bot-token pushes do not trigger the push workflow. Rerunning Pages alone does not make source-check dates newer.

## Retired OpenAI Sites hosting

The former Sites deployment is no longer used. Its public access is removed and its pending `myshows.davecross.co.uk` attachment is detached. The Sites manifest has been removed from the repository. Available connector tools do not expose deletion/unpublishing, so the retained old Site is owner-only rather than deleted. There were no Site schedules to migrate.

No DNS changes are needed for the GitHub Pages project URL. The old Sites CNAME/TXT setup instructions no longer apply. The ignored `.sites/` directory is only historical local publishing state; it is never read or uploaded by the Pages workflow.

## Validation

The Python suite covers status evidence/precision validation, stable-ID matching, independent release/ending facts, public-field allowlisting, HTML/script injection prevention, cached/unknown progress, offline building and output-directory protection. Maintenance tests also cover research-source validation, request privacy, partial failures and last-good-value preservation. JavaScript syntax and Python compilation checks pass.

Chromium checks at 1440, 1024, 768, 390 and 320 pixels confirm that all eight statuses and sources render without horizontal overflow; search, status filters, sorting, details and empty states work; and the page makes no external requests. A future-date check confirms that passed announcements and old evidence are flagged without inferring availability. Desktop and mobile screenshots were inspected. Browser tooling is temporary under `/tmp`, not a project dependency.

The portable-snapshot tests also cover a clean checkout with no credentials/state, public-field round trips, invalid-input preservation, stable IDs and retained freshness. The workflow is checked with actionlint, and browser checks verify that assets and interactions work under the `/myshows/` project path.
