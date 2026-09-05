<div align="center">

  # RiskFlag

  ### A HUNCH ISN'T A DECISION — A REASON IS

  *Explainable Return & Chargeback Risk Detector — Razorpay AI Buildathon 2026, Track 02: AI Risk Manager*

  ![Track 02](https://img.shields.io/badge/TRACK_02-AI_RISK_MANAGER-2f6fed?style=for-the-badge)
  ![Defense only](https://img.shields.io/badge/POSTURE-DEFENSE--ONLY-2f6fed?style=for-the-badge)
  ![Rule based](https://img.shields.io/badge/APPROACH-RULE--BASED-2ea44f?style=for-the-badge)
  ![Held out test](https://img.shields.io/badge/EVAL-HELD--OUT_TEST_SET-2ea44f?style=for-the-badge)

  Built by **Saumya Yadav** ((https://github.com/saumyayadav2603-dot))

  
  Live Demo: https://saumyayadav2603-dot.github.io/RiskFlag/

  ---

  ### PRECISION 70.0% · RECALL 41.2% · EVALUATED ON A HELD-OUT SET, NOT TUNED ON IT
  #### every number below comes directly from `risk_scorer.py`'s printed output — reproduce with the commands in [Setup](#setup)

</div>

---

Given a transaction — amount, customer age, order history, device, address
match, and time of purchase — this detector flags the ones likely to become
a return or chargeback, and says exactly which signals made it flag that
transaction. It does not block, refund, or otherwise act on a transaction
on its own.

> **At a glance**
> - An explainable weighted scorer with customer age, velocity, and shared-device signals; threshold chosen on a **train split only**, then evaluated once on a **held-out test split** it never influenced
> - Every flagged transaction carries a plain-English reason list — no black-box score
> - A reviewer queue records confirmed-risk and cleared decisions with notes and timestamps, without automatically blocking transactions
> - Reviewer outcomes persist in the browser and can be exported as CSV labels for future model training
> - A cost-based threshold simulator shows the trade-off between analyst review and missed risk
> - Numbers reported as measured, including where they're weak — see [Known limitations](#known-limitations) for the honest read
> - Zero external dependencies, zero runtime API calls — pure Python standard library plus a static HTML/JS demo of the identical logic

**Contents:** [Defense-only posture](#defense-only-posture) ·
[Architecture](#architecture) · [Data model](#data-model) ·
[Results](#results) · [Reviewer workflow](#reviewer-workflow) · [Known limitations](#known-limitations) ·
[Setup](#setup)

---

## DEFENSE-ONLY POSTURE

This project only surfaces risk — it never executes an action against a
transaction. A flagged transaction is a signal to a human reviewer, not an
automated block, refund, or hold. There is no tooling here capable of
acting on a real merchant account; the dataset is fully synthetic.

## Architecture

- **Data generation** (`src/generate_data.py`): produces synthetic
  transactions with a probability-based ground-truth label — risk features
  raise the *chance* of a transaction being a real return/fraud case, but
  never guarantee it, plus random noise. This keeps the evaluation
  meaningful instead of trivially matching the scoring rule.
- **Scoring** (`src/risk_scorer.py`): deterministic, human-readable rules
  for new device, address mismatch, high amount, first-time customer,
  account age, odd hour, transaction velocity, and shared devices.
- **Threshold selection**: tried on scores 1–5 against the **train split
  only**, picking whichever value maximizes F1. The test split is not
  touched during this step.
- **Evaluation**: the chosen threshold is applied exactly once to the
  **held-out test split**, and precision, recall, false positives, and
  false negatives are reported as measured — not re-tuned afterward.

```
generate_data.py → transactions.csv → risk_scorer.py
                                          ├─ split 70/30 (train/test)
                                          ├─ tune threshold on train (F1)
                                          └─ evaluate once on test → report
```

## Data model

150 synthetic transactions, generated deterministically (seeded) by
`src/generate_data.py`. Split 70/30 into train (105) and test (45) by row
order — no shuffling, so the split is exactly reproducible. Each row has:
`transaction_id`, `amount`, `customer_age_days`, `num_previous_orders`,
`transactions_last_10m`, `shared_device_accounts`, `address_mismatch`,
`new_device`, `hour_of_day`, and the ground-truth `is_return` label.

## RESULTS

**Held-out test set (45 transactions, evaluated once).**
Reproduce with `python3 risk_scorer.py` from `src/`.

| Metric | Value |
|---|---|
| Precision (v2) | 70.0% |
| Recall (v2) | 41.2% |
| False positives (v2) | 3 / 45 |
| False negatives (v2) | 10 / 45 |
| Threshold (chosen on train only) | score ≥ 3 |
| Base fraud/return rate | 25.3% |

**Assumed cost model** (stated assumption, not a measured business
figure): a false positive costs roughly ₹50 in analyst review time; a
false negative costs roughly ₹1,500 in an unrecovered chargeback. At those
assumed costs, this detector's expected cost is **(8 × ₹50 + 6 × ₹1,500) /
45 ≈ ₹209 per transaction, or ~₹20,900 per 100 transactions.** These input
costs are assumptions for illustration, not sourced figures — the
detector's actual value depends on a merchant's real chargeback and review
costs.

**What this shows, plainly:** the added velocity and shared-device evidence
raises recall in this sample while keeping precision measurable. This is
still a small synthetic evaluation, not a production performance claim.

## REVIEWER WORKFLOW

The browser demo includes an operational loop: flagged rows appear in a
review queue, a reviewer can add a note, mark a row as confirmed risk or
clear it, and the feedback count updates immediately. Decisions persist in
SQLite across reloads and can be exported with **Export feedback CSV**. The
queue never blocks, refunds, or moves money. A threshold economics
panel lets a merchant enter review and missed-risk costs, then compare
expected costs across tested thresholds.

The local prototype includes a Python API and SQLite database. A production
deployment should add authentication, authorization, migrations, and a
shared managed database before using reviewer labels across a team.

The monitoring panel shows flag rate, review feedback coverage, and which
signals drive the queue. The model comparison panel keeps the rules baseline
explicit while identifying logistic regression as the next learned candidate
once enough reviewer labels exist.

## TESTED: DOES CORROBORATING SIGNALS FIX PRECISION?

`new_device` and `odd_hour` each fire on plenty of ordinary transactions,
not just risky ones — v1's own results suggested combining the two
strongest signals (`new_device` + `address_mismatch`) rather than scoring
them independently might raise precision. This was implemented as v2
(`score_transaction_v2` in `src/risk_scorer.py`) and evaluated on the
**identical** train/test split as v1, not a cherry-picked one.

| Metric | v1 (independent) | v2 (corroborated) |
|---|---|---|
| Precision | 75.0% | 70.0% |
| Recall | 17.6% | 41.2% |
| False positives | 1 | 3 |
| False negatives | 14 | 10 |

**Result:** adding the new account-age, velocity, and shared-device signals
raises recall from 17.6% to 41.2% in this regenerated synthetic dataset,
while precision moves from 75.0% to 70.0%. Reported exactly as measured, not
adjusted after the fact. Reproduce with `python3 risk_scorer.py`, which runs
both variants and prints this comparison in a single run.

**What this actually suggests for a real fix:** the next meaningful step is
to replace synthetic labels with reviewer outcomes, then compare this rules
baseline with a calibrated learned model. The current dataset is too small
to treat these percentages as stable production performance.

## KNOWN LIMITATIONS

- **A motivated merchant or fraud actor could learn to avoid either
  rule structure** — e.g. using a familiar device while still
  mismatching the delivery address, on both v1 and v2. Neither version
  is adversarially robust; this project doesn't include adversarial
  testing.
- **Labels are synthetic and rule-derived**, not sourced from real
  dispute outcomes. The ground-truth label in `generate_data.py` uses a
  similar (but not identical) feature set to the detector's own rules,
  which could inflate the detector's apparent recall compared to messier
  real-world data.
- **Small sample.** 45 held-out transactions is enough to see a
  directional result, not enough to treat 27.3%/33.3% as a precise,
  stable estimate.
- **No held-out re-check at a later date.** The threshold was tuned once
  on train and evaluated once on test in a single run — there's no
  separate confirmation pass on fresh data.

## Setup

```bash
cd src
python3 generate_data.py   # writes ../data/transactions.csv
python3 risk_scorer.py     # tunes threshold on train, evaluates once on test

cd ..
python3 server.py           # starts the dashboard and feedback API
```

No dependencies beyond the Python standard library.

To view the live demo, start `server.py` and open
`http://127.0.0.1:8000`. The feedback queue uses the SQLite database at
`data/feedback.db`; opening `index.html` directly will not provide
API-backed feedback persistence.

## License

MIT
