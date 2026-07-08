# Glossary Generator — LLM Setup & Review-Grid Behaviour

*Copper State Credit Union (CSCU) courseware · companion to the Glossary review step*

Two things people ask once the glossary is scanning: how to make the LLM enrichment
faster, and what's safe to click on the review grid without losing work.

---

## 1. Pointing the LLM at a GPU host (faster enrichment)

By default the app calls **Ollama on the machine it runs on**. On the CSCU lab VM that's
CPU-only, so you're limited to small models and it's slow. If you have a machine with
GPUs on the same network (e.g. the Windows bare-metal host with dual RTX 3060s), point
the app at *that* Ollama instead — the enrichment runs on the GPUs and you can use larger
models.

### On the GPU host (Windows)

1. Make Ollama listen on the network, not just localhost. Add a **system** environment
   variable `OLLAMA_HOST = 0.0.0.0:11434`, then **restart Ollama** (quit from the tray
   and relaunch, or restart the service). By default it binds `127.0.0.1:11434`, which
   rejects connections from the VM.
2. Allow inbound `TCP 11434` through **Windows Firewall** (an inbound rule; Private
   network scope is enough if the VM is on a private adapter). Blocked port 11434 is the
   most common failure.
3. Pull the model you want to use there: `ollama pull <model>`. With 12 GB per GPU a
   12–14B model (or a larger quantised one) runs comfortably.

### On the VM (the app)

1. Confirm the host is reachable: `curl http://<host-ip>:11434/api/tags` — you should get
   JSON listing the models. If it hangs/refuses, it's the firewall or the wrong address.
2. In the app's **Settings → LLM**, change the Ollama base URL from
   `http://localhost:11434` to `http://<host-ip>:11434`, and select a model that's pulled
   on that host.

**Finding `<host-ip>`** depends on the VM networking:
- **Bridged** VM → the Windows machine's LAN IP (`ipconfig` on Windows).
- **NAT** → the host is usually a gateway address (e.g. VirtualBox `10.0.2.2`); `ip route`
  on the VM shows the default gateway.
- **Host-only adapter** → the host's IP on that adapter.

**Trade-offs (call out in courseware):** this makes the app depend on the GPU host being
up and reachable, and it sends the text to be enriched over the network. Fine on a lab
LAN; for a self-contained VM demo, keep the local CPU model. Leave the small local model
configured as a fallback.

---

## 2. Trying different models — Enrich is now non-destructive

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

## 3. What's safe vs. destructive on the review grid

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
