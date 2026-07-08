"""
build_roster.py - merge a persona/roles CSV with a UUID-map CSV into people.json,
the roster the Glossary Suggester uses to populate glossary people-fields.

Join key is email. The UUID map (account_username, email, uuid) supplies the
Keycloak account id + login name; the users/persona CSV supplies display name,
PDC roles, community, and ownership notes. People without a resolved UUID are
kept but flagged (id="") so the UI can show them without offering them as a
binding (a binding needs a real account id).

Usage:
  python build_roster.py users.csv glossary-user-map.csv [out.json]
"""
import sys, csv, json, re

def _read(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))

def _email(r):
    for k in r:
        if k and k.strip().lower() == "email":
            return (r[k] or "").strip().lower()
    return ""

def _role_to_stakeholder(role):
    # stakeholders[].roles uses "Steward" in PDC exports; map persona roles to it.
    return "Steward" if "steward" in (role or "").lower() else (role or "Steward").strip()

def build(users_csv, map_csv):
    personas = { _email(r): r for r in _read(users_csv) if _email(r) }
    roster = []
    seen = set()
    for m in _read(map_csv):
        em = _email(m); 
        if not em: 
            continue
        seen.add(em)
        p = personas.get(em, {})
        roles_raw = (p.get("PDC_Roles") or "").strip()
        roles = [s.strip() for s in re.split(r"[;,]", roles_raw) if s.strip()]
        roster.append({
            "name": (m.get("account_username") or "").strip(),
            "display_name": (m.get("display_name") or f"{p.get('First_Name','')} {p.get('Last_Name','')}").strip(),
            "email": em,
            "id": (m.get("uuid") or "").strip(),
            "roles": roles or ["Business Steward"],
            "stakeholder_role": _role_to_stakeholder(roles[0] if roles else "Steward"),
            "community": (p.get("Community") or "").strip(),
            "owns": (p.get("Notes") or "").strip(),
        })
    # personas with no UUID match: keep, flag id="" so UI won't offer them for binding
    for em, p in personas.items():
        if em in seen:
            continue
        roles_raw = (p.get("PDC_Roles") or "").strip()
        roles = [s.strip() for s in re.split(r"[;,]", roles_raw) if s.strip()]
        roster.append({
            "name": em.split("@")[0],
            "display_name": f"{p.get('First_Name','')} {p.get('Last_Name','')}".strip(),
            "email": em, "id": "", "roles": roles or [],
            "stakeholder_role": "Steward", "community": (p.get("Community") or "").strip(),
            "owns": (p.get("Notes") or "").strip(),
        })
    # resolved (have UUID) first, then pending
    roster.sort(key=lambda r: (r["id"] == "", r["display_name"]))
    return roster

if __name__ == "__main__":
    users_csv = sys.argv[1] if len(sys.argv) > 1 else "users.csv"
    map_csv   = sys.argv[2] if len(sys.argv) > 2 else "glossary-user-map.csv"
    out       = sys.argv[3] if len(sys.argv) > 3 else "people.json"
    roster = build(users_csv, map_csv)
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"people": roster}, f, indent=2, ensure_ascii=False)
    resolved = sum(1 for r in roster if r["id"])
    print(f"wrote {out}: {len(roster)} people, {resolved} with UUID, {len(roster)-resolved} pending")
