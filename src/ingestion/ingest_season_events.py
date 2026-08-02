import os
import random
import time

import requests
from dotenv import load_dotenv
from sqlalchemy import select

from src.db.connection import SessionLocal
from src.db.models import Match, MatchEvent, Team
from src.ingestion.ingest_match import ingest_match_events

load_dotenv()

API_BASE = "https://v3.football.api-sports.io"
LEAGUE_ID = 39  # Premier League, API-Football
SEASON_YEAR = 2025


def already_has_events(session, match_id: int) -> bool:
    return session.scalar(select(MatchEvent).where(MatchEvent.match_id == match_id).limit(1)) is not None


def find_api_fixture_id(home_name: str, away_name: str, date_str: str, all_api_fixtures: list) -> int | None:
    # Team.name is already stored in API-Football's own naming convention (it was created
    # from API-Football's fixture data during ingest_match()), so this is a direct match -
    # no alias resolution needed here, unlike matching against FBref's team names.
    for f in all_api_fixtures:
        if (
            f["teams"]["home"]["name"] == home_name
            and f["teams"]["away"]["name"] == away_name
            and f["fixture"]["date"][:10] == date_str
        ):
            return f["fixture"]["id"]
    return None


def run(limit: int | None = None):
    headers = {"x-apisports-key": os.getenv("API_FOOTBALL_KEY")}

    fixtures_resp = requests.get(
        f"{API_BASE}/fixtures", headers=headers, params={"league": LEAGUE_ID, "season": SEASON_YEAR}, timeout=30
    )
    all_api_fixtures = fixtures_resp.json()["response"]

    session = SessionLocal()
    try:
        matches = session.scalars(select(Match).order_by(Match.match_id)).all()
        match_rows = []
        for m in matches:
            home_team = session.get(Team, m.home_team_id)
            away_team = session.get(Team, m.away_team_id)
            match_rows.append(
                {
                    "match_id": m.match_id,
                    "home_name": home_team.name,
                    "away_name": away_team.name,
                    "date_str": m.match_date.strftime("%Y-%m-%d"),
                }
            )
    finally:
        session.close()

    total = len(match_rows)
    rows_to_process = match_rows[:limit] if limit else match_rows

    counts = {"success": 0, "skipped": 0, "failed": 0}

    for i, row in enumerate(rows_to_process, 1):
        label = f"Match {i}/{total}: {row['home_name']} vs {row['away_name']}"

        session = SessionLocal()
        try:
            if already_has_events(session, row["match_id"]):
                print(f"{label} - skipped (already has events)")
                counts["skipped"] += 1
                continue
        finally:
            session.close()

        fixture_id = find_api_fixture_id(row["home_name"], row["away_name"], row["date_str"], all_api_fixtures)
        if fixture_id is None:
            print(f"{label} - failed: no matching API-Football fixture found")
            counts["failed"] += 1
            continue

        try:
            events = ingest_match_events(db_match_id=row["match_id"], api_fixture_id=fixture_id)
            resolved = sum(1 for e in events if e["resolved_player"])
            print(f"{label} - success ({len(events)} events, {resolved} resolved, {len(events) - resolved} unresolved)")
            counts["success"] += 1
        except Exception as e:
            print(f"{label} - failed: {type(e).__name__}: {e}")
            counts["failed"] += 1

        time.sleep(random.uniform(1, 2))

    print()
    print(
        f"Done: {counts['success']} succeeded, {counts['skipped']} skipped, "
        f"{counts['failed']} failed (of {len(rows_to_process)} processed, {total} total matches)"
    )


if __name__ == "__main__":
    run()
