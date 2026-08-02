# Pundit AI - Architecture decisions

## Project context

This project combines a personal interest in football with a portfolio goal of demonstrating agentic AI architecture, data engineering, and applied machine learning together in one system, rather than each in isolation. Watching and following matches regularly made the idea of an AI that can reason about performance and outcomes the same way a fan or analyst would feel like a natural fit, rather than an arbitrary dataset choice.

The ultimate goal is for the AI to form its own opinion from the underlying stats when a user asks a question, rather than just reporting numbers back. Asking "did Marquinhos play well yesterday" should get a judgment (yes, with specific reasoning drawn from his stats and the match context), not a stat dump. It's structured in two phases: V1 is an AI analyst that forms this kind of opinion on player and match performance; V2 adds a trained model to predict match outcomes using team form, head-to-head history, and player availability. The project is mentor-guided, with biweekly check-ins to review architecture and progress; this document exists specifically to keep the reasoning behind each technical decision visible, separate from the codebase itself.

---

This document tracks the key technical decisions for Pundit AI, and the reasoning behind each one.

## Database: PostgreSQL over NoSQL

**Decision:** Use PostgreSQL (relational) rather than a NoSQL store like MongoDB.

**Reasoning:** Football data has inherent relational structure - a match belongs to two teams, a team has many players, a player has many stat lines across matches - which maps cleanly onto foreign-key relationships. XGBoost training also needs flat, tabular rows, which SQL provides directly via a query; NoSQL would require an extra flattening step. Agent questions (season averages, head-to-head history) are natural JOIN + WHERE queries. Also diversifies the portfolio alongside an existing MongoDB-based project.

**Trade-off accepted:** Requires upfront schema design before data can be inserted, unlike NoSQL's flexible-schema approach.

---

## Scraping: soccerdata library over hand-rolled Scrapy/BeautifulSoup

**Decision:** Use the `soccerdata` Python library (which wraps FBref/Understat scraping internally) rather than writing a custom Scrapy or BeautifulSoup spider.

**Reasoning:** A direct `requests` call to FBref returns a Cloudflare Turnstile JS challenge page instead of real content - confirmed by testing against a real match URL. This isn't a simple rate-limit or User-Agent issue; it's a JS-based bot challenge that a plain HTTP request (which is what both Scrapy and BeautifulSoup fundamentally use) cannot pass, and attempting to defeat it directly would cross into bot-detection bypass, which isn't something to build around. `soccerdata` is an actively maintained, widely used library that already handles FBref's scraping quirks, so it was tested directly as an alternative to hand-rolling a spider from scratch.

A second candidate, `fbrefdata` (a fork of `soccerdata` aiming for broader competition coverage), was also evaluated but ruled out: it depends on `undetected_chromedriver`, which imports `distutils` - a standard library module removed starting in Python 3.12 (not just 3.13, as initially assumed). This makes `fbrefdata` unusable on any current Python version without deeper dependency workarounds, and signals the library isn't being actively maintained to track modern Python. Confirmed by testing on both Python 3.13 and 3.12 venvs - same failure on both, since the underlying stdlib removal applies to both versions.

**Trade-off accepted:** `soccerdata`'s built-in league coverage is the top-5 European domestic leagues (Premier League, La Liga, Ligue 1, Bundesliga, Serie A) plus major international tournaments (Euros, World Cup, Women's World Cup) - it does not include Champions League or Europa League. Custom league addition for Champions League is technically possible in `soccerdata` but its own docs warn this may not scrape correctly, so it's a possible future experiment, not core scope. (See "Data sources" below for what `soccerdata` actually provides at the stat level, and how it's merged with API-Football.)

---

## Orchestration: Airflow over Prefect

**Decision:** Attempt Airflow first; fall back to Prefect if Airflow's setup/infra overhead becomes a blocker.

**Reasoning:** New match data needs to be scraped/pulled on a recurring daily schedule and inserted into the database. Airflow is the longer-standing, more widely recognized industry-standard orchestration tool. Prefect is lighter-weight and easier to set up for a solo, single-pipeline project, making it a reasonable fallback if Airflow's infra requirements (scheduler, webserver, metadata DB) prove too heavy.

**Trade-off accepted:** Same time-boxed evaluation approach as the scraping decision, to avoid extended setup struggles derailing progress.

---

## Data sources: merged soccerdata (FBref) + API-Football, after extensive evaluation

**Decision:** Merge two legitimate sources at the column level rather than relying on one: `soccerdata` (FBref) for goals, assists, cards, minutes, tackles-won, interceptions, and crosses (`crosses SMALLINT DEFAULT 0`, added to `player_match_stats` after this section was originally written); API-Football for passes, duels, and team-level xG. Serp API remains the runtime fallback for information not yet in the database.

**Reasoning - the full investigation, since this scope took real work to arrive at:**

Player-level match stats were originally scoped to include xG, xA, passing, and duels, matching what FBref's site shows generally. Getting there required testing several sources and ruling most of them out for good reason:

- **FBref via `soccerdata`:** confirmed working and legitimate (published bot policy tolerates scraping under a rate limit), but `read_player_match_stats` only exposes Summary and Keeper tables. Verified exhaustively (not just via the library's method whitelist, but by parsing every `<table>` element in the raw cached HTML directly, across two independent matches) that FBref's match report pages for these fixtures genuinely do not contain Passing/Possession/Defensive Actions/Misc tables at all - not hidden, not comment-wrapped, simply absent from the page as fetched. Season-level aggregate stats were also checked (`read_player_season_stats`) and found to lack xG and progression columns entirely, even for `stat_type="standard"`.
- **Understat:** has no official API or published terms of service. `soccerdata`'s Understat reader silently pulls in `tls-client`, a TLS-fingerprint spoofing library used specifically to defeat bot detection (Cloudflare/DataDome-style). This is different in kind from FBref's Selenium-based approach (a real browser rendering a page) - it's purpose-built bot-detection bypass, so it was ruled out entirely rather than used.
- **FotMob:** explicitly prohibited. Their own Terms of Use state that scraping, automated extraction, or use of "robots, spiders" against their data is strictly forbidden, regardless of commercial intent.
- **Sofascore:** same conclusion. Their published terms (confirmed via their Torneo product's ToS) explicitly prohibit automated means - scripts, scraping, crawling - to access their platform.
- **Opta/Stats Perform:** enterprise-only, no self-serve or free tier of any kind; sales-contact-only access model, not viable for a solo project.
- **StatsBomb Open Data:** a genuine, legitimate free option - officially published by StatsBomb for public research use, with real event-level data (passes, xG, duels, pressures). Not used as the primary V1 data source because coverage is a fixed set of historical competitions (e.g. World Cups, women's football, specific past seasons), not live/current matches. Worth revisiting later as a source of richer, curated demo matches or as training data for V2, since it doesn't cover the "yesterday's match" live use case V1 needs.

**API-Football re-evaluated as more than a fixtures/scores source.** Testing its `/fixtures/statistics` and `/fixtures/players` endpoints directly (rather than assuming it was fixtures-only) showed it returns real `passes` (total, accuracy) and `duels` (total, won) objects at the player level, plus team-level `expected_goals` - exactly the data FBref's match pages don't expose. Cross-validated against FBref for the same player in the same match (Declan Rice, Man City vs Arsenal): tackles and interceptions matched exactly between both independently-sourced datasets, confirming API-Football's numbers are real match data, not placeholder/fabricated values.

Some sub-fields (`shots.on`, `tackles.blocks`, `tackles.interceptions`, `key_passes`, `dribbles.*`) were found to be sparsely populated - null for a majority of players in every match checked, with no consistent pattern by position or league. These are treated as legitimately optional data (nullable columns), not evidence the source is unreliable overall, since the core fields (`passes.total`, `passes.accuracy`, `duels.total`, `duels.won`) were populated for every player checked across two leagues.

**Data quality finding: API-Football's `passes.accuracy` field is mislabeled.** Despite the name, it is not a percentage - it's a raw count of completed passes. Confirmed across 19 players spanning 3 fixtures and 2 leagues: the value is always less than or equal to `passes.total`, and scales with pass volume rather than being an independent 0-100 value (e.g. a player with 9 total passes showed `accuracy: 4`, not a percentage like "44"). The schema column was originally named `pass_accuracy` (`NUMERIC(5,2)`, expecting a percentage); it's been renamed to `passes_completed` (`SMALLINT`) to reflect what the field actually contains, before any real data was ingested.

**Trade-off accepted:** Player-level xG, xA, and progressive passing/carries are not available from any legitimate free source for live/current matches, and are dropped from V1 scope entirely (schema updated accordingly - see `db/schema.sql`). This means possession-control players whose value doesn't show up in goals/tackles/passes volume (e.g. a Pedri- or Rodri-type profile) will have a real, honest limitation in how deeply V1 can assess their game - the agent should be designed to acknowledge this rather than present false confidence. Team-level xG (not player-level) is available via API-Football and included in the `matches` table. Two data sources also means reconciling player/team identifiers across them during ingestion, rather than one unified source.

---

## Ingestion pipeline: built and verified end-to-end

**Decision:** Built src/ingestion/ingest_match.py, which pulls FBref (via soccerdata) and API-Football data for a match, aligns players using src/scraping/name_matching.py, and upserts into player_match_stats. Verified against two real matches (Man City vs Arsenal, Liverpool vs Man Utd) with actual database rows checked back, not just "insert succeeded" logs.

**Reasoning:** Name-matching required three layers, discovered by comparing full FBref vs API-Football player lists across real matches rather than assuming names would align: (1) filtering API-Football's full squad list down to players with minutes > 0, since API-Football returns the whole matchday squad while FBref only lists players who actually appeared; (2) Unicode normalization with an explicit override map for non-decomposing characters (O with stroke, sharp s, and similar) that standard NFKD normalization doesn't handle; (3) a manual alias table for genuine name differences that normalization can't fix (e.g. Savio vs Savinho, a full given name vs its short form). Verified to reach 100% match rate (30/30 and 32/32 players) across both test matches, with unmatched cases logged rather than silently dropped.

**New finding: API-Football's sparse fields are non-deterministic, not just incomplete.** Rerunning ingestion for the same completed historical match returned a different value for the same player's tackles field across separate calls (a real 0, then null, on identical input) - confirmed via direct raw-response comparison, ruling out a bug in our own code. This is a stronger caveat than the earlier "some fields are sparsely populated" finding, since it shows the same field for the same player in the same finished match isn't even stable across calls, not just inconsistently present across different players.

**Trade-off accepted / mitigation:** Since a rerun could silently regress a real, previously-ingested value back to null, the upsert logic was changed so incoming null values from API-Football never overwrite an existing non-null value in the database - only real values, or inserts into previously-empty rows, are written. Verified via a direct, deterministic test (set a real value, apply an incoming null, confirm the value is preserved) rather than relying on API-Football happening to demonstrate the flakiness itself.

---

## Match events: built on API-Football only, 98.84% player-resolution rate

**Decision:** match_events ingestion uses API-Football's /fixtures/events endpoint exclusively - no FBref involved, despite FBref also having a real events timeline (confirmed via its events_wrap div, cross-validated against API-Football's data with 100% agreement on a test match). API-Football was chosen since it's structured JSON with no scraping/CAPTCHA risk, and since both sources agreed exactly, there was no benefit to using both.

**Reasoning - player-name resolution required extending the matching approach:** API-Football's events feed uses abbreviated and inconsistent name formats (e.g. "E. Haaland" for a goal but "Erling Haaland" for a card, in the same response). Built a three-tier fallback: exact/alias match, then abbreviated "F. Lastname" matching, then team-scoped bare-first-name matching (scoped to the specific team an event belongs to, to avoid misattributing an event to a same-named player on the opposing team - verified against a real case with two different "Nico"s in the database).

A first pass reached 97.3% resolution (5,519/5,673 events). Spot-checking the unresolved 154 (rather than accepting the aggregate number) found 72% of failures traced to one structural gap: the abbreviated-name matcher only handled a single initial and assumed a single-token surname, which broke on multi-initial names (e.g. "D. M. Wolfe" vs DB's "David Møller Wolfe") and multi-given-name players (e.g. "M. Diouf" vs DB's "El Hadji Malick Diouf"). Fixing this plus adding several nickname aliases raised resolution to 98.84% (5,607/5,673).

**Trade-off accepted - remaining 66 unresolved events (1.16%), left as-is:** every remaining case was individually traced, not left as unexplained noise. Roughly a third are correctly, permanently unresolvable by design (players with zero rows in the database at all, or genuine ambiguity like Arsenal fielding three players named Gabriel - the system correctly declines to guess rather than misattribute). The rest are narrow, low-value edge cases (transliteration spelling differences, hyphen-vs-space compound surnames, Turkish diacritics, Korean name-order, and 3 bare-surname collisions like two different players named Cunha on different teams). Fixing these fully would require increasingly specific logic for a shrinking number of events - judged not worth the effort given the core stat-based analysis (player_match_stats) is entirely unaffected by any of this, and the failure mode throughout is "event stays unresolved/incomplete," never "event attributed to the wrong player."

**Known data-modeling gap, noted for later:** Jørgen Strand Larsen has two separate Player rows (Wolves and Crystal Palace) from a mid-season transfer, since players are currently keyed by (name, team_id) rather than a stable player identity independent of team. Not fixed now - would require a real schema change - but worth knowing about if transfers become relevant elsewhere.

---

## Machine learning approach: no ML in V1, XGBoost in V2

**Decision:** V1 (player/match performance analyst) uses no trained model - the LLM reasons directly over retrieved stats. V2 (match outcome prediction) uses an XGBoost 3-class classifier (home win / draw / away win).

**Reasoning:** V1's task is interpreting known, already-occurred stats - retrieval plus LLM judgment is sufficient, and forcing a trained model into that step would add complexity without adding accuracy. V2's task (predicting a future, unknown outcome) is a genuine supervised learning problem, which XGBoost handles well for structured tabular features (recent form, head-to-head, home advantage, player availability).

**Trade-off accepted:** Two different technical approaches within one project, worth explaining clearly so it doesn't read as an inconsistency.

---

## Agent framework: hand-rolled tool loop for V1, LangGraph for V2

**Decision:** Build V1's tool-calling loop directly against the raw Gemini/OpenRouter API. Introduce LangGraph specifically for V2, where reasoning branches conditionally (e.g. check form -> check head-to-head -> check injuries -> decide).

**Reasoning:** V1's flow (LLM picks 1-3 tools, gets results, responds) is simple enough to hand-roll, which also demonstrates a clear understanding of the underlying mechanics rather than relying on an abstraction from the start. V2's genuinely branching logic is the specific problem LangGraph's state-graph model is designed to simplify.

**Trade-off accepted:** Two different agent implementations within the same project; introducing a framework partway through is a deliberate choice, not an inconsistency.

---

## Deferred: RAG caching layer for Serp API results

**Decision:** Not implemented now; revisit after V1 and V2 are functional, as a stretch goal.

**Reasoning:** Mentor asked whether RAG could reduce redundant Serp API calls by caching prior search results. It's technically sound (would use pgvector alongside the existing Postgres database, with embeddings and a TTL/freshness check to avoid serving stale cached results), but Serp is a fallback tool, not the primary data path - most queries are already answered from the database. The added complexity (vector store, embeddings, freshness handling) isn't justified yet for a tool that's called infrequently.

**Trade-off accepted:** None currently, as long as the Serp API call stays isolated in its own tool function - this keeps the door open to add the cache layer later as a contained, low-risk addition rather than a refactor.
