// Review page — the port of the old UI's Glossary page: the review grid.
// One row per suggested term (one scanned column) with inline editing, keep/
// drop pruning, filters, the duplicate advisor (Merge / Disambiguate / Keep
// separate with evidence -> live probe -> AI escalation), and the AI agent
// toolbar (enrich / AI suggest / QA / categorize / retag). Re-modeled from
// static/js/06-review-aids.js, 08-resolve-dups.js and 10-agents.js.
//
// The grid rows ARE the shared workspace (src/state.js): read via
// useWorkspace(), every mutation goes through setRows()/patchRow() so the
// autosave plumbing there picks it up. Unlike the old UI, the AI agents here
// PROPOSE: each run collects its changes into a diff panel and the steward
// applies the selected ones — nothing mutates the grid behind your back.
import { Fragment, memo, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { apiGet, apiPost } from './../api.js'
import { useWorkspace, usePersistentState, getUi, setUi, setRows, patchRow, setGlossaryMeta, setGovernance, setCategoriesConfirmed, setReviewCompleted, save } from './../state.js'
import { sameSourceCount, selfFold } from './../rowmerge.js'
import './review.css'

/* ---------- row helpers (ported from the old UI's core) ---------- */

const truthy = (v) => ['y', 'yes', 'true', '1'].includes(String(v).toLowerCase())
const deep = (a) => JSON.parse(JSON.stringify(a))
const splitList = (s) => String(s || '').split(';').map((t) => t.trim()).filter(Boolean)
const sevRank = (s) => ({ HIGH: 3, MEDIUM: 2, LOW: 1 })[String(s || '').toUpperCase()] || 0
const confRank = (c) => ({ High: 3, Medium: 2, Low: 1 })[c] || 0
const prettify = (s) => String(s || '').replace(/_+/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()).trim()
const tableOf = (sc) => {
  const f = String(sc || '').split(';')[0].trim().split('.')
  return f.length >= 2 ? f[f.length - 2] : ''
}

// A table-level term is conceptual (no Source_Column) and always kept — the
// confidence cull must never drop it.
function isTableTerm(r) {
  if (!r) return false
  const noCol = !String(r.Source_Column || '').trim()
  const tagged = /(^|;)\s*table-level\s*(;|$)/i.test(r.Suggested_Tags || '')
  const record = /\bRecord$/.test(String(r.Term || '').trim())
  return noCol && (tagged || record)
}

function computeStats(rows) {
  const conf = { High: 0, Medium: 0, Low: 0 }
  const sev = { HIGH: 0, MEDIUM: 0, LOW: 0 }
  const cats = new Set()
  let pii = 0
  let enr = 0
  rows.forEach((r) => {
    // the chip counts the categories of the glossary being EXPORTED — dropped
    // rows' scan-era categories would inflate it after the taxonomy settles
    if (r.Category && truthy(r.Keep)) cats.add(r.Category)
    if (conf[r.Confidence] != null) conf[r.Confidence]++
    if (sev[r.Sensitivity] != null) sev[r.Sensitivity]++
    if (r.PII_Category) pii++
    if (rowLLM(r)) enr++
  })
  return { terms: rows.length, categories: cats.size, pii, confidence: conf, sensitivity: sev, enriched: enr }
}

// Collapse a duplicate group into ONE term linked to all its columns —
// representative = best definition (LLM-enriched, then longest, then highest
// confidence); tags/sources union, sensitivity/CDE/confidence take the max.
function mergeMembers(g) {
  const base = {
    ...g.slice().sort((a, b) => {
      const al = (a.LLM_Definition === 'Yes' || a.LLM_Enriched === 'Yes') ? 1 : 0
      const bl = (b.LLM_Definition === 'Yes' || b.LLM_Enriched === 'Yes') ? 1 : 0
      if (al !== bl) return bl - al
      const ad = (a.Definition || '').length
      const bd = (b.Definition || '').length
      if (ad !== bd) return bd - ad
      return confRank(b.Confidence) - confRank(a.Confidence)
    })[0],
  }
  const tags = new Set()
  g.forEach((r) => splitList(r.Suggested_Tags).forEach((t) => tags.add(t)))
  base.Suggested_Tags = [...tags].join(';')
  base.Sensitivity = g.reduce((m, r) => (sevRank(r.Sensitivity) > sevRank(m) ? r.Sensitivity : m), g[0].Sensitivity)
  base.Critical_Data_Element = g.some((r) => r.Critical_Data_Element === 'Yes') ? 'Yes' : 'No'
  base.Confidence = g.reduce((m, r) => (confRank(r.Confidence) > confRank(m) ? r.Confidence : m), g[0].Confidence)
  base.Suggested_Rating = g.reduce((m, r) => Math.max(m, parseInt(r.Suggested_Rating || 0, 10) || 0), 0)
  const cols = []
  const seen = new Set()
  g.forEach((r) => splitList(r.Source_Column).forEach((s) => { if (!seen.has(s)) { seen.add(s); cols.push(s) } }))
  base.Source_Column = cols.join('; ')
  base.Source_Ratings = Object.assign({}, ...g.map((r) => r.Source_Ratings || {}))
  base.Source_Quality_Dims = Object.assign({}, ...g.map((r) => r.Source_Quality_Dims || {}))
  base.Keep = 'Y'
  return base
}

// Keep a duplicate group separate but rename every member unique by appending
// its source table (falling back to category).
function splitMembersUnique(g, taken) {
  const t = String(g[0].Term || '').trim()
  return g.map((r) => {
    const tbl = prettify(tableOf(r.Source_Column)) || prettify(r.Category)
    let cand = `${t} (${tbl || r.Category || '1'})`
    if (taken.has(cand)) cand = `${t} (${prettify(r.Category)})`
    let k = 2
    while (taken.has(cand)) cand = `${t} (${tbl || r.Category} ${k++})`
    taken.add(cand)
    return { ...r, Term: cand }
  })
}

/* ---------- group model: which cluster does a row belong to? ----------
   Detection is dynamic (a row follows its CURRENT name) except rows inside an
   ACTIVE resolution, which keep their frozen `_grp` key — that's what makes a
   merge/disambiguate survive later renames. Table terms never cluster. */

const soloKey = (i) => '\u0000solo:' + i

function activeNames(grp) {
  return new Set(Object.keys(grp).filter((n) => grp[n].action && grp[n].action !== 'separate'))
}

function keyOf(r, i, active) {
  if (isTableTerm(r)) return soloKey(i)
  // an auto-pruned structural key (surrogate PK/FK) is not a business term, so
  // it never joins a duplicate group — Merge/Disambiguate applies to KEPT
  // business terms only. Ticking Keep restores it to normal clustering.
  if (r.Prune_Reason && !truthy(r.Keep)) return soloKey(i)
  if (r._grp != null && active.has(r._grp)) return r._grp
  return String(r.Term || '').trim()
}

// Apply Merge / Disambiguate / Keep separate to ONE group — pure: returns the
// next {rows, grp}. The group's base (its live members at first action) is
// snapshotted so every action is reversible via 'separate'.
function applyGroupAction(rowsIn, grpIn, name, action) {
  const active = activeNames(grpIn)
  const isMember = (r, i) => r && keyOf(r, i, active) === name
  const live = rowsIn.filter((r, i) => isMember(r, i))
  const prior = grpIn[name]
  const base = prior && prior.base && prior.base.length ? prior.base : deep(live)
  if (!base.length) return { rows: rowsIn, grp: grpIn }
  let derived
  if (action === 'merge') {
    derived = [{ ...mergeMembers(deep(base)), _grp: name }]
  } else if (action === 'split') {
    const taken = new Set(rowsIn.filter((r, i) => r && !isMember(r, i)).map((r) => String(r.Term || '').trim()))
    derived = splitMembersUnique(deep(base), taken).map((r) => ({ ...r, _grp: name }))
  } else {
    derived = deep(base).map((r) => { const { _grp, ...rest } = r; return rest })
  }
  const out = []
  let inserted = false
  rowsIn.forEach((r, i) => {
    if (isMember(r, i)) {
      if (!inserted) { derived.forEach((d) => out.push(d)); inserted = true }
    } else out.push(r)
  })
  if (!inserted) derived.forEach((d) => out.push(d))
  return { rows: out, grp: { ...grpIn, [name]: { action, base } } }
}

// Every kept duplicate name (count > 1) under the current group keys.
function allDupGroups(rowsIn, grpIn) {
  const active = activeNames(grpIn)
  const c = {}
  rowsIn.forEach((r, i) => {
    if (!r || !truthy(r.Keep) || isTableTerm(r)) return
    const k = keyOf(r, i, active)
    if (k) c[k] = (c[k] || 0) + 1
  })
  return Object.keys(c).filter((k) => c[k] > 1)
}

/* ---------- AI agent definitions (each proposes; the steward applies) ---------- */

const CHUNK = 6

// One-line "what it does" per agent — the single source for both the "How to
// review" guide and the proposal strip that appears when a run finishes, so the
// explanation is right there when you're deciding whether to accept. Keyed by
// the agent's proposal label (matches the toolbar button text).
const AGENT_DESC = [
  { label: 'AI pass (all fields)',
    desc: (<>
      <span className="rv-dp">
        <b>One model call per batch of kept rows</b>, covering everything the model is
        allowed to decide: Definition, Purpose, a clearer name, governed tags — and a
        category only where the current one is blank.
      </span>
      <span className="rv-dp">
        <b>What it may not decide:</b> tags come only from the governed allow-list, an
        existing category is never changed, a proposed name lands as a suggestion chip
        rather than being applied, and sensitivity and PII stay deterministic from the
        scan. Two deterministic jobs ride along free — governed tags are re-derived from
        the Dictionary before the model looks, and the definition linter stamps the
        QA chip.
      </span>
      <span className="rv-dp">
        <b>Why one call:</b> every field is proposed together, from the same evidence
        and the same guardrails — so a proposed name never contradicts its own
        definition, category or tags.
      </span>
      <span className="rv-dp">
        <b>Quality dial:</b> Settings → Batch size. At <b>1</b>, every row gets its own
        call and the model&apos;s full attention — the exact prompt <i>AI review</i> uses;
        higher batches answer faster but share one reply across rows, so wording
        flattens toward templates.
      </span>
      <span className="rv-dp">
        <b>To redo:</b> one row — <i>AI review</i> on that row; one field — accept only
        that pill.
      </span>
    </>) },

  { label: 'AI categories (schema)',
    desc: 'One call shown what the scan proved - tables, columns and FK links - proposing an abstract business grouping: the fewest categories that still discriminate, every table placed in one. Each assignment lands as a Category pill for you to accept; tables the model cannot place keep their physical group. Settle the set, rename any group, and Export pack freezes it.' },
  { label: 'AI review (this row)',
    desc: 'The same pass, scoped to one row — for when a single term came back weak and you don’t want to spend a full sweep on it. Identical prompt, evidence and guardrails; the proposals land as pills on that row alone.' },
]
const AGENT_META = Object.fromEntries(AGENT_DESC.map((a) => [a.label, a]))

// Accepting one proposed field carries ONLY that field's provenance flag
// (plus the QA clear for Definition). Row-level LLM_Enriched is deliberately
// absent: it is a legacy flag the chips fall back to when per-field flags are
// missing, so spreading it on a single-field accept lit the LLM chip on
// fields never accepted — accept a Definition, Purpose glows. Field-caught.
const CARRY_FOR = {
  Definition: ['LLM_Definition', 'QA_Issues'],
  Purpose: ['LLM_Purpose'],
  Suggested_Name: ['LLM_Name'],
  Term: ['LLM_Name'],
}

// Chip truth for one field. The per-field flag wins; the row-level fallback
// exists for LEGACY saves enriched before per-field flags existed — and a
// legacy row is recognisable because NO per-field flag exists on it. A row
// carrying any per-field flag is current-format: an absent flag there means
// "not model-written" (this also heals rows the old accept-carry damaged).
const LLM_FIELD_FLAGS = ['LLM_Definition', 'LLM_Purpose', 'LLM_Name']
const llmChip = (r, flag) => r[flag] === 'Yes'
  || (r.LLM_Enriched === 'Yes' && LLM_FIELD_FLAGS.every((f) => r[f] === undefined))

// "Was any of this row model-written?" — reads all four flags, since current
// saves stamp per-field only and legacy saves stamp the row.
const rowLLM = (r) => r.LLM_Enriched === 'Yes' || LLM_FIELD_FLAGS.some((f) => r[f] === 'Yes')

// `names` is the seed-request focus filter (Set of lowercased term names) —
// only the Policy Generator banner's "Show these terms" sets it.
const EMPTY_FILTERS = { q: '', cat: '', sev: '', conf: '', tag: '', pii: false, kept: false, names: null }

export default function ReviewPage({ onNavigate }) {
  const ws = useWorkspace()
  const rows = ws.rows

  // Persisted across page navigation (App unmounts the inactive page) so the
  // steward's working context survives a hop to the Dictionary and back — see
  // usePersistentState in state.js. Cleared when a different glossary loads.
  const [filters, setFilters] = usePersistentState('review.filters', EMPTY_FILTERS)
  const [grp, setGrp] = usePersistentState('review.grp', {})           // {name: {action, base}}
  const [bulk, setBulk] = usePersistentState('review.bulk', { merge: false, disambig: false })
  const [sim, setSim] = usePersistentState('review.sim', null)         // {busy, list, error} | null
  const [simThresh, setSimThresh] = usePersistentState('review.simThresh', 0.6)
  const [expanded, setExpanded] = usePersistentState('review.expanded', null) // open editor row index
  const [hmSnap, setHmSnap] = usePersistentState('review.hmSnap', null)       // [{index, keep}] for the H+M toggle revert

  // Which candidate terms PDC already holds, and in which glossary. Persisted
  // like the other working context: the result is worth keeping across a hop to
  // the Dictionary, and re-running it costs a round trip per distinct name.
  const [xg, setXg] = usePersistentState('review.xglossary', null)  // {found, hits, checked} | null

  // Transient — safe to reset on navigation (in-flight runs, one-off messages).
  const [msg, setMsg] = useState('')
  const [error, setError] = useState(null)
  const [xgConn, setXgConn] = useState({ base: '', ver: 'v3', realm: 'pdc',
                                         user: '', pass: '', verify: false })
  const [xgBusy, setXgBusy] = useState(false)
  const [xgOpen, setXgOpen] = useState(false)

  // Prefill the host from saved settings. Credentials are NOT saved anywhere and
  // are asked for each time - see _pdc_token_and_reauth: the token lives in
  // memory for the call and nothing is persisted.
  useEffect(() => {
    if (!xgOpen) return
    apiGet('/api/settings').then((s) => setXgConn((c) => ({
      ...c,
      base: c.base || s.pdc_base || '',
      realm: s.pdc_realm || c.realm,
      ver: s.pdc_ver || c.ver,
      verify: s.pdc_verify != null ? !!s.pdc_verify : c.verify,
    }))).catch(() => {})
  }, [xgOpen])

  const checkExisting = useCallback(async () => {
    const names = [...new Set(rows.filter((r) => r && truthy(r.Keep))
                                  .map((r) => String(r.Term || '').trim()).filter(Boolean))]
    if (!names.length) { setMsg('No kept terms to check.'); return }
    if (!xgConn.base.trim()) { setMsg('PDC base URL is required.'); return }
    setXgBusy(true); setMsg(`Checking ${names.length} term(s) against PDC…`)
    try {
      const d = await apiPost('/api/pdc/terms/existing', {
        base_url: xgConn.base.trim(), version: xgConn.ver,
        realm: (xgConn.realm || 'pdc').trim(), username: xgConn.user,
        password: xgConn.pass, verify_tls: !!xgConn.verify, names,
      })
      setXg(d)
      setMsg(d.hits
        ? `${d.hits} of ${d.checked} term(s) already exist in PDC — reuse rather than re-author.`
        : `None of the ${d.checked} term(s) exist in PDC yet.`)
    } catch (e) {
      setMsg(`Check failed: ${e.message}`)
    } finally {
      setXgBusy(false)
    }
  }, [rows, xgConn, setXg])
  const [reco, setReco] = useState({})             // {name: recommendation} — re-derived on mount
  const [advising, setAdvising] = useState(false)
  const [agent, setAgent] = useState(null)         // {label, done, total, proposed, cancelling}
  const [proposals, setProposals] = useState(null) // {label, note, items:{rowIndex:{patch, display, issues?}}} — inline pills
  // declared HERE, with its sibling agent states: the silent-heal effect far
  // below reads it in a dependency array, which evaluates during render — a
  // later declaration is a temporal-dead-zone crash that blanks the page
  // (field-caught on the .52 clean install; bundlers cannot catch TDZ)
  const [catBusy, setCatBusy] = useState(false)
  // session flag: an AI-categories run produced proposals — advances the
  // strip's highlight to step 2 (Approve). Not persisted: after a reload the
  // highlight falls back to step 1, which is harmless (re-proposing is safe).
  const [catRan, setCatRan] = useState(false)
  const [evidence, setEvidence] = useState(null)   // row index | null
  const [busy, setBusy] = useState(null)           // 'load' | 'enhance' | 'save'
  const [saveName, setSaveName] = useState('')
  const [seedReqs, setSeedReqs] = useState([])     // Policy Generator seed requests (banner)

  const cancelRef = useRef(false)
  // raw-scan snapshot for Reset all — persisted so remounting doesn't recapture
  // it from already-edited rows (which would make Reset all reset to the edits).
  const snapRef = useRef(getUi('review.snap'))
  const lastPosRef = useRef(null)                  // shift-click keep anchor
  const visRef = useRef([])
  const rowsRef = useRef(rows)
  rowsRef.current = rows
  const proposalsRef = useRef(null)                // acceptProp reads the live pills state
  proposalsRef.current = proposals
  const loadFileRef = useRef(null)
  const enhanceFileRef = useRef(null)
  const masterRef = useRef(null)
  const tableWrapRef = useRef(null)                // scroll container — position persisted across nav

  // Restore the grid scroll position on mount and keep it current, so hopping
  // to the Dictionary and back lands you where you left off.
  useEffect(() => {
    const el = tableWrapRef.current
    if (!el) return undefined
    const saved = getUi('review.scroll', 0)
    if (saved) el.scrollTop = saved
    const onScroll = () => setUi('review.scroll', el.scrollTop)
    el.addEventListener('scroll', onScroll, { passive: true })
    return () => el.removeEventListener('scroll', onScroll)
  }, [])

  // Capture the reset-point the first time rows appear (scan/load happened on
  // another page); the load/enhance actions below refresh it explicitly.
  useEffect(() => {
    if (rows.length && !snapRef.current) { snapRef.current = deep(rows); setUi('review.snap', snapRef.current) }
  }, [rows])

  // Seed requests from the Policy Generator (the no-seed feedback loop): it
  // drops seed-request.json beside the Registry when concepts arrive with no
  // detection seeds and no stated intent. Best-effort — the grid never blocks.
  useEffect(() => {
    let alive = true
    apiGet('/api/seed-requests')
      .then((d) => { if (alive) setSeedReqs((d && d.requests) || []) })
      .catch(() => {})
    return () => { alive = false }
  }, [])

  const seedFocus = useCallback((sr) => {
    setFilters((f) => {
      if (f.names) return { ...f, names: null }
      return { ...f, names: new Set(sr.terms.map((t) => String(t.name || '').trim().toLowerCase())) }
    })
  }, [])

  async function seedHandled(sr) {
    try {
      await apiPost('/api/seed-requests/handle', { file: sr.file })
      setSeedReqs((rs) => rs.filter((r) => r.file !== sr.file))
      setFilters((f) => (f.names ? { ...f, names: null } : f))
      setMsg(`Seed request ${sr.file} marked handled.`)
    } catch (err) { setError(err.message) }
  }

  /* ---------- filtering + clustering ---------- */

  const shown = useMemo(() => {
    const q = filters.q.trim().toLowerCase()
    const out = []
    rows.forEach((r, i) => {
      if (!r) return
      if (filters.cat && r.Category !== filters.cat) return
      if (filters.sev && r.Sensitivity !== filters.sev) return
      if (filters.conf && r.Confidence !== filters.conf) return
      if (filters.tag && !splitList(r.Suggested_Tags).includes(filters.tag)) return
      if (filters.pii && !r.PII_Category) return
      if (filters.kept && !truthy(r.Keep)) return
      if (filters.names && !filters.names.has(String(r.Term || '').trim().toLowerCase())) return
      if (q) {
        const hay = `${r.Term || ''} ${r.Definition || ''} ${r.Source_Column || ''} ${r.Category || ''} ${r.Suggested_Tags || ''}`.toLowerCase()
        if (!hay.includes(q)) return
      }
      out.push(i)
    })
    return out
  }, [rows, filters])

  // FROZEN WHILE TYPING. The duplicate clusters key on the row's own text, and
  // that key ends up in the Fragment key of the row's subtree - so every
  // keystroke in Term or Category renamed the React key, unmounted the input
  // mid-word, and the cursor was gone: one letter at a time. Grouping now works
  // from a snapshot taken when focus enters the grid and regroups on the way
  // out, when losing the element costs nothing.
  const [gridEditing, setGridEditing] = useState(false)
  const frozenRowsRef = useRef(rows)
  const onGridFocusIn = useCallback((e) => {
    const t = e.target
    if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.tagName === 'SELECT')) {
      setGridEditing((was) => {
        if (!was) frozenRowsRef.current = rowsRef.current
        return true
      })
    }
  }, [])
  const onGridFocusOut = useCallback((e) => {
    if (!e.currentTarget.contains(e.relatedTarget)) setGridEditing(false)
  }, [])
  const groupingRows = gridEditing ? frozenRowsRef.current : rows

  const clusters = useMemo(() => {
    const active = activeNames(grp)
    const by = {}
    const order = []
    shown.forEach((i) => {
      // grouping reads the SNAPSHOT so keys stay stable mid-edit; everything
      // rendered inside still reads the live row
      const r = groupingRows[i] || rows[i]
      if (!r) return
      const k = keyOf(r, i, active)
      if (!by[k]) { by[k] = []; order.push(k) }
      by[k].push(i)
    })
    return { by, order }
  }, [shown, groupingRows, rows, grp])

  const vis = useMemo(() => clusters.order.flatMap((k) => clusters.by[k]), [clusters])
  visRef.current = vis
  const posOf = useMemo(() => { const m = new Map(); vis.forEach((i, p) => m.set(i, p)); return m }, [vis])

  const stats = useMemo(() => computeStats(rows), [rows])
  // Filter options split by liveliness. Dropped rows keep their scan-era
  // categories and tags forever (the AI agents deliberately run on KEPT rows
  // only), so a flat list kept offering the physical groups after the
  // taxonomy settled — "the dropdown doesn't update after AI categorize"
  // (field-caught on the fresh-install run). Kept values lead; residue that
  // exists only on dropped rows stays reachable in a labelled group, because
  // filtering is also how a pruned key gets found and restored.
  const cats = useMemo(() => {
    const kept = new Set(); const all = new Set()
    rows.forEach((r) => {
      const c = r.Category
      if (!c) return
      all.add(c)
      if (truthy(r.Keep)) kept.add(c)
    })
    return { kept: [...kept].sort(),
             droppedOnly: [...all].filter((c) => !kept.has(c)).sort() }
  }, [rows])
  const tags = useMemo(() => {
    const kept = new Set(); const all = new Set()
    rows.forEach((r) => splitList(r.Suggested_Tags).forEach((t) => {
      all.add(t)
      if (truthy(r.Keep)) kept.add(t)
    }))
    const cmp = (a, b) => a.toLowerCase().localeCompare(b.toLowerCase())
    return { kept: [...kept].sort(cmp),
             droppedOnly: [...all].filter((t) => !kept.has(t)).sort(cmp) }
  }, [rows])
  const kept = useMemo(() => rows.reduce((n, r) => n + (truthy(r.Keep) ? 1 : 0), 0), [rows])
  // rows sharing a source column with an earlier row — damage from the old
  // label-keyed merge (re-ingestion after the taxonomy settled); heals
  // silently below
  const dupSources = useMemo(() => sameSourceCount(rows), [rows])

  // THE KEYSTONE — the steward's explicit "the taxonomy is settled". Stored
  // with the workspace ({at, categories}); everything downstream keys off it
  // (Dictionary syncs at confirm, Govern reads it instead of guessing). If
  // the kept category set drifts from the confirmed list, the button reverts
  // to actionable — drift is visible, never silent.
  const catsConfirmedCurrent = useMemo(() => {
    const c = ws.categoriesConfirmed
    if (!c || !Array.isArray(c.categories)) return false
    return JSON.stringify(c.categories) === JSON.stringify(cats.kept)
  }, [ws.categoriesConfirmed, cats])
  // The strip reads as a STEPPER: one blue at a time (user-specified flow
  // lighting — "once AI categorize has completed it moves onto Approve…").
  // Highlight only: every button stays clickable, so a manual workflow is
  // never gated. Step derives from durable state where it exists (the
  // keystone; LLM-enriched rows prove the pass ran) and the session catRan
  // flag for step 1 → 2.
  const agentStep = catsConfirmedCurrent
    ? (stats.enriched > 0 ? 0 : 3)
    : (catRan ? 2 : 1)
  // kept categories that are still just the humanized physical name of their
  // own table/folder — same slug rule Govern badges with
  const physicalLooking = useMemo(() => cats.kept.filter((cat) => {
    const slug = cat.trim().toLowerCase().replace(/\s+/g, '_')
    if (!slug) return false
    const withSrc = rows.filter((r) => truthy(r.Keep) && (r.Category || '') === cat
      && String(r.Source_Column || '').trim())
    return withSrc.length && withSrc.every((r) =>
      String(r.Source_Column).toLowerCase().split(/[;,]/).every((src) =>
        !src.trim() || src.split(/[./\\]/).map((x) => x.trim()).includes(slug)))
  }), [rows, cats])

  // Close the Review stage: everything in sync at one deliberate moment —
  // the glossary saves, the Dictionary syncs to this exact grid, and the
  // completion is recorded with the workspace. Warns (never blocks) when the
  // keystone is missing or pills are still pending: the steward stays
  // sovereign, the gate just refuses to be passed accidentally.
  async function completeReview() {
    if (!catsConfirmedCurrent && !window.confirm(
      'Categories have not been approved (2 · Approve categories) — the taxonomy may still move.\n\nComplete the review anyway?')) return
    if (proposals && !window.confirm(
      'There are unaccepted AI pills — they are proposals only and will not travel.\n\nComplete the review anyway?')) return
    setReviewCompleted({ at: new Date().toISOString() })
    try { await save() } catch { /* the autosave banner reports save errors */ }
    try { await apiPost('/api/tagdict/sync', { rows: rowsRef.current }) } catch { /* the Dictionary self-syncs on entry */ }
    onNavigate('dictionary')
  }

  async function confirmCategories() {
    const list = cats.kept
    if (!list.length) return
    if (physicalLooking.length && !window.confirm(
      `${physicalLooking.length} categor${physicalLooking.length === 1 ? 'y still looks' : 'ies still look'} like physical table/folder groups:\n\n`
      + physicalLooking.join(' · ')
      + '\n\nConfirm anyway? Settling them first (1 · AI categories, or filter + Rename) is usually the better order — they will flow to the Dictionary and Govern as-is.')) return
    setCategoriesConfirmed({ at: new Date().toISOString(), categories: list })
    // A settled taxonomy deserves a durable workspace: the autosave only runs
    // once the glossary has a NAME, and two field losses (a window crash and
    // a page reload) each wiped a full unsaved session. If the steward has
    // not named it by the keystone, name it for them — visibly, renameable —
    // and save, so everything after this moment survives a dead window.
    let named = ''
    if (!ws.name && !ws.id) {
      let company = ''
      try { company = ((await apiGet('/api/settings')).company || '').trim() } catch { /* fallback below */ }
      const auto = `${company || 'Glossary'} review — ${new Date().toISOString().slice(0, 10)}`
      setGlossaryMeta({ name: auto })
      setSaveName(auto)
      try {
        await save()
        named = ` Saved as “${auto}” (rename any time) so this work survives a closed window.`
      } catch { /* the autosave banner reports save errors */ }
    }
    let synced = ''
    try {
      const d = await apiPost('/api/tagdict/sync', { rows: rowsRef.current })
      synced = d.pending_refreshed
        ? ` Dictionary synced — ${d.pending_refreshed} pending entr${d.pending_refreshed === 1 ? 'y' : 'ies'} refreshed.`
        : ' Dictionary synced.'
    } catch {
      synced = ' (The Dictionary will sync itself when you open it.)'
    }
    setMsg(`✓ Keystone set: ${list.length} categories confirmed.${named}${synced} Export pack freezes the mapping for future scans.`)
  }
  // SILENT auto-heal. Same-source duplication is DAMAGE, never intent — no
  // steward action can create two rows carrying the same source column; only
  // the old label-keyed merge could (fixed in rowmerge.js). Damage the
  // steward never caused is repaired behind the scenes and never exposed as
  // a decision: no button, no toast — the grid is simply correct ("this
  // should happen behind the scenes"). Deferred while proposals or agents
  // are in flight, because folding re-indexes rows and pills key by row
  // index; the deps re-fire the heal the moment the grid goes quiet.
  useEffect(() => {
    if (dupSources > 0 && !proposals && !agent && !catBusy) {
      const { rows: out, folded } = selfFold(rowsRef.current)
      if (folded) setRows(out)
    }
  }, [dupSources, proposals, agent, catBusy]) // eslint-disable-line react-hooks/exhaustive-deps
  const prunedKeys = useMemo(() => rows.reduce((n, r) => n + (r?.Prune_Reason && !truthy(r.Keep) ? 1 : 0), 0), [rows])
  const keptShown = useMemo(() => vis.reduce((n, i) => n + (truthy(rows[i]?.Keep) ? 1 : 0), 0), [vis, rows])
  const anySuggestedNames = useMemo(() => rows.some((r) => r.Suggested_Name && r.Suggested_Name !== r.Term), [rows])
  const propCount = useMemo(
    () => (proposals ? Object.values(proposals.items).reduce((a, it) => a + (it.display ? it.display.length : 0), 0) : 0),
    [proposals])

  useEffect(() => {
    if (masterRef.current) masterRef.current.indeterminate = keptShown > 0 && keptShown < vis.length
  }, [keptShown, vis.length])

  /* ---------- keep / prune ---------- */

  // Any change that reorders/merges rows also drops still-pending AI pills:
  // proposals are keyed by row index, so after a merge they'd attach to the
  // WRONG rows. Decide pills first (the guide's order); re-running an agent
  // regenerates them cheaply if a structural change discarded some.
  const structuralReset = () => { setHmSnap(null); setExpanded(null); lastPosRef.current = null; setProposals(null) }

  const onKeep = useCallback((e, index, pos) => {
    const on = e.target.checked
    if (e.nativeEvent.shiftKey && lastPosRef.current != null) {
      const v = visRef.current
      const a = Math.min(lastPosRef.current, pos)
      const b = Math.max(lastPosRef.current, pos)
      const idxs = new Set()
      for (let p = a; p <= b; p++) idxs.add(v[p])
      setRows(rowsRef.current.map((r, i) =>
        idxs.has(i) && !(!on && isTableTerm(r)) ? { ...r, Keep: on ? 'Y' : 'N' } : r))
    } else {
      const r = rowsRef.current[index]
      if (r && !(!on && isTableTerm(r))) patchRow(index, { Keep: on ? 'Y' : 'N' })
    }
    lastPosRef.current = pos
  }, [])

  function masterToggle(e) {
    const on = e.target.checked
    const idxs = new Set(visRef.current)
    setRows(rowsRef.current.map((r, i) =>
      idxs.has(i) && !(!on && isTableTerm(r)) ? { ...r, Keep: on ? 'Y' : 'N' } : r))
    structuralReset()
  }

  // Keep High+Med conf: a reversible toggle — snapshots the shown rows it
  // flips so clicking again restores them exactly. Table terms are exempt.
  function toggleHM() {
    if (hmSnap) {
      const m = new Map(hmSnap.map((s) => [s.index, s.keep]))
      setRows(rowsRef.current.map((r, i) => (m.has(i) ? { ...r, Keep: m.get(i) } : r)))
      setHmSnap(null)
      return
    }
    const snap = []
    const idxs = new Set(shown)
    setRows(rowsRef.current.map((r, i) => {
      if (!idxs.has(i)) return r
      snap.push({ index: i, keep: r.Keep })
      if (isTableTerm(r)) return r
      // an auto-pruned structural key is High confidence ("Key column") but was
      // deliberately un-kept by the scan — don't silently resurrect it here
      if (r.Prune_Reason && !truthy(r.Keep)) return r
      return { ...r, Keep: r.Confidence === 'High' || r.Confidence === 'Medium' ? 'Y' : 'N' }
    }))
    setHmSnap(snap)
  }

  /* ---------- inline edits ---------- */

  const onField = useCallback((index, field, value) => { patchRow(index, { [field]: value }) }, [])

  const toggleExpand = useCallback((index) => { setExpanded((e) => (e === index ? null : index)) }, [])

  // Rename every row of one category in a single decision. This is what makes
  // the packless fallback workable: a fresh scan groups rows under PHYSICAL
  // names (Monthly Usage, Gis), and the steward's job is to rename each group
  // to the business word once - not to assign categories row by row. Stewards
  // must never be left guessing from a wall of Uncategorized.
  const renameCategory = useCallback((from) => {
    const cur = String(from || '').trim()
    if (!cur) return
    const to = window.prompt(`Rename category "${cur}" on every row - to:`, cur)
    if (to == null) return
    const name = to.trim()
    if (!name || name === cur) return
    let n = 0
    setRows(rowsRef.current.map((x) => {
      if (String(x.Category || '').trim() !== cur) return x
      n++
      return { ...x, Category: name }
    }))
    setFilters((f) => (f.cat === cur ? { ...f, cat: name } : f))
    // Stewardship travels with the rename. Per-category overrides are keyed
    // by NAME in the workspace governance and baked into the JSONL at
    // generate time — leaving the old key behind silently dropped the
    // steward's decision the moment the taxonomy settled. On collision the
    // destination's filled slots win (both are steward decisions; the name
    // being kept is the deliberate one) and its blanks inherit.
    const g = ws.governance
    const moved = g && g.categories && g.categories[cur]
    if (moved) {
      const gcats = { ...g.categories }
      delete gcats[cur]
      gcats[name] = gcats[name] ? { ...moved, ...gcats[name] } : moved
      setGovernance({ ...g, categories: gcats })
    }
    setMsg(`Renamed "${cur}" to "${name}" on ${n} row(s).`
      + (moved ? ' Its stewardship override moved with it.' : ''))
  }, [setFilters])

  const useName = useCallback((index) => {
    const r = rowsRef.current[index]
    if (!r || !r.Suggested_Name) return
    const sgg = r.Suggested_Name
    const old = r.Term || ''
    let n = 0
    setRows(rowsRef.current.map((x) => {
      if ((x.Term || '') !== old) return x
      n++
      const nx = { ...x, Term: sgg, LLM_Name: 'Used' }
      delete nx.Suggested_Name
      return nx
    }))
    setMsg(n > 1
      ? `Renamed all ${n} instances of “${old}” → “${sgg}” — kept as one mergeable term.`
      : `Renamed to “${sgg}”.`)
  }, [])

  function useAllNames() {
    let n = 0
    setRows(rowsRef.current.map((r) => {
      if (!(r.Suggested_Name && r.Suggested_Name !== r.Term)) return r
      n++
      const nx = { ...r, Term: r.Suggested_Name, LLM_Name: 'Used' }
      delete nx.Suggested_Name
      return nx
    }))
    if (n) setMsg(`Applied ${n} suggested name${n !== 1 ? 's' : ''}.`)
  }

  /* ---------- duplicate groups: per-group + bulk resolution ---------- */

  const locked = !!agent || !!proposals

  function onGroupSet(name, action) {
    if (locked) return
    const cur = grp[name]
    const next = cur && cur.action === action ? 'separate' : action // click the active choice to revert
    const res = applyGroupAction(rowsRef.current, grp, name, next)
    setRows(res.rows)
    setGrp(res.grp)
    setBulk({ merge: false, disambig: false })
    structuralReset()
  }

  function bulkResolve(action, flag, appliedMsg, revertMsg, noneMsg) {
    if (locked) return
    let r = rowsRef.current
    let g = grp
    if (bulk[flag]) {
      Object.keys(g).forEach((n) => {
        if (g[n].action && g[n].action !== 'separate') {
          const res = applyGroupAction(r, g, n, 'separate')
          r = res.rows; g = res.grp
        }
      })
      setRows(r); setGrp(g); setBulk({ merge: false, disambig: false })
      setMsg(revertMsg)
    } else {
      const names = allDupGroups(r, g)
      if (!names.length) { setMsg(noneMsg); return }
      names.forEach((n) => { const res = applyGroupAction(r, g, n, action); r = res.rows; g = res.grp })
      setRows(r); setGrp(g)
      setBulk({ merge: action === 'merge', disambig: action === 'split' })
      setMsg(`${appliedMsg} ${names.length} duplicate group${names.length !== 1 ? 's' : ''}.`)
    }
    structuralReset()
  }

  function resetAll() {
    if (!snapRef.current || locked) return
    setRows(deep(snapRef.current))
    setGrp({}); setBulk({ merge: false, disambig: false }); setReco({}); setSim(null)
    setFilters(EMPTY_FILTERS)
    structuralReset()
    setMsg('Reset to the raw scan.')
  }

  /* ---------- duplicate advisor: evidence -> live probe -> AI ---------- */

  const dupFp = useMemo(() => {
    const c = {}
    rows.forEach((r) => {
      if (!r || !truthy(r.Keep)) return
      const t = String(r.Term || '').trim()
      if (t) c[t] = (c[t] || 0) + 1
    })
    return Object.keys(c).filter((t) => c[t] > 1).sort().map((t) => `${t}:${c[t]}`).join('|')
  }, [rows])

  // Background pass: cached scan evidence only (no DB, no LLM), debounced.
  useEffect(() => {
    if (!dupFp) { setReco({}); return undefined }
    let stale = false
    const t = setTimeout(() => {
      apiPost('/api/recommend-resolutions', { rows: rowsRef.current, ai: false })
        .then((d) => {
          if (stale) return
          const m = {}
          ;(d.groups || []).forEach((g) => { m[g.name] = g })
          setReco(m)
        })
        .catch(() => {})
    }, 600)
    return () => { stale = true; clearTimeout(t) }
  }, [dupFp])

  // Groups the deterministic pass could not settle — the ones wearing the `check`
  // badge. Both escalation rungs on the server key off exactly this (band !==
  // 'high'), so it is also the true scope of the AI advise button: everything
  // else was already decided from profiled evidence and is never re-judged.
  const checkGroups = Object.values(reco).filter((r) => r && r.band !== 'high').length

  // Full pass (the AI advise button): + live data-value probe + AI adjudication,
  // both scoped server-side to the `check` groups above.
  async function aiAdvise() {
    if (!checkGroups) {
      setMsg('Nothing to escalate — every duplicate group was settled from profiled evidence.')
      return
    }
    setAdvising(true)
    setError(null)
    try {
      let conn = null
      try {
        const c = await apiGet('/api/connections')
        conn = ((c.connections || []).find((x) => x.type === 'db') || {}).config || null
      } catch { /* probe is optional — evidence + AI still apply */ }
      const d = await apiPost('/api/recommend-resolutions', { rows: rowsRef.current, conn, ai: true })
      const m = {}
      ;(d.groups || []).forEach((g) => { m[g.name] = g })
      setReco(m)
      // `used_llm: false` means the model was not NEEDED as often as it means the
      // model was not AVAILABLE — say which, rather than blaming a healthy Ollama
      // for a run the data already settled.
      const probedTxt = d.probed ? `Live-probed ${d.probed} group${d.probed !== 1 ? 's' : ''}` : 'No group needed a live probe'
      setMsg(d.used_llm
        ? `AI adjudicated ${d.ambiguous} still-ambiguous group${d.ambiguous !== 1 ? 's' : ''}${d.probed ? ` (live-probed ${d.probed})` : ''}.`
        : d.ambiguous
          ? `${probedTxt}; ${d.ambiguous} still ambiguous but the model did not answer — evidence decides. Check the LLM on Settings.`
          : `${probedTxt} — the data settled every one, so no model call was needed.`)
    } catch (e) { setError(e.message) }
    setAdvising(false)
  }

  // The scope check. A steward reviewing hundreds of tables in ONE glossary is
  // being asked to govern the ungovernable, and hoping they notice is not a
  // mechanism - the strategy guide's rule is one glossary per accountable
  // domain, and this is the moment the evidence can say the scope is too wide.
  const tableCount = useMemo(() => {
    const t = new Set()
    for (const r of rows) {
      const sc = String(r.Source_Column || '').split(';')[0].trim()
      if (!sc) continue
      if (sc.includes('/')) t.add(sc.replace(/\/+$/, '').split('/').pop())
      else {
        const parts = sc.split('.')
        t.add(parts.length >= 2 ? parts[parts.length - 2] : parts[0])
      }
    }
    return t.size
  }, [rows])

  /* ---------- AI categories: an abstract grouping from the schema ---------- */
  // The model is shown what the scan PROVED - tables, columns, FK links - and
  // asked for a holistic business grouping: the fewest abstract categories that
  // still discriminate, every table placed in one. Proposals only: the steward
  // confirms, the Rename button adjusts, Export pack freezes the outcome.
  // Tables the model leaves out keep their physical group, visibly.
  async function aiCategories() {
    setCatBusy(true)
    setMsg('Proposing business categories from the schema\u2026')
    try {
      const d = await apiPost('/api/ai-categories', { rows })
      const cats = (d.categories || []).filter((c) => !c.unassigned)
      const un = (d.categories || []).find((c) => c.unassigned)
      if (!d.used_llm || !cats.length) {
        setMsg(d.timed_out
          ? 'The model TIMED OUT on the schema-wide call \u2014 larger models need a longer LLM timeout (Settings) and a warm first load. Nothing was proposed; not a quality verdict.'
          : d.used_llm
            ? 'The model proposed nothing usable \u2014 set a few categories by hand and re-run.'
            : 'No model available (or fewer than two tables) \u2014 nothing proposed.')
        return
      }
      // Land as PILLS through the shared proposal machinery, not a bulk
      // apply: acceptance IS the steward's approval, per pill or Accept all,
      // exactly like every other thing the model proposes. Nothing changes
      // a row until it is accepted.
      const a = d.assignments || []
      const items = {}
      let n = 0
      rowsRef.current.forEach((r, i) => {
        const cur = String(r.Category || '')
        if (!a[i] || cur === a[i]) return
        n++
        items[i] = { patch: { Category: a[i] },
                     display: [{ field: 'Category', from: cur, to: a[i] }] }
      })
      if (!n) { setCatRan(true); setMsg('Every row already carries its proposed category.'); return }
      setProposals((prev) => {
        const label = 'AI categories (schema)'
        // A fresh categorize run REPLACES the previous one's Category pills
        // everywhere — merging them interleaves two taxonomies (field: rerun
        // after a disappointing proposal left stale pills on rows the new
        // run did not re-pill, and the union sprawled). Other agents' field
        // pills are untouched.
        const merged = {}
        for (const [i, c] of Object.entries(prev ? prev.items : {})) {
          const display = c.display.filter((x) => x.field !== 'Category')
          if (!display.length) continue
          const patch = { ...c.patch }
          delete patch.Category
          merged[i] = { ...c, patch, display }
        }
        for (const [i, it] of Object.entries(items)) {
          const c = merged[i]
          merged[i] = c ? { ...c, patch: { ...c.patch, ...it.patch },
                            display: [...c.display.filter((x) => x.field !== 'Category'), ...it.display] }
                        : it
        }
        const mixed = !!(prev && prev.label !== label)
        return { label: mixed ? 'AI agents' : label,
                 desc: mixed ? 'proposals from several agents \u2014 accept per pill, or all at once'
                             : (AGENT_META[label] || {}).desc || '',
                 gate: !!(prev && prev.gate), items: merged }
      })
      setCatRan(true)
      // The delta is the trap-catcher (field: 11 groups quietly became 15):
      // categorization exists to CONSOLIDATE, so show what accepting every
      // pill would do to the kept grid's distinct-category count \u2014 and say
      // so plainly when the number would not shrink. Same accounting as the
      // keystone (kept rows only), so the numbers agree with the Approve
      // button.
      const keptCats = (pick) => new Set(rowsRef.current
        .map((r, i) => (truthy(r.Keep) ? String(pick(r, i) || '').trim() : ''))
        .filter(Boolean)).size
      const before = keptCats((r) => r.Category)
      const after = keptCats((r, i) => a[i] || r.Category)
      // one-table categories are renames wearing a category name \u2014 count
      // them separately so the steward sees WHY the number failed to shrink
      const singles = cats.filter((c) => (c.tables || []).length === 1).length
      setMsg(`${cats.length} categories proposed on ${n} row(s) \u2014 accepting every pill would take the grid from ${before} to ${after} categories` +
             (after >= before
               ? ' \u00b7 NOT a consolidation \u2014 reject or edit near-duplicate pills before approving'
               : '') +
             (singles > 0 ? ` \u00b7 ${singles} propose a single table \u2014 renames, not groupings` : '') +
             (un ? ` \u00b7 ${un.tables.length} table(s) kept their physical group` : '') + '.')
    } catch (e) {
      setMsg(`AI categories failed: ${e.message}`)
    } finally {
      setCatBusy(false)
    }
  }

  /* ---------- Find similar (same concept, different names) ---------- */

  async function findSimilar(thr = simThresh) {
    setSim((s) => ({ busy: true, list: (s && s.list) || [] }))
    try {
      const d = await apiPost('/api/similarity', { rows: rowsRef.current, threshold: thr })
      setSim({ busy: false, list: d.suggestions || [] })
    } catch (e) { setSim({ busy: false, list: [], error: e.message }) }
  }

  useEffect(() => {
    if (!sim) return undefined
    const t = setTimeout(() => { findSimilar(simThresh) }, 400)
    return () => clearTimeout(t)
  }, [simThresh]) // eslint-disable-line react-hooks/exhaustive-deps

  function simMerge(idx) {
    const s = sim.list[idx]
    if (!s) return
    let n = 0
    setRows(rowsRef.current.map((r) => {
      if ((r.Term || '') !== s.drop) return r
      n++
      const nx = { ...r, Term: s.keep }
      if (nx.Suggested_Name === s.keep) delete nx.Suggested_Name
      return nx
    }))
    setSim({ busy: false, list: sim.list.filter((x) => x.keep !== s.drop && x.drop !== s.drop) })
    setMsg(`Merged “${s.drop}” into “${s.keep}” (${n} row${n !== 1 ? 's' : ''}). Use the duplicate header (or Merge duplicates) to collapse into one row.`)
  }

  function simFlip(idx) {
    setSim({ busy: false, list: sim.list.map((s, i) => i === idx
      ? { ...s, keep: s.drop, keep_count: s.drop_count, drop: s.keep, drop_count: s.keep_count }
      : s) })
  }

  function simDismiss(idx) { setSim({ busy: false, list: sim.list.filter((_, i) => i !== idx) }) }

  /* ---------- the AI agents: run chunked, diff, propose ---------- */

  // The agents run on KEPT rows only — you prune first, then spend LLM time on
  // what survives. `targets` holds the absolute workspace-row indices of every
  // kept row (table terms are always kept, so they ride along via their own
  // Keep state). Each chunk sends targets.slice(...) rows and re-joins the
  // backend's positional echo through that same slice — d.rows[j] belongs to
  // working[idx[j]] — so dropped rows can never shift the mapping.
  // Run an agent over the kept rows in chunks. With a `propose` config, each
  // returned batch is diffed against the base rows RIGHT AWAY and merged into
  // the inline proposal state — so the click-to-accept pills light up in the
  // grid batch by batch while the run is still going. The grid itself never
  // mutates: pills/Accept-all are the only way a proposal lands.
  async function runChunks(label, call, { offlineBreak = true, chunk = CHUNK, propose = null,
                                          only = null } = {}) {
    const baseRows = rowsRef.current
    const targets = []
    if (only) {
      // a per-row action names its row outright: the steward clicked THAT row,
      // so it runs whether or not Keep is ticked (the kept-rows rule exists to
      // stop a sweep spending model time on pruned noise, not to veto a click)
      only.forEach((i) => { if (baseRows[i]) targets.push(i) })
    } else {
      baseRows.forEach((r, i) => { if (r && truthy(r.Keep)) targets.push(i) })
    }
    const total = targets.length
    if (!total) {
      setMsg(only ? 'That row is no longer in the grid.'
                  : 'No kept rows — the AI pass only processes rows with Keep ticked.')
      return null
    }
    const working = baseRows.map((r) => ({ ...r }))
    cancelRef.current = false
    const startedAt = Date.now()
    const batches = Math.ceil(total / chunk)
    setAgent({ label, done: 0, total, proposed: 0, batch: 0, batches, startedAt, names: [] })
    // NOTE: pending proposals from a previous agent are KEPT — new proposals
    // merge in per row/field below, so running the next agent never forces an
    // Accept all / Dismiss all decision on the last one's pills
    setError(null)
    const diffOne = (r, w) => {                    // default builder from watch/carry
      const patch = {}
      const display = []
      ;(propose.watch || []).forEach((f) => {
        const a = r[f] == null ? '' : String(r[f])
        const b = w[f] == null ? '' : String(w[f])
        if (a !== b) { patch[f] = w[f] ?? ''; display.push({ field: f, from: a, to: b }) }
      })
      ;(propose.carry || []).forEach((f) => {
        const a = r[f] == null ? '' : String(r[f])
        const b = w[f] == null ? '' : String(w[f])
        if (a !== b) patch[f] = w[f] ?? ''
      })
      return display.length ? { patch, display } : null
    }
    const mkItem = propose ? (propose.build || diffOne) : null
    const propLabel = (propose && propose.label) || label
    let offline = false
    let failed = 0
    let proposed = 0
    let timedOut = 0
    for (let s = 0; s < total && !cancelRef.current; s += chunk) {
      const idx = targets.slice(s, s + chunk)
      // announce the batch BEFORE the call — a model batch can take 30s+, and a
      // bar that only moves on completion reads as "stuck"
      setAgent((a) => (a ? { ...a, batch: Math.floor(s / chunk) + 1,
                             names: idx.map((i) => (baseRows[i] || {}).Term).filter(Boolean) } : a))
      let add = null
      try {
        const d = await call(idx.map((i) => working[i]))
        timedOut += (d.updated && d.updated.timed_out) || 0
        if (d.llm && d.llm.online === false) {
          offline = true
          if (offlineBreak) break
        }
        ;(d.rows || []).forEach((nr, j) => {
          const i = idx[j]
          if (i == null || !nr || typeof nr !== 'object') return
          working[i] = { ...working[i], ...nr }
        })
        if (mkItem) {
          add = {}
          idx.forEach((i) => {
            const it = mkItem(baseRows[i] || {}, working[i] || {})
            if (it) add[i] = it
          })
          if (!Object.keys(add).length) add = null
        }
      } catch { failed += idx.length }
      if (add) {
        proposed += Object.keys(add).length
        setProposals((p) => {
          // merge per row: a field proposed again is replaced by the newer
          // agent's take; other fields' pending pills survive untouched
          const items = { ...(p ? p.items : {}) }
          for (const [i, it] of Object.entries(add)) {
            const cur = items[i]
            if (!cur) { items[i] = it; continue }
            items[i] = {
              ...cur, ...it,
              patch: { ...cur.patch, ...it.patch },
              display: [...cur.display.filter((d) => !it.display.some((n) => n.field === d.field)), ...it.display],
            }
          }
          const mixed = !!(p && p.label !== propLabel)
          return {
            label: mixed ? 'AI agents' : propLabel,
            desc: mixed ? 'proposals from several agents — accept per pill, or all at once'
                        : (AGENT_META[propLabel] || {}).desc || '',
            gate: !!(AGENT_META[propLabel] || {}).gate || !!(p && p.gate),
            items,
          }
        })
      }
      setAgent((a) => (a ? { ...a, done: Math.min(s + chunk, total), proposed } : a))
    }
    setAgent(null)
    return { baseRows, working, targets, offline, failed, proposed, timedOut,
             stopped: cancelRef.current }
  }

  /* ---------- inline proposal pills: accept / dismiss ---------- */

  // Accept ONE field of one row's proposal (field == null accepts the row's
  // whole patch). Suggested_Name behaves like the classic → chip: it renames
  // every row that shares the old name in one go. Stable callback (refs) so
  // the memoized grid rows don't all re-render.
  const acceptProp = useCallback((index, field) => {
    const p = proposalsRef.current
    const it = p && p.items[index]
    if (!it || !it.patch) return
    if (field === 'Suggested_Name') {
      const v = it.patch.Suggested_Name
      const old = rowsRef.current[index]?.Term || ''
      let n = 0
      setRows(rowsRef.current.map((x) => {
        if ((x.Term || '') !== old) return x
        n++
        const nx = { ...x, Term: v, LLM_Name: 'Used' }
        delete nx.Suggested_Name
        return nx
      }))
      setMsg(n > 1 ? `Renamed all ${n} instances of “${old}” → “${v}”.` : `Renamed to “${v}”.`)
    } else {
      const patch = {}
      if (field) {
        patch[field] = it.patch[field]
        ;(CARRY_FOR[field] || []).forEach((c) => { if (c in it.patch) patch[c] = it.patch[c] })
      } else {
        Object.assign(patch, it.patch)
        // never land the row-level legacy flag: untouched fields' chips would
        // glow via the fallback — the patch's per-field flags are the record
        delete patch.LLM_Enriched
      }
      patchRow(index, patch)
    }
    setProposals((prev) => {
      if (!prev || !prev.items[index]) return prev
      const cur = prev.items[index]
      const display = field ? cur.display.filter((d) => d.field !== field) : []
      if (!display.length) {
        const items = { ...prev.items }
        delete items[index]
        return Object.keys(items).length ? { ...prev, items } : null
      }
      const patch = { ...cur.patch }
      delete patch[field]
      return { ...prev, items: { ...prev.items, [index]: { ...cur, display, patch } } }
    })
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  function acceptAllProps() {
    const p = proposals
    if (!p) return
    const items = p.items
    let rowsHit = 0
    setRows(rowsRef.current.map((r, i) => {
      const it = items[i]
      if (!it || !it.patch) return r
      rowsHit++
      return { ...r, ...it.patch }
    }))
    setProposals(null)
    structuralReset()
    setMsg(`Applied every proposal from ${p.label} (${rowsHit} row${rowsHit !== 1 ? 's' : ''}). Proposed names land as → chips — click them (or Apply all suggested names) to rename.`)
  }

  function dismissProps() {
    setProposals(null)
    setMsg('Proposals dismissed — nothing changed.')
  }

  // Per-run summary once the chunks finish (the pills carry the substance).
  function runDone(run, label, none) {
    const note = [
      run.stopped ? 'stopped early — batches already returned kept their pills' : '',
      run.failed ? `${run.failed} row(s) failed` : '',
    ].filter(Boolean).join(' · ')
    const timedOut = run.timedOut || 0
    if (timedOut && !run.proposed)
      setMsg(`${label}: the model did not answer within its time budget on ${timedOut} row(s) — `
        + 'raise the LLM timeout on Settings, or pick a smaller model. Nothing was proposed.')
    else if (!run.proposed) setMsg(`${label}: ${none}${note ? ` (${note})` : ''}.`)
    else setMsg(`${label}: proposals on ${run.proposed} of ${run.targets.length} kept rows — click the pills to accept, or Accept all above the grid.${note ? ` (${note})` : ''}`)
  }

  // The default agent: one call per row covering every LLM-decidable field.
  async function runAiPass() {
    const run = await runChunks('AI pass — definitions, purposes, names, categories, tags',
      // no model/compute here: ReviewPage has no settings prop (that was a
      // copy from the Dictionary page and threw ReferenceError before the
      // fetch, failing every row) — the server uses its configured model
      (rs) => apiPost('/api/ai-pass', { rows: rs }), {
        propose: {
          label: 'AI pass (all fields)',
          watch: ['Definition', 'Purpose', 'Suggested_Name', 'Suggested_Tags', 'Category', 'PII_Category'],
          carry: ['LLM_Definition', 'LLM_Purpose', 'LLM_Enriched', 'LLM_Name', 'AI_Suggested',
                  'Suggested_Reason', 'QA_Issues'],
        },
      })
    if (!run) return
    if (run.offline) { setMsg('LLM offline — start Ollama and pull a model on the Settings page, then try again.'); return }
    runDone(run, 'AI pass (all fields)', 'no changes proposed')
  }

  // The same pass, scoped to ONE row — this replaced the Enrich and AI suggest
  // buttons. Both survived only to re-run a field on a row you didn't like, and
  // both were subsets of this endpoint's prompt, so they were two more places to
  // restate the guardrails and two more chances for them to drift. Same call,
  // same evidence, same guards; only the target set is different.
  async function runAiPassRow(index) {
    const term = (rowsRef.current[index] || {}).Term || 'this row'
    const run = await runChunks(`AI review — ${term}`,
      (rs) => apiPost('/api/ai-pass', { rows: rs }), {
        only: [index],
        propose: {
          label: 'AI review (this row)',
          watch: ['Definition', 'Purpose', 'Suggested_Name', 'Suggested_Tags', 'Category', 'PII_Category'],
          carry: ['LLM_Definition', 'LLM_Purpose', 'LLM_Enriched', 'LLM_Name', 'AI_Suggested',
                  'Suggested_Reason', 'QA_Issues'],
        },
      })
    if (!run) return
    if (run.offline) { setMsg('LLM offline — start Ollama and pull a model on the Settings page, then try again.'); return }
    setMsg(run.proposed
      ? `AI review: proposals on “${term}” — click the pills to accept.`
      : `AI review: the model had nothing to improve on “${term}”.`)
  }




  /* ---------- open / enhance / save ---------- */

  async function onLoadFile(e) {
    const f = e.target.files && e.target.files[0]
    e.target.value = ''
    if (!f) return
    setBusy('load')
    setError(null)
    try {
      const text = await f.text()
      const d = await apiPost('/api/load-glossary', { glossary: text })
      setRows(d.rows || [])
      snapRef.current = deep(d.rows || []); setUi('review.snap', snapRef.current)
      setGrp({}); setBulk({ merge: false, disambig: false }); setReco({}); setSim(null)
      setFilters(EMPTY_FILTERS)
      structuralReset()
      const rp = d.report || {}
      setMsg(`Loaded ${rp.terms || (d.rows || []).length} terms from ${rp.glossary || f.name} for review.`)
    } catch (err) { setError(err.message) }
    setBusy(null)
  }

  async function onEnhanceFile(e) {
    const f = e.target.files && e.target.files[0]
    e.target.value = ''
    if (!f || !rowsRef.current.length) return
    setBusy('enhance')
    setError(null)
    try {
      const text = await f.text()
      const d = await apiPost('/api/enhance-glossary', { rows: rowsRef.current, glossary: text, append_missing: true })
      setRows(d.rows || [])
      snapRef.current = deep(d.rows || []); setUi('review.snap', snapRef.current)
      setGrp({}); setBulk({ merge: false, disambig: false })
      structuralReset()
      const rp = d.report || {}
      setMsg(`Enhanced from ${rp.glossary || f.name}: ${rp.matched || 0} matched, ${rp.added || 0} added.`)
    } catch (err) { setError(err.message) }
    setBusy(null)
  }

  async function nameAndSave() {
    const n = saveName.trim()
    if (!n) return
    setBusy('save')
    setGlossaryMeta({ name: n })
    await save()
    setBusy(null)
    setSaveName('')
  }

  /* ---------- render ---------- */

  const noRows = rows.length === 0
  // pending proposals do NOT disable the agents: new runs merge their
  // proposals into the pending pills (see runChunks) instead of wiping them,
  // so nobody is forced through Accept all / Dismiss all to keep working
  const aiDisabled = noRows || !!agent

  return (
    <>
      <div className="page-head">
        <h1>Review candidate terms</h1>
        <p className="psub">
          Every scanned column is one candidate term — prune rather than hunt for gaps.
          Edit definition, purpose, sensitivity, CDE and tags inline; the AI agents propose, you apply.
        </p>
      </div>

      <ReviewGuide onNavigate={onNavigate} />

      {tableCount > 20 && (
        <div className="notice-warn">
          <b>This glossary spans {tableCount} physical tables.</b> That is usually more
          than one business domain, and a glossary that wide becomes unmanageable — too
          many categories, no single accountable steward. Consider splitting by domain:
          scope each bulk load with <code>includePatterns</code> to one subject area, run
          a glossary per domain with its own steward, and let the cross-glossary check
          keep shared concepts reused rather than re-authored. The pack you export still
          serves every domain of the same company.
        </div>
      )}

      <details className="uth">
        <summary>How terms are defined &amp; built</summary>
        <div className="uth-body">
          <p>
            One candidate term per meaningful column, so the job is <b>pruning</b> rather than
            hunting for what the scan missed. Rows collapse on <b>(category, term)</b> before you
            see them: sixty <code>customer_id</code> columns across sixty tables arrive as one
            term carrying sixty sources, which is why the count you review is far smaller than the
            column count and levels off as an estate grows.
          </p>
          <dl className="uth-dl">
            <dt>Category</dt>
            <dd>
              The pack's table map, else the pack's keywords, else the <b>physical name
              itself</b> — <i>Monthly Usage</i> from <code>monthly_usage</code>, a document's
              top folder. Evidence, not invention: your job is to <b>rename each group
              once</b> (filter to a category and use <i>Rename</i>), never to assign
              categories row by row. Export pack records the mapping, so the next scan
              arrives categorised.
            </dd>
            <dt>Name</dt>
            <dd>
              From the column name, expanded through the domain pack's abbreviations —{' '}
              <code>mbr_no</code> becomes <b>Member Number</b> once the pack knows{' '}
              <code>mbr</code>.
            </dd>
            <dt>Definition</dt>
            <dd>
              A database comment where one exists — the best source, because a human wrote it about
              that column. Otherwise templated from the name, and flagged low confidence so you can
              see which is which.
            </dd>
            <dt>Confidence</dt>
            <dd>
              A <i>review signal</i>, not a score of correctness. <b>High</b> means a comment or a
              key backed it; <b>Low</b> means it was templated from the name alone. Sort by it to
              spend your attention where the evidence is thinnest.
            </dd>
            <dt>Sensitivity &amp; PII</dt>
            <dd>
              Computed from the profile — value patterns, signatures, reference lists — never
              proposed by a model. Two runs over the same data must agree, or the classification
              cannot be defended in an audit.
            </dd>
            <dt>Tags</dt>
            <dd>
              Drawn from the governed allow-list on the Dictionary page, never free text. This is
              what stops <code>PII</code>, <code>pii</code> and <code>PII-Data</code> becoming
              three labels for one idea.
            </dd>
            <dt>CDE</dt>
            <dd>
              Inferred from keys, sensitivity and compliance terms — and always the steward's to
              confirm.
            </dd>
            <dt>Detection — Auto vs Mapping-only</dt>
            <dd>
              Every term answers one question for the Policy Generator: <b>can this term be
              recognised in data by the look of its values?</b> <b>Auto</b> (the default) answers
              from evidence — a profiled value shape (pattern, signature, reference values) seeds
              a detection method in the exported Registry; no shape leaves the question <i>open</i>,
              and Policy will ask the steward for a seed. <b>Mapping-only</b> closes the question
              deliberately: this term is governed purely by the term→column links Apply makes —
              there is no value shape to recognise (conceptual and table-level terms, surrogate
              keys, free text) — so Policy stops expecting a detection method at all. Mapping-only
              always wins, even over existing seeds. Set it in a row&apos;s expanded editor
              (DETECTION toggle); the choice travels in the exported Registry, nowhere else.
            </dd>
          </dl>
        </div>
      </details>

      <details className="uth">
        <summary>Under the hood — this page's calls</summary>
        <div className="uth-body">
          <ol className="uth-steps">
            <li>
              <code>POST /api/ai-pass</code> — one model call per batch of kept rows, covering
              definition, purpose, name and governed tags. It proposes; nothing changes until you
              apply. <b>Deliberately not asked</b> about sensitivity, PII or category — those are
              deterministic from the scan, and a model that varies per run would make them
              unauditable.
            </li>
            <li>
              <code>POST /api/similarity</code> and{' '}
              <code>/api/recommend-resolutions</code> — group rows sharing a term name and
              recommend <b>Merge</b>, <b>Disambiguate</b> or <b>Keep separate</b>. The rubric is
              evidence first: matching value patterns and value sets beat matching names, because
              two columns called <code>status</code> are usually not the same concept.
            </li>
            <li>
              <code>POST /api/pdc/terms/existing</code> — asks PDC which candidates it already
              holds, and in which glossary, so you reuse rather than re-author.
            </li>
            <li>
              <code>POST /api/enhance-glossary</code> and{' '}
              <code>/api/load-glossary</code> — open a previous export for review, or enrich this
              scan against one, which is how a re-scan updates in place instead of starting over.
            </li>
          </ol>
          <p className="uth-note">
            Only <code>/api/ai-pass</code> leaves this machine, and only when a hosted provider is
            configured — with Ollama it stays local too. Everything else is computed here.
          </p>
        </div>
      </details>

      <section className="card">
        <header>
          <h2>Review grid <span>prune candidate terms</span></h2>
          {rows.length > 0 && (ws.name || ws.id
            ? (
              <span className="badge neutral rv-saved">
                {ws.name || 'Saved glossary'}
                {' · '}
                {ws.saving ? 'saving…' : ws.dirty ? 'unsaved changes (autosave pending)' : ws.savedAt ? `saved ${ws.savedAt}` : 'autosave on'}
              </span>
            )
            : (
              <span className="rv-actionbar">
                <input className="rv-savename" type="text" placeholder="Name this glossary to autosave…" value={saveName}
                       onChange={(e) => setSaveName(e.target.value)}
                       onKeyDown={(e) => e.key === 'Enter' && nameAndSave()} />
                <button className="primary sm" disabled={!saveName.trim() || busy === 'save'} onClick={nameAndSave}>
                  {busy === 'save' ? 'Saving…' : 'Save glossary'}
                </button>
              </span>
            ))}
        </header>

        <div className="rv-actionbar">
          <input ref={loadFileRef} type="file" accept=".json,.jsonl,.csv" style={{ display: 'none' }} onChange={onLoadFile} />
          <input ref={enhanceFileRef} type="file" accept=".json,.jsonl,.csv" style={{ display: 'none' }} onChange={onEnhanceFile} />
          <button className="ghost sm" disabled={busy === 'load'} onClick={() => loadFileRef.current?.click()}
                  title="Open an existing PDC glossary export directly in the grid to review and edit (round-trip).">
            {busy === 'load' ? 'Loading…' : 'Open glossary for review…'}
          </button>
          <button className="ghost sm" disabled={noRows || busy === 'enhance'} onClick={() => enhanceFileRef.current?.click()}
                  title="Overlay an existing glossary's real definitions, purpose, tags and sensitivity onto matched scanned terms.">
            {busy === 'enhance' ? 'Enhancing…' : 'Enhance from glossary…'}
          </button>
          <span className="rv-grow" />
          <span className="rv-agents" role="group" aria-label="AI agents — they run on kept rows only; they propose, you accept per pill"
                title="Each agent processes KEPT rows only — untick Keep to exclude a row. Results land as click-to-accept pills right on the grid, batch by batch while the run goes; nothing touches a row until you accept its pill (or Accept all).">
            <span className="rv-agentslbl">AI AGENTS<small>kept rows · propose → you accept</small></span>
            {/* Ordered as the work is done: categories settle the taxonomy
                first (one schema-wide call), then the AI pass writes language
                inside it - definitions against final groups, no pill fights
                over the Category column. */}
            <button className={`${agentStep === 1 ? 'primary' : 'ghost'} sm`} disabled={catBusy} onClick={aiCategories}
                    title="Run FIRST. One call over the schema the scan proved — tables, columns, FK links — proposing an abstract business grouping. Assignments land as Category pills: accept, rename any group, and only then run the AI pass so definitions are written against the final taxonomy.">
              {catBusy ? 'Proposing…' : '1 · AI categories'}
            </button>
            <button className={`${agentStep === 2 ? 'primary' : 'ghost'} sm${catsConfirmedCurrent ? ' applied' : ''}`}
                    disabled={catBusy || !cats.kept.length} onClick={confirmCategories}
                    title="The KEYSTONE. Declare the category set settled: the Dictionary syncs immediately so its queue reflects this taxonomy, Govern keys stewardship to settled names, and Export pack freezes the mapping for future scans. If you change categories afterwards, this asks to be approved again — the drift is visible, never silent.">
              {/* the count is on the button so the number being approved is
                  read BEFORE the click — field: 11 groups quietly became 15 */}
              {catsConfirmedCurrent
                ? `✓ 2 · Categories approved (${cats.kept.length})`
                : `2 · Approve categories (${cats.kept.length})`}
            </button>
            <button className={`${agentStep === 3 ? 'primary' : 'ghost'} sm`} disabled={aiDisabled} onClick={runAiPass}
                    title="One model call per row for every field the LLM can decide — definition, purpose, a clearer name, governed tags and a blank category. Replaces running Enrich + AI suggest + AI categorize separately (three passes over the same rows, each overwriting the last). Proposals only — accept per pill.">
              3 · AI pass (all fields)
            </button>
            {anySuggestedNames && (
              <button className="ghost sm" disabled={locked} onClick={useAllNames}
                      title="Apply every pending → suggested-name chip at once.">
                Apply all suggested names
              </button>
            )}
          </span>
        </div>

        {catBusy && !agent && (
          <div className="rv-progress">
            <span className="ep">
              AI categories — one call over the whole schema graph
              <span className="rv-thinking" role="status" aria-label="AI categories running"><i /><i /><i /></span>
            </span>
            <span className="ep muted">bigger models take up to a minute — proposals land as Category pills</span>
          </div>
        )}

        {agent && (
          <div className="rv-progress">
            <span className="ep">
              {agent.cancelling ? 'Finishing current batch…' : `${agent.label} — ${agent.done}/${agent.total} (kept rows) · ${Math.round((100 * agent.done) / Math.max(agent.total, 1))}%`}
            </span>
            <div className="progress-track rv-agenttrack" role="progressbar" aria-valuemin={0} aria-valuemax={agent.total} aria-valuenow={agent.done}>
              <div className="progress-bar" style={{ width: `${Math.round((100 * agent.done) / Math.max(agent.total, 1))}%` }} />
              {agent.done < agent.total && (agent.names || []).length > 0 && (
                <div className="rv-agentinflight"
                     style={{ left: `${(agent.done / Math.max(agent.total, 1)) * 100}%`,
                              width: `${(agent.names.length / Math.max(agent.total, 1)) * 100}%` }} />
              )}
            </div>
            <AgentEta agent={agent} />
            {(agent.proposed || 0) > 0 && (
              <span className="rv-livecount"
                    title="Rows already back from finished batches — their pills are live in the grid right now, click one to accept it. Nothing has touched the grid yet.">
                {agent.proposed} row{agent.proposed !== 1 ? 's' : ''} with proposals so far
              </span>
            )}
            <button className="ghost sm" disabled={agent.cancelling}
                    onClick={() => { cancelRef.current = true; setAgent((a) => (a ? { ...a, cancelling: true } : a)) }}>
              Cancel
            </button>
          </div>
        )}

        {proposals && (
          <div className="rv-propstrip">
            <div className="rv-proptext">
              <div className="rv-propline">
                <b>{proposals.label}</b>
                {proposals.gate && <span className="rv-gate">the gate · runs last</span>}
                <span> — {propCount} AI proposal{propCount !== 1 ? 's' : ''} on{' '}
                  {Object.keys(proposals.items).length} row{Object.keys(proposals.items).length !== 1 ? 's' : ''}</span>
              </div>
              {proposals.desc && <div className="rv-propdesc">{proposals.desc}</div>}
              <div className="rv-propdesc muted">
                Click a pill in the grid to accept just that change; the grid’s LLM pills appear only after a proposal is accepted.
              </div>
            </div>
            <span className="rv-grow" />
            <button className="primary sm" disabled={!!agent} onClick={acceptAllProps}>Accept all</button>
            <button className="ghost sm" disabled={!!agent} onClick={dismissProps}>Dismiss all</button>
          </div>
        )}

        {error && <div className="error">{error}</div>}

        {seedReqs.map((sr) => (
          <div key={sr.file} className="rv-seedreq" role="status">
            <span>
              <b>Policy Generator requested detection seeds for {sr.terms.length} term{sr.terms.length !== 1 ? 's' : ''}</b>
              {sr.requested_at ? <span className="muted"> · {sr.requested_at}</span> : null}
              {sr.registry_file ? <span className="muted"> · {sr.registry_file}</span> : null}
            </span>
            <button className={`ghost sm${filters.names ? ' applied' : ''}`} onClick={() => seedFocus(sr)}
                    title="Filter the grid to just the requested terms; click again to show everything.">
              {filters.names ? 'Showing these terms — clear' : 'Show these terms'}
            </button>
            <button className="ghost sm" onClick={() => seedHandled(sr)}
                    title="Rename the request file to .handled.json so it stops showing here — do this after re-scanning or marking terms Mapping-only, then Generate again.">
              Mark handled
            </button>
            <span className="rv-seedhint">
              Re-scan with <b>Profile data</b> on for columns that should have a value shape; mark free-text
              terms <b>Mapping-only</b> (open the row&apos;s editor — Detection toggle), then <b>Generate</b> again.
            </span>
          </div>
        ))}

        {rows.length > 0 && (
          <div className="rv-chips">
            <span className="rv-chip">Terms<b>{stats.terms}</b></span>
            <span className="rv-chip">Categories<b>{stats.categories}</b></span>
            <button className={`rv-chip${filters.pii ? ' on' : ''}`}
                    onClick={() => setFilters((f) => ({ ...f, pii: !f.pii }))}
                    title="Toggle the PII-only filter">
              PII <b className="sens-hi">{stats.pii}</b>
            </button>
            <span className="rv-chip">
              Confidence H<b className="conf-hi">{stats.confidence.High}</b> M<b className="conf-md">{stats.confidence.Medium}</b> L<b className="conf-lo">{stats.confidence.Low}</b>
            </span>
            <span className="rv-chip">
              Sensitivity HIGH<b className="sens-hi">{stats.sensitivity.HIGH}</b> MED<b className="sens-md">{stats.sensitivity.MEDIUM}</b> LOW<b className="sens-lo">{stats.sensitivity.LOW}</b>
            </span>
            {stats.enriched > 0 && <span className="rv-chip">LLM-enriched<b>{stats.enriched}</b></span>}
            {prunedKeys > 0 && (
              <span className="rv-chip"
                    title="Surrogate PK / FK reference-id columns the scan auto-pruned as business terms (best practice — the KEY badge in the grid). Their PK/FK relationships still travel to the Registry's physical model; tick Keep on a row to restore it as a term.">
                Structural keys auto-pruned<b>{prunedKeys}</b>
              </span>
            )}
          </div>
        )}

        {rows.length > 0 && (
          <div className="rv-bar">
            <span className="lbl">FILTER</span>
            <input className="rv-q" type="text" placeholder="Filter term, definition, source…" value={filters.q}
                   onChange={(e) => setFilters((f) => ({ ...f, q: e.target.value }))} />
            <select value={filters.cat} onChange={(e) => setFilters((f) => ({ ...f, cat: e.target.value }))} aria-label="Category filter">
              <option value="">All categories</option>
              {cats.kept.map((c) => <option key={c}>{c}</option>)}
              {cats.droppedOnly.length > 0 && (
                <optgroup label="— only on dropped rows —">
                  {cats.droppedOnly.map((c) => <option key={c}>{c}</option>)}
                </optgroup>
              )}
            </select>
            {filters.cat && (
              <button className="ghost sm" onClick={() => renameCategory(filters.cat)}
                      title="Rename this category on every row that carries it - one decision per group, not one per row.">
                Rename &quot;{filters.cat}&quot;…
              </button>
            )}
            <select value={filters.sev} onChange={(e) => setFilters((f) => ({ ...f, sev: e.target.value }))} aria-label="Sensitivity filter">
              <option value="">All sensitivity</option>
              <option>HIGH</option><option>MEDIUM</option><option>LOW</option>
            </select>
            <select value={filters.conf} onChange={(e) => setFilters((f) => ({ ...f, conf: e.target.value }))} aria-label="Confidence filter">
              <option value="">All confidence</option>
              <option>High</option><option>Medium</option><option>Low</option>
            </select>
            <select value={filters.tag} onChange={(e) => setFilters((f) => ({ ...f, tag: e.target.value }))} aria-label="Tag filter">
              <option value="">All tags</option>
              {tags.kept.map((t) => <option key={t}>{t}</option>)}
              {tags.droppedOnly.length > 0 && (
                <optgroup label="— only on dropped rows —">
                  {tags.droppedOnly.map((t) => <option key={t}>{t}</option>)}
                </optgroup>
              )}
            </select>
            <label className="rv-cbx"><input type="checkbox" checked={filters.pii} onChange={(e) => setFilters((f) => ({ ...f, pii: e.target.checked }))} /> PII only</label>
            <label className="rv-cbx"><input type="checkbox" checked={filters.kept} onChange={(e) => setFilters((f) => ({ ...f, kept: e.target.checked }))} /> Kept only</label>
            <button className="ghost sm" onClick={() => setFilters(EMPTY_FILTERS)}>Clear</button>
          </div>
        )}

        {rows.length > 0 && (
          <div className="rv-bar">
            <span className="rv-keepcount">
              <b>{kept}</b> of <b>{rows.length}</b> kept{vis.length !== rows.length ? ` · ${vis.length} shown` : ''}
            </span>
            <span className="rv-sep" aria-hidden="true" />
            <span className="lbl">PRUNE</span>
            <button className={`ghost sm${hmSnap ? ' applied' : ''}`} onClick={toggleHM}
                    title="Keep only High/Medium-confidence terms; table terms are always kept. Click again to revert.">
              Keep High+Med conf
            </button>
            <span className="rv-sep" aria-hidden="true" />
            <span className="lbl">DUPLICATES</span>
            <button className={`ghost sm${bulk.merge ? ' applied' : ''}`} disabled={locked}
                    onClick={() => bulkResolve('merge', 'merge', 'Merged', 'Reverted merge.', 'No duplicate term names to merge.')}
                    title="Collapse same-named terms into one term linked to all their columns — PDC's one-term-many-data-elements model. Click again to revert.">
              Merge duplicates
            </button>
            <button className={`ghost sm${bulk.disambig ? ' applied' : ''}`} disabled={locked}
                    onClick={() => bulkResolve('split', 'disambig', 'Disambiguated', 'Reverted disambiguation.', 'No duplicate term names to disambiguate.')}
                    title="Make every term name unique by appending its source table, so name-based Resolve can't mis-link. Click again to revert.">
              Auto-disambiguate
            </button>
            <button className="ghost sm" disabled={advising || noRows || !checkGroups} onClick={aiAdvise}
                    title={!checkGroups
                      ? 'Nothing to escalate — every duplicate group was already settled from profiled evidence. This button only ever acts on groups badged “check”.'
                      : `Escalate only the ${checkGroups} group${checkGroups !== 1 ? 's' : ''} badged “check” — the ones with no profiled value sets to compare. Probes LIVE data values over your database connection, then lets the AI agent adjudicate what is left. Groups already decided on evidence are never re-judged. Hints only.`}>
              {advising ? 'Advising…' : `AI advise${checkGroups ? ` (${checkGroups})` : ''}`}
            </button>
            <button className="ghost sm" disabled={noRows} onClick={() => (sim ? setSim(null) : findSimilar())}
                    title="Score the shown terms pairwise and suggest same-concept names to merge (e.g. Phone / Customer Phone / Cust Phone No).">
              Find similar
            </button>
            <span className="rv-grow" />
            <button className="ghost sm" disabled={!snapRef.current || locked} onClick={resetAll}
                    title="Undo all review actions and edits — back to the raw scan.">
              Reset all
            </button>
          </div>
        )}

        {sim && (
          <SimilarityPanel sim={sim} threshold={simThresh} onThreshold={setSimThresh}
                           onMerge={simMerge} onFlip={simFlip} onDismiss={simDismiss}
                           onClose={() => setSim(null)} />
        )}

        <div className="rv-xg">
          <button className="ghost" onClick={() => setXgOpen((v) => !v)}
                  title="Ask PDC which of these terms already exist, and in which glossary. An enterprise runs many small governed glossaries; reuse rises as coverage grows, and this is far cheaper to act on now than at Apply.">
            {xgOpen ? '▾' : '▸'} Check PDC for existing terms
            {xg && xg.hits > 0 && <span className="rv-ttbadge rv-xgbadge">{xg.hits}</span>}
          </button>
          {xgOpen && (
            <div className="rv-xgform">
              <input type="text" placeholder="https://[PDC SERVER]" value={xgConn.base}
                     onChange={(e) => setXgConn({ ...xgConn, base: e.target.value })}
                     aria-label="PDC base URL" />
              <input type="text" placeholder="PDC admin user" value={xgConn.user}
                     onChange={(e) => setXgConn({ ...xgConn, user: e.target.value })}
                     aria-label="PDC username" />
              <input type="password" placeholder="PDC admin password" value={xgConn.pass}
                     onChange={(e) => setXgConn({ ...xgConn, pass: e.target.value })}
                     aria-label="PDC password" />
              <button className="primary" disabled={xgBusy} onClick={checkExisting}>
                {xgBusy ? 'Checking…' : 'Check'}
              </button>
              {xg && (
                <button className="ghost" onClick={() => setXg(null)} title="Clear the badges">
                  Clear
                </button>
              )}
              <span className="muted" style={{ fontSize: '.78rem' }}>
                Credentials are used for this call only and never saved.
              </span>
            </div>
          )}
        </div>

        <div className="rv-tablewrap" ref={tableWrapRef} onFocus={onGridFocusIn} onBlur={onGridFocusOut}>
          <table className="rv-table">
            <colgroup>
              <col style={{ width: 36 }} /><col style={{ width: 140 }} /><col style={{ width: 190 }} />
              <col /><col /><col style={{ width: 96 }} /><col style={{ width: 62 }} />
              <col style={{ width: 150 }} /><col style={{ width: 68 }} /><col style={{ width: 156 }} />
            </colgroup>
            <thead>
              <tr>
                <th className="rv-stick rv-s0">
                  <input ref={masterRef} type="checkbox" checked={vis.length > 0 && keptShown === vis.length}
                         onChange={masterToggle} disabled={!vis.length}
                         title="Keep or clear all shown rows" aria-label="Keep or clear all shown rows" />
                </th>
                <th className="rv-stick rv-s1">Category</th><th className="rv-stick rv-s2">Term</th>
                <th>Definition</th><th>Purpose</th>
                <th>Sensitivity</th><th>CDE</th><th>Tags</th><th>Conf.</th><th>Source</th>
              </tr>
            </thead>
            <tbody>
              {noRows && (
                <tr><td colSpan={10} className="rv-empty">
                  No terms yet — scan a connection, load a saved glossary from Home, or open an export above.
                </td></tr>
              )}
              {!noRows && vis.length === 0 && (
                <tr><td colSpan={10} className="rv-empty">No terms match the filter.</td></tr>
              )}
              {clusters.order.map((k) => {
                const idxs = clusters.by[k]
                const solo = k.startsWith('\u0000solo:')
                const act = (grp[k] && grp[k].action) || 'separate'
                const cluster = !solo && (idxs.length > 1 || act !== 'separate')
                const rec = idxs.length > 1 ? reco[k] : null
                return (
                  <Fragment key={`${k}:${idxs[0]}`}>
                    {cluster && <ClusterHead name={k} count={idxs.length} action={act} rec={rec}
                                             decided={!!grp[k]} locked={locked} onSet={onGroupSet} />}
                    {idxs.map((i) => (
                      <Fragment key={i}>
                        <GridRow row={rows[i]} index={i} pos={posOf.get(i)} expanded={expanded === i}
                                 prop={proposals ? proposals.items[i] : undefined} onAcceptProp={acceptProp}
                                 onField={onField} onKeep={onKeep} onUseName={useName}
                                 existsIn={xg && xg.found
                                   ? xg.found[String(rows[i]?.Term || '').trim()]
                                   : undefined}
                                 onEvidence={setEvidence} onToggle={toggleExpand} />
                        {expanded === i && rows[i] && (
                          <ExpandedRow row={rows[i]} index={i} onField={onField}
                                       prop={proposals ? proposals.items[i] : undefined} onAcceptProp={acceptProp}
                                       onEvidence={setEvidence} onClose={() => setExpanded(null)}
                                       onAiReview={runAiPassRow} aiBusy={aiDisabled} />
                        )}
                      </Fragment>
                    ))}
                  </Fragment>
                )
              })}
            </tbody>
          </table>
        </div>

        <div className="actions">
          <span className="rv-msg">{msg || 'Reviewed and pruned? Approve the pending vocabulary next — it already carries your accepted edits — then set stewardship on Govern.'}</span>
          <span className="rv-grow" />
          <button className="ghost" onClick={() => onNavigate('connect')}>← Connect a source</button>
          <button className="primary" disabled={kept === 0} onClick={completeReview}
                  title={kept ? 'Close the Review stage: the glossary saves, the Dictionary syncs to this exact grid, and the completion is recorded with the workspace — then approve the vocabulary there and set stewardship on Govern.' : 'Keep at least one term first (tick a Keep box, or use Keep High+Med conf)'}>
            ✓ Review complete → Dictionary
          </button>
        </div>
      </section>

      {evidence != null && rows[evidence] && (
        <EvidenceModal row={rows[evidence]} onClose={() => setEvidence(null)} />
      )}
    </>
  )
}

/* Live elapsed / ETA under the agent bar. A batched model run is minutes long,
   so the steward needs to see it moving and know roughly how long is left —
   the rate comes from the batches already finished. */
function AgentEta({ agent }) {
  const [, tick] = useState(0)
  useEffect(() => {
    const t = setInterval(() => tick((n) => n + 1), 1000)
    return () => clearInterval(t)
  }, [])
  const secs = Math.max(0, Math.round((Date.now() - agent.startedAt) / 1000))
  const mmss = (n) => `${Math.floor(n / 60)}:${String(Math.round(n % 60)).padStart(2, '0')}`
  const perRow = agent.done > 0 ? secs / agent.done : 0
  const left = perRow > 0 ? Math.round(perRow * (agent.total - agent.done)) : 0
  return (
    <p className="rv-agenteta notes">
      {agent.batches > 1 && <>batch <b>{agent.batch}</b> of {agent.batches} · </>}
      elapsed {mmss(secs)}
      {agent.done > 0 && <> · ~{mmss(left)} left · {perRow.toFixed(1)}s/row</>}
      {(agent.names || []).length > 0 && agent.done < agent.total && (
        <> · now: {agent.names.slice(0, 4).join(' · ')}{agent.names.length > 4 ? ` +${agent.names.length - 4}` : ''}</>
      )}
    </p>
  )
}

/* ---------- "How to review" guide: the steward's working order ----------
   A Home-style CLICKABLE flow (components/WorkflowDiagram.jsx interaction
   pattern): the Dictionary hop and Govern are role=link nodes that navigate
   via onNavigate; the AI-agent chips and "Name the glossary" highlight the
   matching on-page control instead of navigating. Open by default,
   full width, theme tokens only (review.css .rv-wf rules). */

// Flash-highlight the first on-page control that matches one of `sels`.
function flashTarget(sels) {
  for (const sel of sels) {
    const el = document.querySelector(sel)
    if (!el) continue
    el.scrollIntoView({ behavior: 'smooth', block: 'center' })
    el.classList.add('rv-flash')
    window.setTimeout(() => el.classList.remove('rv-flash'), 2200)
    return
  }
}

// One guide box. With onActivate it behaves like a WorkflowDiagram node:
// role=link (or button for the highlight chips), Enter/Space activates.
function RvNode({ className = 'rv-wfnode', role = 'link', x, y, w, h, title, sub, chip, onActivate, aria }) {
  const props = onActivate
    ? {
        role, tabIndex: 0, 'aria-label': aria || title,
        onClick: onActivate,
        onKeyDown: (e) => {
          if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault()
            onActivate()
          }
        },
      }
    : {}
  const cy = y + h / 2
  return (
    <g className={`${className}${onActivate ? ' rv-wflink' : ''}`} {...props}>
      <rect x={x} y={y} width={w} height={h} rx="8" />
      <text className={chip ? 'rv-wfct' : 'rv-wft'} x={x + w / 2} y={sub ? cy - 5 : cy + 4} textAnchor="middle">{title}</text>
      {sub && <text className="rv-wfs" x={x + w / 2} y={cy + 12} textAnchor="middle">{sub}</text>}
    </g>
  )
}

function ReviewGuide({ onNavigate }) {
  const flashAgents = () => flashTarget(['.rv-agents'])
  const flashName = () => flashTarget(['.rv-savename', '.rv-saved'])
  return (
    <details className="card rv-guide" open>
      <summary>How to review — the working order</summary>
      <div className="rv-wfwrap">
        <svg className="rv-wf" viewBox="0 0 950 240"
             aria-label="Working order: 1 prune the rows; 2 name the glossary — autosave keeps your review and streams accepted improvements into the Dictionary's pending vocabulary; 3 run the AI agents in sequence — Enrich, then Suggest, Categorize and Tags, with QA as the gate (they propose, you apply) — suggested names do part of the disambiguation; 4 resolve remaining duplicate names with final names and enriched definitions in hand; 5 when you're happy with the review, go to the Dictionary page and approve the pending vocabulary — it already carries your enrichments — then continue to the Govern page. The Dictionary and Govern boxes navigate; the agent chips highlight the AI toolbar.">
          <defs>
            <marker id="rv-wfhead" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="8" markerHeight="8"
                    markerUnits="userSpaceOnUse" orient="auto-start-reverse">
              <path className="rv-wfheadp" d="M0.5 0.5 L7.5 4 L0.5 7.5 Z" />
            </marker>
          </defs>

          {/* row 1: prune → name (autosave = the Review→Dictionary sync) */}
          <RvNode x={4} y={8} w={168} h={46} title="① Prune" sub="keep / drop · High+Med cull" />
          <path className="rv-wfarrow" d="M176 31 H194" markerEnd="url(#rv-wfhead)" />
          <RvNode role="button" x={198} y={8} w={244} h={46} title="② Name the glossary" sub="autosave on · syncs the Dictionary"
                  onActivate={flashName}
                  aria="Name the glossary — autosave keeps your review and streams accepted improvements into the Dictionary's pending vocabulary" />

          {/* wrap connector into row 2 */}
          <path className="rv-wfarrow" d="M320 58 V72 H60 V82" markerEnd="url(#rv-wfhead)" />

          {/* row 2: the pass runs BEFORE duplicate resolution — it finalizes
              names (dissolving false duplicates), and real definitions make the
              remaining same-name calls easy. Two scopes, one agent: the sweep
              over every kept row, and the same call aimed at a single row. */}
          <g className="rv-wfgroup">
            <rect x={4} y={88} width={568} height={62} rx="10" />
            <text className="rv-wfglbl" x={14} y={101}>③ AI PASS — KEPT ROWS · ONE CALL PER BATCH · PROPOSE → YOU APPLY</text>
          </g>
          <RvNode chip role="button" className="rv-wfnode rv-wfchip" x={14} y={108} w={230} h={32}
                  title="3 · AI pass (all fields)" onActivate={flashAgents}
                  aria="Run the combined AI pass — definition, purpose, name, tags and a blank category in one call per batch of kept rows" />
          <text className="rv-wfglbl" x={252} y={129}>or</text>
          <RvNode chip x={274} y={108} w={286} h={32}
                  title="AI review (this row)" sub="same pass · expand a row"
                  aria="AI review — the same pass scoped to one row, from that row's expanded editor" />


          {/* wrap connector into row 3 */}
          <path className="rv-wfarrow" d="M60 150 V162" markerEnd="url(#rv-wfhead)" />

          {/* row 3: dedupe on FINAL names, then one Dictionary hop, then Govern */}
          <RvNode x={4} y={168} w={214} h={46} title="④ Resolve duplicates" sub="Merge · Disambiguate · AI advise" />
          <path className="rv-wfarrow" d="M222 191 H240" markerEnd="url(#rv-wfhead)" />
          <RvNode x={244} y={168} w={244} h={46} title="⑤ Approve pending vocabulary" sub="Dictionary ↗ · enriched by your review"
                  onActivate={() => onNavigate('dictionary')}
                  aria="When you're happy with the review, go to the Dictionary page — the pending vocabulary already carries your accepted enrichments; approve or retire it there" />
          <path className="rv-wfarrow" d="M492 191 H510" markerEnd="url(#rv-wfhead)" />
          <RvNode x={514} y={168} w={140} h={46} title="Govern ↗" sub="set stewardship"
                  onActivate={() => onNavigate('govern')} aria="Go to the Govern page to set stewardship" />
        </svg>
      </div>
      <ol className="workcycle">
        <li><b>Prune.</b> Every scanned column is a candidate — untick <b>Keep</b> on noise (or use <b>Keep High+Med conf</b>) rather than hunting for gaps; table-level terms always stay. <b>Structural keys arrive already pruned</b> (the <b>KEY</b> badge): a surrogate PK / FK reference-id isn&apos;t a business term — its PK/FK relationship still travels to the Registry&apos;s physical model, and ticking Keep restores it.</li>
        <li><b>Name the glossary</b> (top right of the grid) — autosave keeps your review <b>and</b> streams every accepted improvement into the Dictionary&apos;s <i>pending</i> vocabulary, so the two never drift. The flow is one-way: Review edits refresh pending entries; nothing in the Dictionary is approved without you.</li>
        <li><b>Run the AI pass.</b> <b>AI pass (all fields)</b> covers definition, purpose, a clearer name, governed tags and a blank category in <b>one model call per batch of rows</b> — every field proposed together from the same evidence, so none contradicts another — and it folds in the free deterministic work (governed tags re-derived from the Dictionary, the definition linter's QA ⚠ chip). To redo one row, expand it and use <b>AI review</b>; to redo one field, accept only that field's pill. Agents never edit the grid: as each batch returns, click-to-accept pills light up on the affected cells — accept them one by one, or <b>Accept all</b> from the strip above the grid. The grid's <b>LLM</b> pills appear only after a proposal is accepted. The governed tags it can propose come from the <i>approved</i> allow-list, so tags you approve on the Dictionary enrich the next run: the flywheel.</li>
        <li><b>Resolve duplicates — with final names and real definitions in hand.</b> The <b>AI pass</b> runs first on purpose: it finalizes names, dissolving false duplicates before you judge them (a rename <i>is</i> disambiguation), and real definitions make the remaining same-name calls easy. Same-named <i>kept</i> terms get a header bar: <b>Merge</b> into one term linked to all its columns, <b>Disambiguate</b> into unique names, or keep separate. Each header already carries a recommendation <i>and its reason</i>, derived from the scan evidence the moment the glossary loads — no button, no model. <b>AI advise</b> only escalates the groups that reason marks <b>(check)</b>: the ones with no profiled value sets to compare, where it probes live values over your database connection and lets the model adjudicate what is left. Auto-pruned keys sit outside duplicate resolution.</li>
        <li><b>Approve the pending vocabulary — once, at the end.</b> When you&apos;re happy with the review, hop to the <b>Dictionary</b> (click the box above): its pending terms and tags already carry your accepted definitions and corrected names (a fixed name folds the scan&apos;s raw misread in as an alias, so rescans don&apos;t re-propose it). Approve or retire, then <b>Set stewardship →</b> on the Govern page.</li>
      </ol>

      <div className="rv-agentdocs-h">
        What each AI agent does
        <small>— all run on <b>kept rows only</b> and <i>propose</i> changes; nothing lands until you accept a pill (or <b>Accept all</b>)</small>
      </div>
      <ul className="workcycle rv-agentdocs">
        {AGENT_DESC.map((a) => (
          <li key={a.label}>
            <b>{a.label}</b>{a.gate && <span className="rv-gate">the gate · runs last</span>} — {a.desc}
          </li>
        ))}
      </ul>

      <p className="hint-line">
        Review flows one way into the Dictionary: autosave refreshes its <i>pending</i>
        entries with your accepted edits (never the approved vocabulary — approval stays
        a steward click on the Dictionary page). The Dictionary in turn governs what the
        agents may propose.
      </p>
    </details>
  )
}

/* ---------- one data row of the review grid ----------
   `prop` is this row's inline AI proposal ({patch, display}) — each proposed
   field renders a click-to-accept pill on its own cell, populated live batch
   by batch while an agent runs. Nothing lands until a pill (or Accept all)
   is clicked. */

const GridRow = memo(function GridRow({ row: r, index, pos, expanded, prop, onAcceptProp, onField, onKeep, onUseName, onEvidence, onToggle, existsIn }) {
  const tt = isTableTerm(r)
  const keptRow = truthy(r.Keep)
  const srcs = splitList(r.Source_Column)
  const hasEv = !!(r.Value_Pattern || r.Value_Signature || r.Enum_Values)
  const sev = r.Sensitivity || 'LOW'
  // the proposed value for a field, or undefined when nothing is pending
  const pf = (f) => (prop && prop.patch && prop.display && prop.display.some((d) => d.field === f)
    ? prop.patch[f] : undefined)
  const pfDef = pf('Definition')
  const pfPur = pf('Purpose')
  const pfSev = pf('Sensitivity')
  const pfCat = pf('Category')
  const pfTags = pf('Suggested_Tags')
  const pfPii = pf('PII_Category')
  const pfName = pf('Suggested_Name')
  const pfTerm = pf('Term')
  return (
    <tr className={(keptRow ? '' : 'rv-dropped') + (tt ? ' rv-tterm' : '') + (expanded ? ' rv-open' : '')}>
      <td className="rv-keep rv-stick rv-s0">
        {tt
          ? <input type="checkbox" checked disabled title="Table-level term — always kept; can't be dropped even at low confidence." aria-label="Table term — always kept" />
          : <input type="checkbox" checked={keptRow} aria-label={`Keep ${r.Term || ''}`} onChange={(e) => onKeep(e, index, pos)} />}
      </td>
      <td className="rv-stick rv-s1">
        <input type="text" value={r.Category || ''} title={r.Category || ''}
               onChange={(e) => onField(index, 'Category', e.target.value)} aria-label="Category" />
        {pfCat !== undefined && (
          <button className="rv-aipill" onClick={() => onAcceptProp(index, 'Category')}
                  title={`AI proposes category “${pfCat}” — click to accept.`}>
            AI → {pfCat || '(clear)'}
          </button>
        )}
      </td>
      <td className="rv-stick rv-s2">
        <input type="text" value={r.Term || ''} title={r.Term || ''}
               onChange={(e) => onField(index, 'Term', e.target.value)} aria-label="Term" />
        {tt && <span className="rv-ttbadge" title="Table-level record term — links to the whole table; always kept.">TABLE</span>}
        {existsIn && (
          <span className="rv-ttbadge rv-xgbadge"
                title={`Already in PDC${existsIn.glossary ? ` — glossary "${existsIn.glossary}"` : ''}. Apply will link to the existing term rather than create a second one, so the definition PDC already holds is the one that stands. Reuse it, or rename this row if you mean a different concept.`}>
            IN PDC{existsIn.glossary ? ` · ${existsIn.glossary}` : ''}
          </span>
        )}
        {!keptRow && r.Prune_Reason && (
          <span className="rv-ttbadge rv-keybadge"
                title={`Auto-pruned by the scan: ${r.Prune_Reason}. ${/key|reference/i.test(r.Prune_Reason) ? "The PK/FK relationship still travels to the Registry's physical model — tick" : 'Tick'} Keep to restore it as a term.`}>
            {/* the badge says WHY it was pruned — "KEY" on an envelope date
                field read as a misjudgment when it was just a hardcoded label
                (field-caught: "Dates have now been identified as Keys") */}
            {/envelope/i.test(r.Prune_Reason) ? 'ENVELOPE'
              : /key|reference/i.test(r.Prune_Reason) ? 'KEY' : 'PRUNED'}
          </span>
        )}
        {r.Suggested_Name && r.Suggested_Name !== r.Term && (
          <button className="rv-ren" onClick={() => onUseName(index)}
                  title="LLM-suggested name from a cryptic column — click to apply to every row with this name">
            → {r.Suggested_Name}
          </button>
        )}
        {pfName !== undefined && pfName !== r.Term && (
          <button className="rv-ren rv-renai" onClick={() => onAcceptProp(index, 'Suggested_Name')}
                  title="AI-proposed name from this run — click to accept and rename every row with this name">
            → {pfName}
          </button>
        )}
        {pfTerm !== undefined && (
          <button className="rv-ren rv-renai" onClick={() => onAcceptProp(index, 'Term')}
                  title="AI-proposed term name — click to accept">
            → {pfTerm}
          </button>
        )}
      </td>
      <td>
        <div className="rv-cell">
          <button className="rv-prev" onClick={() => onToggle(index)} aria-expanded={expanded}
                  title={r.Definition ? `${r.Definition}\n\nClick to edit definition & purpose.` : 'Click to add a definition'}
                  aria-label={`Edit definition and purpose for ${r.Term || 'term'}`}>
            <span className={r.Definition ? 'rv-prevtext' : 'rv-prevtext empty'}>{r.Definition || 'add definition…'}</span>
            {llmChip(r, 'LLM_Definition') && <span className="rv-enr">LLM</span>}
            {r.QA_Issues ? <span className="rv-qaflag" title={`QA: ${String(r.QA_Issues).split(';').join(' · ')}`}>QA ⚠</span> : null}
            <span className="rv-caret" aria-hidden="true">{expanded ? '▾' : '▸'}</span>
          </button>
          {pfDef !== undefined && (
            <button className="rv-aipill" onClick={() => onAcceptProp(index, 'Definition')}
                    title={`AI proposes:\n\n${pfDef}\n\nClick to accept into Definition (expand the row to compare side by side).`}>
              AI →
            </button>
          )}
        </div>
      </td>
      <td>
        <div className="rv-cell">
          <button className="rv-prev" onClick={() => onToggle(index)} aria-expanded={expanded}
                  title={r.Purpose ? `${r.Purpose}\n\nClick to edit definition & purpose.` : 'Click to add a purpose'}
                  aria-label={`Edit purpose for ${r.Term || 'term'}`}>
            <span className={r.Purpose ? 'rv-prevtext' : 'rv-prevtext empty'}>{r.Purpose || 'purpose…'}</span>
            {llmChip(r, 'LLM_Purpose') && <span className="rv-enr">LLM</span>}
          </button>
          {pfPur !== undefined && (
            <button className="rv-aipill" onClick={() => onAcceptProp(index, 'Purpose')}
                    title={`AI proposes:\n\n${pfPur}\n\nClick to accept into Purpose (expand the row to compare side by side).`}>
              AI →
            </button>
          )}
        </div>
      </td>
      <td>
        <select className={`rv-sev sev-${sev}`} value={sev}
                onChange={(e) => onField(index, 'Sensitivity', e.target.value)} aria-label="Sensitivity">
          <option>HIGH</option><option>MEDIUM</option><option>LOW</option>
        </select>
        {r.PII_Category ? <div className={`rv-pii sev-${sev}`}>{r.PII_Category}</div> : null}
        {pfSev !== undefined && (
          <button className="rv-aipill" onClick={() => onAcceptProp(index, 'Sensitivity')}
                  title={`AI proposes sensitivity ${pfSev} — click to accept.`}>
            AI → {pfSev}
          </button>
        )}
        {pfPii !== undefined && (
          <button className="rv-aipill" onClick={() => onAcceptProp(index, 'PII_Category')}
                  title={`AI proposes PII category “${pfPii}” — click to accept.`}>
            AI → {pfPii || '(clear)'}
          </button>
        )}
      </td>
      <td>
        <select className={r.Critical_Data_Element === 'Yes' ? 'rv-cde on' : 'rv-cde'}
                value={r.Critical_Data_Element === 'Yes' ? 'Yes' : 'No'}
                onChange={(e) => onField(index, 'Critical_Data_Element', e.target.value)} aria-label="Critical Data Element">
          <option value="No">False</option><option value="Yes">True</option>
        </select>
      </td>
      <td>
        <input type="text" value={r.Suggested_Tags || ''} title={r.Suggested_Tags || ''}
               onChange={(e) => onField(index, 'Suggested_Tags', e.target.value)} aria-label="Tags" />
        {pfTags !== undefined && (
          <button className="rv-aipill" onClick={() => onAcceptProp(index, 'Suggested_Tags')}
                  title={`AI proposes tags:\n${pfTags || '(clear)'}\n\nClick to accept.`}>
            AI → tags
          </button>
        )}
      </td>
      <td>
        <span className={`badge ${r.Confidence === 'High' ? 'good' : r.Confidence === 'Medium' ? 'warning' : 'neutral'}`}>
          {r.Confidence || '—'}
        </span>
      </td>
      <td>
        <button className="rv-src" onClick={() => onEvidence(index)} title="View all sources & the scan evidence behind this term">
          <span className="rv-srctext">{srcs[0] || (tt ? 'table-level' : '—')}</span>
          {srcs.length > 1 && <span className="rv-more">+{srcs.length - 1}</span>}
          {hasEv && <span className="rv-evdot" aria-hidden="true">ⓘ</span>}
        </button>
      </td>
    </tr>
  )
})

/* ---------- expanded row editor: full-width Definition + Purpose + evidence ----------
   The old UI kept always-on textareas in two wide columns and let the page
   scroll; at 10 columns that squashed everything. Here the two prose fields
   collapse to one-line previews and this row expands in place (no modal) with
   full-width textareas and the scan-evidence bits underneath. */

function ExpandedRow({ row: r, index, prop, onAcceptProp, onField, onEvidence, onClose,
                       onAiReview, aiBusy }) {
  const srcs = splitList(r.Source_Column)
  const enums = splitList(r.Enum_Values)
  // pending AI proposal for a prose field → the old value stays in the
  // textarea, the proposed text shows beside/below it with its own Accept
  const pending = (f) => (prop && prop.patch && prop.display && prop.display.some((d) => d.field === f)
    ? prop.patch[f] : undefined)
  const pDef = pending('Definition')
  const pPur = pending('Purpose')
  const propBox = (field, text) => (
    <div className="rv-propbox">
      <span className="rv-expevk">AI PROPOSES</span>
      <span className="rv-propto">{text}</span>
      <button className="ghost sm" onClick={() => onAcceptProp(index, field)}>Accept</button>
    </div>
  )
  return (
    <tr className="rv-exprow">
      <td colSpan={10}>
        <div className="rv-exp" onKeyDown={(e) => { if (e.key === 'Escape') onClose() }}>
          <div className="rv-expgrid">
            <label>
              Definition
              {llmChip(r, 'LLM_Definition') && <span className="rv-enr">LLM</span>}
              <textarea autoFocus value={r.Definition || ''}
                        onChange={(e) => onField(index, 'Definition', e.target.value)} aria-label="Definition" />
              {pDef !== undefined && propBox('Definition', pDef)}
            </label>
            <label>
              Purpose
              {llmChip(r, 'LLM_Purpose') && <span className="rv-enr">LLM</span>}
              <textarea value={r.Purpose || ''} placeholder="why the business keeps this data…"
                        onChange={(e) => onField(index, 'Purpose', e.target.value)} aria-label="Purpose" />
              {pPur !== undefined && propBox('Purpose', pPur)}
            </label>
          </div>
          {r.QA_Issues ? <div className="rv-issues">⚠ QA: {String(r.QA_Issues).split(';').join(' · ')}</div> : null}
          <div className="rv-expev">
            <span className="rv-expevk">EVIDENCE</span>
            <span>
              sources <b>{srcs.length || 0}</b>
              {srcs.length > 0 && <>{': '}<code>{srcs.slice(0, 3).join('; ')}{srcs.length > 3 ? ` +${srcs.length - 3} more` : ''}</code></>}
            </span>
            {r.Value_Pattern && <span>pattern <code>{r.Value_Pattern}</code></span>}
            {r.Value_Signature && <span>signature <code>{r.Value_Signature}</code></span>}
            {enums.length > 0 && (
              <span>
                reference values <b>{enums.length}</b>{': '}
                {enums.slice(0, 6).map((v) => <code key={v} className="rv-expenum">{v}</code>)}
                {enums.length > 6 ? ` +${enums.length - 6}` : ''}
              </span>
            )}
            {!srcs.length && !hasEvidence(r) && <span className="rv-msg">table-level (conceptual) term — no profiled evidence</span>}
            <span className="rv-detseg"
                  title="Auto = detectable by value shape: with profiled evidence the Registry seeds a detection method, with none Policy asks for a seed. Mapping-only = governed by term links (Apply) alone, no value shape exists — Policy stops expecting a detection method. Full note: How terms are defined & built.">
              <span className="rv-expevk">DETECTION</span>
              <span className="seg" role="group" aria-label="Detection intent">
                <button className={r.Detection_Intent !== 'mapping_only' ? 'on' : ''}
                        onClick={() => onField(index, 'Detection_Intent', '')}>Auto</button>
                <button className={r.Detection_Intent === 'mapping_only' ? 'on' : ''}
                        onClick={() => onField(index, 'Detection_Intent', 'mapping_only')}>Mapping-only</button>
              </span>
              {/* the choice only shows up in the exported Registry, so spell out
                  what it does for THIS row — with a value shape it seeds a
                  detection method; without one, Auto leaves Policy to ask for a
                  seed while Mapping-only closes the question */}
              <span className="rv-msg rv-detwhy">
                {r.Detection_Intent === 'mapping_only'
                  ? '→ Registry says mapping_only — Policy won’t ask for a detection seed'
                  : hasEvidence(r)
                    ? '→ Registry seeds detection from this row’s value shape'
                    : '→ no value shape: Registry leaves detection open, so Policy will request a seed'}
              </span>
            </span>
            <span className="rv-grow" />
            <button className="primary sm" disabled={aiBusy} onClick={() => onAiReview(index)}
                    title="Run the pass on this row alone — richest evidence, and the model's whole attention on one term. The full sweep uses this exact prompt when Settings → Batch size is 1. Proposals land as pills on this row; nothing changes until you accept one.">
              {aiBusy ? 'AI running…' : 'AI review'}
            </button>
            <button className="ghost sm" onClick={() => onEvidence(index)}
                    title="All sources and the full scan evidence behind this term">Full evidence…</button>
            <button className="ghost sm" onClick={onClose} title="Collapse this editor (Esc)">Close ▴</button>
          </div>
        </div>
      </td>
    </tr>
  )
}

const hasEvidence = (r) => !!(r.Value_Pattern || r.Value_Signature || r.Enum_Values)

/* ---------- duplicate cluster header (Merge / Disambiguate / Keep separate) ---------- */

// `decided` separates "the steward chose Keep separate" from "nobody has chosen
// anything yet" — both are action === 'separate', because that is the neutral
// state a Merge/Disambiguate reverts to. Without the distinction an untouched
// group renders Keep separate as SELECTED, which reads as a decision the app
// made: the one outcome that ships two terms under one name, highlighted as if
// it were the advice. Until a steward picks, nothing is selected and the
// recommendation is the only thing lit.
function ClusterHead({ name, count, action, rec, locked, decided, onSet }) {
  const seg = (v, label) => (
    <button key={v} disabled={locked}
            className={(decided && action === v ? 'on' : '')
                       + (!decided && rec && rec.action === v ? ' rec' : '')}
            aria-pressed={decided && action === v}
            onClick={() => onSet(name, v)}>
      {label}
    </button>
  )
  const recLabel = rec && rec.action === 'merge' ? 'Merge' : rec && rec.action === 'split' ? 'Disambiguate' : 'Keep separate'
  return (
    <tr className="rv-gclhead">
      <td colSpan={10}>
        <div className="rv-gclwrap">
          <span className="rv-gclname" title={name}>{name}</span>
          <span className="badge warning">duplicate</span>
          <span className="rv-gclcnt">
            {count} candidate{count !== 1 ? 's' : ''}
            {action === 'merge' ? ' → merged into one' : action === 'split' ? ' → split & renamed' : ''}
          </span>
          {rec && rec.action && (
            <span className="rv-grec">
              Recommended: <b>{recLabel}</b>
              {rec.band !== 'high' && <span className="badge warning">check</span>}
              {rec.source === 'ai' && <span className="badge accent">AI</span>}
              {' — '}{rec.reason || ''}
            </span>
          )}
          <span className="rv-gsegs seg">{seg('merge', 'Merge')}{seg('split', 'Disambiguate')}{seg('separate', 'Keep separate')}</span>
        </div>
      </td>
    </tr>
  )
}

/* ---------- Find similar panel (same concept, different names) ---------- */

function SimilarityPanel({ sim, threshold, onThreshold, onMerge, onFlip, onDismiss, onClose }) {
  const bar = (v) => (
    <span className="rv-simbar"><i style={{ width: `${Math.round((v || 0) * 100)}%` }} /></span>
  )
  return (
    <div className="rv-bar" style={{ display: 'block' }}>
      <div className="rv-actionbar">
        <b>Suggested merges</b>
        <span className="rv-msg">same concept, different names — PDC would treat these as unrelated terms</span>
        <span className="rv-grow" />
        <label className="rv-cbx">
          Threshold
          <input type="range" min="0.5" max="0.9" step="0.02" value={threshold}
                 onChange={(e) => onThreshold(parseFloat(e.target.value))} />
          {threshold.toFixed(2)}
        </label>
        <button className="ghost sm" onClick={onClose}>Close</button>
      </div>
      {sim.error && <div className="error">Similarity failed: {sim.error}</div>}
      {sim.busy && <p className="loading">Scoring…</p>}
      {!sim.busy && !sim.error && sim.list.length === 0 && (
        <p className="hint-line">No same-concept name pairs above the threshold — lower it to widen the net.</p>
      )}
      {sim.list.map((s, idx) => (
        <div className="rv-panelrow" key={`${s.keep}→${s.drop}`}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div>
              <b>{s.keep}</b> <span className="muted">({s.keep_count})</span>
              <span className="muted"> ← merge </span>
              <b>{s.drop}</b> <span className="muted">({s.drop_count})</span>
            </div>
            <div className="meta">
              <span className={s.score >= 0.85 ? 'sens-lo ok' : 'sens-md'}>score {s.score.toFixed(2)}</span>
              {s.band === 'high' && <span className="badge good">strong</span>}
              {s.band === 'conflict' && <span className="badge serious">different concepts</span>}
              {s.band !== 'high' && s.band !== 'conflict' && <span className="badge warning">review</span>}
              <span>name {bar(s.signals?.lexical)}</span>
              <span>tokens {bar(s.signals?.token)}</span>
              <span>context {bar(s.signals?.structural)}</span>
            </div>
            {s.evidence_reason && (
              <div className={`rv-evline ${s.evidence === 'different' ? 'diff' : 'same'}`}>
                {s.evidence_reason}
                {s.evidence === 'different' ? ' — do not merge; rename with qualifiers if they collide' : ''}
              </div>
            )}
          </div>
          {s.band !== 'conflict' && (
            <>
              <button className="ghost sm" title="Swap which name is kept" onClick={() => onFlip(idx)}>⇆</button>
              <button className="ghost sm" onClick={() => onMerge(idx)}>Merge</button>
            </>
          )}
          <button className="ghost sm" onClick={() => onDismiss(idx)}>Dismiss</button>
        </div>
      ))}
    </div>
  )
}

/* ---------- evidence popover: sources + the scan evidence behind a term ---------- */

function EvidenceModal({ row: r, onClose }) {
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  const srcs = splitList(r.Source_Column)
  const enums = splitList(r.Enum_Values)
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" aria-label="Scan evidence"
           onClick={(e) => e.stopPropagation()}>
        <header>
          <h3>{r.Term || 'Term'} <span className="muted">— sources &amp; scan evidence</span></h3>
          <button className="ghost" onClick={onClose} aria-label="Close">✕</button>
        </header>
        <div className="modal-body">
          <div className="rv-evk">Sources ({srcs.length || 0})</div>
          {srcs.length
            ? <div className="rv-srclist">{srcs.map((s) => <div key={s}>{s}</div>)}</div>
            : <p className="hint-line">No source column recorded — a table-level (conceptual) term.</p>}
          {r.Value_Pattern && (
            <>
              <div className="rv-evk">Induced value pattern (regex)</div>
              <div className="rv-evv"><pre>{r.Value_Pattern}</pre></div>
            </>
          )}
          {r.Value_Signature && (
            <>
              <div className="rv-evk">Profiled value signature</div>
              <div className="rv-evv"><pre>{r.Value_Signature}</pre></div>
            </>
          )}
          {enums.length > 0 && (
            <>
              <div className="rv-evk">Reference values ({enums.length})</div>
              <div className="rv-evchips">{enums.map((v) => <span key={v}>{v}</span>)}</div>
            </>
          )}
          <div className="rv-evk">Review signals</div>
          <p className="hint-line" style={{ margin: 0 }}>
            Confidence <b>{r.Confidence || '—'}</b>
            {r.PII_Category ? <> · PII <b>{r.PII_Category}</b></> : null}
            {' · '}Sensitivity <b>{r.Sensitivity || '—'}</b>
            {r.Critical_Data_Element === 'Yes' ? <> · <b>CDE</b></> : null}
            {rowLLM(r) ? <> · LLM-enriched</> : null}
          </p>
          {!r.Value_Pattern && !r.Value_Signature && !enums.length && (
            <p className="hint-line">
              No profiled evidence on this term — scan a live connection with “Sample values” on so
              profiling can induce value formats and reference lists.
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
