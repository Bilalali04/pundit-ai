import pandas as pd
import shap
from sklearn.utils.class_weight import compute_sample_weight
from xgboost import XGBClassifier

from src.ml.elo_lookup import get_latest_elo
from src.ml.form import compute_recent_form
from src.ml.head_to_head import compute_h2h_features
from src.ml.home_advantage import compute_home_advantage_features
from src.ml.prepare_features import FEATURE_COLUMNS, TARGET_COLUMN
from src.ml.train_baseline import ID_TO_LABEL, LABEL_TO_ID
from src.ml.train_test_split import time_based_split


def train_for_explanation():
    """Train the same baseline model as train_baseline.py (current feature set - Elo, form,
    h2h, home advantage - and plain balanced class weights, no draw up-weighting, per the
    decision not to adopt that experiment) - kept separate from train_baseline.train_baseline()
    only because this also needs train/test dataframes carrying HomeTeam/AwayTeam/MatchDate
    for identifying a specific real match, which the training scripts deliberately don't
    carry (they only ever select FEATURE_COLUMNS)."""
    train_df, test_df, train_seasons, test_seasons = time_based_split(keep_meta=True, keep_teams=True)

    X_train = train_df[FEATURE_COLUMNS]
    y_train = train_df[TARGET_COLUMN].map(LABEL_TO_ID)

    sample_weight = compute_sample_weight(class_weight="balanced", y=y_train)

    model = XGBClassifier(objective="multi:softmax", num_class=3, eval_metric="mlogloss", random_state=42)
    model.fit(X_train, y_train, sample_weight=sample_weight)

    return model, train_df, test_df


def _explain_row(model, X_row: pd.DataFrame) -> dict:
    """Shared core: given a trained model and a single row of FEATURE_COLUMNS, return the
    prediction, probabilities, XGBoost's global feature importance, and this row's own SHAP
    breakdown - used both for explaining a real test-set match (explain_match) and a
    hypothetical new matchup (build_and_explain_matchup).
    """
    proba = model.predict_proba(X_row)[0]
    predicted_id = int(proba.argmax())
    predicted_label = ID_TO_LABEL[predicted_id]

    explainer = shap.TreeExplainer(model)
    shap_values = explainer(X_row)  # shape: (1, n_features, n_classes)

    # Explain the class the model actually predicted, not always e.g. "H" - the point is to
    # explain why the model landed on ITS chosen outcome for this match.
    per_feature_shap = shap_values.values[0, :, predicted_id]

    contributions = sorted(
        zip(FEATURE_COLUMNS, X_row.iloc[0].tolist(), per_feature_shap.tolist()),
        key=lambda item: abs(item[2]),
        reverse=True,
    )

    global_importance = sorted(
        zip(FEATURE_COLUMNS, model.feature_importances_.tolist()),
        key=lambda item: item[1],
        reverse=True,
    )

    return {
        "predicted_label": predicted_label,
        "probabilities": {ID_TO_LABEL[i]: float(p) for i, p in enumerate(proba)},
        "shap_base_value": float(shap_values.base_values[0, predicted_id]),
        "contributions": contributions,
        "global_importance": global_importance,
    }


def explain_match(model, test_df, match_index: int) -> dict:
    """Explain one specific REAL test-set match - predicted outcome + probabilities, XGBoost's
    global feature importance (for context - which features matter most across all
    predictions), and a SHAP breakdown of exactly this match (which features pushed THIS
    prediction toward its actual outcome, and by how much) - the two are not the same thing.
    Global importance can rank a feature highly overall while it barely mattered for one
    specific match, and vice versa; SHAP values are what actually explain an individual
    prediction.
    """
    row = test_df.iloc[[match_index]]
    X_row = row[FEATURE_COLUMNS]

    result = _explain_row(model, X_row)
    result["home_team"] = row["HomeTeam"].iloc[0]
    result["away_team"] = row["AwayTeam"].iloc[0]
    result["match_date"] = row["MatchDate"].iloc[0]
    result["actual_label"] = row[TARGET_COLUMN].iloc[0]
    return result


def build_matchup_features(home_team: str, away_team: str, reference_date=None) -> pd.DataFrame:
    """Build a single feature row for a HYPOTHETICAL matchup between two already-resolved
    team names (in the offline dataset's own naming convention - see
    db/training_data/README.md), computed the same way the training data itself was: latest
    Elo (elo_lookup.py), recent-form points (form.py), head-to-head (head_to_head.py), and
    home advantage (home_advantage.py) - all using data strictly before `reference_date`
    (defaults to now; any date after the dataset's real coverage behaves identically, since
    all of these only ever look backward from that date).
    """
    if reference_date is None:
        reference_date = pd.Timestamp.now()

    home_elo = get_latest_elo(home_team, reference_date)
    away_elo = get_latest_elo(away_team, reference_date)
    if home_elo is None or away_elo is None:
        missing = [t for t, e in [(home_team, home_elo), (away_team, away_elo)] if e is None]
        raise ValueError(f"No Elo rating found for: {', '.join(missing)} (as of {reference_date})")

    row = pd.DataFrame(
        [
            {
                "HomeTeam": home_team,
                "AwayTeam": away_team,
                "MatchDate": reference_date,
                "HomeElo": home_elo,
                "AwayElo": away_elo,
                "Form3Home": compute_recent_form(home_team, reference_date, lookback=3),
                "Form3Away": compute_recent_form(away_team, reference_date, lookback=3),
                "Form5Home": compute_recent_form(home_team, reference_date, lookback=5),
                "Form5Away": compute_recent_form(away_team, reference_date, lookback=5),
            }
        ]
    )
    row["elo_diff"] = row["HomeElo"] - row["AwayElo"]
    row = compute_h2h_features(row)
    row = compute_home_advantage_features(row)

    return row[FEATURE_COLUMNS]


def build_and_explain_matchup(model, home_team: str, away_team: str, reference_date=None) -> dict:
    """Same explanation as explain_match(), but for a hypothetical matchup built fresh from
    current data rather than a specific row already in the test set. No actual_label, since
    there's no real outcome yet to compare against.
    """
    X_row = build_matchup_features(home_team, away_team, reference_date)
    result = _explain_row(model, X_row)
    result["home_team"] = home_team
    result["away_team"] = away_team
    return result


LABEL_NAMES = {"H": "home win", "D": "draw", "A": "away win"}


def _format_contribution(feature: str, value: float, shap_value: float) -> str:
    direction = "toward" if shap_value > 0 else "away from"
    return f"  {feature:<28} value={value:>8.2f}   SHAP={shap_value:+.3f}  ({direction} the prediction)"


if __name__ == "__main__":
    model, train_df, test_df = train_for_explanation()

    # Picked for a readable demo: the first test-set match the model predicted correctly,
    # so the "why" being walked through corresponds to a real, right call - not required by
    # explain_match() itself, which works identically on a wrong prediction too.
    match_index = None
    for i in range(len(test_df)):
        X_row = test_df.iloc[[i]][FEATURE_COLUMNS]
        predicted = ID_TO_LABEL[int(model.predict_proba(X_row)[0].argmax())]
        if predicted == test_df.iloc[i][TARGET_COLUMN]:
            match_index = i
            break

    result = explain_match(model, test_df, match_index)

    print(f"Match: {result['home_team']} vs {result['away_team']} ({result['match_date'].date()})")
    print(f"Actual result: {LABEL_NAMES[result['actual_label']]}")
    print(f"Predicted: {LABEL_NAMES[result['predicted_label']]}")
    print("Predicted probabilities: " + ", ".join(f"{LABEL_NAMES[k]}={v:.3f}" for k, v in result["probabilities"].items()))
    print()

    print("Global feature importance (XGBoost, across all predictions):")
    for feature, importance in result["global_importance"]:
        print(f"  {feature:<28} {importance:.3f}")
    print()

    print(f"Per-match SHAP breakdown for THIS prediction ({LABEL_NAMES[result['predicted_label']]}):")
    print(f"  base rate for this outcome (before any features): {result['shap_base_value']:+.3f}")
    for feature, value, shap_value in result["contributions"]:
        print(_format_contribution(feature, value, shap_value))
