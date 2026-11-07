# Dashboard

The public snapshot is live at [My Shows](https://myshows-davecross.reassuringhibiscus1.chatgpt.site). It uses eight real shows from the owner's cached Trakt list, plus dated, sourced status updates. There is no sample-show fallback and no live Trakt/news access from the browser.

## Build and preview

From the repository root:

```sh
python3 -m myshows build --list following
python3 -m http.server 8000 --bind 127.0.0.1 --directory site/dist
```

Open `http://127.0.0.1:8000`. Replace `following` with the actual list slug/ID if different. `build` reads the private SQLite cache without network requests or a valid access token. Use `--output /path/to/public-directory` to choose another output folder. It rejects the private state directory, its ancestors/descendants, and output folders containing unrelated files. Only the four dashboard files are exported.

Serve **only `site/dist`**, rather than the repository root. The source assets live in `myshows/web/`; the exporter is `myshows/dashboard.py`. Generated assets are ignored by the main repository. The deployed snapshot is public; no Trakt credentials, account identifiers, list notes, raw API URLs or error bodies are exported.

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
python3 -m myshows sync --list following
python3 -m myshows build --list following
```

Run `build` even if `sync` exits unsuccessfully when you want to publish retained data with failure indicators. These are separate commands deliberately: a refresh error must not prevent exporting useful cached values. Neither command by itself updates the hosted Site. Publish the new `site/dist` snapshot after rebuilding. There is no scheduled refresh/publication yet, and a visitor cannot trigger either operation.

`build` also reads `data/statuses.json`. Research and edit that file separately to refresh status information; Trakt sync does not check those sources. Unknown shows remain unknown, and invalid status data aborts the build before replacing the previous export.

## Sites publication

The Site identity and static output configuration are stored in `site/.openai/hosting.json`. Reuse that project ID for all future publications. The current saved Site version is **2**, published on 7 November 2026 with the modernist redesign and sourced statuses. Site source is kept in an isolated ignored checkout at `.sites/myshows/`; it contains only the manifest and exported public assets. The source helper commits and pushes that isolated snapshot before packaging and deploying it. Do not copy the repository root or private state into that checkout.

To update through the Sites workflow, rebuild `site/dist`, copy its four files and the manifest into the same isolated checkout, obtain a current source write credential for the existing Site, and use the Sites source helper to save/package that checkout. Pass its exact pushed commit and archive to the native save/deploy tools. Keep write credentials in memory and supply them through the helper's hidden stdin, never in files or command arguments. Public audience was explicitly chosen by the owner and must be preserved.

The exported files are also ordinary static assets and can be hosted independently if preferred.

## Custom domain

`myshows.davecross.co.uk` is attached to the Site, but is **pending DNS verification**. Add these records in the `davecross.co.uk` DNS zone. DNS panels that append the zone name should use the relative Name column:

| Type | Name | Value |
| --- | --- | --- |
| CNAME | `myshows` | `custom-domains.chatgpt.site.` |
| TXT | `_openai-site-verification.myshows` | `openai-site-verification=hxDVYZfdI8-2iObZTDw5w3O_JD1iOiGAGaIr3s7j9ZI` |
| TXT | `_cf-custom-hostname.myshows` | `437fdf7d-a668-4ecb-8539-9fec379896b8` |

Full TXT hostnames are `_openai-site-verification.myshows.davecross.co.uk` and `_cf-custom-hostname.myshows.davecross.co.uk`. After the records propagate, refresh the custom-domain status in Sites to verify routing and TLS. The hosted Sites URL already works while DNS is pending. No DNS records were changed by the agent.

## Validation

The Python suite currently passes 37 tests, including status evidence/precision validation, stable-ID matching, independent release/ending facts, public-field allowlisting, HTML/script injection prevention, cached/unknown progress, offline building and output-directory protection. JavaScript syntax and Python compilation checks pass.

Chromium checks at 1440, 1024, 768, 390 and 320 pixels confirm that all eight statuses and sources render without horizontal overflow; search, status filters, sorting, details and empty states work; and the page makes no external requests. A future-date check confirms that passed announcements and old evidence are flagged without inferring availability. Desktop and mobile screenshots were inspected. Browser tooling is temporary under `/tmp`, not a project dependency.
