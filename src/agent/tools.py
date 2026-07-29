from sqlalchemy import select

from src.db.connection import SessionLocal
from src.db.models import Player, PlayerMatchStats


def get_player_match_stats(player_name: str, match_id: int) -> dict | None:
    """Get a player's recorded stats for one specific match.

    Args:
        player_name: The player's full name, e.g. "Declan Rice".
        match_id: The database match_id to look up stats for.
    """
    session = SessionLocal()
    try:
        stats = session.scalar(
            select(PlayerMatchStats)
            .join(Player, PlayerMatchStats.player_id == Player.player_id)
            .where(Player.name == player_name, PlayerMatchStats.match_id == match_id)
        )
        if stats is None:
            return None

        return {
            "player_name": player_name,
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
