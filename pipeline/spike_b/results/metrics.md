# Spike B — TF-IDF + Logistic Regression Baseline (OPP-115)

Trained on 3029 segments (train split, majority-vote labels,
split by policy, seed 42). One-vs-rest logistic regression over
TF-IDF 1-2 grams. No tuning — this is the floor, not the model.

Week-10 target (proposal objective 2): macro F1 >= 0.70 in the live
pipeline. Polisis (USENIX 2018) reported ~0.78 micro-average F1 on
segment classification with CNNs — numbers here frame that gap.

## dev split

**Macro F1: 0.765** · micro F1: 0.771

| Category | P | R | F1 | support |
| --- | --- | --- | --- | --- |
| First Party Collection/Use | 0.828 | 0.793 | 0.81 | 164 |
| Third Party Sharing/Collection | 0.766 | 0.842 | 0.802 | 101 |
| User Choice/Control | 0.565 | 0.684 | 0.619 | 38 |
| User Access, Edit and Deletion | 0.773 | 0.895 | 0.829 | 19 |
| Data Retention | 0.4 | 0.5 | 0.444 | 8 |
| Data Security | 0.615 | 0.727 | 0.667 | 22 |
| Policy Change | 1.0 | 0.824 | 0.903 | 17 |
| Do Not Track | 1.0 | 1.0 | 1.0 | 3 |
| International and Specific Audiences | 0.828 | 0.857 | 0.842 | 28 |
| Other | 0.718 | 0.752 | 0.735 | 105 |

## test split

**Macro F1: 0.765** · micro F1: 0.799

| Category | P | R | F1 | support |
| --- | --- | --- | --- | --- |
| First Party Collection/Use | 0.81 | 0.914 | 0.859 | 93 |
| Third Party Sharing/Collection | 0.742 | 0.947 | 0.832 | 76 |
| User Choice/Control | 0.735 | 0.806 | 0.769 | 31 |
| User Access, Edit and Deletion | 0.706 | 0.8 | 0.75 | 15 |
| Data Retention | 0.75 | 0.429 | 0.545 | 7 |
| Data Security | 0.708 | 0.895 | 0.791 | 19 |
| Policy Change | 0.643 | 0.75 | 0.692 | 12 |
| Do Not Track | 1.0 | 0.667 | 0.8 | 3 |
| International and Specific Audiences | 0.867 | 0.929 | 0.897 | 28 |
| Other | 0.741 | 0.698 | 0.719 | 86 |
