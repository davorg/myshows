# My Shows

A personal, read-only dashboard for the television series I'm following: **what's happening next, how far I've watched, and where I can watch them in the UK**.

Trakt is the source of truth for viewing history. My Shows is not another episode tracker or a notification service. It is a high-level view to consult occasionally, especially when seasons are separated by years.

## The problem

It's easy to forget whether a favourite drama has been renewed, cancelled, finished as planned, begun filming, or acquired a release date. Information is scattered across trackers, streaming catalogues and news articles. A compact, curated dashboard should make it easy to see the situation at a glance.

## MVP

- Follow a **curated selection** of shows, ideally through a dedicated Trakt custom list, without duplicating viewing history.
- Display the **last watched season/episode** and number of available, unwatched episodes from Trakt.
- Show the **latest known status**: awaiting decision, renewed, in production, scheduled, ended or cancelled. Distinguish confirmed facts from speculation and unknowns.
- Show the next season and release date/window, where known; don't invent dates.
- Show **UK streaming availability**, including service, with an investigation of legitimate data-provider access (JustWatch if feasible, alternatives if not).
- Group or filter shows by streaming service and status.
- Provide a responsive, readable **single-page dashboard**, with links to sources and last-checked timestamps.
- Handle absent, stale and conflicting metadata honestly.

The initial reference set includes *Severance*, *Pluribus*, *The Rings of Power*, *Doctor Who*, *3 Body Problem*, *Silo*, *Rivals*, *Star Trek: Strange New Worlds* and *Star Trek: Starfleet Academy*. These are examples, not a hard-coded list.

### MVP boundaries

No real-time notifications, no replacement for Trakt's watched-history management, no billing integration and no requirement to track active streaming subscriptions. No particular framework or language has been selected yet.

## Data sources to investigate

| Need | Candidate | Considerations |
| --- | --- | --- |
| Followed shows and watched progress | Trakt API | OAuth, custom lists, watched progress and API limits |
| Show metadata, renewals, seasons and schedules | TVmaze / TMDB | Coverage, semantics, attribution, reliability and API terms |
| UK streaming availability | JustWatch or another licensed provider | Official access, cost, licensing, regional coverage and caching |
| Production news and context | Official announcements / attributable reporting | Store source URLs and dates; avoid unsupported claims |

A renewal flag is not the same as a filming date; a series finale is not necessarily a cancellation. The interface should make these distinctions clear.

## Future ideas (not MVP)

- Track which streaming services I'm currently subscribed to, and subscription dates/costs.
- Suggest sensible **one-month subscription windows** when multiple unwatched seasons are available on one service.
- Show what's changed since the previous visit.
- Optional periodic digests or alerts.
- Personal notes, watch priorities and recommendations.
- More sophisticated production-stage timelines and source reconciliation.

## Development

See [Issues](https://github.com/davorg/myshows/issues) for the proposed MVP backlog. Start by validating API access and the data model, then build the smallest end-to-end slice. Contributions and implementation decisions can be discussed in issues.

## Status

Early planning / proof of concept. No implementation yet.
