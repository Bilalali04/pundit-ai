from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.utils.class_weight import compute_sample_weight
from xgboost import XGBClassifier

from src.ml.prepare_features import FEATURE_COLUMNS, TARGET_COLUMN
from src.ml.train_test_split import time_based_split

# FTResult is stored as H/D/A - XGBoost needs numeric class labels. Order is arbitrary
# (multi:softmax doesn't treat classes as ordinal), fixed here just for readable reporting.
LABEL_TO_ID = {"H": 0, "D": 1, "A": 2}
ID_TO_LABEL = {v: k for k, v in LABEL_TO_ID.items()}


def train_baseline(draw_weight_multiplier: float = 1.0):
    """First baseline XGBoost 3-class classifier for match outcome (H/D/A) - default
    hyperparameters, no tuning, just a real first result to see where we're starting from.

    Draws are the minority class (~23% of matches, see train_test_split.py's distribution
    report), and a naive model tends to just never predict them since predicting the
    majority class is often the accuracy-maximizing shortcut. Countered here via
    sample_weight computed on the training set only (test set stays at its natural,
    unweighted distribution, since evaluation should reflect the real class balance the
    model will actually face) - not by ignoring the imbalance.

    draw_weight_multiplier: applied on top of the automatic "balanced" weight, to the draw
    class only (e.g. 1.5 or 2.0), to test whether manually pushing harder on draws recovers
    draw performance that other features (home advantage) have eaten into - see
    draw_weight_sweep.py for the comparison this is meant to support. 1.0 = pure balanced
    weighting, unchanged from the original baseline.
    """
    train_df, test_df, train_seasons, test_seasons = time_based_split()

    X_train = train_df[FEATURE_COLUMNS]
    y_train = train_df[TARGET_COLUMN].map(LABEL_TO_ID)
    X_test = test_df[FEATURE_COLUMNS]
    y_test = test_df[TARGET_COLUMN].map(LABEL_TO_ID)

    sample_weight = compute_sample_weight(class_weight="balanced", y=y_train)
    if draw_weight_multiplier != 1.0:
        sample_weight = sample_weight.copy()
        sample_weight[y_train.to_numpy() == LABEL_TO_ID["D"]] *= draw_weight_multiplier

    model = XGBClassifier(objective="multi:softmax", num_class=3, eval_metric="mlogloss", random_state=42)
    model.fit(X_train, y_train, sample_weight=sample_weight)

    y_pred = model.predict(X_test)

    return model, y_test, y_pred, train_seasons, test_seasons


if __name__ == "__main__":
    model, y_test, y_pred, train_seasons, test_seasons = train_baseline()

    target_names = [ID_TO_LABEL[i] for i in sorted(ID_TO_LABEL)]

    print(f"Trained on {train_seasons}, evaluated on {test_seasons}")
    print()
    print(f"Overall accuracy: {accuracy_score(y_test, y_pred):.3f}")
    print()
    print("Per-class precision/recall/F1:")
    print(classification_report(y_test, y_pred, target_names=target_names, digits=3))
    print("Confusion matrix (rows = actual, columns = predicted):")
    cm = confusion_matrix(y_test, y_pred)
    header = "        " + "  ".join(f"pred_{n}" for n in target_names)
    print(header)
    for name, row in zip(target_names, cm):
        print(f"actual_{name}  " + "  ".join(f"{v:6d}" for v in row))
