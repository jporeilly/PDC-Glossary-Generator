# Courseware — one workshop set per scenario

| Set | Scenario | Contents |
| --- | --- | --- |
| [`CSCU/`](CSCU/) | **Copper State Credit Union** — financial services | Workshops 00–05 (Preflight → Data Identification), the Glossary Generator app workshop, topic notes, and the **Technical Track** (identification engine, build-your-own methods, similarity & ML) |
| [`RETAIL/`](RETAIL/) | **Canyon Trail Outfitters** — retail | Workshops 00–05 with the CTO cast, the PCI full-PAN and marketing-opt-out planted defects, and the loyalty-number custom pattern |
| [`HEALTH/`](HEALTH/) | **Lakeshore Health Partners** — healthcare | Workshops 00–05 with the LHP cast, HIPAA framing, the SSN-in-notes free-text blind spot, the unauthorized-disclosure rule, and the MRN custom pattern |

Each workshop folder carries a markdown guide master (authoritative, with
`[SCREENSHOT]` markers for captures on that scenario's lab), a `.docx`
generated from it in the course design (`<set>/tools/build-docx.py`), and its
assets. Scenario data (lab SQL, documents, domain pack, bulk-load CSV) lives
in `data_sources/<ID>/`; the shared lab stack in `data_sources/lab/`.

The Technical Track is authored on the CSCU scenario and transfers directly
to the others. Additional scenarios plug in the same way: a
`courseware/<ID>/` set beside a `data_sources/<ID>/` data folder.

*All scenario data is fictional and generated for training.*
