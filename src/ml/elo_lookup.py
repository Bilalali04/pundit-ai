import pandas as pd

ELO_RATINGS_PATH = "db/training_data/EloRatings.csv"


def get_latest_elo(team: str, as_of_date, elo_path: str = ELO_RATINGS_PATH) -> float | None:
    """Most recent Elo rating for `team` at or before `as_of_date`, from the twice-monthly
    ClubElo snapshots (see db/training_data/README.md). Returns None if the team has no
    snapshot on or before that date at all (e.g. a club not covered by ClubElo).
    """
    elo = pd.read_csv(elo_path)
    elo["date"] = pd.to_datetime(elo["date"])
    as_of_date = pd.to_datetime(as_of_date)

    matches = elo[(elo["club"] == team) & (elo["date"] <= as_of_date)].sort_values("date", ascending=False)
    if matches.empty:
        return None
    return float(matches.iloc[0]["elo"])
