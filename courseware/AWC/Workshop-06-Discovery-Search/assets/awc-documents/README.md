# Arizona Water Company — Sample Document Set

This is the unstructured-data companion to the AWC operational database. Upload
the whole `awc-documents/` folder into the MinIO bucket of the same name (see the
Lab Environment Setup Guide, Part C2) so Workshop 1 can connect and scan it.

The files are deliberately consistent with the `awc_operations` database: the same
eight water systems, the same customers and account numbers, and the same
water-quality figures (Apache Junction and Bisbee carry a turbidity WARNING).

## Folders

| Folder            | Files | Type                | Purpose in the course |
|-------------------|-------|---------------------|-----------------------|
| `compliance/`     | 4 PDF | Unstructured docs   | EPA water-quality compliance reports. Ideal for Summarize Documents and Data Classification. Apache Junction & Bisbee show the turbidity WARNING that matches `water_quality_reports`. |
| `inspections/`    | 3 DOCX| Unstructured docs   | Field inspection & maintenance reports. The Apache Junction main-break report ties to the system's WARNING status. |
| `correspondence/` | 3 DOCX + 2 TXT | Unstructured docs | Customer letters and email threads. **Contain PII** — names, service addresses, account numbers, phones, emails — for Address Detection and PII discovery. The opt-out letter ties to the `opted_out_marketing` compliance scenario. |
| `scada/`          | 2 JSON| Semi-structured     | SCADA telemetry exports (pressure, flow, reservoir level). Schema detection and field profiling. |
| `gis/`            | 2 CSV | Structured-in-files | Pipe-network segments and asset inventory. Delimited-file profiling with header detection. |

## Scenario tie-ins
- **Opt-out compliance**: `correspondence/letter_optout_confirmation_AWC-PV-100204.docx`
  confirms a customer opted out of marketing — the documentary side of the
  `opted_out_marketing` business rule.
- **Overdue account**: `correspondence/letter_overdue_notice_AWC-SV-100337.docx`
  matches the Sierra Vista Medical $684.45 overdue balance.
- **EPA WARNING**: `compliance/epa_compliance_apache_junction_2026Q1.pdf` and
  `inspections/inspection_apache_junction_main_break.docx` both reflect the
  Apache Junction turbidity exceedance.

All content is fictional and generated for training purposes.
