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
import { useWorkspace, setRows, patchRow, setGlossaryMeta, save } from './../state.js'
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
    cats.add(r.Category)
    if (conf[r.Confidence] != null) conf[r.Confidence]++
    if (sev[r.Sensitivity] != null) sev[r.Sensitivity]++
    if (r.PII_Category) pii++
    if (r.LLM_Enriched === 'Yes') enr++
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
const AGENT_FIELD_LABELS = {
  Term: 'Term', Definition: 'Definition', Purpose: 'Purpose', Category: 'Category',
  Sensitivity: 'Sensitivity', Suggested_Tags: 'Tags', Suggested_Name: 'Suggested name',
  PII_Category: 'PII category', Critical_Data_Element: 'CDE',
}

const EMPTY_FILTERS = { q: '', cat: '', sev: '', conf: '', tag: '', pii: false, kept: false }

export default function ReviewPage({ onNavigate }) {
  const ws = useWorkspace()
  const rows = ws.rows

  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const [msg, setMsg] = useState('')
  const [error, setError] = useState(null)
  const [grp, setGrp] = useState({})               // {name: {action, base}}
  const [bulk, setBulk] = useState({ merge: false, disambig: false })
  const [reco, setReco] = useState({})             // {name: recommendation}
  const [advising, setAdvising] = useState(false)
  const [sim, setSim] = useState(null)             // {busy, list, error} | null
  const [simThresh, setSimThresh] = useState(0.6)
  const [agent, setAgent] = useState(null)         // {label, done, total, cancelling}
  const [proposals, setProposals] = useState(null) // {label, note, items: [...]}
  const [evidence, setEvidence] = useState(null)   // row index | null
  const [expanded, setExpanded] = useState(null)   // row index whose editor row is open
  const [hmSnap, setHmSnap] = useState(null)       // [{index, keep}] for the H+M toggle revert
  const [busy, setBusy] = useState(null)           // 'load' | 'enhance' | 'save'
  const [saveName, setSaveName] = useState('')

  const cancelRef = useRef(false)
  const snapRef = useRef(null)                     // raw-scan snapshot for Reset all
  const lastPosRef = useRef(null)                  // shift-click keep anchor
  const visRef = useRef([])
  const rowsRef = useRef(rows)
  rowsRef.current = rows
  const loadFileRef = useRef(null)
  const enhanceFileRef = useRef(null)
  const masterRef = useRef(null)

  // Capture the reset-point the first time rows appear (scan/load happened on
  // another page); the load/enhance actions below refresh it explicitly.
  useEffect(() => {
    if (rows.length && !snapRef.current) snapRef.current = deep(rows)
  }, [rows])

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
      if (q) {
        const hay = `${r.Term || ''} ${r.Definition || ''} ${r.Source_Column || ''} ${r.Category || ''} ${r.Suggested_Tags || ''}`.toLowerCase()
        if (!hay.includes(q)) return
      }
      out.push(i)
    })
    return out
  }, [rows, filters])

  const clusters = useMemo(() => {
    const active = activeNames(grp)
    const by = {}
    const order = []
    shown.forEach((i) => {
      const r = rows[i]
      if (!r) return
      const k = keyOf(r, i, active)
      if (!by[k]) { by[k] = []; order.push(k) }
      by[k].push(i)
    })
    return { by, order }
  }, [shown, rows, grp])

  const vis = useMemo(() => clusters.order.flatMap((k) => clusters.by[k]), [clusters])
  visRef.current = vis
  const posOf = useMemo(() => { const m = new Map(); vis.forEach((i, p) => m.set(i, p)); return m }, [vis])

  const stats = useMemo(() => computeStats(rows), [rows])
  const cats = useMemo(() => [...new Set(rows.map((r) => r.Category).filter(Boolean))].sort(), [rows])
  const tags = useMemo(
    () => [...new Set(rows.flatMap((r) => splitList(r.Suggested_Tags)))].sort((a, b) => a.toLowerCase().localeCompare(b.toLowerCase())),
    [rows])
  const kept = useMemo(() => rows.reduce((n, r) => n + (truthy(r.Keep) ? 1 : 0), 0), [rows])
  const keptShown = useMemo(() => vis.reduce((n, i) => n + (truthy(rows[i]?.Keep) ? 1 : 0), 0), [vis, rows])
  const anySuggestedNames = useMemo(() => rows.some((r) => r.Suggested_Name && r.Suggested_Name !== r.Term), [rows])

  useEffect(() => {
    if (masterRef.current) masterRef.current.indeterminate = keptShown > 0 && keptShown < vis.length
  }, [keptShown, vis.length])

  /* ---------- keep / prune ---------- */

  const structuralReset = () => { setHmSnap(null); setExpanded(null); lastPosRef.current = null }

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
      return { ...r, Keep: r.Confidence === 'High' || r.Confidence === 'Medium' ? 'Y' : 'N' }
    }))
    setHmSnap(snap)
  }

  /* ---------- inline edits ---------- */

  const onField = useCallback((index, field, value) => { patchRow(index, { [field]: value }) }, [])

  const toggleExpand = useCallback((index) => { setExpanded((e) => (e === index ? null : index)) }, [])

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

  // Full pass (the AI advise button): + live data-value probe + AI adjudication.
  async function aiAdvise() {
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
      setMsg(d.used_llm
        ? `AI adjudicated the ambiguous duplicate groups${d.probed ? ` (live-probed ${d.probed} group${d.probed !== 1 ? 's' : ''})` : ''}.`
        : d.probed
          ? `Live-probed ${d.probed} group(s); Ollama offline so evidence decides.`
          : 'Evidence-only recommendations (Ollama offline, no ambiguous groups probed).')
    } catch (e) { setError(e.message) }
    setAdvising(false)
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

  async function runChunks(label, call, { offlineBreak = true, chunk = CHUNK } = {}) {
    const baseRows = rowsRef.current
    const total = baseRows.length
    const working = baseRows.map((r) => ({ ...r }))
    cancelRef.current = false
    setAgent({ label, done: 0, total })
    setError(null)
    let offline = false
    let failed = 0
    for (let s = 0; s < total && !cancelRef.current; s += chunk) {
      const idx = []
      for (let i = s; i < Math.min(s + chunk, total); i++) idx.push(i)
      try {
        const d = await call(idx.map((i) => working[i]))
        if (d.llm && d.llm.online === false) {
          offline = true
          if (offlineBreak) break
        }
        ;(d.rows || []).forEach((nr, j) => {
          const i = idx[j]
          if (i == null || !nr || typeof nr !== 'object') return
          working[i] = { ...working[i], ...nr }
        })
      } catch { failed += idx.length }
      setAgent((a) => (a ? { ...a, done: Math.min(s + chunk, total) } : a))
    }
    setAgent(null)
    return { baseRows, working, offline, failed, stopped: cancelRef.current }
  }

  function diffProposals(label, run, watch, carry = [], extraNote = '') {
    const items = []
    run.baseRows.forEach((r, i) => {
      const w = run.working[i]
      const patch = {}
      const display = []
      watch.forEach((f) => {
        const a = r[f] == null ? '' : String(r[f])
        const b = w[f] == null ? '' : String(w[f])
        if (a !== b) { patch[f] = w[f] ?? ''; display.push({ field: f, from: a, to: b }) }
      })
      carry.forEach((f) => {
        const a = r[f] == null ? '' : String(r[f])
        const b = w[f] == null ? '' : String(w[f])
        if (a !== b) patch[f] = w[f] ?? ''
      })
      if (display.length) items.push({ index: i, term: r.Term || '', category: r.Category || '', display, patch, selected: true })
    })
    const note = [
      extraNote,
      run.offline ? 'Ollama offline' : '',
      run.stopped ? 'stopped early — rows already processed kept their proposals' : '',
      run.failed ? `${run.failed} row(s) failed` : '',
    ].filter(Boolean).join(' · ')
    if (!items.length) {
      setMsg(`${label}: no changes proposed${note ? ` (${note})` : ''}.`)
      return
    }
    setProposals({ label, note, items })
  }

  async function runEnrich() {
    const run = await runChunks('Enriching definitions & purposes', (rs) => apiPost('/api/enrich', { rows: rs }))
    if (run.offline) { setMsg('LLM offline — start Ollama and pull a model on the Settings page, then try again.'); return }
    diffProposals('Enrich with LLM', run,
      ['Definition', 'Purpose', 'Suggested_Name'],
      ['LLM_Definition', 'LLM_Purpose', 'LLM_Enriched', 'LLM_Name'])
  }

  async function runAiSuggest() {
    const run = await runChunks('AI suggesting from scan evidence', (rs) => apiPost('/api/ai-suggest', { rows: rs }))
    if (run.offline) { setMsg('LLM offline — start Ollama and pull a model on the Settings page, then try again.'); return }
    diffProposals('AI suggest (evidence)', run,
      ['Suggested_Name', 'Suggested_Tags', 'Sensitivity', 'Category', 'PII_Category'],
      ['LLM_Enriched'],
      'guardrailed: tags governed-only, sensitivity tighten-only, names land as → chips')
  }

  async function runCategorize() {
    const known = cats
    const run = await runChunks('AI categorizing', (rs) => apiPost('/api/ai-categorize', { rows: rs, categories: known, only_blank: true }))
    if (run.offline) { setMsg('Ollama offline — categorization needs the local model.'); return }
    diffProposals('AI categorize', run, ['Category'])
  }

  async function runRetag() {
    const run = await runChunks('Deriving governed tags', (rs) => apiPost('/api/retag', { rows: rs }), { chunk: Math.max(rowsRef.current.length, 1) })
    diffProposals('Suggest tags', run, ['Suggested_Tags'], [],
      'deterministic — re-derived from the governed vocabulary (Dictionary page)')
  }

  // AI QA definitions: linter always runs server-side; the AI judge adds
  // suggestions when Ollama is up. Flags are stamped onto the rows (so the
  // grid shows the QA chip) but definition rewrites stay proposals.
  async function runQa() {
    const run = await runChunks('QA-checking definitions',
      (rs) => apiPost('/api/qa-definitions', { rows: rs, ai: true }), { offlineBreak: false })
    const { working } = run
    setRows(rowsRef.current.map((r, i) => {
      const w = working[i]
      const nx = { ...r }
      delete nx.QA_Issues
      delete nx.QA_Suggestion
      if (w && w.QA_Issues) nx.QA_Issues = w.QA_Issues
      return nx
    }))
    const items = []
    run.baseRows.forEach((r, i) => {
      const w = working[i]
      if (!w || (!w.QA_Issues && !w.QA_Suggestion)) return
      const hasSugg = !!w.QA_Suggestion && w.QA_Suggestion !== (r.Definition || '')
      items.push({
        index: i,
        term: r.Term || '',
        category: r.Category || '',
        issues: w.QA_Issues || '',
        display: hasSugg ? [{ field: 'Definition', from: r.Definition || '', to: w.QA_Suggestion }] : [],
        patch: hasSugg ? { Definition: w.QA_Suggestion, QA_Issues: '' } : null,
        selected: hasSugg,
      })
    })
    const note = [
      run.offline ? 'linter only — Ollama offline' : 'linter + AI judge',
      run.stopped ? 'stopped early' : '',
      run.failed ? `${run.failed} row(s) failed` : '',
    ].filter(Boolean).join(' · ')
    if (!items.length) { setMsg(`Definition QA: nothing flagged (${note}).`); return }
    setMsg(`Definition QA: ${items.length} of ${run.baseRows.length} definitions flagged.`)
    setProposals({ label: 'AI QA definitions', note, items })
  }

  function applyProposals() {
    const sel = proposals.items.filter((it) => it.selected && it.patch)
    sel.forEach((it) => patchRow(it.index, it.patch))
    setProposals(null)
    structuralReset()
    setMsg(`Applied ${sel.length} change${sel.length !== 1 ? 's' : ''} from ${proposals.label}.`)
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
      snapRef.current = deep(d.rows || [])
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
      snapRef.current = deep(d.rows || [])
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
  const aiDisabled = noRows || !!agent || !!proposals

  return (
    <>
      <div className="page-head">
        <h1>Review candidate terms</h1>
        <p className="psub">
          Every scanned column is one candidate term — prune rather than hunt for gaps.
          Edit definition, purpose, sensitivity, CDE and tags inline; the AI agents propose, you apply.
        </p>
      </div>

      <ReviewGuide />

      <section className="card">
        <header>
          <h2>Review grid <span>prune candidate terms</span></h2>
          {rows.length > 0 && (ws.name || ws.id
            ? (
              <span className="badge neutral">
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
                <button className="ghost sm" disabled={!saveName.trim() || busy === 'save'} onClick={nameAndSave}>
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
          <span className="rv-agents" role="group" aria-label="AI agents — they propose, you review and apply"
                title="Each agent run collects its changes into a proposal diff — nothing touches the grid until you tick and apply.">
            <span className="rv-agentslbl">AI AGENTS<small>propose → you apply</small></span>
            <button className="ghost sm" disabled={aiDisabled} onClick={runEnrich}
                    title="Rewrite definitions & purposes with the local LLM. Proposals only — you review the diff before anything lands.">
              Enrich with LLM
            </button>
            <button className="ghost sm" disabled={aiDisabled} onClick={runAiSuggest}
                    title="Evidence-grounded pass: the local model reads each row's scan evidence (profiled value signature, induced regex, reference values) and proposes names, governed tags and tightened sensitivity.">
              AI suggest (evidence)
            </button>
            <button className="ghost sm" disabled={aiDisabled} onClick={runQa}
                    title="Definition quality check: the deterministic linter (circular, vague, echoed, duplicated) always runs; the local AI judge adds rewrites when Ollama is up. Flags and proposals only.">
              AI QA definitions
            </button>
            <button className="ghost sm" disabled={aiDisabled} onClick={runCategorize}
                    title="AI category assignment: files uncategorized terms into the known categories; off-list answers are discarded.">
              AI categorize
            </button>
            <button className="ghost sm" disabled={aiDisabled} onClick={runRetag}
                    title="Re-derive meaningful, controlled tags for every term from the governed dictionary — deterministic, no rescan.">
              Suggest tags
            </button>
            {anySuggestedNames && (
              <button className="ghost sm" disabled={locked} onClick={useAllNames}
                      title="Apply every pending → suggested-name chip at once.">
                Apply all suggested names
              </button>
            )}
          </span>
        </div>

        {agent && (
          <div className="rv-progress">
            <span className="ep">
              {agent.cancelling ? 'Finishing current batch…' : `${agent.label} — ${agent.done}/${agent.total} (${Math.round((100 * agent.done) / Math.max(agent.total, 1))}%)`}
            </span>
            <div className="progress-track" role="progressbar" aria-valuemin={0} aria-valuemax={agent.total} aria-valuenow={agent.done}>
              <div className="progress-bar" style={{ width: `${Math.round((100 * agent.done) / Math.max(agent.total, 1))}%` }} />
            </div>
            <button className="ghost sm" disabled={agent.cancelling}
                    onClick={() => { cancelRef.current = true; setAgent((a) => (a ? { ...a, cancelling: true } : a)) }}>
              Cancel
            </button>
          </div>
        )}

        {error && <div className="error">{error}</div>}

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
              Confidence H<b className="sens-hi">{stats.confidence.High}</b> M<b className="sens-md">{stats.confidence.Medium}</b> L<b className="sens-lo">{stats.confidence.Low}</b>
            </span>
            <span className="rv-chip">
              Sensitivity HIGH<b className="sens-hi">{stats.sensitivity.HIGH}</b> MED<b className="sens-md">{stats.sensitivity.MEDIUM}</b> LOW<b className="sens-lo">{stats.sensitivity.LOW}</b>
            </span>
            {stats.enriched > 0 && <span className="rv-chip">LLM-enriched<b>{stats.enriched}</b></span>}
          </div>
        )}

        {rows.length > 0 && (
          <div className="rv-bar">
            <span className="lbl">FILTER</span>
            <input className="rv-q" type="text" placeholder="Filter term, definition, source…" value={filters.q}
                   onChange={(e) => setFilters((f) => ({ ...f, q: e.target.value }))} />
            <select value={filters.cat} onChange={(e) => setFilters((f) => ({ ...f, cat: e.target.value }))} aria-label="Category filter">
              <option value="">All categories</option>
              {cats.map((c) => <option key={c}>{c}</option>)}
            </select>
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
              {tags.map((t) => <option key={t}>{t}</option>)}
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
            <button className="ghost sm" disabled={advising || noRows} onClick={aiAdvise}
                    title="Escalate the duplicate-group advice: probe LIVE data values for ambiguous groups (when a database connection exists) and let the local AI agent adjudicate what's left. Hints only.">
              {advising ? 'Advising…' : 'AI advise'}
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

        <div className="rv-tablewrap">
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
                    {cluster && <ClusterHead name={k} count={idxs.length} action={act} rec={rec} locked={locked} onSet={onGroupSet} />}
                    {idxs.map((i) => (
                      <Fragment key={i}>
                        <GridRow row={rows[i]} index={i} pos={posOf.get(i)} expanded={expanded === i}
                                 onField={onField} onKeep={onKeep} onUseName={useName}
                                 onEvidence={setEvidence} onToggle={toggleExpand} />
                        {expanded === i && rows[i] && (
                          <ExpandedRow row={rows[i]} index={i} onField={onField}
                                       onEvidence={setEvidence} onClose={() => setExpanded(null)} />
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
          <span className="rv-msg">{msg || 'Reviewed and pruned? Set stewardship next — it saves with the workspace and bakes into the JSONL you generate on Apply.'}</span>
          <span className="rv-grow" />
          <button className="ghost" onClick={() => onNavigate('connect')}>← Connect a source</button>
          <button className="primary" disabled={kept === 0} onClick={() => onNavigate('govern')}
                  title={kept ? 'Set stewardship, then generate on the Govern page' : 'Keep at least one term first (tick a Keep box, or use Keep High+Med conf)'}>
            Set stewardship →
          </button>
        </div>
      </section>

      {proposals && (
        <ProposalModal proposals={proposals} setProposals={setProposals} onApply={applyProposals} />
      )}
      {evidence != null && rows[evidence] && (
        <EvidenceModal row={rows[evidence]} onClose={() => setEvidence(null)} />
      )}
    </>
  )
}

/* ---------- "How to review" guide: the working order, collapsed by default ----------
   Same details.card > summary pattern as the Dictionary flywheel explainer;
   the flow itself is a compact inline SVG in the WorkflowDiagram style
   (theme tokens only — see review.css .rv-wf rules). */

const GUIDE_STEPS = [
  { n: '①', title: 'Prune', sub: 'keep / drop · High+Med cull' },
  { n: '②', title: 'Resolve duplicates', sub: 'Merge · Disambiguate · keep' },
  { n: '③', title: 'Enrich & QA', sub: 'agents propose — you apply' },
  { n: '④', title: 'Name the glossary', sub: 'turns autosave on' },
]

function ReviewGuide() {
  const W = 158
  const xs = GUIDE_STEPS.map((_, i) => 4 + i * (W + 24))
  return (
    <details className="card rv-guide">
      <summary>How to review — the working order</summary>
      <div className="rv-wfwrap">
        <svg className="rv-wf" viewBox="0 0 820 62"
             aria-label="Working order: 1 prune the rows, 2 resolve duplicate names, 3 enrich and QA with the AI agents (they propose, you apply), 4 name the glossary to turn on autosave, then set stewardship on the Govern page.">
          <defs>
            <marker id="rv-wfhead" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="8" markerHeight="8"
                    markerUnits="userSpaceOnUse" orient="auto-start-reverse">
              <path className="rv-wfheadp" d="M0.5 0.5 L7.5 4 L0.5 7.5 Z" />
            </marker>
          </defs>
          {xs.slice(0, -1).map((x) => (
            <path key={x} className="rv-wfarrow" d={`M${x + W + 4} 31 H${x + W + 18}`} markerEnd="url(#rv-wfhead)" />
          ))}
          {GUIDE_STEPS.map((s, i) => (
            <g className="rv-wfnode" key={s.title}>
              <rect x={xs[i]} y={8} width={W} height={46} rx={8} />
              <text className="rv-wft" x={xs[i] + W / 2} y={27} textAnchor="middle">{s.n} {s.title}</text>
              <text className="rv-wfs" x={xs[i] + W / 2} y={43} textAnchor="middle">{s.sub}</text>
            </g>
          ))}
          <path className="rv-wfarrow rv-wfdotted" d="M734 31 H748" markerEnd="url(#rv-wfhead)" />
          <g className="rv-wfout">
            <rect x={752} y={16} width={64} height={30} rx={8} />
            <text className="rv-wft" x={784} y={35} textAnchor="middle">Govern</text>
          </g>
        </svg>
      </div>
      <ol className="workcycle">
        <li><b>Prune.</b> Every scanned column is a candidate — untick <b>Keep</b> on noise (or use <b>Keep High+Med conf</b>) rather than hunting for gaps; table-level terms always stay.</li>
        <li><b>Resolve duplicates.</b> Same-named terms get a header bar: <b>Merge</b> into one term linked to all its columns, <b>Disambiguate</b> into unique names, or keep separate — <b>AI advise</b> and <b>Find similar</b> recommend, you decide.</li>
        <li><b>Enrich &amp; QA.</b> The AI AGENTS toolbar never edits the grid: each run opens a diff of proposals you tick and apply (definitions, names, tags, categories, QA rewrites).</li>
        <li><b>Name the glossary</b> (top right of the grid) so autosave keeps your review, then move on to <b>Set stewardship →</b> on the Govern page.</li>
      </ol>
    </details>
  )
}

/* ---------- one data row of the review grid ---------- */

const GridRow = memo(function GridRow({ row: r, index, pos, expanded, onField, onKeep, onUseName, onEvidence, onToggle }) {
  const tt = isTableTerm(r)
  const keptRow = truthy(r.Keep)
  const srcs = splitList(r.Source_Column)
  const hasEv = !!(r.Value_Pattern || r.Value_Signature || r.Enum_Values)
  const sev = r.Sensitivity || 'LOW'
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
      </td>
      <td className="rv-stick rv-s2">
        <input type="text" value={r.Term || ''} title={r.Term || ''}
               onChange={(e) => onField(index, 'Term', e.target.value)} aria-label="Term" />
        {tt && <span className="rv-ttbadge" title="Table-level record term — links to the whole table; always kept.">TABLE</span>}
        {r.Suggested_Name && r.Suggested_Name !== r.Term && (
          <button className="rv-ren" onClick={() => onUseName(index)}
                  title="LLM-suggested name from a cryptic column — click to apply to every row with this name">
            → {r.Suggested_Name}
          </button>
        )}
      </td>
      <td>
        <button className="rv-prev" onClick={() => onToggle(index)} aria-expanded={expanded}
                title={r.Definition ? `${r.Definition}\n\nClick to edit definition & purpose.` : 'Click to add a definition'}
                aria-label={`Edit definition and purpose for ${r.Term || 'term'}`}>
          <span className={r.Definition ? 'rv-prevtext' : 'rv-prevtext empty'}>{r.Definition || 'add definition…'}</span>
          {(r.LLM_Definition === 'Yes' || (r.LLM_Definition === undefined && r.LLM_Enriched === 'Yes')) && <span className="rv-enr">LLM</span>}
          {r.QA_Issues ? <span className="rv-qaflag" title={`QA: ${String(r.QA_Issues).split(';').join(' · ')}`}>QA ⚠</span> : null}
          <span className="rv-caret" aria-hidden="true">{expanded ? '▾' : '▸'}</span>
        </button>
      </td>
      <td>
        <button className="rv-prev" onClick={() => onToggle(index)} aria-expanded={expanded}
                title={r.Purpose ? `${r.Purpose}\n\nClick to edit definition & purpose.` : 'Click to add a purpose'}
                aria-label={`Edit purpose for ${r.Term || 'term'}`}>
          <span className={r.Purpose ? 'rv-prevtext' : 'rv-prevtext empty'}>{r.Purpose || 'purpose…'}</span>
          {(r.LLM_Purpose === 'Yes' || (r.LLM_Purpose === undefined && r.LLM_Enriched === 'Yes')) && <span className="rv-enr">LLM</span>}
        </button>
      </td>
      <td>
        <select className={`rv-sev sev-${sev}`} value={sev}
                onChange={(e) => onField(index, 'Sensitivity', e.target.value)} aria-label="Sensitivity">
          <option>HIGH</option><option>MEDIUM</option><option>LOW</option>
        </select>
        {r.PII_Category ? <div className={`rv-pii sev-${sev}`}>{r.PII_Category}</div> : null}
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

function ExpandedRow({ row: r, index, onField, onEvidence, onClose }) {
  const srcs = splitList(r.Source_Column)
  const enums = splitList(r.Enum_Values)
  return (
    <tr className="rv-exprow">
      <td colSpan={10}>
        <div className="rv-exp" onKeyDown={(e) => { if (e.key === 'Escape') onClose() }}>
          <div className="rv-expgrid">
            <label>
              Definition
              {(r.LLM_Definition === 'Yes' || (r.LLM_Definition === undefined && r.LLM_Enriched === 'Yes')) && <span className="rv-enr">LLM</span>}
              <textarea autoFocus value={r.Definition || ''}
                        onChange={(e) => onField(index, 'Definition', e.target.value)} aria-label="Definition" />
            </label>
            <label>
              Purpose
              {(r.LLM_Purpose === 'Yes' || (r.LLM_Purpose === undefined && r.LLM_Enriched === 'Yes')) && <span className="rv-enr">LLM</span>}
              <textarea value={r.Purpose || ''} placeholder="why the business keeps this data…"
                        onChange={(e) => onField(index, 'Purpose', e.target.value)} aria-label="Purpose" />
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
            <span className="rv-grow" />
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

function ClusterHead({ name, count, action, rec, locked, onSet }) {
  const seg = (v, label) => (
    <button key={v} disabled={locked}
            className={(action === v ? 'on' : '') + (rec && rec.action === v && action === 'separate' ? ' rec' : '')}
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

/* ---------- agent proposals: the steward reviews the diff, then applies ---------- */

function ProposalModal({ proposals, setProposals, onApply }) {
  const selectable = proposals.items.filter((it) => it.patch)
  const selected = selectable.filter((it) => it.selected)
  const toggleAll = (on) => setProposals({
    ...proposals,
    items: proposals.items.map((it) => (it.patch ? { ...it, selected: on } : it)),
  })
  const toggle = (i) => setProposals({
    ...proposals,
    items: proposals.items.map((it, j) => (j === i ? { ...it, selected: !it.selected } : it)),
  })
  return (
    <div className="modal-overlay" onClick={() => setProposals(null)}>
      <div className="modal rv-wide" role="dialog" aria-modal="true" aria-label={`${proposals.label} — proposed changes`}
           onClick={(e) => e.stopPropagation()}>
        <header>
          <h3>{proposals.label} <span className="muted">— {proposals.items.length} row(s) flagged{proposals.note ? ` · ${proposals.note}` : ''}</span></h3>
          <button className="ghost" onClick={() => setProposals(null)} aria-label="Close">✕</button>
        </header>
        <div className="modal-body">
          <p className="hint-line">
            Nothing has touched the grid yet — tick the proposals to accept, then Apply. Rows flagged without a
            proposal are listed for your own edit.
          </p>
          {selectable.length > 0 && (
            <div className="rv-propbar">
              <label className="rv-cbx">
                <input type="checkbox" checked={selected.length === selectable.length}
                       onChange={(e) => toggleAll(e.target.checked)} />
                Select / deselect all
              </label>
              <span className="rv-grow" />
              <button className="primary sm" disabled={!selected.length} onClick={onApply}>
                Apply {selected.length} selected
              </button>
              <button className="ghost sm" onClick={() => setProposals(null)}>Dismiss all</button>
            </div>
          )}
          {proposals.items.map((it, i) => (
            <div className="rv-panelrow" key={it.index}>
              {it.patch
                ? <input type="checkbox" checked={it.selected} onChange={() => toggle(i)} aria-label={`select ${it.term}`} />
                : <span style={{ width: 13 }} aria-hidden="true" />}
              <div style={{ flex: 1, minWidth: 0 }}>
                <b>{it.term}</b> <span className="muted">{it.category}</span>
                {it.issues && <div className="rv-issues">⚠ {String(it.issues).split(';').join(' · ')}</div>}
                {it.display.map((d) => (
                  <div className="rv-diff" key={d.field}>
                    <span className="fld">{AGENT_FIELD_LABELS[d.field] || d.field}</span>
                    {d.from && <span className="from">{d.from}</span>}
                    {d.from && ' '}
                    <span className="to">{d.to || '(cleared)'}</span>
                  </div>
                ))}
                {!it.display.length && !it.issues && <div className="rv-msg">no visible change</div>}
                {!it.patch && it.issues && <div className="rv-msg">no rewrite proposed — edit the definition in the grid</div>}
              </div>
            </div>
          ))}
        </div>
      </div>
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
            {r.LLM_Enriched === 'Yes' ? <> · LLM-enriched</> : null}
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
