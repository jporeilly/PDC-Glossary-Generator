# Metadata Similarity & ML Inference in PDC (CSCU)

*Copper State Credit Union scenario · PDC 11.0.0 · Technical Track Module 04*

**Primary role:** Platform administrators, solution architects, technical stewards
**Estimated time:** 60 min

## Workshop overview

This workshop covers two tightly related capabilities in Pentaho Data
Catalog: the metadata **Similarity Score** that drives glossary suggestions,
and the **machine-learning inference layer** those suggestions depend on. It
is deliberately split from the steward-facing glossary modules because it
serves a different audience and a different layer of the platform — the
engine room rather than the cockpit.

> **The motivating question.** Open a column such as `mbr_no` in the CSCU
> catalog, switch to Glossary → Suggested, and you may see nothing but "No
> data to display." That empty pane is rarely a broken feature. It usually
> means the similarity job has not run, or the AI/ML layer it relies on has
> not been configured. By the end of this workshop you will be able to make
> both true.

### Who this is for

- Platform administrators who own the PDC deployment and its environment
  configuration.
- Solution architects designing how governance and AI features fit together.
- Technical data stewards who run similarity and curate the resulting
  suggestions.

### Prerequisites

- A running PDC 11.0.0 environment with at least one connected data source
  (the CSCU `cscu_core` schema is used throughout).
- Access to the deployment's environment configuration (the `conf/.env`
  layer).
- An inference endpoint you can point PDC at — a local model server or a
  hosted, OpenAI-compatible API. This guide stays backend-agnostic. (In the
  CSCU lab, the Windows host's Ollama at `http://192.168.1.200:11434/v1`
  serves an OpenAI-compatible API and runs models on dual RTX 3060s.)
- Familiarity with PDC glossaries, terms, and the term-to-column link
  (Workshop 3).

### Learning objectives

1. Explain what the metadata Similarity Score is and how it is produced.
2. Run the similarity process and review suggestions across columns,
   tables/files, and terms.
3. Tune the score threshold and apply the approve/reject workflow
   responsibly.
4. Stand up the ML inference layer and verify it end to end.
5. Diagnose an empty Suggested pane using a repeatable troubleshooting chain.

### Where it fits in the Technical Track

Place this module alongside Data Identification (02), Build-Your-Own (03),
and the Glossary Generator App (01). Part A (the Similarity Score) is
steward-facing and can be taught on its own. Part B (ML inference) is
administrator-facing and doubles as a platform prerequisite — the same AI/ML
layer also powers the PDC chatbot, so configuring it once benefits more than
the similarity feature. The Glossary Generator app applies the same principle
to *vocabulary*: its **Find similar** feature proposes similarity-scored term
merges, with the steward deciding.

## The concept: ML-driven metadata similarity

Metadata similarity uses machine learning to identify and suggest similar
tables, columns, and business terms across the data landscape. Rather than
matching on column names alone, it scores candidates on metadata structure
and meaning, so semantically equivalent fields can be matched even when their
names differ — `mbr_id` in one table and `member_ref` in another. The
practical payoff is threefold: more consistent term tagging, less duplicated
effort, and a direct contribution to data trust.

> **Key idea.** Similarity is a **batch process**, not a live lookup.
> Suggestions appear only after the similarity job has run. Opening the
> Suggested pane does not generate matches — it displays the results of the
> most recent run.

## Part A — Working with the Similarity Score

### Running the metadata similarity process

Run the process from the administration area before expecting any
suggestions to appear:

1. **Open Management.** From the left navigation, choose Management to open
   the Manage Your Environment page.
2. **Configure Similarity.** On the Metadata Similarity card, click
   Configure Similarity to open the Metadata Similarity Configuration page.
3. **Select scope.** Choose the databases to analyze. Optionally select one
   or more business terms to focus the run.
4. **Apply.** Click Apply. The metadata similarity process (handled by the
   Miscellaneous Jobs Worker) begins.
5. **Monitor.** Track the run on the Workers page until it completes; only
   then will suggestions populate.
   `[SCREENSHOT: Metadata Similarity Configuration — cscu_core scoped]`

> **Remember.** The run is the prerequisite that everything else depends on.
> With no completed run, the Suggested pane stays empty no matter how you set
> the threshold.

### Reviewing suggestions

Once a run completes, suggestions surface in three places depending on what
you select:

| You select | Where to look | What approval does |
| --- | --- | --- |
| A column | Glossary tab → Suggested pane | Assigns the matched term to the column; it then appears under Elements |
| A table or file | Similar Items tab | Updates the suggestion's status in place |
| A business term | Data Elements tab | Assigns the term to the matched column |

In every case the list shows each candidate with a similarity score and a
status. Higher scores indicate a stronger match based on metadata structure
and meaning.

### Score threshold mechanics

The Suggested and Similar Items lists contain only items whose similarity
score is above the threshold, which defaults to 0.5. Adjust the Score
Threshold box and click Submit to re-filter:

- **Lower** the score to see more, more loosely matched items.
- **Raise** the score to see fewer, more closely matched items.

> **Common misconception.** The threshold filters an already-computed result
> set — it does not generate matches. Lowering it to 0.2 still shows nothing
> if the similarity job never ran. Tune the score to *read* results, not to
> create them.

### The approve / reject workflow

Review each suggestion and act on it with the checkboxes:

- **Approve** accepts the match. On a column's Suggested pane, approval
  assigns the term to the column.
- **Reject** discards the suggestion from the current list.

> **Caution — reject is permanent.** A rejected item is excluded from future
> similarity suggestions for that asset. Reject deliberately to remove
> genuinely wrong matches, not as a quick way to clear a cluttered list. On
> CSCU's status columns this matters: every `*_status` enum looks alike to
> the engine, so expect loose matches there and reject only the truly wrong
> ones.

You can also use the Show Approved and Show Rejected filters to revisit
prior decisions.

### How suggestions feed the Trust Score

The calculated Trust Score weighs four inputs. Approving a similarity
suggestion flips one of them from absent to present:

| Trust Score input | What it measures |
| --- | --- |
| Data Quality | Completeness, accuracy, validity, uniqueness, consistency |
| User Ratings | 1–5 star input from data consumers |
| Data Lineage | Whether lineage is verified |
| Glossary Term | Whether a term is assigned — set when you approve a suggestion |

**CSCU example.** Approve a strong match for `mbr_no` and the `members`
table earns the glossary-term credit on its next Trust Score calculation —
the AI-assisted path to the same term-to-column link you created by hand in
Workshop 3.

### Lab A — Suggesting a term for mbr_no

1. **Run similarity.** From Management → Metadata Similarity → Configure
   Similarity, select the `cscu_core` database and click Apply. Wait for the
   Workers page to show completion.
2. **Open the column.** In Data Canvas, navigate to CopperState_Core_Banking
   → members → `mbr_no`, then open the Glossary tab and select the Suggested
   pane.
3. **Tune the threshold.** Start at 0.5. If you see nothing, lower it and
   Submit to widen the result set.
4. **Approve.** Select a high-scoring, correct match (the **Member Number**
   term) and click Approve. Confirm the term now appears on the Elements
   pane.
   `[SCREENSHOT: Suggested pane — Member Number approved on mbr_no]`
5. **Confirm trust impact.** Re-run the Trust Score calculation for the
   members table and note the glossary-term input is now satisfied.

## Part B — Setting up ML inference

### The AI/ML architecture

Similarity scoring and the PDC chatbot share one machine-learning layer.
Three services do the heavy lifting:

| Service | Role |
| --- | --- |
| ml-gateway-service | Routes ML requests to the configured inference backend |
| psc-ml-models | Manages ML model metadata and the similarity workload |
| pdc-chatbot-backend | Shares the same layer — configured once, benefits both features |

### Service profiles

None of the ML services deploy unless their profiles are active. Confirm that
`COMPOSE_PROFILES` includes both `ml-models` and `ai-ml` (alongside the other
profiles your deployment uses). If these are absent, the similarity and
inference services simply never start — a frequent root cause of an empty
Suggested pane.

### The inference configuration

Three environment variables connect PDC to your inference backend. All three
are empty by default and must be populated when using external LLM services:

| Variable | Purpose | Default |
| --- | --- | --- |
| ML_LLM_MODEL | The model identifier your backend serves | (empty) |
| ML_LLM_API_KEY | Credential for the inference service | (empty) |
| ML_LLM_INFERENCE_BASE_URL | The endpoint PDC calls for inference | (empty) |

> **Backend-agnostic by design.** Point these three values at whatever
> OpenAI-compatible endpoint you operate — a self-hosted model server or a
> hosted API. PDC does not care which provider you choose, only that the
> three values resolve to a reachable, authenticated endpoint. In the CSCU
> lab a natural choice is the Windows host's Ollama
> (`http://192.168.1.200:11434/v1`, any non-empty API key, a pulled model
> such as `qwen2.5:14b-instruct`) — the same GPUs that accelerate the
> Glossary Generator's enrichment.

### Supporting ML parameters

These tune behavior once a backend is connected. The defaults are sensible to
start; revisit them when you know your model and typical document sizes:

| Variable | Default | Meaning |
| --- | --- | --- |
| ML_CUSTOM_TOKENS | 6000 | Token limit for an ML operation |
| ML_TOKEN_WINDOW_SIZE | 8000 | Context window size for the model |
| PDC_WS_DEFAULT_MAX_FILE_SIZE_FOR_ML | 10 MB | Largest file sent for ML processing |
| ML_BENTO_TIME_OUT | 6000 | Serving timeout before a run gives up |

### Where configuration lives

Defaults ship in `.env.default`. Override sensitive or environment-specific
values in your client configuration layer (the `conf/.env` file referenced by
`PDC_CLIENT_PATH`). Keep secrets such as `ML_LLM_API_KEY` out of the defaults
and managed through your environment's secret-handling practice.

### Verifying the setup

1. **Profiles.** Confirm `ml-models` and `ai-ml` are active and the ML
   services are running.
2. **Inference values.** Confirm all three `ML_LLM_*` variables are
   populated.
3. **Reachability.** From the PDC host, confirm the inference base URL is
   reachable and authenticates.
4. **End-to-end.** Run similarity, watch the Workers page, then confirm the
   Suggested pane populates for a known column.

### Troubleshooting the empty Suggested pane

Walk the chain from top to bottom. The first check that fails is almost
always the cause:

| # | Check | If it fails |
| --- | --- | --- |
| 1 | ml-models and ai-ml profiles active? | Enable the profiles and redeploy the stack |
| 2 | All three ML_LLM_* values populated? | Set the model, key, and base URL |
| 3 | Inference endpoint reachable from PDC? | Fix networking, DNS, or credentials |
| 4 | Similarity job completed on Workers page? | Run it from Management → Configure Similarity |
| 5 | Threshold not set too high? | Lower the score and click Submit |
| 6 | Suggestions not all previously rejected? | Past rejects are excluded permanently; re-run scope or check another asset |

### Lab B — Wiring inference and confirming suggestions

1. **Enable profiles.** Ensure `ml-models` and `ai-ml` are in
   `COMPOSE_PROFILES`; redeploy if you changed them.
2. **Set inference.** Populate `ML_LLM_MODEL`, `ML_LLM_API_KEY`, and
   `ML_LLM_INFERENCE_BASE_URL` for your chosen backend.
3. **Verify reachability.** Confirm the PDC host can reach and authenticate
   against the endpoint.
4. **Re-run similarity.** Run the process across `cscu_core` and wait for
   completion.
5. **Confirm.** Reopen `mbr_no` → Glossary → Suggested and verify matches now
   appear. The empty pane from the cold open is resolved.
   `[SCREENSHOT: Suggested pane populated after inference wiring]`

## Appendix A — ML configuration reference

| Variable | Default | Notes |
| --- | --- | --- |
| COMPOSE_PROFILES | — | Must include ml-models and ai-ml |
| ML_LLM_MODEL | (empty) | Model identifier; set for external LLM services |
| ML_LLM_API_KEY | (empty) | Credential for the inference service |
| ML_LLM_INFERENCE_BASE_URL | (empty) | Inference endpoint URL |
| ML_CUSTOM_TOKENS | 6000 | Token limit per ML operation |
| ML_TOKEN_WINDOW_SIZE | 8000 | Context window size |
| PDC_WS_DEFAULT_MAX_FILE_SIZE_FOR_ML | 10485760 | Max bytes (10 MB) per file for ML |
| ML_BENTO_TIME_OUT | 6000 | ML serving timeout |

Variable names should be confirmed against your PDC 11.0.0 deployment's
configuration files.

## Appendix B — Facilitator checklist

- Environment reachable; CSCU `cscu_core` source connected and profiled.
- `ml-models` and `ai-ml` profiles active before the session.
- Inference backend chosen and the three `ML_LLM_*` values set.
- One similarity run completed in advance as a known-good demo.
- `members.mbr_no` identified as the live worked example (term: Member
  Number).

All Copper State Credit Union data is fictional and generated for training.
