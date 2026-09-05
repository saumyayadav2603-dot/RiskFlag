"""
Generates synthetic e-commerce transactions with a hand-crafted
ground-truth label (is_return) so we can later score precision/recall
of our rule-based risk detector against something real.
"""

import random
import csv

random.seed(42)  # reproducible runs

N = 150  # total transactions


def generate_transaction(tx_id):
    amount = round(random.uniform(200, 15000), 2)
    customer_age_days = random.randint(0, 1000)
    num_previous_orders = random.randint(0, 20)
    transactions_last_10m = random.choices([0, 1, 2, 3, 4], weights=[55, 25, 12, 6, 2])[0]
    shared_device_accounts = random.choices([1, 2, 3], weights=[82, 14, 4])[0]
    address_mismatch = random.random() < 0.15       # 15% of orders have mismatched billing/delivery
    new_device = random.random() < 0.25              # 25% from a device never seen before
    hour = random.randint(0, 23)
    odd_hour = hour < 5 or hour > 23  # basically midnight-5am, rare

    # ---- risk scoring for the GROUND TRUTH label ----
    # This simulates "reality": what actually correlates with returns/fraud.
    # It intentionally does NOT perfectly match the rules we'll write later —
    # real signals are noisy, and pretending otherwise would make the test meaningless.
    risk_score = 0
    if amount > 8000:
        risk_score += 2
    if customer_age_days < 30:
        risk_score += 2
    if num_previous_orders == 0:
        risk_score += 1
    if address_mismatch:
        risk_score += 3
    if new_device:
        risk_score += 2
    if transactions_last_10m >= 3:
        risk_score += 2
    if shared_device_accounts >= 3:
        risk_score += 2
    if odd_hour:
        risk_score += 1

    # Convert score to a probability of actually being a return/fraud,
    # plus random noise so it's not perfectly deterministic.
    probability = min(0.9, risk_score / 10) + random.uniform(-0.1, 0.1)
    is_return = random.random() < max(0.02, probability)

    return {
        "transaction_id": f"TX{tx_id:04d}",
        "amount": amount,
        "customer_age_days": customer_age_days,
        "num_previous_orders": num_previous_orders,
        "transactions_last_10m": transactions_last_10m,
        "shared_device_accounts": shared_device_accounts,
        "address_mismatch": address_mismatch,
        "new_device": new_device,
        "hour_of_day": hour,
        "is_return": is_return,  # ground truth label (what we'll test against)
    }


def main():
    rows = [generate_transaction(i) for i in range(1, N + 1)]

    fraud_count = sum(1 for r in rows if r["is_return"])
    print(f"Generated {N} transactions, {fraud_count} labeled as return/fraud "
          f"({fraud_count / N:.1%})")

    with open("../data/transactions.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    print("Saved to ../data/transactions.csv")


if __name__ == "__main__":
    main()
