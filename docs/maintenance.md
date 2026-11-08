# Refresh and rebuild utilities

Run these independently, normally in this order:

```sh
scripts/refresh-shows
scripts/refresh-production
scripts/rebuild-site
```

The scripts use the repository root as their working directory, even when invoked from elsewhere. They require Python 3.11+ and no third-party packages. The equivalent commands are `python3 -m myshows refresh-shows`, `refresh-production` and `rebuild-site`, run from the repository root. Each command has `--help`.

## Refresh shows

`scripts/refresh-shows` reads the live Trakt `following` custom list, refreshes watched progress and atomically saves the public `data/watchlist.json`. New and removed shows are reported. Use `--list another-slug` or `--output another.json` to override the defaults. Trakt setup and authorization are described in [the setup guide](trakt-prototype.md).

A partial failure saves retained cached values with their original successful dates and failure indicators, returning exit status 1. With no successfully cached list, the previous public snapshot is preserved. A successfully retrieved empty list really does remove all shows. Refreshing Trakt does not research production news, rebuild HTML, commit files or publish anything.

## Refresh production information

`scripts/refresh-production` uses the OpenAI Responses API with live web search and structured JSON output. Set `OPENAI_API_KEY` in your local shell environment; never put it in a public file or pass it on the command line. This is billable API usage, including web-search charges, separate from a ChatGPT subscription. The utility makes one request per selected show without automatic retries, requesting a maximum of eight tool calls and 8,000 output tokens per request. These bounds are not a fixed monetary budget. See [OpenAI pricing](https://developers.openai.com/api/docs/pricing).

The default model is `gpt-6-astra`, recommended in OpenAI's [web-search guide](https://developers.openai.com/api/docs/guides/tools-web-search) and supporting [structured output](https://developers.openai.com/api/docs/models/gpt-6-astra). Override it with `--model MODEL` or `MYSHOWS_RESEARCH_MODEL`. The model must support both features in the Responses API and low reasoning effort. A local API key is required only for this command; the public site and Pages workflow use no OpenAI credentials.

Useful selections:

```sh
scripts/refresh-production --dry-run
scripts/refresh-production --missing-only
scripts/refresh-production --show 154574 --show 204141
scripts/refresh-production --limit 2
```

`--show` takes a stable Trakt ID, printed by `--dry-run`. `--missing-only` researches shows with no saved status record; omit it to recheck existing updates too. `--limit` caps the selected shows, in watchlist order. A dry run makes no API calls and needs no key or private state.

Research requests send only the programme's title, year, public Trakt identity and previous public status assertions. They do not send watched progress, account details or Trakt tokens. Requests set `store: false`. The prompt asks for short, spoiler-free paraphrases, prefers official announcements, preserves region/date precision and distinguishes renewal, production stages and series outcomes. Unknowns are allowed.

Completed responses must include web research. Every accepted fact's source URLs must appear in that request's retrieved sources, page-open events or citation annotations. Facts with unsupported citations are skipped and reported; if no supported facts remain the response is rejected. The prompt asks the model to open source articles; the audit record distinguishes searches from explicit page opens. The remaining facts pass the same evidence, season, date and release-precision validation as manual editorial records. Validated facts update `data/statuses.json`: new assertions replace previous facts of the same kind and season, while independent facts not rechecked retain their original values and dates. Other shows are unchanged. The model chooses the headline from its accepted facts. A passed dated premiere is rejected as the headline when supported newer-season facts exist.

A rejected, incomplete, failed or evidence-free response preserves that show's previous facts and dates. Successful results are saved atomically after each show, so a later failure cannot discard them. Authentication, billing, invalid-request and rate-limit errors stop the run; other per-show failures allow remaining shows to proceed. Failures return exit status 1. No evidence returns success without advancing previous check dates. Old facts become visibly stale under the existing 30-day rule.

The ignored private state directory retains `statuses-before-refresh.json`, a backup from the start of the latest run, and `research/TRAKT_ID.json`, the latest API response for each researched show, including rejected responses. Treat these as diagnostics, not publishable build inputs. Successful research writes today's independent `checked_on` date; source publication dates remain separate. Model-generated citations and summaries still need editorial judgment: a retrieved URL does not prove that every claim about it is correct. Review the source links and `git diff -- data/statuses.json` before publication. The utility does not publish automatically.

Use `--snapshot FILE`, `--statuses FILE` and `--state-dir DIRECTORY` to select other inputs/private storage. The status file must already exist and validate; initialize a new file with `{"schema_version": 1, "shows": {}}` if needed.

## Rebuild the website

`scripts/rebuild-site` builds `site/dist/` from the public watchlist and statuses. It requires no credentials, cache or network access and does not advance source-check dates. Use `--snapshot FILE`, `--statuses FILE` or `--output DIRECTORY` for other paths. Existing output-directory protection and input validation apply.

Preview with:

```sh
python3 -m http.server 8000 --bind 127.0.0.1 --directory site/dist
```

Review changes to `data/watchlist.json` and `data/statuses.json`, commit and push them to `main` to publish. GitHub Actions tests, rebuilds and deploys to [davorg.dev/myshows](https://davorg.dev/myshows/). Generated `site/dist` files stay ignored. A workflow rerun only rebuilds saved data; it never refreshes Trakt or researches news. There is no scheduled refresh yet.

## Why research rather than just TMDB?

On 8 November 2026, we tested TMDB's [TV details endpoint](https://developer.themoviedb.org/reference/tv-series-details) against all ten programmes in the live Following list, using exact TMDB IDs supplied by Trakt. All ten matched and returned `status: "Returning Series"` with `in_production: true`. Only Silo, The Rings of Power and Rivals returned a non-null `next_episode_to_air`; the other seven supplied none.

Those are useful structured metadata fields, but the observed series-level production flag does not distinguish greenlit, writing, filming, wrapped or post-production. Next-episode dates also do not establish UK availability or an independently sourced production milestone. Existing official announcements contain more detail and sometimes differ from that broad series status. We therefore use sourced research for production assertions instead of translating `in_production` into a filming claim or overwriting stronger evidence with generic metadata.

TMDB remains a candidate for supplementary metadata and licensed UK provider information. Its API is [free for non-commercial use with required attribution](https://developer.themoviedb.org/docs/faq); production use would need the approved logo and notice. It is not currently a runtime dependency. The wider TVmaze/TMDB comparison in [issue #6](https://github.com/davorg/myshows/issues/6), including all reference shows, terms and quotas, remains open.

The research integration follows OpenAI's official [web-search](https://developers.openai.com/api/docs/guides/tools-web-search) and [structured-output](https://developers.openai.com/api/docs/guides/structured-outputs) documentation.
