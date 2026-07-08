# Technical Track — Data Identification & the Glossary Generator

A short, hands-on track for the **technical audience** — Data Stewards, Data
Developers, Solution Architects, and Administrators. It goes underneath the
Business-Analyst course and explains (and lets you build) the engine that powers
**Workshop 5 — Protect Sensitive Data**: PDC's **Data Identification**.

It is *not* part of the 11-workshop BA path. Run it with technical staff after
they have seen Connect → Metadata Ingest → Profiling, i.e. once there is profiled
data to identify.

## The three modules, in order

| # | Module | Format | What you do |
|---|--------|--------|-------------|
| 01 | **Data Identification** | deck + guide | Understand the engine: Dictionaries (match by content) + Data Patterns (match by shape) → Policies → Tags & Business Terms. |
| 02 | **Build Your Own AWC Dictionary & Pattern** | deck + guide (lab) | Hands-on: author a custom dictionary and a custom pattern, combine them into a policy, and run it on AWC data. |
| 03 | **Glossary Generator App** | deck + guide + app | Apply the result: an app that rides on the identification tags to build AWC's governed glossary over the PDC API. |

## How it maps to the BA course

- **Prerequisite:** profiled data — so BA Workshops 1, 2 and 4 (Connect, Metadata,
  Profiling) should be done first.
- **Pairs with:** BA **Workshop 5 — Protect Sensitive Data**. Module 01 is the
  deep-dive behind that workshop; module 02 is the hands-on extension.
- **Alternative to:** BA **Workshop 3 — Build the Business Glossary** (manual).
  Module 03 (the app) is the app-driven way to produce the same governed glossary.

## Audience & roles

Authoring dictionaries, patterns and metadata rules requires the **Data Steward**
or **Data Storage Administrator** role. If the Data Operations → Data Identification
Methods area is not visible, that is a permissions matter, not a missing feature.

All data is fictional and generated for training.
