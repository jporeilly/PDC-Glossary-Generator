# Similarity & ML Inference (CSCU)

*Copper State Credit Union scenario · PDC 11.0.0 · Technical Track Module 04*

## 1. Column similarity

PDC compares profiled value distributions between columns. On CSCU:
`members.br_id`, `accounts.br_id`, `branches.br_id` and `gl_entries.br_id` are
near-identical distributions — similarity groups them.
`[SCREENSHOT: similar columns on br_id]`

## 2. Inference — propagate the curation

Tag or link a term on one column and PDC can propose the same on similar
columns: link **Branch ID** on `branches.br_id`, review the inference on the
other three. Inference is a *proposal* — the steward accepts or rejects.
`[SCREENSHOT: inferred term suggestions]`

## 3. The same idea in the Glossary Generator

The app's **Find similar** (Dictionary page) is similarity for *vocabulary*:
similarity-scored suggested merges catch near-duplicate terms (e.g. *Member
Number* vs *Mbr Number*) before they fragment the glossary. Same principle —
measure likeness, propose, let the steward decide.

## 4. Cautions

- Similarity on low-cardinality enums over-groups (every status column looks
  alike) — check the column *name and meaning* before accepting.
- Inference after steward overrides is safe (proposals), unlike re-running
  identification (overwrites).

All Copper State Credit Union data is fictional and generated for training.
