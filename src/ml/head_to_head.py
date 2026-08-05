import pandas as pd

FULL_HISTORY_PATH = "db/training_data/PL_full_history.csv"

# Midpoint of the 0-3 points-per-meeting scale (W=3/D=1/L=0), used when there's no prior
# meeting to average - not 0, which would misleadingly read as "this team always lost".
NEUTRAL_H2H_POINTS = 1.5


def points_for(result: str, side: str) -> int:
    """Points earned by the given side ('home' or 'away') of a historical match."""
    if result == "D":
        return 1
    if (result == "H" and side == "home") or (result == "A" and side == "away"):
        return 3
    return 0


def compute_h2h_features(matches: pd.DataFrame, history_path: str = FULL_HISTORY_PATH, lookback: int = 5) -> pd.DataFrame:
    """For each row in `matches` (needs HomeTeam, AwayTeam, MatchDate), compute the current
    home team's head-to-head record against the current away team over their last
    `lookback` meetings (either venue) strictly before this match's date.

    Uses the full Premier League match history (2000-present, see db/training_data/README.md)
    as the source of prior meetings, not just whatever date range `matches` itself covers -
    otherwise early rows in a truncated slice (e.g. the first season of an 8-season training
    set) would be artificially flagged as first-ever meetings even for fixtures with a long
    real history just outside that window.

    Adds three columns:
    - h2h_home_points_avg: average points (0-3 scale, W=3/D=1/L=0) the CURRENT home team
      earned across however many prior meetings were found (up to `lookback`). Neutral
      1.5 when there were zero prior meetings.
    - h2h_matches_found: how many prior meetings were actually used (0 to `lookback`) - not
      fed to the model, reported separately so h2h coverage can be checked directly (e.g.
      how many rows had fewer than 5, or zero).
    - h2h_no_history: 1 if there were zero prior meetings (e.g. a newly-promoted team's
      first-ever fixture against this opponent), 0 otherwise - an explicit flag, rather than
      letting the neutral-imputed h2h_home_points_avg silently look like real signal.
    """
    history = pd.read_csv(history_path)
    history["MatchDate"] = pd.to_datetime(history["MatchDate"])

    matches = matches.copy()
    matches["MatchDate"] = pd.to_datetime(matches["MatchDate"])

    h2h_avg = []
    h2h_count = []

    for home, away, date in zip(matches["HomeTeam"], matches["AwayTeam"], matches["MatchDate"]):
        prior = (
            history[
                (history["MatchDate"] < date)
                & (
                    ((history["HomeTeam"] == home) & (history["AwayTeam"] == away))
                    | ((history["HomeTeam"] == away) & (history["AwayTeam"] == home))
                )
            ]
            .sort_values("MatchDate", ascending=False)
            .head(lookback)
        )

        if prior.empty:
            h2h_avg.append(NEUTRAL_H2H_POINTS)
            h2h_count.append(0)
            continue

        points = [
            points_for(result, "home" if h == home else "away")
            for h, result in zip(prior["HomeTeam"], prior["FTResult"])
        ]
        h2h_avg.append(sum(points) / len(points))
        h2h_count.append(len(points))

    matches["h2h_home_points_avg"] = h2h_avg
    matches["h2h_matches_found"] = h2h_count
    matches["h2h_no_history"] = (matches["h2h_matches_found"] == 0).astype(int)
    return matches
