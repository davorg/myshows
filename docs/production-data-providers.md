# Structured production-data providers

Research checked on 8 November 2026. This is an evaluation, not an integration or a purchasing decision. Prices below are advertised USD prices, subject to the provider's terms and the intended use.

## Production List / Film & Television Industry Alliance

There is a documented [REST API](https://www.productionlist.com/api), [OpenAPI schema](https://api.productionlist.com/openapi.json) and [official MCP service](https://www.productionlist.com/plugin).

Advertised API plans include free evaluation data (30-day delay, sample cap), Monitor ($199/month or $1,990/year; 72-hour delay; 10,000 calls/month) and Pipeline ($599/month or $5,990/year; real-time; 100,000 calls/month; change feed/webhooks). Attribution is required unless separately waived under the applicable plan.

The published schema exposes five lifecycle stages: development, pre-production, production, post-production and completed. It includes shooting/post-production dates, record-update timestamps and public record URLs. Title filtering, pagination and `updated_since` are documented. Matching needs care: the production schema inspected has no dedicated season number or series IMDb/TMDB ID; some season information appears in titles. API stages alone do not supply all renewal, planned-ending and regional release assertions.

### Live evaluation

The unauthenticated MCP endpoint `https://api.productionlist.com/mcp` responded successfully to initialization, tool listing, three title searches and one production-detail lookup. No account, subscription or billable model request was required. We did not install a connector or copy a production dataset into this repository.

It exposes read-only search/detail tools for productions and companies, plus taxonomy lookup. Searches match titles, not general news or company names embedded in a question.

Representative observations from the live service:

| Search | Observation |
| --- | --- |
| Severance | Separate season records. [Season 3](https://www.productionlist.com/production/severance-season-3) was classified as post-production, updated 29 October 2026. Its detailed production-date fields were partly empty. |
| Silo | Only a [completed season-two record](https://www.productionlist.com/production/silo-season-2) was returned by the title search. This does not establish the state of later seasons. |
| Doctor Who | Older season records and the CBeebies animated project appeared. A broad title match can select a different production or spin-off. |

These are provider assertions and coverage observations, not independent verification of filming activity. The public Severance page also showed differing month-level shooting information in different parts of the page. Structured delivery does not remove the need to retain uncertainty or compare stronger evidence.

### Rights and limitations

The [MCP terms](https://www.productionlist.com/plugin/terms) permit limited assistant lookups but prohibit rebuilding its database and redistributing plugin output as a data product. They direct programmatic use to the separately licensed API. The free MCP is therefore useful for evaluation; it is not a free replacement backend for My Shows.

The [general terms](https://www.productionlist.com/terms-of-service) describe AI-assisted collection and classification, with editorial review where practical rather than verification of every listing. They also impose reuse restrictions. Before adoption, obtain the API-specific terms covering caching and public display of the selected fields; do not assume a website membership grants those rights.

## Luminate Film & TV

[Film & TV](https://luminatedata.com/filmandtv/) advertises API access and data licensing. Its current developer hub documents a [Snowflake Data Share](https://docs.luminatedata.com/docs/getting-started-with-ftv-snowflake-data-share). Older [REST/file-export documentation](https://filmtv.luminatedata.com/luminatefilmandtvapi/) also exists; a guessed direct legacy specification URL returned HTTP 403 during this check, so current delivery options need confirmation.

The [TV/digital project dictionary](https://docs.luminatedata.com/docs/project-metadata) documents season numbers, production status, renewal and planned-ending fields, shooting details, regional premiere/finale information, IMDb IDs, season EIDR IDs, parent-project links and modification dates. Shooting details distinguish actual dates from approximate windows. This is the closest documented match to our independent, season-specific assertions. However, the TV status examples do not explicitly list post-production, unlike the film examples; verify actual TV coverage before promising that phase.

No suitable public feed price was established. Ask for a quote specifically for a consumer dashboard, with a small set of status/date fields, refresh volumes and public-display rights. We have not accessed licensed records or verified coverage against our watchlist.

## IMDb licensed data

IMDb's licensed [bulk title dictionary](https://data.imdb.com/documentation/bulk-data-documentation/data-dictionary/titles) documents dated production-status history and regional release dates with day/month/year precision. Its [status definitions](https://help.imdb.com/article/contribution/titles/production-status/GBBBPNJHFZZKY7W9) include announced, pre-production, filming and post-production, and explicitly distinguish series-level status from episode status. A series title's status is not sufficient proof of the next season's phase.

IMDb also offers a [GraphQL API through AWS Data Exchange](https://data.imdb.com/documentation/api-documentation/getting-access/). We verified production history in the bulk dictionary, not its availability or granularity in a purchased GraphQL schema. Confirm the exact package and fields with IMDb.

The public [Essential Metadata API listing](https://aws.amazon.com/marketplace/pp/prodview-wdqq4hg3bcbws) displayed $150,000 for a 12-month contract, plus usage charges, with final pricing dependent on the licensed use case. This is an enterprise option rather than an economical first trial for this project. Other packages or negotiated terms may differ.

## Recommended next evaluation

1. Compare a representative set of current and forthcoming seasons against Production List's permitted evaluation access, measuring missing records, freshness, season matching and conflicting evidence. The three-title probe above is not a completeness test.
2. Request API licensing clarification from Production List and a narrow-field quote from Luminate. Include storage, public display, attribution, retention after cancellation and source provenance. No vendor has been contacted yet.
3. Keep provider assertions distinct from official announcements. Preserve source URLs, provider update dates and our own check dates separately. Retain unknowns and the existing last-successful-data fallback.
4. Refresh one shared catalogue for all users. Poll changed records where supported; adjust check frequency by lifecycle stage; use model research for gaps and conflicts rather than every show on every run.

The opportunity appears to be an affordable consumer-facing aggregation layer with clear season matching and evidence. Production intelligence itself is already an established product category. That is an assessment of the sources above, not a claim that the market has been exhaustively surveyed.
