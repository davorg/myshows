# My Shows

A personal, read-only dashboard for the television series I'm following: **what's happening next, how far I've watched, and where I can watch them in the UK**.

Trakt is the source of truth for viewing history. My Shows is not another episode tracker or a notification service. It is a high-level view to consult occasionally, especially when seasons are separated by years.

## The problem

It's easy to forget whether a favourite drama has been renewed, cancelled, finished as planned, begun filming, or acquired a release date. Information is scattered across trackers, streaming catalogues and news articles. A compact, curated dashboard should make it easy to see the situation at a glance.

## Planned dashboard

- Follow a **curated selection** of shows, ideally through a dedicated Trakt custom list, without duplicating viewing history.
- Display **watched progress** and released but unwatched episode counts from Trakt, with clear labels for the most recent viewing and any gaps. Released does not necessarily mean available to stream in the UK.
- Show the **latest known status**, keeping series outcome, next-season renewal/production and release information distinct. A show can be releasing one season while another is in production. Distinguish confirmed facts from speculation and unknowns.
- Show the next season and release date/window, where known; don't invent dates.
- Show **UK streaming availability**, including service, with an investigation of legitimate data-provider access (JustWatch if feasible, alternatives if not).
- Group or filter shows by streaming service and status.
- Provide a responsive, readable **single-page dashboard**, with links to sources and last-checked timestamps.
- Handle absent, stale and conflicting metadata honestly.

The initial reference set includes *Severance*, *Pluribus*, *The Rings of Power*, *Doctor Who*, *3 Body Problem*, *Silo*, *Rivals*, *Star Trek: Strange New Worlds* and *Star Trek: Starfleet Academy*. These are examples, not a hard-coded list.

### First MVP

Start with a smaller usable version of the planned dashboard:

- Load the curated Trakt list and display watched progress with basic show metadata where available.
- Present a readable single-page overview with source links and last-successful-update timestamps.
- Persist the latest successfully retrieved information so the dashboard can display it, clearly marked as stale, if an update fails. Show unknown when no successful value exists.
- Give every show a prominent **what's next** headline covering renewal, production, announced releases or ending information, with explicit unknowns where evidence is missing. This is a core MVP requirement. Dated, sourced editorial updates in [data/statuses.json](data/statuses.json) supplement API data; confirmed announcements and industry reports are labelled separately.

UK streaming integration and richer production timelines can follow. Basic status information must be present in the MVP. The availability investigation can proceed alongside this work without blocking it.

### MVP boundaries

No real-time notifications, no replacement for Trakt's watched-history management, no billing integration and no requirement to track active streaming subscriptions. The command-line integration uses Python 3.11+ and SQLite. GitHub Actions builds the static HTML/CSS/JavaScript dashboard from a public watchlist snapshot and publishes it to GitHub Pages. This project no longer uses OpenAI Sites for deployment.

## Data sources to investigate

| Need | Candidate | Considerations |
| --- | --- | --- |
| Followed shows and watched progress | Trakt API | OAuth, custom lists, watched progress and API limits |
| Show metadata, renewals, seasons and schedules | TVmaze / TMDB | Coverage, semantics, attribution, reliability and API terms |
| UK streaming availability | JustWatch or another licensed provider | Official access, cost, licensing, regional coverage and caching |
| Production news and context | Official announcements / attributable reporting, curated in `data/statuses.json` | Store source URLs, publication dates and independent check dates; avoid unsupported claims |

A renewal flag is not the same as a filming date; a series finale is not necessarily a cancellation. The interface should make these distinctions clear.

The [structured production-data investigation](docs/production-data-providers.md) compares Production List's API/MCP, Luminate and IMDb, including live sample lookups, season matching, published prices and licensing questions for a larger shared catalogue.

### Data interpretation

- **Viewing progress:** distinguish the most recently watched episode from the furthest episode watched; rewatches and gaps can make these different. Define whether specials are included in counts.
- **Release information:** retain the region and date precision supplied by the source. An international premiere is not automatically a UK release, and a release window must not become an invented exact date.
- **UK availability:** distinguish subscription, rental and purchase. A show-level provider listing does not prove that every season or episode is available; state the coverage granularity and leave unsupported details unknown.
- **Evidence and freshness:** associate source links and timestamps with individual assertions. A successful check, the source's publication date and a change in the underlying fact are different events. A failed refresh must not make old data appear newly verified.

## Future ideas (not MVP)

- Track which streaming services I'm currently subscribed to, and subscription dates/costs.
- Suggest sensible **one-month subscription windows** when multiple unwatched seasons are available on one service.
- Show what's changed since the previous visit.
- Optional periodic digests or alerts.
- Personal notes, watch priorities and recommendations.
- More sophisticated production-stage timelines and source reconciliation.

## Development

For routine maintenance, the three independent utilities are:

```sh
scripts/refresh-shows       # Refresh Trakt Following and public watched progress
scripts/refresh-production  # Research sourced statuses via the OpenAI API (billable)
scripts/rebuild-site        # Rebuild saved data into the static website, offline
```

The research command needs a local `OPENAI_API_KEY`. Use `--dry-run` to preview or `--missing-only` to research newly followed shows. See [the maintenance guide](docs/maintenance.md) for setup, selections, costs, failure handling and publication. TMDB was tested against the live list; its broad series status does not provide the filming/post-production detail needed for the dashboard.

The [Trakt prototype setup guide](docs/trakt-prototype.md) covers app registration, local authorization, list selection and cached progress reports. It runs with Python 3.11+ on Linux/macOS and has no third-party dependencies:

```sh
python3 -m myshows configure
python3 -m myshows auth
python3 -m myshows lists
python3 -m myshows sync --list following
python3 -m myshows report --list following
python3 -m myshows snapshot --list following
python3 -m myshows build --list following
```

Use the actual ID or slug of your custom list in place of `following`. For a Trakt development app, register a localhost callback and enter that exact URI during `configure` (default: `http://localhost`); the device-code flow needs no local callback server. Credentials and cached personal data stay in the ignored private `.myshows/` directory. Run offline tests with `python3 -m unittest discover -s tests -v`.

The dashboard build writes only public assets to `site/dist/`. To build from a clean checkout without credentials, run `python3 -m myshows build --snapshot data/watchlist.json`. Preview with `python3 -m http.server 8000 --bind 127.0.0.1 --directory site/dist` and visit `http://127.0.0.1:8000`. See the [dashboard guide](docs/dashboard.md) for GitHub Pages publication and refreshing the public snapshot.

The build merges watched progress with [sourced status assertions](docs/status-updates.md), matched by stable Trakt show ID. It does not refresh the news sources or advance their check dates. Use `--statuses /path/to/statuses.json` to select another validated status file.

See [Issues](https://github.com/davorg/myshows/issues) for the proposed MVP backlog. Start by validating API access and the data model, then build the smallest end-to-end slice. Contributions and implementation decisions can be discussed in issues.

Investigate Trakt access ([#3](https://github.com/davorg/myshows/issues/3)) and metadata coverage ([#6](https://github.com/davorg/myshows/issues/6)) to inform the architecture in [#1](https://github.com/davorg/myshows/issues/1). Investigate legitimate UK availability data ([#9](https://github.com/davorg/myshows/issues/9)) alongside this work. Use the reference shows to record actual field coverage, identifier matches and unknowns. Include provenance and refresh-failure handling in the first integration; grouping and richer production detail can follow.

### Deployment and persistent data

The public test is hosted at [davorg.dev/myshows](https://davorg.dev/myshows/). The [Pages workflow](.github/workflows/pages.yml) tests pull requests and deploys pushes to `main` or manual runs. It builds from the committed, public [watchlist snapshot](data/watchlist.json) and sourced status file, with no Trakt credentials or SQLite database in Actions. The published page has no refresh or configuration endpoint.

SQLite persists the latest successfully retrieved Trakt information locally. `scripts/refresh-shows` refreshes it and exports public viewing-progress fields to `data/watchlist.json`; commit and push that file to publish updated progress. `scripts/refresh-production` researches sourced assertions in `data/statuses.json`, retaining previous successful facts on failure. Firebase remains an option if later requirements need a hosted database. Refresh failures preserve original successful-update timestamps and values; an explicitly empty successful response is distinct from an unsuccessful retrieval.

The command-line integration has automated tests using synthetic API responses. The owner has also confirmed successful live authentication, custom-list retrieval and viewing progress against their Trakt account. Initial TMDB coverage has been checked; the wider metadata comparison and UK availability investigation remain open.

## Status

The owner has verified the live Trakt integration. The dashboard reads the curated Following list and includes sourced status headlines, progress, aired-unwatched counts, search, progress/status filters and sorting. Its modernist layout uses sans-serif typography, flat colour blocks and bold headings. GitHub Actions tests and publishes changes automatically. Local utilities refresh Trakt, research production announcements and rebuild the website independently; refresh scheduling and UK streaming integration remain future work.

My Shows uses Trakt but is not endorsed or certified by Trakt.
