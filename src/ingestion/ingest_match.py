import os

import requests
import soccerdata as sd
from dotenv import load_dotenv
from sqlalchemy import select

from src.db.connection import SessionLocal
from src.db.models import League, Match, Player, PlayerMatchStats, Team
from src.scraping.name_matching import filter_active_players, match_player_name

load_dotenv()

API_BASE = "https://v3.football.api-sports.io"


def get_or_create_league(session, name, country):
    league = session.scalar(select(League).where(League.name == name))
    if league is None:
        league = League(name=name, country=country, tier=1)
        session.add(league)
        session.flush()
    return league


def get_or_create_team(session, name, league_id):
    team = session.scalar(select(Team).where(Team.name == name, Team.league_id == league_id))
    if team is None:
        team = Team(name=name, league_id=league_id)
        session.add(team)
        session.flush()
    return team


def get_or_create_player(session, name, team_id, position=None, nationality=None):
    player = session.scalar(select(Player).where(Player.name == name, Player.team_id == team_id))
    if player is None:
        player = Player(name=name, team_id=team_id, position=position, nationality=nationality)
        session.add(player)
        session.flush()
    return player


def get_or_create_match(session, league_id, match_date, home_team, away_team, home_score, away_score, home_xg, away_xg, season, source):
    match = session.scalar(
        select(Match).where(
            Match.match_date == match_date,
            Match.home_team_id == home_team.team_id,
            Match.away_team_id == away_team.team_id,
        )
    )
    if match is None:
        match = Match(
            league_id=league_id,
            match_date=match_date,
            home_team_id=home_team.team_id,
            away_team_id=away_team.team_id,
            home_score=home_score,
            away_score=away_score,
            home_xg=home_xg,
            away_xg=away_xg,
            season=season,
            source=source,
        )
        session.add(match)
        session.flush()
    return match


def get_or_create_player_match_stats(session, match_id, player_id, **fields):
    stats = session.scalar(
        select(PlayerMatchStats).where(
            PlayerMatchStats.match_id == match_id,
            PlayerMatchStats.player_id == player_id,
        )
    )
    if stats is None:
        stats = PlayerMatchStats(match_id=match_id, player_id=player_id, **fields)
        session.add(stats)
    else:
        for key, value in fields.items():
            setattr(stats, key, value)
    session.flush()
    return stats


def ingest_match(fbref_league, fbref_season, fbref_match_id, api_fixture_id):
    headers = {"x-apisports-key": os.getenv("API_FOOTBALL_KEY")}

    # --- pull FBref data: goals, assists, cards, minutes, tackles-won, interceptions, crosses ---
    fbref = sd.FBref(leagues=fbref_league, seasons=fbref_season)
    fbref_stats = fbref.read_player_match_stats(stat_type="summary", match_id=fbref_match_id)

    # --- pull API-Football data: fixture info, team-level xG, player passes/duels/shots/dribbles ---
    fixture_resp = requests.get(f"{API_BASE}/fixtures", headers=headers, params={"id": api_fixture_id}, timeout=20)
    fixture = fixture_resp.json()["response"][0]

    stats_resp = requests.get(f"{API_BASE}/fixtures/statistics", headers=headers, params={"fixture": api_fixture_id}, timeout=20)
    team_xg = {}
    for team_block in stats_resp.json()["response"]:
        for stat in team_block["statistics"]:
            if stat["type"] == "expected_goals" and stat["value"] is not None:
                team_xg[team_block["team"]["name"]] = float(stat["value"])

    players_resp = requests.get(f"{API_BASE}/fixtures/players", headers=headers, params={"fixture": api_fixture_id}, timeout=20)
    all_api_players = [p for team in players_resp.json()["response"] for p in team["players"]]
    active_api_players = filter_active_players(all_api_players)

    session = SessionLocal()
    try:
        league = get_or_create_league(session, fixture["league"]["name"], fixture["league"]["country"])

        home_name = fixture["teams"]["home"]["name"]
        away_name = fixture["teams"]["away"]["name"]
        home_team = get_or_create_team(session, home_name, league.league_id)
        away_team = get_or_create_team(session, away_name, league.league_id)

        match_date = fixture["fixture"]["date"][:10]
        match = get_or_create_match(
            session,
            league_id=league.league_id,
            match_date=match_date,
            home_team=home_team,
            away_team=away_team,
            home_score=fixture["goals"]["home"],
            away_score=fixture["goals"]["away"],
            home_xg=team_xg.get(home_name),
            away_xg=team_xg.get(away_name),
            season=fbref_season,
            source="fbref+api-football",
        )

        team_by_name = {home_name: home_team, away_name: away_team}
        inserted_players = []

        for idx, row in fbref_stats.iterrows():
            fbref_name = idx[-1]
            fbref_team_name = idx[-2]
            team = team_by_name.get(fbref_team_name)
            if team is None:
                continue

            api_name = match_player_name(fbref_name, active_api_players, match_id=fbref_match_id)
            api_stats = active_api_players[api_name]["statistics"][0] if api_name else None

            player = get_or_create_player(
                session,
                name=fbref_name,
                team_id=team.team_id,
                position=row[("pos", "")],
                nationality=row[("nation", "")],
            )

            fields = {
                "minutes_played": row[("min", "")],
                "goals": row[("Performance", "Gls")],
                "assists": row[("Performance", "Ast")],
                "tackles_won": row[("Performance", "TklW")],
                "interceptions": row[("Performance", "Int")],
                "yellow_cards": row[("Performance", "CrdY")],
                "red_cards": row[("Performance", "CrdR")],
            }
            # crosses has no dedicated schema column; captured via FBref's Crs -> not in schema, skipped

            if api_stats is not None:
                fields.update(
                    {
                        "tackles": api_stats["tackles"]["total"],
                        "passes_total": api_stats["passes"]["total"],
                        "passes_completed": api_stats["passes"]["accuracy"],
                        "key_passes": api_stats["passes"]["key"],
                        "duels_total": api_stats["duels"]["total"],
                        "duels_won": api_stats["duels"]["won"],
                        "shots_total": api_stats["shots"]["total"],
                        "shots_on_target": api_stats["shots"]["on"],
                        "dribbles_attempted": api_stats["dribbles"]["attempts"],
                        "dribbles_successful": api_stats["dribbles"]["success"],
                        "rating": api_stats["games"]["rating"],
                    }
                )

            get_or_create_player_match_stats(session, match.match_id, player.player_id, **fields)
            inserted_players.append(fbref_name)

        session.commit()
        return match.match_id, inserted_players
    finally:
        session.close()


if __name__ == "__main__":
    match_id, players = ingest_match(
        fbref_league="ENG-Premier League",
        fbref_season="2025-2026",
        fbref_match_id="7e3c19a1",
        api_fixture_id=1379295,
    )
    print(f"Ingested match_id={match_id}, {len(players)} players")
