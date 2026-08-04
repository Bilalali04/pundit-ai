import shap
from sklearn.utils.class_weight import compute_sample_weight
from xgboost import XGBClassifier

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


def explain_match(model, test_df, match_index: int):
    """Explain one specific prediction: predicted outcome + probabilities, XGBoost's global
    feature importance (for context - which features matter most across all predictions),
    and a SHAP breakdown of exactly this match (which features pushed THIS prediction toward
    its actual outcome, and by how much) - the two are not the same thing. Global importance
    can rank a feature highly overall while it barely mattered for one specific match, and
    vice versa; SHAP values are what actually explain an individual prediction.
    """
    row = test_df.iloc[[match_index]]
    X_row = row[FEATURE_COLUMNS]

    proba = model.predict_proba(X_row)[0]
    predicted_id = int(proba.argmax())
    predicted_label = ID_TO_LABEL[predicted_id]
    actual_label = row[TARGET_COLUMN].iloc[0]

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
        "home_team": row["HomeTeam"].iloc[0],
        "away_team": row["AwayTeam"].iloc[0],
        "match_date": row["MatchDate"].iloc[0],
        "predicted_label": predicted_label,
        "actual_label": actual_label,
        "probabilities": {ID_TO_LABEL[i]: float(p) for i, p in enumerate(proba)},
        "shap_base_value": float(shap_values.base_values[0, predicted_id]),
        "contributions": contributions,
        "global_importance": global_importance,
    }


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
