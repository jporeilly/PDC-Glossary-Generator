# Module 01 — Glossary Generator App

**Track:** Technical · **Audience:** Data Steward / Solution Architect
**Alternative to:** BA Workshop 3 — Build the Business Glossary (manual)

The app-driven way to produce CSCU's governed glossary: scan `cscu_core` and
the `cscu-documents` bucket, review with the steward, govern, generate the
import JSONL (+ the Classification Registry), and apply term links back to PDC
over the public API. Since app 1.8.x the review is agent-assisted — evidence-
grounded AI suggestions, a Merge/Disambiguate advisor on duplicate groups,
definition QA, AI categorization — and **Draft policies (AI)** turns the
scan's detection seeds into Module-03-shape pattern/dictionary files ready
for PDC's Data Identification import.

**Nothing ships inside this module** — the app and its materials live in the
repository, always current:

| What | Where |
| --- | --- |
| The app itself | `/glossary_generator/` (run with `./run.sh` / `run.ps1`) |
| Scenario install | `./install-scenario.sh` at the repo root (or unzip `data_sources/CSCU/cscu-domain-pack.zip`) |
| Workshop guide | [`../../Workshop-Glossary-Generator-CSCU.md`](../../Workshop-Glossary-Generator-CSCU.md) |
| Topic notes | [`Tags & the Domain Pack`](../../Glossary-Generator-Tags-and-Domain-Pack.md) · [`LLM & Review`](../../Glossary-Generator-LLM-and-Review.md) · [`Object Stores`](../../PDC-Object-Stores-AWS-S3-MinIO.md) |
| App documentation | `/docs/` (REFERENCE, GUIDE, INSTALL, CHALLENGE-AND-GOAL) |
| Architecture figures | `/glossary_generator/diagrams/` (PNG + SVG) |

Deck and Word builds for the CSCU edition are pending — produce them from the
workshop guide and capture screenshots on the CSCU lab.

All Copper State Credit Union data is fictional and generated for training.
