"""
Rule-based return/fraud risk scorer.

Approach:
1. Split data into train/test (train is only used to eyeball thresholds,
   test is held out until final scoring — no cheating).
2. Score each transaction with a simple, explainable weighted rule.
3. Flag anything above a threshold as "risky".
4. Report precision, recall, and false positives on the TEST set only.
"""

import csv


def load_transactions(path):
    rows = []
    with open(path) as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append({
                "transaction_id": r["transaction_id"],
                "amount": float(r["amount"]),
                "customer_age_days": int(r["customer_age_days"]),
                "num_previous_orders": int(r["num_previous_orders"]),
                "transactions_last_10m": int(r.get("transactions_last_10m", 0)),
                "shared_device_accounts": int(r.get("shared_device_accounts", 1)),
                "address_mismatch": r["address_mismatch"] == "True",
                "new_device": r["new_device"] == "True",
                "hour_of_day": int(r["hour_of_day"]),
                "is_return": r["is_return"] == "True",
            })
    return rows


def score_transaction_v1(tx):
    """
    v1: each signal scored independently. Simple, but a single weak
    signal (e.g. just an odd purchase hour) can trigger a flag on its own.
    Returns (score, reasons) — reasons make the flag explainable,
    not just a black-box number.
    """
    score = 0
    reasons = []

    if tx["new_device"]:
        score += 2
        reasons.append("new device")
    if tx["address_mismatch"]:
        score += 2
        reasons.append("billing/delivery address mismatch")
    if tx["amount"] > 8000:
        score += 1
        reasons.append("high amount (>8000)")
    if tx["num_previous_orders"] == 0:
        score += 1
        reasons.append("first-time customer")
    if tx["customer_age_days"] < 30:
        score += 1
        reasons.append("new customer account (<30 days)")
    if tx["transactions_last_10m"] >= 3:
        score += 2
        reasons.append("high transaction velocity (3+ in 10 minutes)")
    if tx["shared_device_accounts"] >= 3:
        score += 2
        reasons.append("device shared by 3+ accounts")
    if tx["hour_of_day"] < 5 or tx["hour_of_day"] > 23:
        score += 1
        reasons.append("odd hour of purchase")

    return score, reasons


def score_transaction_v2(tx):
    """
    v2: same base signals, but new_device and address_mismatch — the two
    strongest individual signals — only score at full weight when they
    co-occur. Alone, each is downweighted, since v1's evaluation showed
    both firing on plenty of ordinary transactions in isolation. This
    requires corroborating evidence for a flag, rather than one weak
    signal alone, which is the specific fix v1's own results pointed to.
    """
    score = 0
    reasons = []

    if tx["new_device"] and tx["address_mismatch"]:
        score += 5  # corroborated — stronger combined signal than 2+2 alone
        reasons.append("new device AND billing/delivery address mismatch")
    else:
        if tx["new_device"]:
            score += 1  # downweighted: too common alone to justify full weight
            reasons.append("new device (uncorroborated)")
        if tx["address_mismatch"]:
            score += 1  # downweighted: too common alone to justify full weight
            reasons.append("address mismatch (uncorroborated)")

    if tx["amount"] > 8000:
        score += 1
        reasons.append("high amount (>8000)")
    if tx["num_previous_orders"] == 0:
        score += 1
        reasons.append("first-time customer")
    if tx["customer_age_days"] < 30:
        score += 1
        reasons.append("new customer account (<30 days)")
    if tx["transactions_last_10m"] >= 3:
        score += 2
        reasons.append("high transaction velocity (3+ in 10 minutes)")
    if tx["shared_device_accounts"] >= 3:
        score += 2
        reasons.append("device shared by 3+ accounts")
    if tx["hour_of_day"] < 5 or tx["hour_of_day"] > 23:
        score += 1
        reasons.append("odd hour of purchase")

    return score, reasons


# Default scorer used by evaluate() unless a variant is passed explicitly.
score_transaction = score_transaction_v1


def evaluate(rows, threshold, scorer=score_transaction_v1):
    """Compute precision, recall, and false-positive count at a given threshold."""
    true_positives = 0
    false_positives = 0
    false_negatives = 0
    true_negatives = 0

    flagged_examples = []

    for tx in rows:
        score, reasons = scorer(tx)
        flagged = score >= threshold

        if flagged and tx["is_return"]:
            true_positives += 1
        elif flagged and not tx["is_return"]:
            false_positives += 1
        elif not flagged and tx["is_return"]:
            false_negatives += 1
        else:
            true_negatives += 1

        if flagged:
            flagged_examples.append((tx["transaction_id"], score, reasons, tx["is_return"]))

    precision = true_positives / (true_positives + false_positives) if (true_positives + false_positives) else 0
    recall = true_positives / (true_positives + false_negatives) if (true_positives + false_negatives) else 0

    return {
        "threshold": threshold,
        "true_positives": true_positives,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "true_negatives": true_negatives,
        "precision": precision,
        "recall": recall,
        "flagged_examples": flagged_examples,
    }


def tune_and_evaluate(rows_train, rows_test, scorer, label):
    """Tune threshold on train (by F1), then evaluate ONCE on test. Prints results."""
    print(f"--- {label} : tuning threshold on TRAIN set ---")
    best_threshold = None
    best_f1 = -1
    for t in range(1, 8):
        result = evaluate(rows_train, t, scorer=scorer)
        f1 = (2 * result["precision"] * result["recall"] / (result["precision"] + result["recall"])
              if (result["precision"] + result["recall"]) else 0)
        print(f"  threshold={t}: precision={result['precision']:.2f}, "
              f"recall={result['recall']:.2f}, f1={f1:.2f}")
        if f1 > best_f1:
            best_f1 = f1
            best_threshold = t

    print(f"  chosen threshold (train only): {best_threshold}\n")

    result = evaluate(rows_test, best_threshold, scorer=scorer)
    print(f"--- {label} : FINAL result on held-out TEST set ---")
    print(f"  Precision: {result['precision']:.2%}")
    print(f"  Recall:    {result['recall']:.2%}")
    print(f"  False positives: {result['false_positives']}")
    print(f"  False negatives: {result['false_negatives']}")
    print()
    return result


def main():
    rows = load_transactions("../data/transactions.csv")

    # 70/30 split. Train is used only to pick a reasonable threshold;
    # test is held out and untouched until final scoring. Same split
    # used for both v1 and v2, so the comparison is controlled.
    split_point = int(len(rows) * 0.7)
    train, test = rows[:split_point], rows[split_point:]

    print(f"Train set: {len(train)} transactions, Test set: {len(test)} transactions\n")

    v1_result = tune_and_evaluate(train, test, score_transaction_v1, "v1 (independent rules)")
    v2_result = tune_and_evaluate(train, test, score_transaction_v2, "v2 (corroborated device+address)")

    print("=" * 60)
    print("CONTROLLED BEFORE/AFTER COMPARISON (identical train/test split)")
    print("=" * 60)
    print(f"{'Metric':<18}{'v1':>10}{'v2':>10}")
    print(f"{'Precision':<18}{v1_result['precision']:>9.1%} {v2_result['precision']:>9.1%}")
    print(f"{'Recall':<18}{v1_result['recall']:>9.1%} {v2_result['recall']:>9.1%}")
    print(f"{'False positives':<18}{v1_result['false_positives']:>10}{v2_result['false_positives']:>10}")
    print(f"{'False negatives':<18}{v1_result['false_negatives']:>10}{v2_result['false_negatives']:>10}")
    print()

    print("Sample v2 flagged transactions with reasons (explainability):")
    for tx_id, score, reasons, actual in v2_result["flagged_examples"][:8]:
        verdict = "correct" if actual else "false alarm"
        print(f"  {tx_id} | score={score} | {', '.join(reasons)} | actually_return={actual} ({verdict})")


if __name__ == "__main__":
    main()
