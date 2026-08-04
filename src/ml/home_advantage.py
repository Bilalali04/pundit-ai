import pandas as pd

from src.ml.head_to_head import FULL_HISTORY_PATH

# Neutral fallback when a team has no prior home or away matches to average (e.g. a team's
# actual first-ever Premier League fixture) - 0 means "no known differential", not "no
# advantage at all", which is why it's paired with an explicit home_advantage_no_history flag.
NEUTRAL_GOAL_DIFF = 0.0


def compute_home_advantage_features(matches: pd.DataFrame, history_path: str = FULL_HISTORY_PATH, lookback: int = 10) -> pd.DataFrame:
    """For each row in `matches` (needs HomeTeam, MatchDate), compute the CURRENT home team's
    own home-advantage: how many more goals they've scored in their last `lookback` home
    matches than in their last `lookback` away matches, strictly before this match's date.

    Deliberately a differential (avg goals at home - avg goals away), not just a home win
    rate - a plain win rate would likely just re-derive overall team strength, which Elo
    already captures. This isolates whether THIS team specifically benefits from playing at
    home (some teams have a much bigger home/away gap than others), which Elo (venue-agnostic)
    and head-to-head (specific-opponent) don't directly capture.

    Uses the full Premier League match history (2000-present, see db/training_data/README.md)
    the same way head_to_head.py does, so early rows in a truncated training slice still get
    a real recency-window average instead of an artificially thin one.

    A larger lookback (10) than head_to_head.py's (5) is used deliberately - this is a
    per-venue scoring-rate average, not a specific-pairing average, so a larger sample
    reduces noise from any single fixture.

    Adds two columns:
    - home_advantage_goal_diff: avg goals scored at home - avg goals scored away, for the
      current home team, each averaged over up to `lookback` prior matches. Neutral 0.0 if
      either side has zero prior matches to average (e.g. a team's actual PL debut).
    - home_advantage_no_history: 1 if EITHER side (home matches or away matches) had zero
      prior data, 0 otherwise - explicit flag, same principle as head_to_head.py's.
    """
    history = pd.read_csv(history_path)
    history["MatchDate"] = pd.to_datetime(history["MatchDate"])

    matches = matches.copy()
    matches["MatchDate"] = pd.to_datetime(matches["MatchDate"])

    diffs = []
    no_history_flags = []

    for team, date in zip(matches["HomeTeam"], matches["MatchDate"]):
        prior_home = (
            history[(history["MatchDate"] < date) & (history["HomeTeam"] == team)]
            .sort_values("MatchDate", ascending=False)
            .head(lookback)
        )
        prior_away = (
            history[(history["MatchDate"] < date) & (history["AwayTeam"] == team)]
            .sort_values("MatchDate", ascending=False)
            .head(lookback)
        )

        if prior_home.empty or prior_away.empty:
            diffs.append(NEUTRAL_GOAL_DIFF)
            no_history_flags.append(1)
            continue

        avg_goals_home = prior_home["FTHome"].mean()
        avg_goals_away = prior_away["FTAway"].mean()
        diffs.append(avg_goals_home - avg_goals_away)
        no_history_flags.append(0)

    matches["home_advantage_goal_diff"] = diffs
    matches["home_advantage_no_history"] = no_history_flags
    return matches
