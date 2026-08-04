import pandas as pd

from src.ml.head_to_head import compute_h2h_features
from src.ml.home_advantage import compute_home_advantage_features

FEATURE_COLUMNS = [
    "HomeElo",
    "AwayElo",
    "elo_diff",
    "Form3Home",
    "Form3Away",
    "Form5Home",
    "Form5Away",
    "h2h_home_points_avg",
    "h2h_no_history",
    "home_advantage_goal_diff",
    "home_advantage_no_history",
]
TARGET_COLUMN = "FTResult"

TRAINING_DATA_PATH = "db/training_data/PL_last8seasons.csv"


def load_feature_set(csv_path: str = TRAINING_DATA_PATH, keep_date: bool = False) -> pd.DataFrame:
    """Load the V2 match-outcome feature set from the offline training CSV (see
    db/training_data/README.md - not the live database).

    Selects HomeElo, AwayElo, Form3Home/Away, Form5Home/Away, the computed elo_diff, the
    computed head-to-head features (see head_to_head.py), the computed home-advantage
    features (see home_advantage.py), and the FTResult target (H/D/A). Drops rows missing
    any of these - see the missing-value report this was validated against: only 2 of 3040
    rows (0.066%) were affected, both from a single isolated ClubElo snapshot gap for
    Nott'm Forest in late Dec 2024, not a systemic coverage problem worth imputing around.
    (Neither the h2h nor home-advantage features ever introduce new missing values
    themselves - a match with no prior data gets a neutral imputed value plus an explicit
    flag, not NaN.)

    keep_date: also include MatchDate in the result - needed for a time-based train/test
    split (see train_test_split.py), not for training itself.
    """
    raw = pd.read_csv(csv_path)
    raw["elo_diff"] = raw["HomeElo"] - raw["AwayElo"]
    raw = compute_h2h_features(raw)
    raw = compute_home_advantage_features(raw)

    columns = FEATURE_COLUMNS + [TARGET_COLUMN]
    if keep_date:
        columns = ["MatchDate"] + columns

    df = raw[columns].dropna(subset=FEATURE_COLUMNS + [TARGET_COLUMN])
    return df.reset_index(drop=True)


if __name__ == "__main__":
    raw = pd.read_csv(TRAINING_DATA_PATH)
    raw["elo_diff"] = raw["HomeElo"] - raw["AwayElo"]
    raw = compute_h2h_features(raw)
    raw = compute_home_advantage_features(raw)

    cols = FEATURE_COLUMNS + [TARGET_COLUMN]
    print(f"Raw rows: {len(raw)}")
    print()
    print("Missing values per column:")
    print(raw[cols].isna().sum())
    print()
    print("h2h coverage - number of prior meetings actually found (0-5):")
    print(raw["h2h_matches_found"].value_counts().sort_index())
    print(f"Matches with zero prior history: {(raw['h2h_matches_found'] == 0).sum()} / {len(raw)}")
    print()
    print(f"Home-advantage matches with zero prior history: {raw['home_advantage_no_history'].sum()} / {len(raw)}")
    print()

    df = load_feature_set()
    print(f"Feature set shape after dropping incomplete rows: {df.shape}")
    print(f"Rows dropped: {len(raw) - len(df)}")
    print()
    print("Sample rows:")
    print(df.head(10).to_string(index=False))
    print()
    print("Target distribution:")
    print(df[TARGET_COLUMN].value_counts())
