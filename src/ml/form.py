import pandas as pd

from src.ml.head_to_head import FULL_HISTORY_PATH, points_for


def compute_recent_form(team: str, as_of_date, history_path: str = FULL_HISTORY_PATH, lookback: int = 5) -> int:
    """Points gathered by `team` in their last `lookback` matches (any venue) strictly before
    `as_of_date` - same scoring convention (W=3/D=1/L=0) as the training data's own
    Form3Home/Form3Away/Form5Home/Form5Away columns (see db/training_data/README.md), so a
    value computed here is directly comparable to those.

    Returns 0 if there are no prior matches to draw on (e.g. a team's actual PL debut) -
    the same low end of the real 0-9/0-15 scale, not a distinct sentinel, since "no matches
    played yet" and "lost all matches played" are both genuinely 0 points either way.
    """
    history = pd.read_csv(history_path)
    history["MatchDate"] = pd.to_datetime(history["MatchDate"])
    as_of_date = pd.to_datetime(as_of_date)

    prior = (
        history[(history["MatchDate"] < as_of_date) & ((history["HomeTeam"] == team) | (history["AwayTeam"] == team))]
        .sort_values("MatchDate", ascending=False)
        .head(lookback)
    )

    if prior.empty:
        return 0

    return sum(points_for(row.FTResult, "home" if row.HomeTeam == team else "away") for row in prior.itertuples())
