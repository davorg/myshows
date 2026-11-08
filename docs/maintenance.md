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

A partial failure saves retained cached values with their original successful dates and failure indicators, returning exit status 1. With no successfully cached list, the previous public snapshot is preserved. A successfully retrieved empty list really does remove all shows. The local refresh utility does not research production news, rebuild HTML, commit files or publish anything. The Actions workflow adds publication after changed data is saved.

## Refresh production information

`scripts/refresh-production` uses the OpenAI Responses API with live web search and structured JSON output. Set `OPENAI_API_KEY` in your local shell environment; never put it in a public file or pass it on the command line. This is billable API usage, including web-search charges, separate from a ChatGPT subscription. The utility makes one request per selected show without automatic retries, requesting a maximum of eight tool calls and 8,000 output tokens per request. These bounds are not a fixed monetary budget. See [OpenAI pricing](https://developers.openai.com/api/docs/pricing).

The default model is `gpt-6.1-sol`, supporting [web search, structured output and low reasoning effort](https://developers.openai.com/api/docs/models/gpt-6.1-sol). Override it with `--model MODEL` or `MYSHOWS_RESEARCH_MODEL`. The model must support those features in the Responses API. The public site and Pages build use no OpenAI credentials; the separate production-refresh workflow reads a repository Actions secret.

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

Review changes to `data/watchlist.json` and `data/statuses.json`, commit and push them to `main` to publish. GitHub Actions tests, rebuilds and deploys to [davorg.dev/myshows](https://davorg.dev/myshows/). Generated `site/dist` files stay ignored. Rerunning the Pages workflow only rebuilds saved data; it never refreshes Trakt or researches news.

## GitHub Actions production refresh

[Refresh production information](../.github/workflows/refresh-production.yml) runs `scripts/refresh-production` with the default GPT-6.1 Sol model, reading the committed public watchlist. It can be started manually from Actions on `main`. It does not refresh Trakt or need Trakt credentials.

The weekly schedule is prepared for **Monday at 03:17 UTC** (`17 3 * * 1`), with both schedule lines **commented out**. To enable it:

1. Add a repository Actions secret named `OPENAI_API_KEY` in Settings → Secrets and variables → Actions.
2. Uncomment `schedule:` and its `cron` line in `.github/workflows/refresh-production.yml`, then commit and push.

A manual run also needs that secret; without it the workflow stops before making research requests. Adding the secret alone leaves the schedule disabled. GitHub schedules use UTC here and may start later when runners are busy.

Unlike the local utility, this workflow publishes validated research automatically when its saved data changes. The shared publisher runs tests and an offline build, commits only `data/statuses.json` as `github-actions[bot]`, and pushes to `main`. Both refresh jobs use the same concurrency group, preventing overlapping Trakt/production refreshes. The publisher rebases on current `main` before pushing; conflicts or push failures stop publication rather than overwrite remote work. Repository branch rules must allow the bot to push.

The job requests `contents: write` for those data commits and `actions: write` to dispatch the existing Pages workflow. An ordinary push made with `GITHUB_TOKEN` does not start another workflow, so successful changed-data pushes explicitly dispatch `pages.yml` on `main`. No changes means no commit or deployment request. See [GitHub's token-trigger behavior](https://docs.github.com/en/actions/concepts/security/github_token).

If research partially fails, the workflow validates and saves successful updates while retaining failed shows' previous facts/dates, then marks the run failed so the failure remains visible. Invalid data or failing tests prevent the data commit and deployment request. Private response diagnostics stay on the runner; neither they nor credentials are committed or uploaded. The existing Pages workflow separately reports deployment success or failure.

## GitHub Actions Trakt refresh

[Refresh Trakt progress](../.github/workflows/refresh-trakt.yml) runs every six hours, at **00:41, 06:41, 12:41 and 18:41 UTC** (`41 */6 * * *`), and supports manual runs on `main`. It refreshes Following and watched progress, then publishes changes to `data/watchlist.json`. The production schedule remains separately commented out.

This needs a dedicated **`trakt-refresh` GitHub environment**, with two environment secrets:

| Secret | Value |
| --- | --- |
| `TRAKT_CREDENTIALS_JSON` | The complete `credentials.json` from a dedicated, verified Trakt authorization, including Client ID, callback, account and tokens. |
| `TRAKT_SECRET_UPDATE_TOKEN` | A fine-grained GitHub PAT restricted to this repository, with **Environments: read and write** permission, so rotated credentials can be saved. |

The normal `GITHUB_TOKEN` still handles public data commits and Pages dispatch. The PAT is used only for `gh secret set` in the credential-persistence code. Keep it valid; an expired token stops the refresh before Trakt requests begin.

### Configure the environment

1. Create the `trakt-refresh` environment under repository Settings → Environments. Restrict it to `main`. For unattended operation, do not add required reviewers that would block each scheduled run.
2. Register a separate Trakt application for Actions and authorize it in a separate ignored state directory. This keeps scheduled token rotation independent of local commands:

   ```sh
   python3 -m myshows --state-dir .myshows/ci-auth configure
   python3 -m myshows --state-dir .myshows/ci-auth auth
   ```

   Follow the [Trakt setup guide](trakt-prototype.md), including the localhost callback for a development application. Verify that this is the account owning the dashboard's Following list.
3. Store that credentials file directly in the environment secret, without printing it or pasting it into an issue/chat:

   ```sh
   gh secret set TRAKT_CREDENTIALS_JSON --repo davorg/myshows --env trakt-refresh < .myshows/ci-auth/credentials.json
   ```

4. Create the repository-scoped fine-grained PAT described above, then use GitHub's environment-secret UI or the hidden prompt:

   ```sh
   gh secret set TRAKT_SECRET_UPDATE_TOKEN --repo davorg/myshows --env trakt-refresh
   ```

5. Run **Refresh Trakt progress** manually from Actions to verify the setup. Subsequent scheduled runs use the latest saved environment credentials. Once uploaded, leave the dedicated local authorization to Actions; local commands should use their separate original app/state. Reauthorize and replace the environment credential secret if the Actions authorization is revoked.

Scheduled runs with missing secrets print a setup notice and skip refresh/publication. Manual runs with missing secrets fail with a setup message. Neither path calls Trakt. No credentials have been uploaded by adding these workflow files.

### Rotating credentials and retained progress

Trakt refresh tokens rotate. `python -m myshows.github_trakt` verifies that it can save the credential secret before making Trakt requests. Each subsequent token rotation is saved locally and immediately written back to the environment secret before another authenticated GET. Failed secret writes stop further Trakt requests. The GitHub CLI encrypts the value from stdin; credentials never appear in command-line arguments or diagnostic output.

Environment secrets are intentional: GitHub reads them when the serialized job starts, whereas repository secrets are captured when a workflow is queued. This lets a queued run receive credentials rotated by the preceding run. See [secret-loading times](https://docs.github.com/en/actions/reference/security/secrets) and [environment-secret API permissions](https://docs.github.com/en/rest/actions/secrets#create-or-update-an-environment-secret).

The runner restores fallback list/progress values from the latest validated public snapshot into its private temporary SQLite cache. This preserves known progress and original successful-check times after partial failures without uploading credentials or private caches as artifacts. A complete, successfully empty list still removes old entries. Private state is scoped to the workflow's dedicated account and remains on the ephemeral runner.

As with production research, partial success can publish validated retained/new progress while the overall workflow reports failure. If remote secret persistence fails just after an OAuth rotation, local replacement credentials remain on that runner, but later runs may require reauthorization; there is no blind retry of a consumed refresh token.

## When refreshes rebuild the website

Both refresh workflows call [the same publication helper](../.github/scripts/publish-refresh.sh). It checks its one allowed public JSON input before running tests or building. No file change means **no website build, data commit or Pages dispatch**. Changed data must pass tests and an offline build before publication.

Successful last-check times count as changes, as requested, even when episode counts or status headlines are unchanged. Publishing those times prevents recently checked shows from being labelled as stale. Failed refreshes never advance successful-check dates. A repeated failure with identical retained data/failure indicators needs no new build.

The helper explicitly dispatches Pages after a successful changed-data push. Both refreshed files are read by that build; the public site needs no refresh credentials. Runner delays can shift actual execution times from the UTC schedules.

## Why research rather than just TMDB?

On 8 November 2026, we tested TMDB's [TV details endpoint](https://developer.themoviedb.org/reference/tv-series-details) against all ten programmes in the live Following list, using exact TMDB IDs supplied by Trakt. All ten matched and returned `status: "Returning Series"` with `in_production: true`. Only Silo, The Rings of Power and Rivals returned a non-null `next_episode_to_air`; the other seven supplied none.

Those are useful structured metadata fields, but the observed series-level production flag does not distinguish greenlit, writing, filming, wrapped or post-production. Next-episode dates also do not establish UK availability or an independently sourced production milestone. Existing official announcements contain more detail and sometimes differ from that broad series status. We therefore use sourced research for production assertions instead of translating `in_production` into a filming claim or overwriting stronger evidence with generic metadata.

TMDB remains a candidate for supplementary metadata and licensed UK provider information. Its API is [free for non-commercial use with required attribution](https://developer.themoviedb.org/docs/faq); production use would need the approved logo and notice. It is not currently a runtime dependency. The wider TVmaze/TMDB comparison in [issue #6](https://github.com/davorg/myshows/issues/6), including all reference shows, terms and quotas, remains open.

The research integration follows OpenAI's official [web-search](https://developers.openai.com/api/docs/guides/tools-web-search) and [structured-output](https://developers.openai.com/api/docs/guides/structured-outputs) documentation.

Structured production providers do exist beyond TMDB. See [the provider investigation](production-data-providers.md) for Production List's API/MCP, Luminate and IMDb. These remain evaluation candidates; the current refresh utility still uses OpenAI research.
