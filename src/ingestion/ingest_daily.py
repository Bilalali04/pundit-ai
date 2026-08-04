import os
import random
import time

import requests
import soccerdata as sd
from dotenv import load_dotenv

from src.db.connection import SessionLocal
from src.ingestion.ingest_match import ingest_match, ingest_match_events
from src.ingestion.ingest_season import (
    API_BASE,
    FBREF_LEAGUE,
    FBREF_SEASON,
    LEAGUE_ID,
    SEASON_YEAR,
    already_ingested,
    find_api_fixture_id,
)

load_dotenv()


def run_daily() -> dict:
    """Find Premier League matches that have been played but aren't yet in the database, and
    ingest both player stats and match events for each - meant to run once a day rather than
    the full-season backfill ingest_season.py does.

    Reuses the exact same schedule-matching (already_ingested, find_api_fixture_id) and
    ingestion (ingest_match, ingest_match_events) logic those already-proven scripts use -
    the only new behavior here is chaining events ingestion onto each newly-ingested match,
    which neither existing script does on its own.
    """
    headers = {"x-apisports-key": os.getenv("API_FOOTBALL_KEY")}

    fbref = sd.FBref(leagues=FBREF_LEAGUE, seasons=FBREF_SEASON, headless=True)
    try:
        schedule = fbref.read_schedule().reset_index()

        fixtures_resp = requests.get(
            f"{API_BASE}/fixtures", headers=headers, params={"league": LEAGUE_ID, "season": SEASON_YEAR}, timeout=30
        )
        all_api_fixtures = fixtures_resp.json()["response"]

        counts = {"success": 0, "skipped": 0, "failed": 0}

        for row in schedule.to_dict("records"):
            home = row["home_team"]
            away = row["away_team"]
            date = row["date"]
            date_str = date.strftime("%Y-%m-%d") if hasattr(date, "strftime") else str(date)[:10]
            game_id = row["game_id"]
            label = f"{home} vs {away} ({date_str})"

            session = SessionLocal()
            try:
                if already_ingested(session, date_str, home, away):
                    counts["skipped"] += 1
                    continue
            finally:
                session.close()

            fixture_id = find_api_fixture_id(home, away, date_str, all_api_fixtures)
            if fixture_id is None:
                print(f"{label} - failed: no matching API-Football fixture found for this team name/date")
                counts["failed"] += 1
                continue

            try:
                match_id, players = ingest_match(
                    fbref_league=FBREF_LEAGUE,
                    fbref_season=FBREF_SEASON,
                    fbref_match_id=game_id,
                    api_fixture_id=fixture_id,
                    fbref_reader=fbref,
                )
                events = ingest_match_events(db_match_id=match_id, api_fixture_id=fixture_id)
                print(f"{label} - success ({len(players)} players, {len(events)} events)")
                counts["success"] += 1
                time.sleep(random.uniform(10, 12))
            except (RuntimeError, ConnectionError):
                # Same stop condition as ingest_season.py: a zero-player match (likely a new
                # team-name mismatch) or an exhausted download retry loop (possible CAPTCHA)
                # both need human review, not a silent skip-and-continue.
                raise
            except Exception as e:
                print(f"{label} - failed: {type(e).__name__}: {e}")
                counts["failed"] += 1
                time.sleep(random.uniform(10, 12))

        print(f"Daily ingestion done: {counts}")
        return counts
    finally:
        try:
            fbref._driver.quit()
        except Exception:
            pass


if __name__ == "__main__":
    run_daily()
