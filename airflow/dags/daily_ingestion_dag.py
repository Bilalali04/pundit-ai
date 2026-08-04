"""Daily Premier League ingestion.

Finds matches that have been played but don't yet have match_events ingested, and ingests
events for each - see src/ingestion/ingest_daily.py for the actual logic. Deliberately
API-Football-only: FBref's player-stats scraping can't run reliably from this environment
(hits FBref's CAPTCHA gate every time on this Docker-hosted browser session), so that piece
is left to be run manually from the venv via ingest_season.py instead.

The heavy imports (sqlalchemy, requests, etc.) are deferred to inside the task callable
rather than module scope, so DAG parsing stays fast and doesn't require those packages to be
installed just to list this DAG - only actually running the task does.
"""

from __future__ import annotations

import sys
from datetime import datetime

from airflow.sdk import dag, task

# src/ is mounted into the container read-only (see airflow/docker-compose.yaml) so the
# project's own ingestion/db/scraping code can be imported here, the same modules the venv
# uses - but it isn't on PYTHONPATH inside every execution context by default, so add it
# explicitly. (PYTHONPATH is also set via docker-compose.yaml; this is a defensive fallback.)
PUNDIT_AI_ROOT = "/opt/airflow/pundit-ai"
if PUNDIT_AI_ROOT not in sys.path:
    sys.path.insert(0, PUNDIT_AI_ROOT)


@dag(
    dag_id="daily_premier_league_ingestion",
    description="Find and ingest match events for any newly-played Premier League matches (API-Football only, no FBref)",
    schedule="0 6 * * *",
    start_date=datetime(2025, 8, 1),
    catchup=False,
    tags=["pundit-ai", "ingestion"],
)
def daily_premier_league_ingestion():
    @task
    def run_daily_ingestion():
        from src.ingestion.ingest_daily import run_daily

        return run_daily()

    run_daily_ingestion()


daily_premier_league_ingestion()
