from sqlalchemy import select

from src.db.connection import SessionLocal
from src.db.models import MatchEvent, Player, PlayerMatchStats, Team


def get_player_match_stats(player_name: str, match_id: int) -> dict | None:
    """Get a player's recorded stats for one specific match.

    Args:
        player_name: The player's full name, e.g. "Declan Rice".
        match_id: The database match_id to look up stats for.
    """
    session = SessionLocal()
    try:
        result = session.execute(
            select(PlayerMatchStats, Player)
            .join(Player, PlayerMatchStats.player_id == Player.player_id)
            .where(Player.name == player_name, PlayerMatchStats.match_id == match_id)
        ).first()
        if result is None:
            return None
        stats, player = result

        return {
            "player_name": player_name,
            "position": player.position,
            "match_id": stats.match_id,
            "minutes_played": stats.minutes_played,
            "goals": stats.goals,
            "assists": stats.assists,
            "tackles": stats.tackles,
            "tackles_won": stats.tackles_won,
            "interceptions": stats.interceptions,
            "crosses": stats.crosses,
            "passes_total": stats.passes_total,
            "passes_completed": stats.passes_completed,
            "key_passes": stats.key_passes,
            "duels_total": stats.duels_total,
            "duels_won": stats.duels_won,
            "shots_total": stats.shots_total,
            "shots_on_target": stats.shots_on_target,
            "dribbles_attempted": stats.dribbles_attempted,
            "dribbles_successful": stats.dribbles_successful,
            "yellow_cards": stats.yellow_cards,
            "red_cards": stats.red_cards,
            "rating": float(stats.rating) if stats.rating is not None else None,
        }
    finally:
        session.close()


def get_player_season_baseline(player_name: str) -> dict | None:
    """Get a player's aggregate/average stats across all matches ingested so far this season.

    Args:
        player_name: The player's full name, e.g. "Erling Haaland".
    """
    session = SessionLocal()
    try:
        results = session.execute(
            select(PlayerMatchStats, Player)
            .join(Player, PlayerMatchStats.player_id == Player.player_id)
            .where(Player.name == player_name)
        ).all()

        if not results:
            return None

        rows = [r[0] for r in results]
        position = results[0][1].position

        matches_played = len(rows)
        total_minutes = sum(r.minutes_played or 0 for r in rows)
        total_goals = sum(r.goals or 0 for r in rows)
        total_assists = sum(r.assists or 0 for r in rows)
        total_yellow_cards = sum(r.yellow_cards or 0 for r in rows)
        total_red_cards = sum(r.red_cards or 0 for r in rows)

        avg_tackles_won_per_match = sum(r.tackles_won or 0 for r in rows) / matches_played
        avg_interceptions_per_match = sum(r.interceptions or 0 for r in rows) / matches_played

        total_duels_won = sum(r.duels_won or 0 for r in rows)
        total_duels_total = sum(r.duels_total or 0 for r in rows)
        duels_won_rate = total_duels_won / total_duels_total if total_duels_total else None

        total_passes_completed = sum(r.passes_completed or 0 for r in rows)
        total_passes_total = sum(r.passes_total or 0 for r in rows)
        pass_completion_rate = total_passes_completed / total_passes_total if total_passes_total else None

        small_sample_size = matches_played < 5

        return {
            "player_name": player_name,
            "position": position,
            "matches_played": matches_played,
            "total_minutes": total_minutes,
            "total_goals": total_goals,
            "total_assists": total_assists,
            "avg_tackles_won_per_match": round(avg_tackles_won_per_match, 2),
            "avg_interceptions_per_match": round(avg_interceptions_per_match, 2),
            "duels_won_rate": round(duels_won_rate, 3) if duels_won_rate is not None else None,
            "pass_completion_rate": round(pass_completion_rate, 3) if pass_completion_rate is not None else None,
            "total_yellow_cards": total_yellow_cards,
            "total_red_cards": total_red_cards,
            "small_sample_size": small_sample_size,
            "note": (
                f"Only {matches_played} match(es) played this season - averages may not be "
                "a reliable baseline."
                if small_sample_size
                else None
            ),
        }
    finally:
        session.close()


def get_match_events(match_id: int) -> list[dict]:
    """Get all recorded events (goals, cards, substitutions) for one match, ordered by minute.

    Args:
        match_id: The database match_id to look up events for.
    """
    session = SessionLocal()
    try:
        rows = session.execute(
            select(MatchEvent, Player, Team)
            .outerjoin(Player, MatchEvent.player_id == Player.player_id)
            .outerjoin(Team, Player.team_id == Team.team_id)
            .where(MatchEvent.match_id == match_id)
            .order_by(MatchEvent.minute)
        ).all()

        return [
            {
                "event_type": event.event_type,
                "minute": event.minute,
                "player_name": player.name if player else None,
                "team": team.name if team else None,
                "detail": event.detail,
            }
            for event, player, team in rows
        ]
    finally:
        session.close()
