# Technical Track — Data Identification & the Glossary Generator (CSCU)

A hands-on track for the **technical audience** — Data Stewards, Data
Developers, Solution Architects, and Administrators. It goes underneath the
Business-Analyst course and explains (and lets you build) the engine that
powers **Workshop 5 — Data Identification**, then applies it with the
**Glossary Generator** app.

It is *not* part of the BA path. Run it with technical staff after they have
seen Connect → Metadata Ingest → Profiling (BA Workshops 1, 2 and 4), i.e.
once there is profiled CSCU data to identify.

## The modules

| Folder | Module | What you do |
| --- | --- | --- |
| `02-Data-Identification` | **Data Identification (deep dive)** | Understand the engine: Dictionaries (content) + Patterns (shape) → Policies → Tags & Terms |
| `03-Build-Your-Own-Dictionary-and-Pattern` | **Build Your Own (lab)** | Author a CSCU dictionary + pattern, combine into a policy, run it — 18 dictionaries and 7 patterns ship ready-made |
| `01-Glossary-Generator-App` | **Glossary Generator App** | Apply the result: build CSCU's governed glossary over the PDC API — and let its agents draft the Module-03-style rule files from scan evidence |
| `04-Similarity & ML` | **Similarity & ML Inference** | Propagate curation to similar columns; the app's evidence-aware Find similar + duplicate-group advisor |
| `05-Visualizations` | **PDC Insights** | Dashboards over the app's governance-summary API |

**Recommended order:** 02 → 03 → 01 → 04 → 05.

## Status

The markdown guide masters are authoritative; decks and Word builds for the
CSCU edition are pending (produce from the guides, capture screenshots on the
CSCU lab). Module 03's dictionaries/patterns are generated from the live
`cscu_core` schema and ready to upload.

## Audience & roles

Authoring dictionaries, patterns and metadata rules requires the **Data
Steward** or **Data Storage Administrator** role. If Data Operations → Data
Identification Methods is not visible, that is a permissions matter, not a
missing feature.

All Copper State Credit Union data is fictional and generated for training.
