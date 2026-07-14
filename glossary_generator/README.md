# Glossary Generator — the app

Scenario-generic Flask app: scan → suggest → steward review → govern → export
PDC-importable glossary JSONL (+ the Classification Registry).

- **Run:** `./run.sh` (Linux/macOS) · `run.ps1` / `run.bat` (Windows) ·
  `docker compose up --build` → http://127.0.0.1:5000
- **Install a scenario:** unzip PDC-Scenarios' `data_sources/CSCU/cscu-domain-pack.zip`
  (Copper State Credit Union) into this folder — one scenario at a time.
- **Documentation:** lives in [`../docs/`](../docs/) —
  [REFERENCE](../docs/REFERENCE.md) (env vars, drivers, LLM/GPU, API table),
  [GUIDE](../docs/GUIDE.md) (full walkthrough),
  [GUIDE](../docs/GUIDE.md) Part B (against your own PDC instance).
- **Offline test:** `python -m registry.selftest`
