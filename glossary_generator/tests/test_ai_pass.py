"""The combined AI pass: one call per row for every LLM-decidable field, under
the same guardrails the separate agents apply."""
from ai import llm
from conftest import make_row


class _FakeLLM:
    """Stand in for the model so the guardrails are tested, not Ollama."""
    def __init__(self, reply):
        self.reply = reply
        self.calls = 0

    def __call__(self, prompt, model=None, num_gpu=None, **kw):
        self.calls += 1
        return self.reply


def _run(monkeypatch, reply, rows, allow=("customer", "identifier"), cats=("Customer",)):
    fake = _FakeLLM(reply)
    monkeypatch.setattr(llm, "_complete_json", fake)
    monkeypatch.setattr(llm, "status", lambda m=None: {"online": True})
    monkeypatch.setattr(llm, "_warm", lambda m=None: None)
    out, counts, used = llm.ai_pass_rows(rows, allow_tags=list(allow),
                                         categories=list(cats), workers=1)
    return out, counts, used, fake


class TestAiPass:
    """A flat (non-items) reply exercises the per-row fallback — deliberate:
       one malformed batch answer must never drop a chunk."""

    def test_one_call_covers_a_whole_batch(self, monkeypatch):
        """The point of the pass: N rows x every field in ONE call."""
        rows = [make_row("Cust Acct No", "public.customers.cust_acct_no",
                         Definition="", Purpose="", Category="", Suggested_Tags=""),
                make_row("Email", "public.customers.email",
                         Definition="", Purpose="", Category="", Suggested_Tags="")]
        reply = {"items": [
            {"n": 1, "name": "Customer Account Number",
             "definition": "The number identifying a customer's billing account.",
             "purpose": "Links every bill and payment to one customer.",
             "category": "Customer", "tags": ["customer", "identifier"],
             "rationale": "column holds a formatted account number"},
            {"n": 2, "name": "Email", "definition": "A customer's contact address.",
             "purpose": "Reaches the customer about their account.",
             "category": "Customer", "tags": ["customer"]},
        ]}
        out, counts, used, fake = _run(monkeypatch, reply, rows)
        assert used and fake.calls == 1, "one call, two rows, every field"
        assert out[1]["Definition"].startswith("A customer's contact address")
        r = out[0]
        assert r["Definition"].startswith("The number identifying")
        assert r["Purpose"].startswith("Links every bill")
        assert r["Suggested_Name"] == "Customer Account Number"
        assert r["Term"] == "Cust Acct No", "the name is a proposal, never an overwrite"
        assert r["Category"] == "Customer"
        assert set(r["Suggested_Tags"].split(";")) == {"customer", "identifier"}
        assert counts == {"definitions": 2, "purposes": 2, "names": 1,
                          "tags": 2, "category": 2}, "name repeats unchanged for row 2"

    def test_ungoverned_tags_are_dropped(self, monkeypatch):
        rows = [make_row("Email", "public.customers.email", Suggested_Tags="")]
        out, _, _, _ = _run(monkeypatch, {"tags": ["customer", "make-believe"]}, rows)
        assert out[0]["Suggested_Tags"] == "customer"

    def test_existing_category_is_never_overwritten(self, monkeypatch):
        rows = [make_row("Email", "public.customers.email", Category="Governance")]
        out, counts, _, _ = _run(monkeypatch, {"category": "Customer"}, rows,
                                 cats=("Customer", "Governance"))
        assert out[0]["Category"] == "Governance"
        assert counts["category"] == 0

    def test_model_cannot_touch_sensitivity_or_pii(self, monkeypatch):
        rows = [make_row("Email", "public.customers.email",
                         Sensitivity="LOW", PII_Category="")]
        reply = {"sensitivity": "HIGH", "PII_Category": "CONTACT_INFO",
                 "pii": "CONTACT_INFO", "definition": "A contact address."}
        out, _, _, _ = _run(monkeypatch, reply, rows)
        assert out[0]["Sensitivity"] == "LOW", "sensitivity stays deterministic"
        assert out[0]["PII_Category"] == "", "PII comes from the scan, not the model"

    def test_bad_batch_reply_falls_back_to_per_row(self, monkeypatch):
        rows = [make_row("Email", "public.customers.email", Definition=""),
                make_row("Phone", "public.customers.phone", Definition="")]
        out, _, _, fake = _run(monkeypatch, {"definition": "A contact value."}, rows)
        assert fake.calls == 3, "1 batch attempt + 1 call per row"
        assert all(r["Definition"] == "A contact value." for r in out)

    def test_linter_flag_reaches_the_prompt_as_a_rewrite_order(self, monkeypatch):
        """A QA flag must become the model's instruction — a flag the steward
           can't act on is noise (and the judge that used to rewrite is gone).
           TWO rows, so this exercises the BATCH prompt's wording — a single
           row now routes to the rich per-row prompt, whose flag handling is
           covered by test_per_row_fallback_states_the_flag_once."""
        seen = {}

        def capture(prompt, **kw):
            seen["prompt"] = prompt
            return {"items": [{"n": 1, "definition": "A specific, useful sentence."},
                              {"n": 2, "definition": "A customer's contact address."}]}

        monkeypatch.setattr(llm, "_complete_json", capture)
        monkeypatch.setattr(llm, "status", lambda m=None: {"online": True})
        monkeypatch.setattr(llm, "_warm", lambda m=None: None)
        rows = [make_row("Severity", "public.account_alerts.severity",
                         Definition="Severity associated with a account alert record.",
                         QA_Issues="generic;echoes the term"),
                make_row("Email", "public.customers.email", Definition="")]
        out, _, _ = llm.ai_pass_rows(rows, allow_tags=[], categories=[], workers=1)
        assert "REWRITE REQUIRED" in seen["prompt"]
        assert "generic, echoes the term" in seen["prompt"]
        assert out[0]["Definition"] == "A specific, useful sentence."

    def test_per_row_fallback_states_the_flag_once(self, monkeypatch):
        """The fallback built its evidence list with the QA_Issues block pasted
           twice, so a flagged row was told the same thing two times in one
           prompt. Harmless, but it wastes the budget and reads as emphasis."""
        seen = []

        def capture(prompt, **kw):
            seen.append(prompt)
            return {"definition": "A specific, useful sentence."}   # flat = fallback

        monkeypatch.setattr(llm, "_complete_json", capture)
        monkeypatch.setattr(llm, "status", lambda m=None: {"online": True})
        monkeypatch.setattr(llm, "_warm", lambda m=None: None)
        rows = [make_row("Severity", "public.account_alerts.severity",
                         Definition="Severity associated with a account alert record.",
                         QA_Issues="generic;echoes the term")]
        llm.ai_pass_rows(rows, allow_tags=[], categories=[], workers=1)
        per_row = seen[-1]
        assert per_row.count("the current definition was flagged as:") == 1
        assert "generic, echoes the term" in per_row

    def test_scan_reasoning_reaches_the_batch_prompt(self, monkeypatch):
        """The retired evidence agent leaned on Suggested_Reason; the batched
           pass that replaced it did not send it, so absorbing that agent meant
           absorbing its evidence too."""
        seen = []

        def capture(prompt, **kw):
            seen.append(prompt)
            return {"items": [{"n": 1, "definition": "A specific, useful sentence."}]}

        monkeypatch.setattr(llm, "_complete_json", capture)
        monkeypatch.setattr(llm, "status", lambda m=None: {"online": True})
        monkeypatch.setattr(llm, "_warm", lambda m=None: None)
        rows = [make_row("Account Number", "public.customers.account_number",
                         Suggested_Reason="matches the AWC-<city>-<n> account format")]
        llm.ai_pass_rows(rows, allow_tags=[], categories=[], workers=1)
        assert "scan reasoning" in seen[0]
        assert "AWC-<city>-<n> account format" in seen[0]

    def test_the_pass_is_not_fed_its_own_previous_rationale(self, monkeypatch):
        """ai_pass_rows appends 'AI(pass): …' to Suggested_Reason, so sending
           that field raw would hand a second run its own last answer as if the
           scan had observed it. Only the scan's half is evidence."""
        seen = []

        def capture(prompt, **kw):
            seen.append(prompt)
            return {"items": [{"n": 1, "definition": "A specific, useful sentence."}]}

        monkeypatch.setattr(llm, "_complete_json", capture)
        monkeypatch.setattr(llm, "status", lambda m=None: {"online": True})
        monkeypatch.setattr(llm, "_warm", lambda m=None: None)
        rows = [make_row("Account Number", "public.customers.account_number",
                         Suggested_Reason="formatted account code · AI(pass): "
                                          "the column holds billing identifiers")]
        llm.ai_pass_rows(rows, allow_tags=[], categories=[], workers=1)
        assert "formatted account code" in seen[0]
        assert "AI(pass)" not in seen[0]
        assert "holds billing identifiers" not in seen[0]

    def test_offline_is_a_no_op(self, monkeypatch):
        monkeypatch.setattr(llm, "status", lambda m=None: {"online": False})
        rows = [make_row("Email", "public.customers.email")]
        out, counts, used = llm.ai_pass_rows(rows, allow_tags=[], categories=[])
        assert used is False and out == rows
        assert all(v == 0 for v in counts.values())


class TestAiPassEndpoint:
    def test_a_cleared_qa_flag_comes_back_as_empty_not_missing(self, client, monkeypatch):
        """The UI merges each returned row over its working copy with a spread,
           so a DELETED key is invisible — the stale flag would survive under a
           definition the model had just rewritten. The cleared flag has to be
           sent as an explicit empty value."""
        monkeypatch.setattr(llm, "status", lambda m=None: {"online": True})
        monkeypatch.setattr(llm, "_warm", lambda m=None: None)
        monkeypatch.setattr(llm, "_complete_json", lambda *a, **k: {
            "definition": "The full name of the member legally responsible for the account."})
        r = client.post("/api/ai-pass", json={"rows": [make_row(
            "Member Name", "cscu_core.members.member_name",
            Definition="Member Name associated with a member record.",
            QA_Issues="generic scan template - says nothing specific to this column")]})
        assert r.status_code == 200
        row = r.json()["rows"][0]
        assert "QA_Issues" in row, "the key must be PRESENT so a spread-merge clears it"
        assert row["QA_Issues"] == "", "rewritten to something specific -> no longer flagged"


    def test_route_returns_rows_and_counts(self, client, monkeypatch):
        monkeypatch.setattr(llm, "status", lambda m=None: {"online": True})
        monkeypatch.setattr(llm, "_warm", lambda m=None: None)
        monkeypatch.setattr(llm, "_complete_json",
                            lambda *a, **k: {"definition": "A customer's email address."})
        r = client.post("/api/ai-pass", json={
            "rows": [make_row("Email", "public.customers.email", Definition="")]})
        assert r.status_code == 200
        body = r.json()
        assert body["rows"][0]["Definition"] == "A customer's email address."
        assert body["updated"]["definitions"] == 1


class TestBatchOfOneIsThePerRowPrompt:
    """Settings' batch size 1 is a quality dial, not a smaller batch: a
       single-row batch must take the RICH per-row prompt (_ai_pass_one) with
       its full evidence and instructions, never the compressed pipe-format.
       That routing is the guarantee behind "AI review quality, sweep-wide" -
       field-caught when batched definitions flattened to templates while
       AI review on the same rows wrote real ones."""

    def test_single_row_batch_routes_to_the_rich_prompt(self, monkeypatch):
        captured = []

        def capture(prompt, model=None, num_gpu=None, **kw):
            captured.append(prompt)
            return {"definition": "A precise thing."}

        monkeypatch.setattr(llm, "_complete_json", capture)
        row = make_row("Gis", "awc-documents/gis/asset_inventory.csv",
                       Definition="Object 'asset_inventory.csv'",
                       Purpose="Holds Gis data", Category="", Suggested_Tags="")
        out = llm._ai_pass_batch([row], ["customer"], ["Infrastructure"])
        assert len(out) == 1 and out[0]["definition"] == "A precise thing."
        p = captured[0]
        assert "For ONE database column" in p, "one row must take the per-row prompt"
        assert "not a restatement of the definition" in p
        assert "For EACH numbered column" not in p

    def test_multi_row_batch_carries_full_drafts_and_anti_echo(self, monkeypatch):
        captured = []

        def capture(prompt, model=None, num_gpu=None, **kw):
            captured.append(prompt)
            return {"items": [{"n": 1, "definition": "A."},
                              {"n": 2, "definition": "B."}]}

        monkeypatch.setattr(llm, "_complete_json", capture)
        rows = [make_row("A", "t.a", Definition="d" * 300, Purpose="",
                         Category="", Suggested_Tags=""),
                make_row("B", "t.b", Definition="", Purpose="",
                         Category="", Suggested_Tags="")]
        llm._ai_pass_batch(rows, [], [])
        p = captured[0]
        assert "For EACH numbered column" in p
        assert "d" * 220 in p and "d" * 221 not in p, \
            "draft definition travels at 220 chars (was 120 - starved the model)"
        assert "NOT a restatement of the definition" in p
        assert "do NOT reuse sentence" in p, "the anti-template-rhythm instruction"
