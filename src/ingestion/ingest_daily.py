import os

import requests
from dotenv import load_dotenv

from src.db.connection import SessionLocal
from src.ingestion.ingest_match import (
    get_or_create_league,
    get_or_create_match,
    get_or_create_team,
    ingest_match_events,
)
from src.ingestion.ingest_season import API_BASE, FBREF_SEASON, LEAGUE_ID, SEASON_YEAR
from src.ingestion.ingest_season_events import already_has_events

load_dotenv()


def run_daily() -> dict:
    """Find Premier League matches that have been played but don't yet have match_events
    ingested, and ingest events for each - meant to run once a day inside the Docker/Airflow
    environment.

    Deliberately API-Football-only, unlike ingest_season.py's full FBref+API-Football
    pipeline: FBref's player-stats scraping (soccerdata's headless browser session) can't run
    reliably from this environment - every attempt has hit FBref's CAPTCHA gate on a fresh,
    cookie-less, datacenter-hosted browser session, and correctly refuses to attempt a solve
    in headless mode rather than hanging or bypassing it, so it just fails loudly every time.

    Match/Team/League rows are created here from API-Football's fixture data alone, reusing
    the same get_or_create_league/team/match helpers ingest_match() uses for that piece
    (unchanged, still used as-is by ingest_season.py's venv-based full pipeline) - just
    without the FBref-dependent player-stats step. Player stats for these matches can still
    be backfilled later from the venv via ingest_season.py, which is unaffected by this and
    remains the source of truth for that data.
    """
    headers = {"x-apisports-key": os.getenv("API_FOOTBALL_KEY")}

    fixtures_resp = requests.get(
        f"{API_BASE}/fixtures", headers=headers, params={"league": LEAGUE_ID, "season": SEASON_YEAR}, timeout=30
    )
    all_api_fixtures = fixtures_resp.json()["response"]

    counts = {"success": 0, "skipped": 0, "not_played_yet": 0, "failed": 0}

    for fixture in all_api_fixtures:
        if fixture["fixture"]["status"]["short"] != "FT":
            counts["not_played_yet"] += 1
            continue

        api_fixture_id = fixture["fixture"]["id"]
        home_name = fixture["teams"]["home"]["name"]
        away_name = fixture["teams"]["away"]["name"]
        match_date = fixture["fixture"]["date"][:10]
        label = f"{home_name} vs {away_name} ({match_date})"

        session = SessionLocal()
        try:
            league = get_or_create_league(session, fixture["league"]["name"], fixture["league"]["country"])
            home_team = get_or_create_team(session, home_name, league.league_id)
            away_team = get_or_create_team(session, away_name, league.league_id)

            # xG is left for ingest_season.py's venv-based full pipeline to fill in later -
            # not worth an extra /fixtures/statistics call per match here, especially since
            # get_or_create_match doesn't update xG on a match row that already exists (the
            # common case once the season is mostly ingested).
            match = get_or_create_match(
                session,
                league_id=league.league_id,
                match_date=match_date,
                home_team=home_team,
                away_team=away_team,
                home_score=fixture["goals"]["home"],
                away_score=fixture["goals"]["away"],
                home_xg=None,
                away_xg=None,
                season=FBREF_SEASON,
                source="api-football",
            )
            session.commit()

            if already_has_events(session, match.match_id):
                counts["skipped"] += 1
                continue

            match_id = match.match_id
        finally:
            session.close()

        try:
            events = ingest_match_events(db_match_id=match_id, api_fixture_id=api_fixture_id)
            print(f"{label} - success ({len(events)} events)")
            counts["success"] += 1
        except Exception as e:
            print(f"{label} - failed: {type(e).__name__}: {e}")
            counts["failed"] += 1

    print(f"Daily events-only ingestion done: {counts}")
    return counts


if __name__ == "__main__":
    run_daily()
