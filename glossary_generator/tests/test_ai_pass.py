"""The combined AI pass: one call per row for every LLM-decidable field, under
the same guardrails the separate agents apply."""
import llm
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
           can't act on is noise (and the judge that used to rewrite is gone)."""
        seen = {}

        def capture(prompt, **kw):
            seen["prompt"] = prompt
            return {"items": [{"n": 1, "definition": "A specific, useful sentence."}]}

        monkeypatch.setattr(llm, "_complete_json", capture)
        monkeypatch.setattr(llm, "status", lambda m=None: {"online": True})
        monkeypatch.setattr(llm, "_warm", lambda m=None: None)
        rows = [make_row("Severity", "public.account_alerts.severity",
                         Definition="Severity associated with a account alert record.",
                         QA_Issues="generic;echoes the term")]
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

    def test_offline_is_a_no_op(self, monkeypatch):
        monkeypatch.setattr(llm, "status", lambda m=None: {"online": False})
        rows = [make_row("Email", "public.customers.email")]
        out, counts, used = llm.ai_pass_rows(rows, allow_tags=[], categories=[])
        assert used is False and out == rows
        assert all(v == 0 for v in counts.values())


class TestAiPassEndpoint:
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
