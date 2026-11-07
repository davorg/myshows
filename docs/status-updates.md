# Sourced show statuses

Renewal, production and release information is a core MVP requirement. The owner approved a small file of sourced updates because metadata APIs do not cover all these facts. `data/statuses.json` currently contains researched assertions for all eight shows in the real Trakt Following list. A newly followed show with no matching record displays **Status unknown**, without falling back to made-up information.

## Data model

The file has `schema_version: 1` and a `shows` mapping keyed by the stable numeric **Trakt show ID**, represented as a JSON string. Names and list order are not used for matching.

Each show record contains a list of independent `facts` and a `lead` identifying the most useful fact for its headline. Facts have:

- `id`: unique within the show record.
- `kind`: `renewal`, `production`, `release` or `outcome`.
- `season`: the specific season the assertion concerns.
- `headline` and `detail`: a concise, spoiler-free summary and the limits of the evidence.
- `confidence`: `confirmed` for attributable announcements/confirmations, or `reported` for industry reporting that is not official confirmation.
- `checked_on`: the date this evidence was actually reviewed, not the latest export date.
- `sources`: one or more source names, HTTPS URLs and publication dates where known. Unknown publication dates are `null`.
- For releases, `release` contains `precision` (`day`, `month`, `year` or `window`), the original `value`, and the announced `region`.

Example: Rivals has a season-two return-date assertion and a separate season-three renewal assertion. Starfleet Academy has a forthcoming season-two window, a cancellation outcome, and a dated post-production milestone. None of these facts overwrites another merely because it is a different kind of status.

## Editorial rules

Prefer studio/broadcaster announcements and direct, attributable statements. Industry listings or reporting may be useful, but label their evidential status. Store only short paraphrases and factual summaries; link to the full source rather than copying articles. Do not add plot details.

Do not infer filming from renewal, post-production from the absence of filming news, cancellation from a generic ended flag, or UK timing from a release elsewhere. If evidence confirms a final planned season, distinguish that from cancellation. Date older milestones explicitly instead of presenting them as freshly observed current activity.

Retain release precision. A March 2027 announcement remains `month: 2027-03`; it must not become 1 March. A 2026 slate entry remains year-only. Unverified UK timing must be stated. The page shows passed announcements as needing another check, without inferring that episodes are now streaming. Window sorting uses the end of an announced month/year internally and does not publish an invented premiere date.

When sources conflict, compare their dates and authority, retain the evidence needed to explain the conflict, and revise the headline/detail to acknowledge uncertainty. There is no automatic source reconciliation in this MVP. The selected lead is an editorial choice, not a computed claim that every other assertion is obsolete.

Only advance `checked_on` after reviewing the evidence. Editing styling, syncing Trakt or rebuilding the page must not make old status evidence look newly verified. Status checks older than 30 days are flagged in the browser; Trakt progress retains its separate 24-hour indicator. Neither threshold asserts that the underlying facts have changed.

## Update and publish

1. Research current sources for the affected show.
2. Add/update its dated facts, preserve the correct season/region/precision, and select the lead.
3. Run `python3 -m unittest discover -s tests -v`.
4. Run `python3 -m myshows build --snapshot data/watchlist.json` to check the result, then commit and push the status file. The GitHub Actions workflow publishes the new dashboard to GitHub Pages.

`myshows/status.py` validates the file and allowlists its public fields. Missing evidence, bad dates, unsupported precision, duplicate fact IDs and unknown lead IDs reject the build before changing the exported page. A missing/unreadable file also fails the build instead of silently removing every status. Select a different file with `build --statuses /path/to/statuses.json`.

Research is manual for this MVP. `sync` refreshes watched history only; `build` reads existing local data without calling news sites. The public page has no editorial write endpoint. Later API integrations should populate the same assertion model, preserving provenance and uncertainty.

## Initial research

The assertions were reviewed on 7 November 2026. Each fact in the JSON file carries its supporting links and publication dates. The initial coverage includes official Apple, Amazon, Disney, Netflix and Paramount announcements; Adam Scott's filming confirmation reported by The Wrap; a reported Pluribus production listing from FTIA; and the studio statement/showrunners' letter carried by Variety for Starfleet Academy. The Pluribus industry listing is explicitly labelled reported. Release windows for the Paramount shows and Netflix's year-only slate are not presented as independently verified UK dates.
