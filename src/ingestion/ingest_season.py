import os
import random
import time

import requests
import soccerdata as sd
from dotenv import load_dotenv
from sqlalchemy import select

from src.db.connection import SessionLocal
from src.db.models import League, Match, PlayerMatchStats, Team
from src.ingestion.ingest_match import ingest_match
from src.scraping.name_matching import match_team_name

load_dotenv()

API_BASE = "https://v3.football.api-sports.io"
LEAGUE_ID = 39  # Premier League, API-Football
SEASON_YEAR = 2025
FBREF_LEAGUE = "ENG-Premier League"
FBREF_SEASON = "2025-2026"


def already_ingested(session, match_date: str, home_fbref: str, away_fbref: str) -> bool:
    existing_team_names = set(session.scalars(select(Team.name)))
    if not existing_team_names:
        return False

    home_resolved = match_team_name(home_fbref, existing_team_names)
    away_resolved = match_team_name(away_fbref, existing_team_names)
    if not home_resolved or not away_resolved:
        return False

    league = session.scalar(select(League).where(League.name == "Premier League"))
    if league is None:
        return False

    home_team = session.scalar(select(Team).where(Team.name == home_resolved, Team.league_id == league.league_id))
    away_team = session.scalar(select(Team).where(Team.name == away_resolved, Team.league_id == league.league_id))
    if home_team is None or away_team is None:
        return False

    match = session.scalar(
        select(Match).where(
            Match.match_date == match_date,
            Match.home_team_id == home_team.team_id,
            Match.away_team_id == away_team.team_id,
        )
    )
    if match is None:
        return False

    has_stats = session.scalar(select(PlayerMatchStats).where(PlayerMatchStats.match_id == match.match_id).limit(1))
    return has_stats is not None


def find_api_fixture_id(home_fbref: str, away_fbref: str, date_str: str, all_api_fixtures: list) -> int | None:
    all_api_team_names = set()
    for f in all_api_fixtures:
        all_api_team_names.add(f["teams"]["home"]["name"])
        all_api_team_names.add(f["teams"]["away"]["name"])

    home_resolved = match_team_name(home_fbref, all_api_team_names)
    away_resolved = match_team_name(away_fbref, all_api_team_names)
    if not home_resolved or not away_resolved:
        return None

    for f in all_api_fixtures:
        if (
            f["teams"]["home"]["name"] == home_resolved
            and f["teams"]["away"]["name"] == away_resolved
            and f["fixture"]["date"][:10] == date_str
        ):
            return f["fixture"]["id"]
    return None


def run(limit: int | None = None):
    headers = {"x-apisports-key": os.getenv("API_FOOTBALL_KEY")}

    # One FBref reader (one browser session) for the whole run, reused across every match,
    # instead of launching a new browser per match. Always closed when the run ends, whether
    # it finishes normally, hits the zero-player RuntimeError, or fails some other way.
    # headless=True: soccerdata's solve_captcha() skips its real GUI-automation solve
    # attempts entirely in headless mode (just waits, doesn't try to bypass) - there is
    # no dedicated config flag for this in soccerdata/seleniumbase, this is the only lever.
    fbref = sd.FBref(leagues=FBREF_LEAGUE, seasons=FBREF_SEASON, headless=True)
    try:
        schedule = fbref.read_schedule().reset_index()

        fixtures_resp = requests.get(
            f"{API_BASE}/fixtures", headers=headers, params={"league": LEAGUE_ID, "season": SEASON_YEAR}, timeout=30
        )
        all_api_fixtures = fixtures_resp.json()["response"]

        all_rows = schedule.to_dict("records")
        total = len(all_rows)
        rows_to_process = all_rows[:limit] if limit else all_rows

        counts = {"success": 0, "skipped": 0, "failed": 0}

        for i, row in enumerate(rows_to_process, 1):
            home = row["home_team"]
            away = row["away_team"]
            date = row["date"]
            date_str = date.strftime("%Y-%m-%d") if hasattr(date, "strftime") else str(date)[:10]
            game_id = row["game_id"]
            label = f"Match {i}/{total}: {home} vs {away}"

            session = SessionLocal()
            try:
                if already_ingested(session, date_str, home, away):
                    print(f"{label} - skipped (already in database)")
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
                _, players = ingest_match(
                    fbref_league=FBREF_LEAGUE,
                    fbref_season=FBREF_SEASON,
                    fbref_match_id=game_id,
                    api_fixture_id=fixture_id,
                    fbref_reader=fbref,
                )
                print(f"{label} - success ({len(players)} players)")
                counts["success"] += 1
                time.sleep(random.uniform(5, 6))
            except RuntimeError as e:
                print(f"{label} - STOPPED: {e}")
                raise
            except ConnectionError as e:
                # soccerdata raises a plain ConnectionError when its internal 5-attempt
                # retry loop is exhausted - this is what surfaces after a CAPTCHA it
                # couldn't get past, but the message doesn't confirm CAPTCHA specifically,
                # so treat any such total download failure as a stop condition.
                print(f"{label} - STOPPED (possible CAPTCHA block): {e}")
                raise
            except Exception as e:
                print(f"{label} - failed: {type(e).__name__}: {e}")
                counts["failed"] += 1
                time.sleep(random.uniform(5, 6))

        print()
        print(
            f"Done: {counts['success']} succeeded, {counts['skipped']} skipped, "
            f"{counts['failed']} failed (of {len(rows_to_process)} processed, {total} total in season)"
        )
    finally:
        try:
            fbref._driver.quit()
        except Exception:
            pass


if __name__ == "__main__":
    run()
