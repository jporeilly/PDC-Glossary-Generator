# Module 03 — Build Your Own CSCU Dictionary & Pattern (Lab)

**Track:** Technical · **Audience:** Data Steward / Data Storage Administrator
**Estimated time:** 45 min · **Prerequisite:** profiled `cscu_core` tables; Module 02

A hands-on lab: you author **one dictionary** and **one pattern**, combine them
into a **policy**, and run it on Copper State Credit Union data.

> The deck and Word guide for the CSCU edition have not been produced yet —
> `Lab-Build-Your-Own-CSCU-Dictionary-and-Pattern.md` is the authoritative
> source: build the .docx/.pptx from it and capture the screenshots at each
> `[SCREENSHOT]` marker on the CSCU lab.

Worked examples: the **CSCU Transaction Types** dictionary (match by content)
and the **CSCU Member Number** pattern `CSCU-nnnnnn` (match by shape). Profile
first; author once; the Trust Score comes last.

## What ships in this module

- **`CSCU-Dictionaries/`** — 18 ready-made dictionaries: a single-column
  `term` CSV plus a PDC rule JSON per method (enum columns, branch names,
  service cities, NACHA return codes, …). `CSCU-Dictionaries.zip` bundles them
  for upload.
- **`CSCU-Patterns/`** — 7 ready-made patterns (member/account/loan
  numbers, ABA routing, card PAN, email, GL account). `CSCU-Patterns.zip`
  bundles them.
- **`INDEX.csv`** — every method with the column it matches, its format/size,
  and the tags/terms it applies.

All Copper State Credit Union data is fictional and generated for training.
