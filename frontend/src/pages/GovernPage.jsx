// Govern page — the React port of the old UI's Govern section
// (static/js/11-govern.js + templates/index.html #page-govern):
// the user roster (manual entry or a live Keycloak fetch), per-person
// governance-function toggles, AI expertise suggestions, stewardship
// defaults with per-category overrides (candidate pools constrained to each
// person's actual roster functions), keyword auto-assign with
// strict-win-over-default semantics, DQ-derived ratings and review dates,
// apply-stewardship-to-rows and the read-only governance summary. The built
// governance object lives in the shared workspace (state.js) and is baked
// into the JSONL by the Apply page's Generate card.
import { useEffect, useMemo, useState } from 'react'
import { apiGet, apiPost } from './../api.js'
import { setGlossaryMeta, setGovernance, setRows, useWorkspace } from './../state.js'
import './govern.css'

/* ====================================================================
   Pure govern logic — ported 1:1 from static/js/11-govern.js. Everything
   takes (people, rows) explicitly so it stays unit-testable.
   ==================================================================== */

const OWN_KEYWORDS = {
  Customer: ['customer'],
  Governance: ['governance', 'alert', 'policy'],
  'Billing & Rates': ['billing', 'rate', 'invoice', 'account number'],
  Usage: ['usage', 'consumption'],
  'Records & Documents': ['document', 'record', 'file'],
}

const PDC_DOMAINS = ['Human Resources', 'Marketing', 'Sales', 'Finance',
  'Logistics and supply chain Management', 'Technology', 'Construction',
  'E-commerce', 'Engineering', 'Energy', 'Utilities', 'Sustainability',
  'Renewable Energy', 'Healthcare', 'LifeSciences', 'Manufacturing',
  'Semiconductor', 'Telecommunication', 'Automotive', 'Banking', 'Real estate',
  'Gaming', 'Cybersecurity', 'Business', 'Fitness', 'Legal', 'Biology',
  'Services', 'Transportation', 'Government sector', 'Online services']

const SLOTS = ['businessSteward', 'owner', 'custodian']
const SLOT_LABEL = { businessSteward: 'Business steward', owner: 'Owner', custodian: 'Custodian' }

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/

// Same Keep semantics as the Review grid — Govern acts on KEPT terms only
// (dropped rows neither drive the category cards nor receive stamps).
const isKept = (r) => ['y', 'yes', 'true', '1'].includes(String(r.Keep).toLowerCase())

// Map a user's Keycloak realm roles to a governance function. PDC's model:
// Business_Steward maintains glossaries; Data_Steward gives governance
// ownership; Data_Storage_Administrator is the technical custodian.
function roleFns(roles) {
  const R = (roles || []).map((x) => String(x).toLowerCase())
  const any = (...ks) => R.some((r) => ks.some((k) => r.includes(k)))
  return {
    businessSteward: any('business_steward', 'business steward'),
    owner: any('data_steward', 'data steward'),
    custodian: any('data_storage', 'storage_admin', 'storage administrator', 'custodian'),
  }
}

// Effective governance functions: the steward's explicit roster toggles
// (p.fns, persisted in people.json) OVERRIDE the Keycloak-derived roles.
function personFns(p) {
  const base = roleFns(p && p.roles)
  const o = (p && p.fns) || {}
  return {
    businessSteward: o.businessSteward != null ? !!o.businessSteward : base.businessSteward,
    owner: o.owner != null ? !!o.owner : base.owner,
    custodian: o.custodian != null ? !!o.custodian : base.custodian,
  }
}

// Best roster member for a governance function: prefer the most specialised
// account (fewest functions), tie-break by name.
function pickByFn(people, fn) {
  const c = people.filter((p) => p.id && personFns(p)[fn])
  if (!c.length) return null
  const gcount = (p) => {
    const f = personFns(p)
    return (f.businessSteward ? 1 : 0) + (f.owner ? 1 : 0) + (f.custodian ? 1 : 0)
  }
  return c.slice().sort((a, b) => gcount(a) - gcount(b)
    || String(a.display_name || a.name).localeCompare(String(b.display_name || b.name)))[0]
}

// Dynamic roster rule: a person's functions are EXCLUSIVE capabilities when
// present — someone marked only Custodian is never swept into Steward/Owner
// slots, even by the expertise-only fallback. People with NO functions at all
// remain fair game for any slot.
function eligibleFor(p, slot) {
  const f = personFns(p)
  const scoped = f.businessSteward || f.owner || f.custodian
  return !scoped || f[slot]
}

function candidatesFor(people, slot) {
  return people.filter((p) => p.id && personFns(p)[slot])
}

function personById(people, id) {
  return people.find((p) => p.id === id)
}

function personByEmail(people, em) {
  const e = (em || '').toLowerCase()
  return people.find((p) => (p.email || '').toLowerCase() === e)
}

function personName(people, id) {
  const p = personById(people, id)
  return p ? (p.display_name || p.name) : ''
}

/* ---- keyword auto-assign: tokenizer, synonym buckets, scoring ---- */

const STOP = new Set(['the', 'and', 'of', 'for', 'a', 'an', 'to', 'in', 'on', 'with', 'by',
  'is', 'are', 'term', 'terms', 'data', 'id', 'code', 'number', 'name', 'date', 'type',
  'value', 'flag', 'status', 'tbl', 'col'])

function tok(s) {
  return String(s || '').toLowerCase().replace(/[_./\-]+/g, ' ').replace(/[^a-z0-9 ]+/g, ' ')
    .split(/\s+/).filter((w) => w && w.length > 2 && !STOP.has(w))
}

// small domain synonym map: bridges a person's words to a category's words
// even when they don't share an exact token
const DOMAIN_SYNONYMS = {
  billing: ['billing', 'bill', 'rate', 'rates', 'invoice', 'invoicing', 'charge', 'charges',
    'tariff', 'payment', 'finance', 'financial', 'revenue', 'balance', 'dollar', 'cost', 'amount'],
  customer: ['customer', 'account', 'consumer', 'client', 'household', 'subscriber', 'contact',
    'address', 'resident'],
  usage: ['usage', 'consumption', 'meter', 'metering', 'volume', 'gallons', 'demand', 'flow'],
  governance: ['governance', 'policy', 'compliance', 'alert', 'audit', 'steward', 'regulatory',
    'standard', 'rule', 'approval', 'review', 'escalation'],
  records: ['document', 'record', 'file', 'report', 'archive', 'attachment', 'scan', 'pdf'],
}

function bucketsOf(tokenSet) {
  const b = new Set()
  for (const [name, words] of Object.entries(DOMAIN_SYNONYMS)) {
    if (words.some((w) => tokenSet.has(w))) b.add(name)
  }
  return b
}

// the vocabulary a category represents: core (label + curated owns-keywords)
// counts for more than ext (incidental term/column tokens)
function catVocab(rows, cat) {
  const catRows = rows.filter((r) => r.Category === cat)
  const core = new Set([...tok(cat), ...(OWN_KEYWORDS[cat] || []).flatMap(tok)])
  const ext = new Set()
  for (const r of catRows) {
    for (const t of tok(r.Term)) ext.add(t)
    for (const sc of String(r.Source_Column || '').split(';')) {
      for (const t of tok(sc.trim().split('.').pop())) ext.add(t)
    }
  }
  for (const t of core) ext.delete(t)
  return { core, ext, buckets: bucketsOf(new Set([...core, ...ext])) }
}

function personVocab(p) {
  const exp = new Set(tok(p.expertise))
  const own = new Set(tok(p.owns))
  return { exp, own, buckets: bucketsOf(new Set([...exp, ...own])) }
}

function gcountP(p) {
  const f = roleFns(p.roles)
  return (f.businessSteward ? 1 : 0) + (f.owner ? 1 : 0) + (f.custodian ? 1 : 0)
}

// keyword score: expertise dominates owns, and the category label (core)
// dominates incidental tokens (ext); a shared domain bucket bridges synonyms.
function scorePC(pv, cv) {
  const hits = (a, b) => {
    const h = []
    a.forEach((t) => { if (b.has(t)) h.push(t) })
    return h
  }
  const ec = hits(pv.exp, cv.core)
  const ee = hits(pv.exp, cv.ext)
  const oc = hits(pv.own, cv.core)
  const oe = hits(pv.own, cv.ext)
  const bHits = [...pv.buckets].filter((b) => cv.buckets.has(b))
  const score = 3 * ec.length + 1 * ee.length + 2 * oc.length + 0.5 * oe.length + 3 * bHits.length
  const matched = [...new Set([...ec, ...bHits, ...ee, ...oc, ...oe])].slice(0, 6)
  return { score, matched, bHits: bHits.length }
}

function confOf(s) {
  return s >= 6 ? 'high' : s >= 3 ? 'med' : s > 0 ? 'low' : 'none'
}

// choose the best person for one slot in one category
function pickSlot(people, cv, slot, fallbackOn) {
  let pool = candidatesFor(people, slot)
  let fallback = false
  if (!pool.length && fallbackOn) {
    pool = people.filter((p) => p.id && eligibleFor(p, slot))
    fallback = true
  }
  if (!pool.length) return { id: '', name: '', conf: 'none', reason: `no ${slot} candidate in roster`, fallback: false }
  const scored = pool.map((p) => ({ p, ...scorePC(personVocab(p), cv) }))
  scored.sort((a, b) => b.score - a.score
    || ((b.p.expertise ? 1 : 0) - (a.p.expertise ? 1 : 0))
    || (gcountP(a.p) - gcountP(b.p))
    || String(a.p.display_name || a.p.name).localeCompare(String(b.p.display_name || b.p.name)))
  const top = scored[0]
  if (top.score === 0) {
    const def = pickByFn(people, slot)
    if (def) {
      return { id: def.id, name: def.display_name || def.name, conf: 'low', score: 0,
        reason: fallback ? 'no role/expertise match — role default' : 'role default (no expertise match)', fallback }
    }
    return { id: '', name: '', conf: 'none', score: 0, reason: 'no match', fallback }
  }
  return { id: top.p.id, name: top.p.display_name || top.p.name, conf: confOf(top.score),
    score: top.score, reason: `${fallback ? 'expertise-only: ' : ''}matched ${top.matched.join(', ')}`, fallback }
}

// One slot's decision when the steward set a DEFAULT: expertise routing still
// runs, but a candidate must STRICTLY BEAT the default person's own expertise
// score for this category to override — otherwise the default holds.
function slotDecision(people, cat, cv, slot, fb, defId) {
  const pk = pickSlot(people, cv, slot, fb)
  if (!defId) return { mode: 'assign', pk }
  const defP = personById(people, defId)
  const defScore = defP ? scorePC(personVocab(defP), cv).score : 0
  if (pk.id && pk.id !== defId && (pk.score || 0) > 0 && (pk.score || 0) > defScore) {
    return {
      mode: 'override',
      pk: { ...pk, reason: `${pk.reason} — beats your default ${personName(people, defId)} (${(pk.score || 0).toFixed(1)} vs ${defScore.toFixed(1)})` },
      defScore,
    }
  }
  const why = (pk.id === defId && (pk.score || 0) > 0)
    ? `your default is also the best expertise match — ${pk.reason || ''}`
    : (pk.id && (pk.score || 0) > 0)
      ? `default holds — ${pk.name} matched but not better (${(pk.score || 0).toFixed(1)} vs ${defScore.toFixed(1)})`
      : `left on your default — ${personName(people, defId)}`
  return { mode: 'default', pk: { id: '', name: '', conf: 'default', reason: why }, defScore }
}

// Suggested steward for a category: MinIO owner tag, then the owns-map, then
// the Business Steward role.
function prefillFor(rows, people, cat) {
  const hints = rows.filter((r) => r.Category === cat && r.Owner_Hint).map((r) => r.Owner_Hint)
  if (hints.length) {
    const top = hints.slice().sort((a, b) =>
      hints.filter((x) => x === b).length - hints.filter((x) => x === a).length)[0]
    const p = personByEmail(people, top) || personById(people, top)
    if (p && p.id) return { id: p.id, src: 'minio' }
  }
  const kws = OWN_KEYWORDS[cat] || [String(cat || '').toLowerCase()]
  for (const p of people) {
    if (!p.id) continue
    if (kws.some((k) => (p.owns || '').toLowerCase().includes(k))) return { id: p.id, src: 'owns' }
  }
  const bs = pickByFn(people, 'businessSteward')
  if (bs) return { id: bs.id, src: 'role' }
  return { id: '', src: 'def' }
}

/* ---- auto-rating from scan Data Quality (mirrors server quality_score_column) ---- */

function dqScoreOfDims(d) {
  const W = { c: 0.4, u: 0.3, v: 0.3 }
  const dims = []
  const comp = (d.c == null && d.nn) ? 1.0 : d.c
  if (comp != null) dims.push([W.c, Math.max(0, Math.min(1, comp))])
  if (d.eu && d.u != null) dims.push([W.u, Math.max(0, Math.min(1, d.u))])
  if (d.v != null) dims.push([W.v, Math.max(0, Math.min(1, d.v))])
  const wsum = dims.reduce((s, x) => s + x[0], 0)
  if (wsum <= 0) return null
  return Math.round(100 * dims.reduce((s, x) => s + x[0] * x[1], 0) / wsum)
}

function rowDQ(r) {
  if (typeof r.Suggested_Quality === 'number') return r.Suggested_Quality
  const dims = r.Source_Quality_Dims || {}
  const vals = Object.values(dims).map(dqScoreOfDims).filter((x) => x != null)
  return vals.length ? Math.round(vals.reduce((a, b) => a + b, 0) / vals.length) : null
}

function starsFromDQ(p) {
  return p >= 97 ? 5 : p >= 90 ? 4 : p >= 80 ? 3 : p >= 70 ? 2 : 1
}

function meanStars(vals) {
  const v = vals.filter((x) => x != null)
  if (!v.length) return { mean: 0, n: 0, stars: 0 }
  const m = Math.round(v.reduce((a, b) => a + b, 0) / v.length)
  return { mean: m, n: v.length, stars: starsFromDQ(m) }
}

function dqForCategory(rows, cat) {
  return meanStars(rows.filter((r) => r.Category === cat).map(rowDQ))
}

function dqForAll(rows) {
  return meanStars(rows.map(rowDQ))
}

// default reviewed date = today + N months, yyyy-mm-dd for <input type=date>
function plusMonthsISO(n) {
  const d = new Date()
  d.setMonth(d.getMonth() + n)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

function emptyOverride(stewardId = '') {
  return { businessSteward: stewardId, owner: '', custodian: '', status: '',
    rating: '', reviewedAt: '', shOn: false, stakeholders: [], src: {} }
}

// Rebuild one category's override card from a saved workspace's governance
// (the legacy applyGovernance restore path) — so a reopened glossary keeps its
// per-category picks instead of falling back to the prefill.
function overrideFromSaved(sc) {
  if (!sc) return null
  const stakeholders = (sc.stakeholders || []).map((s) => s.id).filter(Boolean)
  return {
    businessSteward: sc.businessSteward || '',
    owner: sc.owner || '',
    custodian: sc.custodian || '',
    status: sc.status || '',
    rating: sc.rating != null ? String(sc.rating) : '',
    reviewedAt: sc.reviewedAt || '',
    shOn: stakeholders.length > 0,
    stakeholders,
    src: {},
  }
}

/* ==================================================================== */

export default function GovernPage({ onNavigate }) {
  const ws = useWorkspace()
  const rows = ws.rows

  const [people, setPeople] = useState(null)
  const [settings, setSettings] = useState(null)
  const [rosterDirty, setRosterDirty] = useState(false)
  const [defaults, setDefaults] = useState(null)
  const [overrides, setOverrides] = useState({})
  const [autoInfo, setAutoInfo] = useState({})
  const [openCats, setOpenCats] = useState({})
  const [autoFallback, setAutoFallback] = useState(true)
  const [autoRespect, setAutoRespect] = useState(true)

  const [kMsg, setKMsg] = useState('')
  const [rosterMsg, setRosterMsg] = useState('')
  const [expMsg, setExpMsg] = useState('')
  const [defMsg, setDefMsg] = useState('')
  const [autoMsg, setAutoMsg] = useState('Keyword match on role + expertise — deterministic and offline. Won’t overwrite slots you set by hand.')
  const [applyMsg, setApplyMsg] = useState('')
  const [loadError, setLoadError] = useState(null)

  const cats = useMemo(
    () => [...new Set(rows.filter(isKept).map((r) => r.Category).filter(Boolean))], [rows])
  const accounts = useMemo(
    () => (people || []).filter((p) => p.id), [people])
  const pools = useMemo(() => ({
    businessSteward: accounts.filter((p) => eligibleFor(p, 'businessSteward')),
    owner: accounts.filter((p) => eligibleFor(p, 'owner')),
    custodian: accounts.filter((p) => eligibleFor(p, 'custodian')),
  }), [accounts])

  // initial load: roster + settings (gov_defaults restore, LLM model/compute)
  useEffect(() => {
    Promise.all([
      apiGet('/api/people').catch(() => ({ people: [] })),
      apiGet('/api/settings').catch(() => ({})),
    ]).then(([p, s]) => {
      setPeople(p.people || [])
      setSettings(s || {})
    }).catch((e) => setLoadError(e.message))
  }, [])

  // build the stewardship defaults once roster + settings are in: a saved
  // gov_defaults value wins when its person is still eligible, else the
  // role-based prefill (pickByFn, else the first account). One-time seeding:
  // rating Auto (DQ), reviewed date 3 months out — like the old initGovDefaults.
  useEffect(() => {
    if (!people || !settings || defaults) return
    const gd = settings.gov_defaults || {}
    const b = people.filter((p) => p.id)
    const pick = (slot) => (pickByFn(people, slot) || b[0] || {}).id || ''
    const valid = (id, slot) => !!id && b.some((p) => p.id === id && eligibleFor(p, slot))
    setDefaults({
      steward: valid(gd.steward, 'businessSteward') ? gd.steward : pick('businessSteward'),
      owner: valid(gd.owner, 'owner') ? gd.owner : pick('owner'),
      custodian: valid(gd.custodian, 'custodian') ? gd.custodian : pick('custodian'),
      status: gd.status || 'Draft',
      domain: gd.domain || 'Utilities',
      rating: gd.rating != null && gd.rating !== '' ? String(gd.rating) : 'auto',
      reviewed: gd.reviewed || plusMonthsISO(3),
      applycats: gd.applycats != null ? !!gd.applycats : true,
      stakeholders: (gd.stakeholders || []).filter((id) => b.some((p) => p.id === id)),
    })
  }, [people, settings, defaults])

  // roster changed: re-derive any default whose person vanished or lost eligibility
  useEffect(() => {
    if (!people) return
    setDefaults((d) => {
      if (!d) return d
      const b = people.filter((p) => p.id)
      const fix = {}
      for (const [key, slot] of [['steward', 'businessSteward'], ['owner', 'owner'], ['custodian', 'custodian']]) {
        const ok = d[key] && b.some((p) => p.id === d[key] && eligibleFor(p, slot))
        if (!ok) fix[key] = (pickByFn(people, slot) || b[0] || {}).id || ''
      }
      return Object.keys(fix).length ? { ...d, ...fix } : d
    })
  }, [people])

  // one override card per scanned category; the steward slot is pre-filled
  // (MinIO owner tag → owns-map → Business Steward role), everything else
  // starts on "(use default)" and inherits
  useEffect(() => {
    if (!people) return
    setOverrides((prev) => {
      const next = {}
      const saved = (ws.governance && ws.governance.categories) || {}
      for (const c of cats) {
        next[c] = prev[c] || overrideFromSaved(saved[c])
          || emptyOverride(prefillFor(rows, people, c).id)
      }
      return next
    })
  }, [cats, people]) // eslint-disable-line react-hooks/exhaustive-deps

  /* ---------- stewardship defaults (persist to settings.json) ---------- */

  function changeDefaults(patch, explicit) {
    const next = { ...defaults, ...patch }
    setDefaults(next)
    const gd = { steward: next.steward, owner: next.owner, custodian: next.custodian,
      status: next.status, domain: next.domain, rating: next.rating,
      reviewed: next.reviewed, applycats: next.applycats, stakeholders: next.stakeholders }
    setSettings((s) => ({ ...(s || {}), gov_defaults: gd }))
    apiPost('/api/settings', { gov_defaults: gd }).catch(() => {})
    if (explicit) setDefMsg('✓ defaults saved — they restore on restart and Auto-assign respects them')
    else {
      setDefMsg('✓ saved')
      setTimeout(() => setDefMsg((m) => (m === '✓ saved' ? '' : m)), 2500)
    }
  }

  // Pick the DOMAIN classifier from the company's own data (deterministic
  // keyword map first, local AI as fallback — POST /api/suggest-domain).
  async function autoDomain(explicit) {
    try {
      const dcats = [...new Set(rows.map((r) => (r.Category || '').trim()).filter(Boolean))]
      const terms = rows.slice(0, 60).map((r) => r.Term).filter(Boolean).slice(0, 15)
      const d = await apiPost('/api/suggest-domain', {
        domains: PDC_DOMAINS, categories: dcats, terms,
        model: (settings && settings.model) || null,
        compute: (settings && settings.compute) || undefined,
      })
      if (d.domain) changeDefaults({ domain: d.domain })
      if (explicit) setDefMsg(d.domain ? `✓ domain: ${d.domain} — ${d.reason || ''}` : (d.reason || 'no suggestion'))
      return !!d.domain
    } catch (err) {
      if (explicit) setDefMsg(`Domain suggestion failed: ${err.message}`)
      return false
    }
  }

  /* ---------- roster actions ---------- */

  function toggleFn(idx, key) {
    setPeople((ps) => ps.map((p, j) =>
      j === idx ? { ...p, fns: { ...(p.fns || {}), [key]: !personFns(p)[key] } } : p))
    setRosterDirty(true)
  }

  function setExpertise(idx, v) {
    setPeople((ps) => ps.map((p, j) => (j === idx ? { ...p, expertise: v } : p)))
    setRosterDirty(true)
  }

  function rmPerson(idx) {
    setPeople((ps) => ps.filter((_, j) => j !== idx))
    setRosterDirty(true)
  }

  function addPerson(pf) {
    setPeople((ps) => [...ps, {
      name: pf.name.trim() || pf.email.split('@')[0],
      display_name: pf.display.trim(),
      email: pf.email.trim(),
      id: pf.id.trim(),
      roles: [], stakeholder_role: 'Steward', community: '', owns: '',
      expertise: pf.expertise.trim(),
    }])
    setRosterDirty(true)
  }

  async function saveRoster() {
    try {
      const d = await apiPost('/api/people', { people })
      setRosterDirty(false)
      setRosterMsg(`Saved ${(d.people || []).length} people ✓`)
    } catch (err) {
      setRosterMsg(`Save failed: ${err.message}`)
    }
  }

  // LLM expertise keywords per person (drives auto-assign); merges results
  // back by id → email → name, exactly like the old suggestExpertise.
  async function suggestExpertise(overwrite, roster) {
    const P = roster || people
    if (!P.length) {
      setExpMsg('No people in the roster yet.')
      return P
    }
    const ecats = [...new Set(rows.map((r) => r.Category).filter(Boolean))]
    setExpMsg(`Generating expertise from roles, responsibilities${ecats.length ? ' and scanned categories' : ''}…`)
    try {
      const d = await apiPost('/api/suggest-expertise', { people: P, categories: ecats, overwrite: !!overwrite })
      const by = {}
      for (const p of d.people || []) {
        if (p.id) by[`i:${p.id}`] = p
        if (p.email) by[`e:${(p.email || '').toLowerCase()}`] = p
        if (p.name) by[`n:${(p.name || '').toLowerCase()}`] = p
      }
      const next = P.map((p) => {
        const m = by[`i:${p.id}`] || by[`e:${(p.email || '').toLowerCase()}`] || by[`n:${(p.name || '').toLowerCase()}`]
        return m && m.expertise ? { ...p, expertise: m.expertise } : p
      })
      setPeople(next)
      if (d.updated) setRosterDirty(true)
      const via = d.used_llm ? 'the LLM'
        : `offline rules (${d.llm && d.llm.online ? 'LLM returned nothing' : 'Ollama offline'})`
      setExpMsg(`⚡ Set expertise for ${d.updated || 0} people via ${via}.`
        + (ecats.length ? '' : ' Scan a source first for sharper, category-aware keywords.')
        + (d.updated ? ' Review, then Save roster.' : ''))
      return next
    } catch (err) {
      setExpMsg(`Suggest failed: ${err.message}`)
      return P
    }
  }

  // Live roster fetch from Keycloak's Admin API; carries over any expertise
  // typed this session but not saved yet, then optionally LLM-fills blanks.
  async function fetchKeycloak(kc) {
    setKMsg('Fetching from Keycloak…')
    try {
      const d = await apiPost('/api/keycloak-users', {
        base_url: kc.base, realm: kc.realm,
        auth_realm: kc.authRealm.trim() || 'master',
        username: kc.user, password: kc.pass, token: kc.token,
        verify_tls: kc.verify, save: kc.save,
      })
      if (!d.ok) {
        setKMsg(`✗ ${d.message}`)
        return
      }
      const prevBy = {}
      for (const p of people || []) {
        if (!p.expertise) continue
        if (p.id) prevBy[`i:${p.id}`] = p.expertise
        if (p.email) prevBy[`e:${p.email.toLowerCase()}`] = p.expertise
        if (p.name) prevBy[`n:${p.name.toLowerCase()}`] = p.expertise
      }
      const fetched = (d.people || []).map((p) => {
        if (p.expertise) return p
        const e = prevBy[`i:${p.id}`] || prevBy[`e:${(p.email || '').toLowerCase()}`] || prevBy[`n:${(p.name || '').toLowerCase()}`]
        return e ? { ...p, expertise: e } : p
      })
      setPeople(fetched)
      setRosterDirty(!d.saved)
      const kept = d.expertise_preserved || 0
      const blanks = fetched.filter((p) => p.id && !(p.expertise || '').trim()).length
      setKMsg(`✓ Fetched ${d.count} users${d.saved ? ' (saved to roster)' : ' — review and Save roster'}${kept ? ` · kept expertise for ${kept}` : ''}.`)
      if (blanks && kc.genExp) {
        setKMsg(`✓ Fetched ${d.count} users. Generating expertise for ${blanks}…`)
        await suggestExpertise(false, fetched)
        setKMsg(`✓ Fetched ${d.count} users · expertise generated — review and Save roster.`)
      } else if (blanks) {
        setKMsg(`✓ Fetched ${d.count} users — ${blanks} have no expertise yet; run ⚡ Suggest expertise so auto-assign can match on more than role.`)
      }
    } catch (err) {
      setKMsg(`✗ ${err.message}`)
    }
  }

  /* ---------- per-category overrides + auto-assign ---------- */

  function setOvField(cat, field, value) {
    setOverrides((prev) => ({
      ...prev,
      [cat]: { ...prev[cat], [field]: value, src: { ...prev[cat].src, [field]: 'user' } },
    }))
  }

  function setOvPlain(cat, patch) {
    setOverrides((prev) => ({ ...prev, [cat]: { ...prev[cat], ...patch } }))
  }

  function autoAssign(peopleArg) {
    const P = peopleArg || people
    if (!rows.length) {
      setAutoMsg('Scan a source first — auto-assign reads each category’s columns.')
      return
    }
    if (!P.filter((p) => p.id).length) {
      setAutoMsg('Add at least one account with a UUID first.')
      return
    }
    // explicit defaults are the steward's word — with "respect defaults" on, a
    // slot that has one stays on (use default) unless a candidate strictly wins
    const defs = { businessSteward: defaults.steward || '', owner: defaults.owner || '', custodian: defaults.custodian || '' }
    let filled = 0
    let locked = 0
    let defaulted = 0
    const nextOv = { ...overrides }
    const nextInfo = {}
    for (const cat of cats) {
      const cv = catVocab(rows, cat)
      const prev = nextOv[cat] || emptyOverride(prefillFor(rows, P, cat).id)
      const ov = { ...prev, src: { ...prev.src } }
      const picks = {}
      for (const slot of SLOTS) {
        if (ov.src[slot] === 'user') {
          picks[slot] = { conf: 'low', reason: 'kept your manual pick', locked: true, id: ov[slot], name: personName(P, ov[slot]) }
          locked += 1
          continue
        }
        const dec = slotDecision(P, cat, cv, slot, autoFallback, autoRespect ? defs[slot] : '')
        picks[slot] = dec.pk
        if (dec.mode === 'default') {
          ov[slot] = ''
          ov.src[slot] = ''
          defaulted += 1
          continue
        }
        if (dec.pk.id) {
          ov[slot] = dec.pk.id
          ov.src[slot] = 'auto'
          filled += 1
        }
      }
      nextOv[cat] = ov
      nextInfo[cat] = picks
    }
    setOverrides(nextOv)
    setAutoInfo(nextInfo)
    setAutoMsg(`⚡ Filled ${filled} slot(s) across ${cats.length} categories`
      + (defaulted ? `, left ${defaulted} on your defaults` : '')
      + (locked ? `, kept ${locked} manual pick(s)` : '')
      + '. Expand a category to see why each person was chosen.')
  }

  function clearAuto() {
    setOverrides((prev) => {
      const next = {}
      for (const [cat, ov] of Object.entries(prev)) {
        const o = { ...ov, src: { ...ov.src } }
        for (const slot of SLOTS) {
          if (o.src[slot] === 'auto') {
            o[slot] = ''
            o.src[slot] = ''
          }
        }
        next[cat] = o
      }
      return next
    })
    setAutoInfo({})
    setAutoMsg('Cleared auto-filled picks. Manual edits and locks were kept.')
  }

  // One-click macro: fill missing expertise (LLM/offline), derive the domain
  // unless the steward saved one, then auto-assign every slot.
  async function setupStewardship() {
    if (!rows.length) {
      setAutoMsg('Scan a source first — stewardship reads each category’s columns.')
      return
    }
    if (!accounts.length) {
      setAutoMsg('Add at least one account with a UUID first.')
      return
    }
    let P = people
    const blanks = accounts.filter((p) => !(p.expertise || '').trim()).length
    if (blanks) {
      setAutoMsg(`Generating expertise for ${blanks} people…`)
      P = await suggestExpertise(false)
    }
    if (!(settings && settings.gov_defaults && settings.gov_defaults.domain)) await autoDomain(false)
    autoAssign(P)
  }

  // Collapsed summary: only fields that differ from the global defaults count
  // as overrides, so a category matching the defaults reads clean.
  function summaryBits(cat, ov) {
    const bits = []
    const nm = (id) => personName(people, id)
    if (ov.businessSteward && ov.businessSteward !== (defaults.steward || '')) bits.push(`Steward: ${nm(ov.businessSteward)}`)
    if (ov.owner && ov.owner !== (defaults.owner || '')) bits.push(`Owner: ${nm(ov.owner)}`)
    if (ov.custodian && ov.custodian !== (defaults.custodian || '')) bits.push(`Custodian: ${nm(ov.custodian)}`)
    if (ov.status && ov.status !== (defaults.status || '')) bits.push(ov.status)
    if (ov.rating === 'auto') {
      const d = dqForCategory(rows, cat)
      bits.push(d.n ? `★ ${d.stars} (auto ${d.mean}%)` : 'auto (no DQ)')
    } else if (ov.rating !== '' && ov.rating !== (defaults.rating || '')) {
      bits.push(ov.rating === '0' ? 'No rating' : `★ ${ov.rating}`)
    }
    if (ov.reviewedAt && ov.reviewedAt !== (defaults.reviewed || '')) bits.push(`Reviewed ${ov.reviewedAt}`)
    if (ov.shOn) bits.push(`${ov.stakeholders.length} stakeholder${ov.stakeholders.length === 1 ? '' : 's'}`)
    return bits
  }

  /* ---------- governance object + apply / generate ---------- */

  // The old buildGovernance(), verbatim in substance: default people scope,
  // per-category deltas only, and Auto ratings resolved to concrete 1–5 stars
  // from scan DQ so the server keeps receiving plain integers.
  function buildGovernance() {
    const mk = (id) => {
      const p = personById(people, id)
      return p ? { id: p.id, name: p.name, email: p.email, roles: ['Steward'] } : null
    }
    const stakeholders = defaults.stakeholders.map(mk).filter(Boolean)
    const gAuto = defaults.rating === 'auto'
    const gRating = gAuto ? dqForAll(rows).stars : (parseInt(defaults.rating || '0', 10) || 0)
    const categories = {}
    for (const cat of cats) {
      const o = overrides[cat]
      if (!o) continue
      const ov = {}
      for (const k of ['businessSteward', 'owner', 'custodian', 'status']) {
        if (o[k]) ov[k] = o[k]
      }
      if (o.rating === 'auto') {
        const d = dqForCategory(rows, cat)
        if (d.n) ov.rating = String(d.stars)
      } else if (o.rating !== '') {
        ov.rating = o.rating
      } else if (gAuto) {
        const d = dqForCategory(rows, cat)
        if (d.n) ov.rating = String(d.stars)
      }
      if (o.reviewedAt) ov.reviewedAt = o.reviewedAt
      if (o.shOn) {
        const sh = o.stakeholders.map(mk).filter(Boolean)
        if (sh.length) ov.stakeholders = sh
      }
      if (Object.keys(ov).length) categories[cat] = ov
    }
    return {
      status: defaults.status,
      domain: defaults.domain || '',
      rating: gRating,
      ratingMode: gAuto ? 'auto' : 'fixed',
      reviewedAt: defaults.reviewed || '',
      applyToCategories: defaults.applycats,
      createdBy: defaults.steward || defaults.owner || '',
      default: { owner: defaults.owner, custodian: defaults.custodian, businessSteward: defaults.steward, stakeholders },
      categories,
    }
  }

  // Keep the shared workspace's governance current whenever the inputs
  // change — it autosaves with the glossary (legacy `governance` key) and the
  // Apply page's Generate bakes it into the JSONL. setGovernance no-ops on an
  // identical value, so this is cheap on plain re-renders.
  useEffect(() => {
    if (!people || !defaults) return
    setGovernance(buildGovernance())
  }, [people, defaults, overrides, cats, rows]) // eslint-disable-line react-hooks/exhaustive-deps

  // Stamp each term's effective steward / owner / custodian (default +
  // category override) onto the workspace rows — they persist with the
  // autosaved glossary and ride into every export.
  function applyStewardshipToRows() {
    const nm = (id) => personName(people, id)
    let kept = 0
    let stamped = 0
    const next = rows.map((r) => {
      if (!isKept(r)) return r                 // dropped rows don't export — leave them alone
      kept += 1
      const ov = overrides[r.Category] || {}
      const bs = ov.businessSteward || defaults.steward || ''
      const own = ov.owner || defaults.owner || ''
      const cus = ov.custodian || defaults.custodian || ''
      if (bs || own || cus) stamped += 1
      return {
        ...r,
        Business_Steward: nm(bs),
        Business_Steward_ID: bs,
        Owner: nm(own),
        Owner_ID: own,
        Custodian: nm(cus),
        Custodian_ID: cus,
      }
    })
    setRows(next)
    setApplyMsg(`✓ Stamped steward / owner / custodian onto ${stamped} of ${kept} kept term(s) — autosaved with the workspace.`)
  }

  /* ---------- render ---------- */

  if (loadError) return <div className="error">{loadError}</div>
  if (!people || !defaults) {
    return (
      <>
        <div className="page-head">
          <h1>Govern</h1>
          <p className="psub">Manage the user roster and set stewardship applied to terms on export.</p>
        </div>
        <p className="loading">Loading roster &amp; saved defaults…</p>
      </>
    )
  }

  return (
    <>
      <div className="page-head">
        <h1>Govern</h1>
        <p className="psub">
          Manage the user roster and set stewardship applied to terms on export.
          People bind to PDC accounts by UUID.
        </p>
      </div>

      <HowItWorksCard />
      <KeycloakCard onFetch={fetchKeycloak} msg={kMsg} />

      <RosterCard people={people} rosterDirty={rosterDirty} rosterMsg={rosterMsg}
                  expMsg={expMsg} onToggleFn={toggleFn} onExpertise={setExpertise}
                  onRemove={rmPerson} onAdd={addPerson} onSave={saveRoster}
                  onSuggest={suggestExpertise} />

      <section className="card">
        <h2>Stewardship defaults <span>applied to every kept term (and category) — override per category below</span></h2>
        <div className="form-grid">
          <label>
            <span>Domain <span className="muted">· PDC classifier</span></span>
            <span className="gov-inlinerow">
              <select value={defaults.domain} onChange={(e) => changeDefaults({ domain: e.target.value })} style={{ flex: 1 }}>
                {PDC_DOMAINS.map((d) => <option key={d}>{d}</option>)}
              </select>
              <button className="ghost mini" onClick={() => autoDomain(true)}
                      title="Pick the domain classifier from the company data: the installed pack + company name (deterministic keyword map), the local AI as fallback. Saved with the defaults.">
                ⚡ auto
              </button>
            </span>
          </label>
          <label>
            Business steward
            <PeopleSelect pool={pools.businessSteward} value={defaults.steward}
                          onChange={(v) => changeDefaults({ steward: v })} noneLabel="(none)" />
          </label>
          <label>
            Owner
            <PeopleSelect pool={pools.owner} value={defaults.owner}
                          onChange={(v) => changeDefaults({ owner: v })} noneLabel="(none)" />
          </label>
          <label>
            Custodian
            <PeopleSelect pool={pools.custodian} value={defaults.custodian}
                          onChange={(v) => changeDefaults({ custodian: v })} noneLabel="(none)" />
          </label>
          <label>
            Status
            <select value={defaults.status} onChange={(e) => changeDefaults({ status: e.target.value })}>
              {['Draft', 'Review', 'Accepted', 'Deprecated'].map((s) => <option key={s}>{s}</option>)}
            </select>
          </label>
          <label>
            Rating
            <select value={defaults.rating} onChange={(e) => changeDefaults({ rating: e.target.value })}>
              <option value="0">None</option>
              <option value="auto">Auto (DQ)</option>
              {['1', '2', '3', '4', '5'].map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
            {defaults.rating === 'auto' && (
              <span className="muted">
                {dqForAll(rows).n
                  ? `≈ ${dqForAll(rows).stars}★ from ${dqForAll(rows).mean}% mean DQ · each category rated on its own DQ`
                  : 'scan a source to compute DQ'}
              </span>
            )}
          </label>
          <div className="field">
            Reviewed date
            <input type="date" value={defaults.reviewed} aria-label="Reviewed date"
                   onChange={(e) => changeDefaults({ reviewed: e.target.value })} />
            <label className="check gov-applycats"
                   title="Also stamp Status / Rating / Reviewed onto every category (not just the terms).">
              <input type="checkbox" checked={defaults.applycats}
                     onChange={(e) => changeDefaults({ applycats: e.target.checked })} />
              apply to categories too
            </label>
          </div>
        </div>
        <div style={{ marginTop: '.9rem' }}>
          <span className="muted" style={{ fontSize: '.82rem' }}>Stakeholders</span>
          <div className="gov-stakelist">
            {accounts.length === 0 && <span className="notes">No accounts with a UUID yet.</span>}
            {accounts.map((p) => (
              <label key={p.id}>
                <input type="checkbox" checked={defaults.stakeholders.includes(p.id)}
                       onChange={() => changeDefaults({
                         stakeholders: defaults.stakeholders.includes(p.id)
                           ? defaults.stakeholders.filter((x) => x !== p.id)
                           : [...defaults.stakeholders, p.id],
                       })} />
                {p.display_name || p.name}
              </label>
            ))}
          </div>
        </div>
        <div className="actions">
          <button className="ghost" onClick={() => changeDefaults({}, true)}
                  title="Persist these defaults to settings.json — they restore on every restart, and Auto-assign respects them.">
            Save defaults
          </button>
          {defMsg && <span className="summary">{defMsg}</span>}
        </div>

        {cats.length > 0 && accounts.length > 0 && (
          <>
            <h3 className="subhead">Per-category overrides</h3>
            <p className="hint-line">
              Every category inherits the defaults above. Expand one to override any field
              just for that category — fields left on <i>(use default)</i> keep inheriting.
              The steward is pre-filled from a MinIO owner tag, then the owns-map, then the
              Business&nbsp;Steward role. A field you set by hand is locked; re-running
              Auto-assign won’t overwrite it.
            </p>
            <div className="actions" style={{ marginTop: '.4rem' }}>
              <button className="primary" onClick={setupStewardship}
                      title="One click: generate any missing expertise (LLM), derive the domain, then auto-assign steward/owner/custodian across every category. Won't touch slots you set by hand.">
                ⚡ Set up stewardship
              </button>
              <button className="ghost" onClick={() => autoAssign()}
                      title="Match each person's role + expertise against each category and fill the steward, owner and custodian slots. Only fields you haven't changed by hand are touched.">
                Auto-assign all slots
              </button>
              <button className="ghost" onClick={clearAuto}
                      title="Clear the auto-filled picks and unlock everything (your manual edits are kept).">
                Clear auto
              </button>
              <label className="check"
                     title="When no roster member holds a slot's function, fall back to expertise matching — but only over people NOT scoped to other functions.">
                <input type="checkbox" checked={autoFallback} onChange={(e) => setAutoFallback(e.target.checked)} />
                expertise-only fallback when no role match
              </label>
              <label className="check"
                     title="A category override is written only when a candidate's expertise STRICTLY BEATS the default person's own score — otherwise the slot stays on (use default).">
                <input type="checkbox" checked={autoRespect} onChange={(e) => setAutoRespect(e.target.checked)} />
                respect defaults
              </label>
            </div>
            <p className="summary">{autoMsg}</p>
            {cats.map((cat) => (
              <CatCard key={cat} cat={cat} ov={overrides[cat] || emptyOverride()}
                       picks={autoInfo[cat]} open={!!openCats[cat]}
                       onToggle={() => setOpenCats((o) => ({ ...o, [cat]: !o[cat] }))}
                       pools={pools} accounts={accounts}
                       bits={summaryBits(cat, overrides[cat] || emptyOverride())}
                       onField={(f, v) => setOvField(cat, f, v)}
                       onPlain={(patch) => setOvPlain(cat, patch)} />
            ))}
          </>
        )}
        {cats.length > 0 && accounts.length === 0 && (
          <p className="hint-line">Add at least one account with a UUID to unlock per-category overrides and auto-assign.</p>
        )}
        {cats.length === 0 && (
          <p className="hint-line">Scan a source first — the per-category overrides build from the review grid’s categories.</p>
        )}
      </section>

      <section className="card">
        <h2>Apply stewardship <span>stewardship and ratings are written into the JSONL at export</span></h2>
        <div className="form-grid">
          <label>
            Glossary name
            <input type="text" placeholder="Business Glossary (Suggested)"
                   value={ws.glossaryName || ''}
                   onChange={(e) => setGlossaryMeta({ glossaryName: e.target.value })} />
          </label>
        </div>
        <div className="actions">
          <button className="primary" onClick={applyStewardshipToRows} disabled={!rows.length}
                  title="Stamp each term's effective Business Steward / Owner / Custodian (defaults + category overrides) onto the review rows — they persist with the saved workspace.">
            Apply stewardship to terms
          </button>
          {applyMsg && <span className="summary">{applyMsg}</span>}
        </div>
        {!rows.length && <p className="hint-line">Scan and review terms first — there’s nothing to stamp yet.</p>}
        <p className="hint-line">
          Governance is saved — generate the JSONL on the <b>Apply</b> page.
        </p>
      </section>

      <GovernanceSummaryCard />

      <div className="actions">
        <button className="ghost" onClick={() => onNavigate('review')}>← Review terms</button>
        <button className="ghost" onClick={() => onNavigate('dictionary')}>Term &amp; Tag dictionary</button>
        <button className="primary" onClick={() => onNavigate('apply')}>Resolve term IDs →</button>
      </div>
    </>
  )
}

/* ---------- how stewardship & auto-assign work (static explainer) ---------- */

function HowItWorksCard() {
  return (
    <details className="card">
      <summary>How stewardship &amp; auto-assign work</summary>
      <p className="hint-line" style={{ marginTop: '.6rem' }}>
        Governance is baked <b>into the JSONL at generate time</b>, so set it here before you
        generate. Every term carries three roles — set them once as defaults, then override
        per category.
      </p>
      <div className="gov-fielddefs">
        <span className="k">Business Steward</span>
        <span className="v">Owns the <i>meaning</i> of the term — accepts the definition and is
          accountable for it in PDC. Mapped from the Keycloak <code>Business_Steward</code> role.</span>
        <span className="k">Owner</span>
        <span className="v">Owns the <i>governance</i> of the data behind the term. Mapped
          from <code>Data_Steward</code>.</span>
        <span className="k">Custodian</span>
        <span className="v">The <i>technical</i> keeper of where the data is stored. Mapped
          from <code>Data_Storage_Administrator</code>.</span>
        <span className="k">UUID binding</span>
        <span className="v">A person only resolves in PDC by their Keycloak <b>UUID</b>, which is
          per-instance — fetch the roster live to guarantee the ids match.</span>
        <span className="k">Auto-assign</span>
        <span className="v">For each category it scores every person on (1) <b>expertise</b> keywords
          vs. that category’s terms/columns, then (2) their <b>role</b>. Best expertise match wins;
          with no match it falls back to the role default. Each card shows the <i>rationale</i>.
          Manual edits lock that field so a re-run won’t overwrite you.</span>
        <span className="k">Rating</span>
        <span className="v">A 1–5 quality star, set globally or per category. <b>Auto (scan DQ)</b>
          derives each category’s rating from its columns’ scan Data-Quality scores.</span>
      </div>
    </details>
  )
}

/* ---------- Keycloak fetch ---------- */

function KeycloakCard({ onFetch, msg }) {
  const [kc, setKc] = useState({ base: '', realm: '', authRealm: 'master', user: '',
    pass: '', token: '', verify: false, save: true, genExp: true })
  const [busy, setBusy] = useState(false)
  const set = (patch) => setKc((k) => ({ ...k, ...patch }))

  async function fetchNow() {
    setBusy(true)
    try {
      await onFetch(kc)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="card">
      <h2>Fetch users from Keycloak <span>start here — then set the roster below</span></h2>
      <p className="hint-line">
        Pull the roster live from Keycloak’s Admin API so ids always match the target
        instance. PDC fronts Keycloak at <code>&lt;server&gt;/keycloak</code>; list users from
        the <b>pdc</b> realm, get the admin token from the <b>master</b> realm.
      </p>
      <div className="form-grid gov-kcgrid">
        <label>
          Base URL
          <input type="text" placeholder="https://host/keycloak" value={kc.base}
                 onChange={(e) => set({ base: e.target.value })} />
        </label>
        <label>
          Realm (users)
          <input type="text" placeholder="pdc" value={kc.realm}
                 onChange={(e) => set({ realm: e.target.value })} />
        </label>
        <label>
          Admin realm
          <input type="text" placeholder="master" value={kc.authRealm}
                 onChange={(e) => set({ authRealm: e.target.value })} />
        </label>
        <label>
          Username
          <input type="text" placeholder="admin" value={kc.user}
                 onChange={(e) => set({ user: e.target.value })} />
        </label>
        <label>
          Password
          <input type="password" autoComplete="off" value={kc.pass}
                 onChange={(e) => set({ pass: e.target.value })} />
        </label>
        <label className="gov-kcspan3">
          Bearer token
          <input type="text" placeholder="eyJhbGciOi…"
                 value={kc.token} onChange={(e) => set({ token: e.target.value })} />
          <span className="muted">optional — instead of username / password; leave blank to use the credentials above</span>
        </label>
      </div>
      <div className="actions">
        <label className="check">
          <input type="checkbox" checked={kc.verify} onChange={(e) => set({ verify: e.target.checked })} />
          Verify TLS
        </label>
        <label className="check">
          <input type="checkbox" checked={kc.save} onChange={(e) => set({ save: e.target.checked })} />
          save to roster
        </label>
        <label className="check">
          <input type="checkbox" checked={kc.genExp} onChange={(e) => set({ genExp: e.target.checked })} />
          ⚡ generate expertise (LLM)
        </label>
        <button className="primary" onClick={fetchNow} disabled={busy}>{busy ? 'Fetching…' : 'Fetch'}</button>
        {msg && <span className="summary">{msg}</span>}
      </div>
    </section>
  )
}

/* ---------- roster ---------- */

function RosterCard({ people, rosterDirty, rosterMsg, expMsg, onToggleFn,
                      onExpertise, onRemove, onAdd, onSave, onSuggest }) {
  const [q, setQ] = useState('')
  const [overwrite, setOverwrite] = useState(false)
  const [pf, setPf] = useState({ name: '', display: '', email: '', id: '', expertise: '' })

  const uuidOk = !pf.id.trim() || UUID_RE.test(pf.id.trim())
  const emOk = !pf.email.trim() || EMAIL_RE.test(pf.email.trim())

  const query = q.trim().toLowerCase()
  const match = (p) => !query
    || [p.name, p.display_name, p.email, p.expertise].some((x) => String(x || '').toLowerCase().includes(query))
  const visible = people.map((p, i) => ({ p, i })).filter(({ p }) => match(p))

  function add() {
    if (!(uuidOk && emOk)) return
    onAdd(pf)
    setPf({ name: '', display: '', email: '', id: '', expertise: '' })
  }

  const fnMap = [['businessSteward', 'Steward'], ['owner', 'Owner'], ['custodian', 'Custodian']]

  return (
    <section className="card">
      <header>
        <h2>User roster <span>the accounts stewardship draws from</span></h2>
        {rosterDirty && <span className="badge warning">unsaved changes — Save roster</span>}
      </header>
      <div className="actions" style={{ marginTop: 0, marginBottom: '.8rem' }}>
        <input type="text" className="text" placeholder="Filter roster (name, email, expertise)…"
               value={q} onChange={(e) => setQ(e.target.value)} style={{ minWidth: '240px' }} />
        <button className="ghost" onClick={() => onSuggest(overwrite)}
                title="Use the local LLM to generate expertise keywords for each person from their role, responsibilities and the scanned categories. Keywords drive auto-assign. Empty people only, unless overwrite is ticked.">
          ⚡ Suggest expertise (LLM)
        </button>
        <label className="check">
          <input type="checkbox" checked={overwrite} onChange={(e) => setOverwrite(e.target.checked)} />
          overwrite existing
        </label>
        {expMsg && <span className="summary">{expMsg}</span>}
      </div>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Name &amp; functions</th><th>Display</th><th>Email</th><th>UUID</th>
              <th>Expertise <span className="muted">comma-separated · matched when auto-assigning</span></th><th></th>
            </tr>
          </thead>
          <tbody>
            {people.length === 0 && (
              <tr><td colSpan={6} className="notes">No people yet — fetch from Keycloak or add one below.</td></tr>
            )}
            {people.length > 0 && visible.length === 0 && (
              <tr><td colSpan={6} className="notes">No matches for “{q.trim()}”.</td></tr>
            )}
            {visible.map(({ p, i }) => {
              const f = personFns(p)
              const base = roleFns(p.roles)
              const ov = p.fns || {}
              return (
                <tr key={p.id || `${p.name}-${i}`}>
                  <td>
                    {p.name || ''}
                    <div className="gov-fnrow">
                      {fnMap.map(([k, l]) => {
                        const held = f[k]
                        const overridden = ov[k] != null && ov[k] !== base[k]
                        const src = held
                          ? (overridden
                            ? 'set manually on the roster (overrides Keycloak)'
                            : `held via Keycloak role${(p.roles || []).length ? ` — ${(p.roles || []).join(', ')}` : ''}`)
                          : (overridden
                            ? 'removed manually on the roster (overrides the Keycloak role)'
                            : (p.roles || []).length
                              ? `not held — the Keycloak roles (${(p.roles || []).join(', ')}) don't map to ${l}`
                              : 'not held — no mapped Keycloak role')
                        return (
                          <button key={k} className={`gov-fnbtn${held ? ' on' : ' off'}`}
                                  aria-pressed={held}
                                  onClick={() => onToggleFn(i, k)}
                                  title={`${l}: ${held ? 'HELD' : 'not held'} — ${src}. Click to toggle the override; it persists with Save roster and the stewardship pools draw from it.`}>
                            {held ? '✓ ' : ''}{l}
                          </button>
                        )
                      })}
                    </div>
                  </td>
                  <td>{p.display_name || ''}</td>
                  <td className="cell-clip">{p.email || ''}</td>
                  <td><code>{p.id || '(none)'}</code></td>
                  <td>
                    <input type="text" className="gov-exp" placeholder="add expertise…"
                           value={p.expertise || ''} onChange={(e) => onExpertise(i, e.target.value)} />
                  </td>
                  <td><button className="ghost" onClick={() => onRemove(i)}>Remove</button></td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <h3 className="subhead">Add a person</h3>
      <div className="form-grid">
        <label>
          Username
          <input type="text" placeholder="jane.doe" value={pf.name}
                 onChange={(e) => setPf({ ...pf, name: e.target.value })} />
        </label>
        <label>
          Display name
          <input type="text" placeholder="Jane Doe" value={pf.display}
                 onChange={(e) => setPf({ ...pf, display: e.target.value })} />
        </label>
        <label>
          Email
          <input type="text" placeholder="jane.doe@example.org" value={pf.email}
                 onChange={(e) => setPf({ ...pf, email: e.target.value })} />
          {!emOk && <span className="gov-invalid">Enter a valid email address.</span>}
        </label>
        <label>
          UUID (Keycloak)
          <input type="text" placeholder="account UUID" value={pf.id}
                 onChange={(e) => setPf({ ...pf, id: e.target.value })} />
          {!uuidOk && <span className="gov-invalid">Not a valid UUID (8-4-4-4-12 hex).</span>}
        </label>
        <label>
          Expertise <span className="muted">comma-separated keywords</span>
          <input type="text" placeholder="e.g. invoices, contracts, reports" value={pf.expertise}
                 onChange={(e) => setPf({ ...pf, expertise: e.target.value })} />
        </label>
      </div>
      <div className="actions">
        <button className="ghost" onClick={add} disabled={!(uuidOk && emOk)}>Add</button>
        <button className="primary" onClick={onSave}>Save roster</button>
        {rosterMsg && <span className="summary">{rosterMsg}</span>}
      </div>
      <p className="hint-line">
        UUIDs are per-instance (Keycloak) — a binding only resolves on the instance the id
        came from.
      </p>
    </section>
  )
}

/* ---------- one collapsible per-category override card ---------- */

function CatCard({ cat, ov, picks, open, onToggle, pools, accounts, bits, onField, onPlain }) {
  return (
    <div className={`gov-catcard${open ? ' open' : ''}`}>
      <button type="button" className="gov-cchead" onClick={onToggle} aria-expanded={open}>
        <span className="gov-ccname">{cat}</span>
        <span className="gov-ccsum">
          {bits.length ? <><span className="ov">Overrides:</span> {bits.join(' · ')}</> : 'Using defaults'}
          {picks && <span className="gov-ccauto-tag">⚡ auto</span>}
        </span>
        <span className="gov-cccar" aria-hidden="true">▸</span>
      </button>
      {open && (
        <div className="gov-ccbody">
          <div className="form-grid">
            {SLOTS.map((slot) => (
              <label key={slot}>
                {SLOT_LABEL[slot]}
                <PeopleSelect pool={pools[slot]} value={ov[slot]}
                              className={ov.src[slot] === 'auto' ? 'is-auto' : undefined}
                              onChange={(v) => onField(slot, v)} noneLabel="(use default)" />
              </label>
            ))}
            <label>
              Status
              <select value={ov.status} onChange={(e) => onField('status', e.target.value)}>
                <option value="">(use default)</option>
                {['Draft', 'Review', 'Accepted', 'Deprecated'].map((s) => <option key={s}>{s}</option>)}
              </select>
            </label>
            <label>
              Rating
              <select value={ov.rating} onChange={(e) => onField('rating', e.target.value)}>
                <option value="">(use default)</option>
                <option value="0">None</option>
                <option value="auto">Auto (DQ)</option>
                {['1', '2', '3', '4', '5'].map((n) => <option key={n} value={n}>{n}</option>)}
              </select>
            </label>
            <label>
              Reviewed date
              <input type="date" value={ov.reviewedAt} onChange={(e) => onField('reviewedAt', e.target.value)} />
            </label>
          </div>
          <label className="check" style={{ marginTop: '.7rem' }}>
            <input type="checkbox" checked={ov.shOn}
                   onChange={(e) => onPlain({ shOn: e.target.checked })} />
            Override stakeholders for this category
          </label>
          {ov.shOn && (
            <div className="gov-stakelist">
              {accounts.length === 0 && <span className="notes">No accounts with a UUID yet.</span>}
              {accounts.map((p) => (
                <label key={p.id}>
                  <input type="checkbox" checked={ov.stakeholders.includes(p.id)}
                         onChange={() => onPlain({
                           stakeholders: ov.stakeholders.includes(p.id)
                             ? ov.stakeholders.filter((x) => x !== p.id)
                             : [...ov.stakeholders, p.id],
                         })} />
                  {p.display_name || p.name}
                </label>
              ))}
            </div>
          )}
          {picks && (
            <div className="gov-auto">
              <div className="gov-auto-title">⚡ Auto-assign rationale</div>
              {SLOTS.map((s) => {
                const pk = picks[s] || {}
                return (
                  <div className="row" key={s}>
                    <span className="slot">{SLOT_LABEL[s]}</span>
                    <span>
                      {pk.id ? pk.name : <i>— left on default</i>}
                      {pk.locked && <> <span className="gov-conf low">your pick</span></>}
                      {' '}<span className={`gov-conf ${pk.conf || 'none'}`}>{pk.conf || 'none'}</span>
                    </span>
                    <span className="why">{pk.reason || ''}</span>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

/* ---------- read-only governance summary (GET /api/governance-summary) ---------- */

function GovernanceSummaryCard() {
  const [sum, setSum] = useState(null)
  const [error, setError] = useState(null)

  const refresh = () =>
    apiGet('/api/governance-summary').then((d) => {
      setSum(d)
      setError(null)
    }).catch((e) => setError(e.message))

  useEffect(() => { refresh() }, [])

  const v = sum?.vocabulary
  const tiles = v ? [
    { value: v.terms.governed, label: `governed terms (of ${v.terms.total})` },
    { value: v.terms.pending, label: 'terms pending review' },
    { value: v.tags.governed, label: `governed tags (of ${v.tags.total})` },
    { value: v.tags.pending, label: 'tags pending review' },
    { value: v.rules, label: 'auto-tag rules' },
    { value: sum.audit?.count ?? 0, label: 'audit trail entries' },
  ] : []

  return (
    <section className="card">
      <header>
        <h2>Governance summary <span>vocabulary health, audit trail and Registry drift</span></h2>
        <button className="ghost" onClick={refresh}>Refresh</button>
      </header>
      {error && <div className="error">{error}</div>}
      {!sum && !error && <p className="loading">Loading summary…</p>}
      {sum && (
        <>
          <div className="tiles">
            {tiles.map((t) => (
              <div className="tile" key={t.label}>
                <div className="value">{String(t.value)}</div>
                <div className="label">{t.label}</div>
              </div>
            ))}
          </div>
          <p className="hint-line">
            Domain: <b>{sum.domain || '—'}</b>
            {sum.audit?.last_action_at && <> · last governance action {String(sum.audit.last_action_at).replace('T', ' ')}</>}
            {sum.audit?.actors?.length > 0 && <> · actors: {sum.audit.actors.join(', ')}</>}
          </p>
          {sum.drift && (
            <p className="hint-line">
              Drift: <b>{sum.drift.total_off_vocabulary_tags}</b> off-vocabulary tag(s) across{' '}
              <b>{sum.drift.registries.length}</b> written Registr{sum.drift.registries.length === 1 ? 'y' : 'ies'}{' '}
              ({sum.drift.total_concepts} concepts) — off-vocabulary = concept tags outside the governed allow-list.
            </p>
          )}
        </>
      )}
    </section>
  )
}

/* ---------- shared: a people <select> whose pool is roster-constrained ---------- */

function PeopleSelect({ pool, value, onChange, noneLabel, className }) {
  const missing = value && !pool.some((p) => p.id === value)
  return (
    <select className={className} value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">{noneLabel}</option>
      {missing && <option value={value}>(no longer in this pool)</option>}
      {pool.map((p) => <option key={p.id} value={p.id}>{p.display_name || p.name}</option>)}
    </select>
  )
}
