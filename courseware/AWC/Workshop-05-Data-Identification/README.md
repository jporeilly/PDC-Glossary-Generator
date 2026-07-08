# Workshop 5: Data Identification

**Primary role:** Business Analyst
**Estimated time:** 45 min
**Focus:** A comprehensive understanding of Data Identification in PDC using **Data Dictionaries** and **Data Patterns** — across both **structured tables** and **unstructured documents** (via Data Discovery / String Detection). The technical workshop goes deeper into building custom methods and tuning rules.

## What's in this package

- **`Workshop-05-Data-Identification.pptx`** — the slide deck for this session (with speaker notes)
- **`Workshop-05-Guide.docx`** — the detailed standalone workshop guide. Read this; it explains the steps *and the reasoning*, with Arizona Water Company context.

## Assets used in this workshop

- `assets/AWC-Service-Cities-Dictionary.csv` — **custom AWC dictionary** (single-column CSV; upload via Data Operations → Dictionaries). Identifies AWC service-area cities in the `service_address` column and in correspondence.
- `assets/Arizona-Water-Company-Business-Rules.sql`
- `assets/Arizona-Water-Company-Glossary.csv`
- `assets/awc-documents/correspondence/email_conservation_inquiry.txt`
- `assets/awc-documents/correspondence/email_service_request_thread.txt`
- `assets/awc-documents/correspondence/letter_dispute_response_AWC-AJ-100118.docx`
- `assets/awc-documents/correspondence/letter_optout_confirmation_AWC-PV-100204.docx`
- `assets/awc-documents/correspondence/letter_overdue_notice_AWC-SV-100337.docx`

## How to run it

1. Make sure the AWC lab is running (`make all` in the awc-lab bundle).
2. Make sure you have completed the previous workshops — this one builds on them (in particular, the `customers` table must be profiled).
3. Present the deck, then follow the guide step by step.

All data is fictional and generated for training.
