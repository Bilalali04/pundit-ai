import pandas as pd

from src.ml.prepare_features import TARGET_COLUMN, load_feature_set


def _season_label(date: pd.Timestamp) -> str:
    # Premier League seasons run Aug-May, so a July+ date belongs to the season starting
    # that year; anything Jan-Jun belongs to the season that started the previous year.
    start_year = date.year if date.month >= 7 else date.year - 1
    return f"{start_year}-{start_year + 1}"


def time_based_split(train_seasons: int = 6, **load_kwargs):
    """Split the feature set into train/test by season rather than a random shuffle.

    Football form and Elo are time-dependent - a random split would let matches from,
    say, March 2023 train on data that includes a team's Elo from November 2023, leaking
    future information into training. Splitting by season keeps all of a team's future form
    entirely out of the training set.

    Trains on the earliest `train_seasons` seasons found in the data, tests on the rest.
    """
    df = load_feature_set(keep_date=True, **load_kwargs)
    df["MatchDate"] = pd.to_datetime(df["MatchDate"])
    df["season"] = df["MatchDate"].apply(_season_label)

    seasons_in_order = sorted(df["season"].unique(), key=lambda s: int(s[:4]))
    train_season_labels = seasons_in_order[:train_seasons]
    test_season_labels = seasons_in_order[train_seasons:]

    train_df = df[df["season"].isin(train_season_labels)].drop(columns=["MatchDate", "season"]).reset_index(drop=True)
    test_df = df[df["season"].isin(test_season_labels)].drop(columns=["MatchDate", "season"]).reset_index(drop=True)

    return train_df, test_df, train_season_labels, test_season_labels


if __name__ == "__main__":
    train_df, test_df, train_seasons, test_seasons = time_based_split()

    print(f"Train seasons ({len(train_seasons)}): {train_seasons}")
    print(f"Test seasons ({len(test_seasons)}): {test_seasons}")
    print()
    print(f"Train shape: {train_df.shape}")
    print(f"Test shape: {test_df.shape}")
    print()
    print("Train FTResult distribution:")
    print(train_df[TARGET_COLUMN].value_counts())
    print(train_df[TARGET_COLUMN].value_counts(normalize=True).round(3))
    print()
    print("Test FTResult distribution:")
    print(test_df[TARGET_COLUMN].value_counts())
    print(test_df[TARGET_COLUMN].value_counts(normalize=True).round(3))
