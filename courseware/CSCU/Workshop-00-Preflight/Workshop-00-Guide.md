# Workshop 0 — Preflight: Provision Users & Roles (CSCU)

*Copper State Credit Union scenario · PDC 10.2.11 · lab at `https://pentaho.io` (VM `192.168.1.200`)*

Every later workshop assumes the CSCU team already has accounts with the right
roles. This preflight creates them.

## The CSCU team (assets/users.csv)

| User | PDC roles | Owns |
| --- | --- | --- |
| `elena.ramirez` | Data Steward · Business Steward | Sources, profiling, identification; Transactions / Accounts & Deposits terms |
| `marcus.webb` | Business Steward | Lending terms (Loan Number, APR) |
| `nadia.flores` | Business Steward | Compliance & Risk terms — all CDE (Risk Rating, SAR) |
| `tom.callahan` | Business Steward | Cards & Payments terms (Card Number, Routing Number) |
| `catalog.admin` | Admin (all seven roles) | Users, custom properties, workers, licence |
| `jordan.blake` | Data User | Business Analyst persona — reads, searches, consumes |
| `dana.ortiz` | Data Steward | Data Analyst persona — profiles, identifies, curates |

All CSCU emails follow `name@copperstatecu.org`.

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
3. Tier: Expert for the stewards and `dana.ortiz`; Business for `jordan.blake`.

## Part C — set each user's password

In Keycloak (**pdc** realm), set each new user's password to the shared lab
value `copperstate` (temporary = off). Verify one steward can sign in.
`[SCREENSHOT: signed in as elena.ramirez — home page]`

## Checkpoint

- [ ] `catalog.admin` has all roles and a known password
- [ ] Seven CSCU users exist with least-privilege roles
- [ ] A Business Steward login works

Lab credentials (like the shared `copperstate` password) are for training only.
All Copper State Credit Union data is fictional and generated for training.
