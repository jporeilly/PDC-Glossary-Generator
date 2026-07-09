# lhp-documents — Lakeshore Health Partners document store

Unstructured content for the HEALTH scenario, uploaded to the `lhp-documents`
MinIO bucket by the lab loader. Six folders, mirroring what a clinic network
really holds:

| Folder | Contents | Format |
| --- | --- | --- |
| compliance | HIPAA security risk analysis (finding: SSNs in clinical notes), accounting-of-disclosures audit (flags the unauthorized marketing disclosure), coding compliance audit, Notice of Privacy Practices | PDF |
| correspondence | Records-request email thread, billing question, cardiology referral, claim-denial appeal, marketing opt-out confirmation | TXT / DOCX |
| intake-forms | New-patient, Medicare-crossover and pediatric intake forms | DOCX |
| interfaces | Inbound lab-results batch, outbound 837 claims export | JSON |
| fee-schedules | 2026 CPT fee schedule | CSV |
| statements | Patient billing statements with MRNs and claim references | TXT |

The content interlocks with the `lhp_clinical` database: the same MRNs
(`LHP-nnnnnn`), claim numbers (`CLM-nnnnnnnn`), NPIs, ICD-10/CPT/LOINC codes,
patients, encounters and defects appear in both — so identification,
discovery and the workshops' triangulation exercises work end to end.

All Lakeshore Health Partners data is fictional and generated for training.
