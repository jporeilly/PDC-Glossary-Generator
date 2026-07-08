# CHANGES — corrected course bundle

## 1 · Numbering corrected (glossary-first)

The materials are authored **glossary-first**; a few files had been renumbered to a
scan-first scheme, creating a duplicate "Workshop 3". Fixed:

- **`README.md` (master):** workshop table reordered to glossary-first to match the guides,
  decks, and course plan — Build the Business Glossary is **3**, Profile **4**, Protect
  Sensitive Data **5**, Discover & Search **6** (7–11 unchanged). Added a note explaining the
  manual vs app-driven glossary paths.
- **READMEs 04 / 05 / 06:** retitled to Workshop 4 / 5 / 6 and filename references fixed.
  (Folder 03's README was already correct. The guides, decks, and `AWC-PDC-Course-Plan.docx`
  were already glossary-first — left untouched.)
- The Generator app was buried in `Workshop-03-Glossary-Terms/AWC project/`; it was lifted
  out into its own top-level folder (see §3 for its final name).

## 2 · Course Overview rebuilt + technical track + badges

- **`Course-Overview-and-Outcomes.pptx`:** the agenda is now **glossary-first** — the
  "Journey" slide reordered (with its step icons rotated to match the new labels) and the
  "How we'll spend the time" slide regrouped. Added a **technical Data Identification**
  deep-dive slide (Dictionaries by content | Patterns by shape) for the technical track.
  *(This supersedes the earlier "still needs attention" note — the overview is now fixed.)*
- **Process badges** added to all 11 workshop **guides** and all 11 **decks** (title blocks).
  The four scan-chain steps read `PDC PROCESS · …` (Metadata Ingest, Data Profiling · Trust
  Score, Data Identification · PII); the rest read `PDC · …` for the feature area.
- **New:** `Lab-Build-Your-Own-AWC-Dictionary-and-Pattern.docx` — a hands-on technical lab
  extending the Data Identification module (author a dictionary + a pattern, run a policy).
- Refreshed `Data-Identification-Guide.docx` and `Data-Identification-Technical.pptx`.

## 3 · Numbering made consistent (padding + de-collision)

- **All workshop files padded to two digits** to match their folders:
  `Workshop-0N-*.docx/.pptx` (were `Workshop-N-*`). Per-folder READMEs updated to match.
  Folders and files now sort cleanly 01 → 11.
- **App folder renamed** `Workshop-5-Glossary-Generator-App/` → **`Supplement-Glossary-Generator-App/`**.
  It had collided with the BA path's **Workshop 5 — Protect Sensitive Data**. The app is a
  *supplement / app-driven alternative to the manual glossary (Workshop 3)*, not a numbered
  BA workshop; it runs at the fifth step of the scan-first chain (after Data Identification).
  Its README was reworded to match.

## 4 · Technical track grouped + Lab deck added

- Created **`Technical-Track/`** to give the technical materials a clear home (they are
  not numbered BA workshops). Three numbered modules, each a deck + guide + README:
  `01-Data-Identification/`, `02-Build-Your-Own-Dictionary-and-Pattern/`,
  `03-Glossary-Generator-App/`. The loose top-level Data-Identification files and the lab
  moved in; the former `Supplement-Glossary-Generator-App/` became module 03.
- **New:** `…/02-…/Lab-Build-Your-Own-AWC-Dictionary-and-Pattern-Deck.pptx` — the lab now
  has a walkthrough deck to match the guide (the other modules already had both).
- Master `README.md` gained a **Technical track** section; the glossary note repoints the
  app to `Technical-Track/03-Glossary-Generator-App/`.
