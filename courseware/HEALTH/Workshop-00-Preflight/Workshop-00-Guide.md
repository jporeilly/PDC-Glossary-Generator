# Workshop 0 — Preflight: Provision Users & Roles (LHP)

*Lakeshore Health Partners scenario · PDC 11.0.0 · lab at `https://pentaho.io` (VM `192.168.1.200`)*

**Primary role:** IT Administrator / Catalog Admin
**Estimated time:** 20 min

## Why this workshop matters

Every governance journey begins with people, not data. Before Pentaho Data
Catalog (PDC) can connect a source, profile a table, or govern a business
term, the Lakeshore Health Partners (LHP) team needs accounts — and each
account needs exactly the access its owner's job requires, and no more.
Workshop 0 is that groundwork. It runs once, before Workshop 1, and
everything the cohort does afterward assumes the users and roles you create
here.

LHP is a covered entity under HIPAA, and in healthcare *who can change
what* — and who can even see what — is regulated, not just good practice. A
business steward who curates the glossary should not be able to rewrite a
data source; an analyst who reads metadata should not be able to administer
the system. PDC expresses these boundaries through role-based access
control, and this workshop maps each LHP person to the role that matches
their responsibility.

> **The business problem.** Hand every trainee the same all-powerful login
> and two things go wrong: nobody can tell, from the catalog, who is
> responsible for what — and a single mistake can change data a regulator
> expects to be controlled. When an OCR investigator asks *"who decided the
> clinical note field is HIGH sensitivity, and when?"*, the answer must be
> a named steward with the right role. Provisioning distinct,
> least-privilege accounts up front makes ownership visible and auditable —
> the same minimum-necessary discipline HIPAA demands of the data itself.

## What you will learn

- How PDC separates identity (who you are, held in Keycloak) from
  authorization (what you may do, expressed as PDC roles and communities).
- The seven default PDC roles across the Business and Expert tiers, and what
  each one can and cannot do.
- How to reset the catalog administrator's password in Keycloak and grant it
  the full set of roles.
- How to add each LHP user in Data Catalog and assign the least-privilege
  role their work requires.
- Why least privilege and separation of duties are governance controls, not
  just IT hygiene — and how each steward's expertise keywords later drive
  the Glossary Generator's auto-assignment of steward, owner and custodian
  slots.

## Background: how PDC does identity and access

PDC delegates authentication to Keycloak, the identity provider bundled with
the platform. Keycloak holds each user's identity and credentials in a realm
— for this instance the realm is `pdc` — and PDC authenticates users against
the `pdc-client` OIDC client. Authorization — what a signed-in user may
actually do — is expressed in PDC as roles and communities. In practice this
means two places do two jobs: you set or reset a password in **Keycloak**,
and you assign roles in **Data Catalog**.
`[SCREENSHOT: Keycloak pdc realm beside PDC user management]`

PDC groups its default roles into two licensed tiers. Business Users mostly
view and explore; Expert Users create, ingest, and curate. When a user holds
more than one role the highest-level role determines effective permissions,
and the number of Expert seats you can assign is capped by your licence —
worth remembering before you hand out steward roles freely.

| Tier | Role | What it can do |
| --- | --- | --- |
| Business | Business User | View business glossaries and policies. No data-source access |
| Business | Data User | Business User, plus view/add/delete data-source content, dashboards, and BI |
| Expert | Business Steward | Create, update, import/export business glossaries and policies. Cannot modify data sources |
| Expert | Data Steward | Create and manage data sources, profiling, business rules, data-identification methods, and reference data |
| Expert | Admin | Manage user accounts, roles, permissions, and system configuration. Can view — but not author — business rules |
| Expert | Data Storage Administrator | Manage data sources, storage utilisation and tiering across sources, folders, and schemas; author identification methods |
| Expert | Data Developer | Design and maintain business rules, metadata and MDM rules, and data-domain logic |

Beyond the defaults, PDC also supports **communities** — custom roles built
on a base role that narrow or widen access to specific assets (a Revenue
Cycle community that sees only billing glossaries, for example). This
workshop uses the default roles; communities become useful once LHP scopes
access by department.

## Before you begin

### Prerequisites

- A running PDC 11.0.0 instance with its Keycloak reachable, and the
  Keycloak administrator credentials (master-realm admin) to reset
  passwords.
- An initial account with the Admin role so you can open Management → Users
  & Communities. In this scenario that account is `catalog.admin`.
- The LHP roster below (`assets/users.csv`). All LHP emails follow the
  pattern `name@lakeshorehealth.org`.

### Reference — admin parameters

Substitute your own host wherever `pentaho.io` appears.

| Field | Value | Notes |
| --- | --- | --- |
| PDC console | https://pentaho.io | Your instance root |
| Keycloak admin | https://pentaho.io/keycloak | Admin console; sign in, then select the realm below |
| Realm | pdc | The PDC tenant realm — not `master` |
| OIDC client | pdc-client | The client PDC authenticates against |
| Admin user | catalog.admin | Reset its password (Part A) |
| Admin password | lakeshore | Lab credential — set non-temporary; change in production |

## The LHP roster — all seven PDC roles covered

The LHP team maps one persona to each role. Business Steward is held by the
four business-domain owners; there is deliberately only **one** Data
Steward.

| User | PDC role(s) | Why |
| --- | --- | --- |
| catalog.admin | ALL SEVEN ROLES | Course superuser / trainer. Password reset in Keycloak to `lakeshore` |
| maya.lindqvist | Data Steward · Business Steward | The single Data Steward: connects sources, profiles, runs identification; stewards Patient, Appointments & Encounters, Clinic Operations |
| anders.berg | Business Steward | HIM lead; stewards Diagnoses & Results and Prescriptions (Diagnosis Code, DEA Schedule) |
| rosa.jimenez | Business Steward | Stewards Claims & Billing and Payers terms (Claim Number, CPT Code) |
| hannah.weiss | Business Steward | Privacy Officer; stewards Privacy & Disclosures (all CDE) and Records & Documents |
| victor.osei | Data Storage Administrator | Storage custodian: creates/ingests data sources, monitors utilisation; fills the app's custodian slot |
| ingrid.dahl | Data Developer | Authors the Workshop 4 business rules and domain logic (this role owns Business Rules — Admin cannot create them) |
| jamal.carter | Data User | Business Analyst persona — reads, searches, views data assets |
| beth.nakamura | Business User | Lightest tier: views the glossary and policies only — the contrast case to Jamal |

> **Licence note:** the Expert-tier roles count against your licensed
> Expert-user limit — this roster uses seven Expert accounts.

> **Expertise drives governance.** Each steward's roster entry carries
> expertise keywords (see
> `data_sources/HEALTH/domain_pack/healthcare.people.json`); the Glossary
> Generator's Govern page matches them against category, term and column
> names to auto-assign the steward / owner / custodian slots. The four
> Business Stewards' keywords deliberately cover all nine glossary
> categories.

## Step-by-step

### Part A — Reset the catalog administrator (Keycloak)

1. Open the Keycloak admin console at `https://pentaho.io/keycloak` and sign
   in with the Keycloak (master-realm) administrator credentials.
2. At the top-left realm selector, switch from `master` to the **pdc**
   realm. Everything below happens in the pdc realm.
   `[SCREENSHOT: Keycloak realm selector — pdc realm selected]`
3. Go to **Users**, search for `catalog.admin`, and open the account. If it
   does not exist yet, click **Add user**, set the username to
   `catalog.admin` and email `catalog.admin@lakeshorehealth.org`, and save.
4. Open the **Credentials** tab, click **Reset password**, enter
   `lakeshore` in both fields, and — importantly — turn **Temporary off**
   so the password works immediately without a forced reset. Save.
   `[SCREENSHOT: Keycloak reset password — Temporary off]`
5. Grant every role. In PDC (signed in as an existing Admin) go to
   **Management → Users & Communities → Users**, open `catalog.admin`,
   click **Add Roles**, tick all seven roles, and click **Done**.
   `[SCREENSHOT: catalog.admin — all seven roles assigned]`
6. Click **Done** again to apply the changes.

> **Why grant the admin every role?** Across the course the trainer account
> needs to demonstrate any action — connect a source (Data Storage
> Administrator), curate a term (Business Steward), author a rule (Data
> Developer), administer users (Admin). Granting all roles avoids switching
> accounts mid-lesson. If the PDC UI refuses an overlapping combination,
> assign the roles directly as Keycloak realm roles instead, which is not
> subject to the UI's same-base restriction. Watch the licence cap on
> Expert seats.

### Part B — Add the LHP users (Data Catalog)

Sign in to PDC as `catalog.admin` / `lakeshore`. Confirm the Administration
area is visible — proof the Admin role took effect — then add each user
from the roster.

1. On the left menu click **Management**. The Manage Your Environment page
   opens.
2. On the **Users & Communities** card, click **Add New** and select **Add
   User**. The Create User page opens.
3. Enter the user's details — username and email from the roster (for
   example `hannah.weiss` / `hannah.weiss@lakeshorehealth.org`).
4. Click **Add Roles**, tick the role or roles listed for that user in the
   roster, and click **Save**. Assign only what the mapping specifies —
   that is the least-privilege discipline in action.
   `[SCREENSHOT: Create User — hannah.weiss with Business Steward]`
5. Click **Done** to create the user. Repeat for all eight LHP users. If
   you see an "exceeded licensed limit" message, you have assigned more
   Expert seats than the licence allows — see Troubleshooting.

### Part C — Set each user's initial password (Keycloak)

New PDC users have no usable password until one is set (or, if SMTP is
configured, until they follow an emailed reset link). For a self-contained
lab, set them directly.

1. Back in the Keycloak admin console, **pdc** realm, open **Users** and
   select each newly created account. Note the **UUID** that uniquely
   identifies the user — the Glossary Generator's roster binds people to
   PDC accounts by this UUID.
   `[SCREENSHOT: Keycloak user detail — UUID visible]`
2. On the **Credentials** tab, **Reset password** to the shared lab
   password `lakeshore`, with Temporary turned **off**. Save.
3. Repeat for each user. In production you would instead enable SMTP and
   let users set their own passwords via the reset link — never a shared
   credential.

> **Least privilege, from the first screen.** Notice what you did not do:
> you did not give every steward the Admin role, and you did not give the
> analyst any steward role. `hannah.weiss` can shape the glossary but
> cannot touch a data source; `jamal.carter` can read the catalog but
> cannot administer users; `ingrid.dahl` can author business rules that
> even the Admin role cannot. That separation is exactly the
> minimum-necessary standard a HIPAA auditor expects to see applied to
> systems as well as records.

## Who does what — the cast across the workshops

| Workshop / task | Performed as | Why that role |
| --- | --- | --- |
| W0 provision users | `catalog.admin` | Admin manages users, roles, communities |
| W1 create + ingest both sources, Scan Files | `victor.osei` | Data Storage Administrator creates data sources (Maya's Data Steward role also can) |
| W2 explore structure & metadata | `jamal.carter` | Data User views data assets (repeat one step as `beth.nakamura` to see the Business User boundary) |
| W3 import + review the glossary | `hannah.weiss` (any Business Steward) | Business Steward creates/imports glossaries |
| W3 link terms to columns | `maya.lindqvist` | Needs data-source write — her Data Steward side |
| W4 profile the tables | `maya.lindqvist` | Data Steward runs profiling jobs |
| W4 author the business rules | `ingrid.dahl` | Data Developer owns Business Rules in v11 |
| W5 dictionaries, patterns, identification | `maya.lindqvist` | Data Steward owns Data Identification Methods (so does Victor) |

## Verify your work

You are done with Workshop 0 when all of the following are true:

- [ ] `catalog.admin` signs in to PDC with the password `lakeshore` and
  sees the Administration area.
- [ ] All eight LHP users exist under Users & Communities, each with the
  role(s) from the roster — covering all seven PDC roles.
- [ ] A Business Steward (for example `hannah.weiss`) can open Business
  Glossary but not create a data source.
- [ ] A Data Storage Administrator (`victor.osei`) can add a data source,
  which the analyst account cannot.
- [ ] No "exceeded licensed limit" warnings remain against any assignment.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| "Exceeded licensed limit" when assigning a role | You have assigned more Expert-tier seats than your licence allows. Free a seat, or use a Business-tier role where it is sufficient |
| Cannot assign an overlapping role | The PDC UI blocks assigning a default role plus a community derived from the same base role. For catalog.admin's all-roles requirement, assign the roles directly as Keycloak realm roles, which the UI restriction does not govern |
| A new user cannot sign in | The Keycloak password was left as Temporary, so PDC forces a reset the user cannot complete without email. Reopen Credentials and turn Temporary off, or configure SMTP so the reset link is delivered |
| 404 or auth error getting a token | Wrong realm or base URL. Use the `pdc` realm (not `master`) and the server root as the base — no port suffix and no `/keycloak` in the base URL you configure elsewhere |
| Role change not reflected | PDC applies permission changes on sign-in. Ask the user to refresh the browser, or sign out and back in |

## Why it matters & discussion

Access control is the quiet foundation of every catalog — doubly so in
healthcare, where HIPAA's minimum-necessary rule makes least privilege a
legal standard, not a preference. By separating identity in Keycloak from
authorization in PDC, and by assigning each LHP user only the role their
work requires, you have made two things true before a single table is
connected: the catalog can show who is responsible for what, and no account
can do more than its job demands. As the cohort moves into Workshop 1 and
beyond, keep asking the governance question this workshop sets up — not
just *"can I do this?"* but *"should this role be able to?"*

## What's next

With the cast in place, Workshop 1 connects the LHP data estate — the
`lhp_clinical` database and the `lhp-documents` object store — performed by
`victor.osei`, whose Data Storage Administrator role exists for exactly
that job.

All Lakeshore Health Partners data is fictional and generated for training.
