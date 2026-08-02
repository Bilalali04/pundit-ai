from sqlalchemy import or_, select

from src.db.connection import SessionLocal
from src.db.models import Match, MatchEvent, Player, PlayerMatchStats, Team
from src.scraping.name_matching import TEAM_ALIASES, normalize_name


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


def get_position_expectations(position: str) -> dict | None:
    """Get average per-match stats across all players listed at a given position this season,
    to use as a baseline for what's normal for that position (e.g. a CB's tackles/interceptions
    vs a FW's goals/assists).

    Positions with multiple listed roles (e.g. "FW,MF") are treated as their own distinct group,
    not split across "FW" and "MF" - an exact match on the position string as stored.

    Args:
        position: The position code to look up, e.g. "CB", "FW", "CM", or a compound value like
            "FW,MF" exactly as stored on the player.
    """
    session = SessionLocal()
    try:
        results = session.execute(
            select(PlayerMatchStats, Player)
            .join(Player, PlayerMatchStats.player_id == Player.player_id)
            .where(Player.position == position)
        ).all()

        if not results:
            return None

        rows = [r[0] for r in results]
        player_count = len({r[1].player_id for r in results})
        matches_played = len(rows)

        avg_goals_per_match = sum(r.goals or 0 for r in rows) / matches_played
        avg_assists_per_match = sum(r.assists or 0 for r in rows) / matches_played
        avg_tackles_won_per_match = sum(r.tackles_won or 0 for r in rows) / matches_played
        avg_interceptions_per_match = sum(r.interceptions or 0 for r in rows) / matches_played

        total_duels_won = sum(r.duels_won or 0 for r in rows)
        total_duels_total = sum(r.duels_total or 0 for r in rows)
        duels_won_rate = total_duels_won / total_duels_total if total_duels_total else None

        total_passes_completed = sum(r.passes_completed or 0 for r in rows)
        total_passes_total = sum(r.passes_total or 0 for r in rows)
        pass_completion_rate = total_passes_completed / total_passes_total if total_passes_total else None

        return {
            "position": position,
            "player_count": player_count,
            "matches_sampled": matches_played,
            "avg_goals_per_match": round(avg_goals_per_match, 3),
            "avg_assists_per_match": round(avg_assists_per_match, 3),
            "avg_tackles_won_per_match": round(avg_tackles_won_per_match, 2),
            "avg_interceptions_per_match": round(avg_interceptions_per_match, 2),
            "duels_won_rate": round(duels_won_rate, 3) if duels_won_rate is not None else None,
            "pass_completion_rate": round(pass_completion_rate, 3) if pass_completion_rate is not None else None,
        }
    finally:
        session.close()


def _resolve_team(session, name: str) -> Team | None:
    """Resolve a team name (possibly shorthand, e.g. "City" or "Man Utd") to a single Team row.

    Returns None if no team matches, or if more than one team matches ambiguously (e.g. a
    substring like "United" that could mean several clubs) - callers should treat both cases
    as "couldn't resolve" rather than guessing.
    """
    all_teams = session.scalars(select(Team)).all()
    normalized_input = normalize_name(name)

    for team in all_teams:
        if normalize_name(team.name) == normalized_input:
            return team

    aliased = TEAM_ALIASES.get(name) or next((k for k, v in TEAM_ALIASES.items() if v == name), None)
    if aliased:
        for team in all_teams:
            if normalize_name(team.name) == normalize_name(aliased):
                return team

    candidates = [
        team
        for team in all_teams
        if normalized_input in normalize_name(team.name) or normalize_name(team.name) in normalized_input
    ]
    if len(candidates) == 1:
        return candidates[0]

    return None


def _summarize_match(session, m: Match) -> dict:
    home = session.get(Team, m.home_team_id)
    away = session.get(Team, m.away_team_id)
    return {
        "match_id": m.match_id,
        "date": m.match_date.isoformat(),
        "home_team": home.name,
        "away_team": away.name,
        "score": f"{m.home_score}-{m.away_score}" if m.home_score is not None else None,
    }


def find_match(home_team: str, away_team: str) -> dict:
    """Find the match_id(s) for a fixture between two named teams this season, regardless of
    which one actually played at home - use this when the user names two teams but not a
    match_id.

    Team names can be shorthand or variants (e.g. "City", "Man Utd", "Spurs") - fuzzy matching
    is applied. If the two teams played each other more than once this season (home and away
    fixtures), all candidates are returned with dates so the correct one can be confirmed
    before looking up stats or events.

    Args:
        home_team: One of the two team names, e.g. "Manchester City".
        away_team: The other team name, e.g. "Arsenal".
    """
    session = SessionLocal()
    try:
        team_a = _resolve_team(session, home_team)
        team_b = _resolve_team(session, away_team)

        if team_a is None or team_b is None:
            unresolved = [name for name, team in [(home_team, team_a), (away_team, team_b)] if team is None]
            return {
                "status": "team_not_found",
                "message": f"Could not resolve team name(s): {', '.join(unresolved)}.",
            }

        matches = session.scalars(
            select(Match)
            .where(
                or_(
                    (Match.home_team_id == team_a.team_id) & (Match.away_team_id == team_b.team_id),
                    (Match.home_team_id == team_b.team_id) & (Match.away_team_id == team_a.team_id),
                )
            )
            .order_by(Match.match_date)
        ).all()

        if not matches:
            return {
                "status": "no_match_found",
                "message": f"No match found between {team_a.name} and {team_b.name} this season.",
            }

        if len(matches) == 1:
            return {"status": "found", **_summarize_match(session, matches[0])}

        return {
            "status": "multiple_matches",
            "message": (
                f"{team_a.name} and {team_b.name} played each other {len(matches)} times this "
                "season - specify which match_id to use."
            ),
            "candidates": [_summarize_match(session, m) for m in matches],
        }
    finally:
        session.close()


def get_team_matches(team_name: str, limit: int | None = None) -> dict:
    """Get a team's match_ids for the season, ordered by date - use this when a question is
    about a team as a whole (e.g. their disciplinary record, form, or results) rather than a
    specific opponent, so you have real match_ids to check events/stats across instead of
    guessing one.

    Args:
        team_name: The team name, possibly shorthand (e.g. "City", "Spurs") - fuzzy matching
            is applied, same as find_match.
        limit: Optional cap on how many matches to return (earliest first). Omit for all
            matches this season.
    """
    session = SessionLocal()
    try:
        team = _resolve_team(session, team_name)
        if team is None:
            return {"status": "team_not_found", "message": f"Could not resolve team name: {team_name}."}

        query = (
            select(Match)
            .where(or_(Match.home_team_id == team.team_id, Match.away_team_id == team.team_id))
            .order_by(Match.match_date)
        )
        if limit:
            query = query.limit(limit)
        matches = session.scalars(query).all()

        if not matches:
            return {"status": "no_matches_found", "message": f"No matches found for {team.name} this season."}

        return {
            "status": "found",
            "team": team.name,
            "match_count": len(matches),
            "matches": [_summarize_match(session, m) for m in matches],
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
