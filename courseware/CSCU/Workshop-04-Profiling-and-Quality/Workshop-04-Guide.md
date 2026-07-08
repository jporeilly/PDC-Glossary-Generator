# Workshop 4 — Profile Data & Assess Quality (CSCU)

*Copper State Credit Union scenario · PDC 11.0.0*

You profile the `cscu_core` tables, read what the profiler found, then turn
CSCU's compliance obligations into **Business Rules** the Rules Engine scores.

## Why this workshop matters

Profiling turns "we have a members table" into "members is 100% complete on
`mbr_no`, 8 distinct transaction types, SSNs match the expected pattern".
Business rules then turn obligations into numbers that recompute on a
schedule — compliance you can trend, not assert.

**The business problem.** Two of CSCU's obligations are already broken in the
data, and nobody can see it: three opted-out members still hold live
marketing emails (GDPR/CCPA exposure), and six stored CVV codes violate PCI
DSS outright. This workshop makes both failures *measurable* — the
prerequisite for fixing them and proving the fix.

## What you will learn

- What the profiler captures per column — completeness, cardinality,
  patterns — and how to read it.
- How PDC business rules work: the three-column SQL contract
  (`total_count / scopeCount / nonCompliant`) the Rules Engine scores.
- Why the rules are authored by a **Data Developer** (Dana) — v11's
  role-gating in practice.
- How the flagship opt-out rule and the PCI no-stored-CVV rule report the
  planted violations.

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
