# Workshop 4 — Profile Data & Assess Quality (CSCU)

*Copper State Credit Union scenario · PDC 10.2.11*

You profile the `cscu_core` tables, read what the profiler found, then turn
CSCU's compliance obligations into **Business Rules** the Rules Engine scores.

## Part A — profile the tables

1. As `elena.ramirez`: select the 11 `cscu_core` tables → **Data Profiling**.
2. When the jobs finish, review per-column statistics on **members**:
   completeness (every member has `mbr_no`; some `email` gaps), cardinality
   (`mbr_no` unique; `st` low-cardinality enum), patterns (SSN, phone).
   `[SCREENSHOT: members profile — column statistics]`
3. On **transactions**, check `txn_amt` min/max (negative = debits) and
   `txn_type_cd`'s eight distinct values — that enum becomes a dictionary in
   Workshop 5.

## Part B — business rules (the point of the workshop)

Switch to `dana.ortiz` (**Data Developer** — in PDC v11 this role owns
Business Rules; notably the Admin role can view but not create them).
`assets/Copper-State-Credit-Union-Business-Rules.sql` carries six ready
conditions in PDC's three-column shape (`total_count / scopeCount /
nonCompliant`). Configure each via **Data Operations → Business Rules**:

| Rule | Dimension | What it protects |
| --- | --- | --- |
| `CSCU-Marketing-OptOut-Compliance` | Conformity | **Flagship:** opted-out members must not be contactable on marketing extracts (GDPR/CCPA) |
| `CSCU-PCI-No-Stored-CVV` | Validity | PCI DSS 3.2 — fails by design until the CVV purge runs |
| `CSCU-SSN-Format-Validity` | Conformity | NNN-NN-NNNN |
| `CSCU-Available-Not-Above-Ledger` | Consistency | available ≤ ledger balance |
| `CSCU-APR-Within-Program-Limits` | Validity | 0 < APR ≤ 36% (Reg Z sanity) |
| `CSCU-ACH-Routing-Number-Format` | Conformity | nine-digit ABA numbers |

For each: **Add Business Rule** → name → **Configure** → type + dimension →
schedule → paste the SQL → run.
`[SCREENSHOT: Business Rule configuration — flagship rule SQL]`

Review results: the flagship rule reports **3 in scope** (opted-out members)
and **3 non-compliant** (all still have live emails) — exactly the gap the
marketing extract must handle. `CSCU-PCI-No-Stored-CVV` reports **6/6
non-compliant**: the planted violation, now measured.
`[SCREENSHOT: Business Rules dashboard — pass/fail statuses]`

## Checkpoint

- [ ] All 11 tables profiled
- [ ] Six business rules configured and evaluated
- [ ] Flagship + PCI rules show the expected failures (and you can say why)

All Copper State Credit Union data is fictional and generated for training.
