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

**Trade-off accepted:** `soccerdata`'s built-in league coverage is the top-5 European domestic leagues (Premier League, La Liga, Ligue 1, Bundesliga, Serie A) plus major international tournaments (Euros, World Cup, Women's World Cup) - it does not include Champions League or Europa League. V1 scope is limited to these supported leagues for full advanced-stats analysis. Champions League/Europa League matches can still get basic coverage (fixtures, scores, lineups) via API-Football, just without the advanced stats (tackles, xG/xA, progressive passes) that power the deeper analyst commentary. Custom league addition for Champions League is technically possible in `soccerdata` but its own docs warn this may not scrape correctly, so it's a possible future experiment, not core scope.

---

## Orchestration: Airflow over Prefect

**Decision:** Attempt Airflow first; fall back to Prefect if Airflow's setup/infra overhead becomes a blocker.

**Reasoning:** New match data needs to be scraped/pulled on a recurring daily schedule and inserted into the database. Airflow is the longer-standing, more widely recognized industry-standard orchestration tool. Prefect is lighter-weight and easier to set up for a solo, single-pipeline project, making it a reasonable fallback if Airflow's infra requirements (scheduler, webserver, metadata DB) prove too heavy.

**Trade-off accepted:** Same time-boxed evaluation approach as the scraping decision, to avoid extended setup struggles derailing progress.

---

## Data sources: soccerdata + API + live search

**Decision:** Use `soccerdata` (which pulls from FBref/Understat internally) for advanced stats on top-5 league matches, API-Football (free tier) for structured fixtures/scores across all competitions including Champions League/Europa League, and Serp API as a runtime fallback for information not yet in the database.

**Reasoning:** No single free source covers both rich advanced stats and structured fixture/score data for every competition. `soccerdata` provides the granular stats (tackles, xG/xA, progressive passes) the analyst feature depends on, for its supported leagues. API-Football provides clean JSON without needing HTML parsing, and covers competitions `soccerdata` doesn't (like Champions League), just without the same stat depth. Serp API only runs at query time (unlike the other two, which only run during scheduled ingestion), covering things like breaking injury news not yet ingested.

**Trade-off accepted:** Three separate data sources to maintain and reconcile (e.g. matching player names/IDs across sources) rather than one unified source. Additionally, stat depth is uneven across competitions - full advanced-stats analysis for top-5 leagues, basic-only for Champions League/Europa League.

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
