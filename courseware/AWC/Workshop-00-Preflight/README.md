# Workshop 0: Preflight — Provision Users & Roles

**Primary role:** IT Administrator / Catalog Admin
**Estimated time:** 20 min
**Prerequisite for:** Workshop 1 onward

## What's in this package

- **`Workshop-00-Users-and-Roles.pptx`** — the slide deck for this session (with the same look as the rest of the course)
- **`Workshop-00-Guide.docx`** — the detailed standalone workshop guide. Read this; it explains the steps *and the reasoning*, with Arizona Water Company context.

## What this workshop sets up

Every later workshop assumes the AWC team already has accounts with the right roles. This preflight creates them:

- Resets the `catalog.admin` password in **Keycloak** (realm `pdc`) to `azwater` and grants it **all seven PDC roles**.
- Adds the six AWC users in **Data Catalog** and maps each to a least-privilege role:
  - `david.chen` — Data Steward · Business Steward
  - `maria.garcia`, `robert.hayes`, `susan.park` — Business Steward
  - `data.analyst` — Data Steward
  - `business.analyst` — Data User
- All AWC emails follow the pattern `name@azwater.gov`.

## How to run it

1. Make sure the PDC instance and its Keycloak are running and reachable (substitute your host for `pentaho.io`).
2. Have the Keycloak (master-realm) administrator credentials handy — you need them to set passwords.
3. Present the deck, then follow the guide step by step: **Part A** (reset the admin in Keycloak), **Part B** (add users in PDC), **Part C** (set each user's password).

Lab credentials shown here (for example the shared `azwater` password) are for training only — change them in production. All data and personas are fictional and generated for training.
