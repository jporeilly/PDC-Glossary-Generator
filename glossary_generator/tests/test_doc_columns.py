"""Terms from file contents — the app-side parity of PDC cataloging a CSV's
columns as COLUMN entities. Field origin: a direct minio scan produced 5
folder terms while PDC's harvest of the same bucket carried every column
("would expect a lot more Terms for Documents"). Everything here is
estate-agnostic: whatever columns the files declare."""
from ai import llm  # noqa: F401  (keeps import side effects consistent with the suite)
from engine import suggester


CSV = (b"asset_id,asset_type,latitude,longitude,install_date\n"
       b"AST-000101,pump,33.44,-112.07,2019-03-01\n"
       b"AST-000102,valve,33.45,-112.08,2020-07-15\n"
       b"AST-000103,pump,33.46,-112.09,2021-01-20\n"
       b"AST-000104,tank,33.47,-112.10,2018-11-05\n"
       b"AST-000105,pump,33.48,-112.11,2022-02-14\n")

JSONL = (b'{"export_metadata": {"export_date": "2026-05-14", "units": {"flow": "gpm"}}, '
         b'"readings": [{"site": "PV-01", "flow_gpm": 812.5, "alarm": false}]}\n')


class TestExtractDocumentColumns:
    def test_csv_header_and_values(self):
        cols = suggester.extract_document_columns(CSV, "csv")
        names = [c["column"] for c in cols]
        assert names == ["asset_id", "asset_type", "latitude", "longitude", "install_date"]
        byname = {c["column"]: c["values"] for c in cols}
        assert byname["asset_id"][0] == "AST-000101"
        assert len(byname["asset_type"]) == 5

    def test_json_flattens_to_dotted_paths(self):
        cols = suggester.extract_document_columns(JSONL, "jsonl")
        names = {c["column"] for c in cols}
        assert "export_metadata.export_date" in names
        assert "export_metadata.units.flow" in names
        assert "readings.flow_gpm" in names and "readings.alarm" in names

    def test_unprofilable_formats_declare_nothing(self):
        assert suggester.extract_document_columns(b"%PDF-1.7 ...", "pdf") == []
        assert suggester.extract_document_columns(b"", "csv") == []


class TestSuggestDocumentColumns:
    def _rows(self):
        files = [{"key": "gis/asset_inventory.csv", "rel": "gis/asset_inventory.csv",
                  "bucket": "awc-documents", "folder": "gis",
                  "base": "asset_inventory.csv", "ext": "csv",
                  "columns": suggester.extract_document_columns(CSV, "csv")},
                 {"key": "scada/pv.jsonl", "rel": "scada/pv.jsonl",
                  "bucket": "awc-documents", "folder": "scada", "base": "pv.jsonl",
                  "ext": "jsonl",
                  "columns": suggester.extract_document_columns(JSONL, "jsonl")}]
        return suggester.suggest_document_columns(files, "awc-documents")

    def test_columns_become_leaf_named_terms_with_evidence(self):
        rows = self._rows()
        assert rows, "columns must become candidate terms"
        by_term = {r["Term"]: r for r in rows}
        # leaf naming: a dotted document path reads as a business term
        assert "Flow Gpm" in by_term, sorted(by_term)
        # the SAME deterministic profiler as a SQL column: the coded asset id
        # carries an induced value pattern
        aid = next((r for r in rows if "asset_id" in str(r.get("Source_Column", ""))), None)
        assert aid is not None
        assert (aid.get("Value_Pattern") or "").startswith("^AST"), \
            "coded values must profile into a pattern, exactly like a database column"

    def test_envelope_fields_arrive_pruned_not_missing(self):
        rows = self._rows()
        env = [r for r in rows if "export_metadata" in str(r.get("Source_Column", ""))]
        assert env, "envelope fields still surface (recoverable), never vanish"
        assert all(r.get("Prune_Reason") for r in env), \
            "…but arrive auto-pruned as document envelope, not as business terms"

    def test_no_files_no_rows(self):
        assert suggester.suggest_document_columns([], "b") == []
        assert suggester.suggest_document_columns([{"rel": "a.pdf", "ext": "pdf"}], "b") == []
