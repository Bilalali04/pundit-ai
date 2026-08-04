from sklearn.metrics import accuracy_score, classification_report, confusion_matrix

from src.ml.train_baseline import ID_TO_LABEL, train_baseline

MULTIPLIERS = [1.0, 1.5, 2.0]


def run_sweep():
    """Retrain the baseline at each draw_weight_multiplier and collect metrics for a direct
    side-by-side comparison - does manually up-weighting draws beyond the automatic
    "balanced" value recover draw performance without giving back the accuracy gained from
    the home-advantage feature, or does it just trade accuracy away?
    """
    target_names = [ID_TO_LABEL[i] for i in sorted(ID_TO_LABEL)]
    results = []

    for multiplier in MULTIPLIERS:
        _, y_test, y_pred, train_seasons, test_seasons = train_baseline(draw_weight_multiplier=multiplier)
        report_dict = classification_report(y_test, y_pred, target_names=target_names, digits=3, output_dict=True)
        report_text = classification_report(y_test, y_pred, target_names=target_names, digits=3)
        cm = confusion_matrix(y_test, y_pred)
        results.append(
            {
                "multiplier": multiplier,
                "accuracy": accuracy_score(y_test, y_pred),
                "report_dict": report_dict,
                "report_text": report_text,
                "confusion_matrix": cm,
            }
        )

    return results, target_names, train_seasons, test_seasons


if __name__ == "__main__":
    results, target_names, train_seasons, test_seasons = run_sweep()

    print(f"Trained on {train_seasons}, evaluated on {test_seasons}")
    print()

    header = f"{'multiplier':>10} | {'accuracy':>8} | {'macro F1':>8} | " + " | ".join(
        f"{name}_P/R/F1" for name in target_names
    )
    print(header)
    print("-" * len(header))
    for r in results:
        rep = r["report_dict"]
        cells = [
            f"{r['multiplier']:>10.1f}",
            f"{r['accuracy']:>8.3f}",
            f"{rep['macro avg']['f1-score']:>8.3f}",
        ]
        for name in target_names:
            cells.append(f"{rep[name]['precision']:.2f}/{rep[name]['recall']:.2f}/{rep[name]['f1-score']:.2f}")
        print(" | ".join(cells))

    print()
    for r in results:
        print(f"=== draw_weight_multiplier = {r['multiplier']} ===")
        print(f"Accuracy: {r['accuracy']:.3f}")
        print(r["report_text"])
        cm = r["confusion_matrix"]
        col_header = "        " + "  ".join(f"pred_{n}" for n in target_names)
        print(col_header)
        for name, row in zip(target_names, cm):
            print(f"actual_{name}  " + "  ".join(f"{v:6d}" for v in row))
        print()
