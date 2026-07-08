# Workshop 0 — Preflight: Provision Users & Roles (CSCU)

*Copper State Credit Union scenario · PDC 10.2.11 · lab at `https://pentaho.io` (VM `192.168.1.200`)*

Every later workshop assumes the CSCU team already has accounts with the right
roles. This preflight creates them.

## The CSCU team (assets/users.csv) — all seven PDC roles covered

PDC v11 ships seven default roles in two licensed tiers — **Business tier:**
Business User, Data User; **Expert tier:** Business Steward, Data Steward,
Admin, Data Storage Administrator, Data Developer. The CSCU team maps one
persona to each (Business Steward is held by the four business-domain owners;
there is deliberately only **one** Data Steward):

| User | PDC roles | Persona |
| --- | --- | --- |
| `elena.ramirez` | Data Steward · Business Steward | The single Data Steward: sources, profiling, identification; stewards Member, Accounts & Deposits, Transactions, Branch Operations |
| `marcus.webb` | Business Steward | Stewards Lending and Finance & Ledger (Loan Number, APR, GL Account) |
| `nadia.flores` | Business Steward | BSA/AML officer; stewards Compliance & Risk (all CDE) and Records & Documents |
| `tom.callahan` | Business Steward | Stewards Cards & Payments (Card Number, Routing Number) |
| `omar.haddad` | Data Storage Administrator | Storage custodian: creates/ingests data sources, monitors utilization; fills the app's custodian slot |
| `dana.ortiz` | Data Developer | Authors the Workshop 4 business rules and domain logic (in v11 this role owns Business Rules — the Admin role cannot create them) |
| `jordan.blake` | Data User | Business Analyst persona — reads, searches, views data assets |
| `riley.morgan` | Business User | Lightest tier: views the glossary and policies only — the contrast case to Jordan |
| `catalog.admin` | Admin (all seven roles in the lab) | Users, communities, custom properties, workers, licence |

All CSCU emails follow `name@copperstatecu.org`.

> **Licence note:** the Expert-tier roles (Business Steward, Data Steward,
> Admin, Data Storage Administrator, Data Developer) count against your
> licensed Expert-user limit — this roster uses seven Expert accounts.

> **Expertise drives governance.** Each steward's roster entry carries
> expertise keywords (see `data_sources/CSCU/domain_pack/credit_union.people.json`);
> the Glossary Generator's Govern page matches them against category, term and
> column names to auto-assign the steward / owner / custodian slots. The four
> Business Stewards' keywords deliberately cover all nine glossary categories.

## Who does what — the cast across the workshops

| Workshop / task | Performed as | Why that role |
| --- | --- | --- |
| W0 provision users | `catalog.admin` | Admin manages users, roles, communities |
| W1 create + ingest both sources, Scan Files | `omar.haddad` | Data Storage Administrator creates data sources (Elena's Data Steward role also can) |
| W2 explore structure & metadata | `jordan.blake` | Data User views data assets (repeat one step as `riley.morgan` to see the Business User boundary) |
| W3 import + review the glossary | `nadia.flores` (any Business Steward) | Business Steward creates/imports glossaries |
| W3 link terms to columns | `elena.ramirez` | Needs data-source write — her Data Steward side |
| W4 profile the tables | `elena.ramirez` | Data Steward runs profiling jobs |
| W4 author the business rules | `dana.ortiz` | Data Developer owns Business Rules in v11 |
| W5 dictionaries, patterns, identification | `elena.ramirez` | Data Steward owns Data Identification Methods (so does Omar) |
| Technical Track modules 02-03 | `elena.ramirez` or `omar.haddad` | DI method authoring is role-gated to those two |

## Part A — reset the admin in Keycloak

1. Open `https://pentaho.io/keycloak` and sign in to the **master** realm with
   the Keycloak administrator credentials.
2. Switch to the **pdc** realm → **Users** → `catalog.admin`.
3. **Credentials** tab → set the lab password to `copperstate` (temporary =
   off). `[SCREENSHOT: Keycloak pdc realm — catalog.admin credentials tab]`
4. In PDC, confirm `catalog.admin` carries **all seven PDC roles**.

## Part B — add the CSCU users in Data Catalog

1. Sign in to `https://pentaho.io` as `catalog.admin`.
2. **Management → Users** → add each user from `assets/users.csv` with the
   role(s) in the table above — least privilege, exactly as listed.
   `[SCREENSHOT: PDC user management — the seven CSCU users]`
3. Tier: **Expert** for Elena, Marcus, Nadia, Tom, Omar, Dana and `catalog.admin`;
   **Business** for Jordan and Riley.

## Part C — set each user's password

In Keycloak (**pdc** realm), set each new user's password to the shared lab
value `copperstate` (temporary = off). Verify one steward can sign in.
`[SCREENSHOT: signed in as elena.ramirez — home page]`

## Checkpoint

- [ ] `catalog.admin` has all roles and a known password
- [ ] Nine CSCU users exist, covering all seven PDC roles, least-privilege
- [ ] A Business Steward login works

Lab credentials (like the shared `copperstate` password) are for training only.
All Copper State Credit Union data is fictional and generated for training.
