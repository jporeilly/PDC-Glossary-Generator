# Glossary Generator — LLM Setup & Review-Grid Behaviour

*Copper State Credit Union (CSCU) courseware · companion to the Glossary review step*

Two things people ask once the glossary is scanning: how to make the LLM enrichment
faster, and what's safe to click on the review grid without losing work.

---

## 1. Using the local GPU Ollama (the standard CSCU lab setup)

In the CSCU lab the app runs **on the Windows 11 bare-metal host** — the same
machine as the GPUs (dual RTX 3060, 12 GB each) — so the fast setup is simply
the **local** Ollama. No network hop, no firewall rule, and the enriched text
never leaves the machine.

### Configure the app for local GPU Ollama

1. Install/run Ollama on Windows and pull a model sized to your VRAM — with
   12 GB per card a 12–14B model runs fully on GPU (Ollama can also split a
   model across both cards):

   ```
   ollama pull qwen2.5:14b-instruct
   ```

2. Point the app at the **IPv4 loopback** in `glossary_generator/.env`:

   ```
   OLLAMA_URL=http://127.0.0.1:11434
   LLM_MODEL=qwen2.5:14b-instruct
   ```

   Use `127.0.0.1`, **not** `localhost` — on Windows `localhost` can resolve to
   IPv6 `::1` and miss Ollama's IPv4 bind, which makes the header pill show
   Ollama as offline even though it's running.

3. Verify: the app's header pill should read something like
   `Ollama · qwen2.5:14b-instruct · 100% GPU` (the placement comes from
   Ollama's `/api/ps`, the same data as `ollama ps`). A `xx%/yy% CPU/GPU`
   split means the model is too big for VRAM — pick a smaller one or accept
   the slower split.

Do **not** point the app at an Ollama inside the Ubuntu VM — the VM is
CPU-only, and enrichment there is an order of magnitude slower.

### Variant: app running elsewhere, GPUs on this host

If the app ever runs on another machine (e.g. inside the VM), it can still use
this host's GPUs remotely: set a **system** environment variable
`OLLAMA_HOST = 0.0.0.0:11434` on Windows and restart Ollama (it binds only
`127.0.0.1` by default), allow inbound `TCP 11434` through Windows Firewall,
then set the app's Ollama base URL to `http://<windows-host-ip>:11434`.
Trade-offs: the app now depends on this host being up, and the text to be
enriched crosses the network — fine on a lab LAN.

---

## 2. The agent roster — what each AI button does

Every agent follows the same contract: deterministic rules first, the model
only for judgment, proposals constrained to the governed vocabulary, and the
steward always clicks — no agent applies its own output.

| Agent (button) | Proposes | Auto-applies? |
| --- | --- | --- |
| **Enrich with LLM** | rewritten definitions/purposes, name & tag suggestions | Overwrites definitions (snapshot + Revert, see below) |
| **AI suggest (evidence)** | name chip, governed tags, tighten-only sensitivity — grounded in the scan evidence | Tags/sensitivity update rows; the name stays a chip |
| **AI advise** (duplicate groups) | Merge / Disambiguate / Keep separate, per group, from evidence + a live value probe + adjudication | Never — hint on the header only |
| **AI QA definitions** | quality flags + a rewritten definition per flagged row | Never — you click *Use suggestion* per row |
| **AI categorize** | a category from the known set for uncategorized terms | Updates Category (off-list answers discarded) |
| **Suggest expertise** (Govern) | roster expertise keywords | Never — marked unsaved until *Save roster* |
| **Draft policies (AI)** (Govern) | PDC pattern/dictionary rule files from detection seeds | Never — a zip you review and import in PDC |

Everything works with Ollama offline except the model-judgment parts: QA falls
back to its deterministic linter, duplicate advice falls back to the scan
evidence, and enrich/suggest/categorize simply report offline.

---

## 3. Trying different models — Enrich is now non-destructive

**Enrich with LLM** rewrites definitions and purposes (and suggests names/tags) for the
shown/kept terms using the selected model, **overwriting** any previous enrichment in
place. To compare models: pick model A in Settings → **Enrich** → review → pick model B →
**Enrich** again (it overwrites with B's output).

Because that overwrites, the app takes a **snapshot before every Enrich run**. After a run
a **"↶ Revert enrich"** button appears — it restores the definitions/purposes from *just
before* the last Enrich, while keeping your prune / merge / manual edits. So the workflow
is safe:

> Enrich with model A → not better? **Revert enrich** → switch model → Enrich with model B.

The snapshot is per-run (reverting undoes the *last* Enrich only) and is cleared when you
load a different glossary, re-scan, or Reset all.

---

## 4. What's safe vs. destructive on the review grid

| Action | What it does | Loses work? |
| --- | --- | --- |
| **Clear** (by the Filter row) | Resets the filter/search/view only | **No** — terms, edits, enrichment all kept |
| **↶ Revert enrich** | Undoes the **last** Enrich run | Only the last enrichment; edits kept |
| **Reset all** | Reverts the grid to the **raw scan snapshot** | **Yes** — drops edits, enrichment, prune/merge decisions |
| Re-scan / re-harvest the source | Rebuilds the grid from scratch | **Yes** |
| Close / reload the tab without saving | The grid is in-memory | **Yes** — nothing persists until you Save |

**Key point:** the review grid lives in memory. Enrichment and edits are **not persisted**
until you click **Save glossary** (or **Generate JSONL** on the Govern page). So before
experimenting with models or big prune/merge operations, **Save glossary** on a state you
like — you can reload it if an experiment goes worse.

- **Clear** = filter reset, always safe.
- **Reset all** = the destructive "back to raw scan" button; use deliberately.
- **Save glossary** = your checkpoint; save early, save before experiments.
