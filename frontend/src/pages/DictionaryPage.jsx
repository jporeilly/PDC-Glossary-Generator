// Dictionary page — the port of the old UI's "Term & Tag dictionary"
// (static/js/07-dictionary.js + templates/index.html #page-dictionary): the
// governed vocabulary (generic baseline + company layer), pending steward
// review with AI advice, per-item approve / durable retire / fold-to-alias,
// the AI fold advisor, the search-facet preview with health flags, the
// governance audit trail, reseed, exports and the domain-pack flywheel with
// conflict review. The "Acting as" actor is recorded on every save/approve.
import { useEffect, useRef, useState } from 'react'
import { apiGet, apiPost } from './../api.js'
import { useWorkspace } from './../state.js'
import './dictionary.css'

function downloadBlob(content, filename, type = 'application/json') {
  const url = URL.createObjectURL(new Blob([content], { type }))
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 5000)
}

function LayerBadge({ status }) {
  if (status === 'generic') return <span className="badge neutral">generic</span>
  if (status === 'pending') return <span className="badge warning">pending</span>
  return <span className="badge good">approved</span>
}

function SevBadge({ s }) {
  if (!s) return <span className="notes">—</span>
  const cls = s === 'HIGH' ? 'serious' : s === 'MEDIUM' ? 'warning' : 'neutral'
  return <span className={`badge ${cls}`}>{s}</span>
}

// Levenshtein distance — the near-duplicate facet check, ported verbatim.
function lev(a, b) {
  const m = a.length, n = b.length
  if (!m) return n
  if (!n) return m
  const d = Array.from({ length: m + 1 }, (_, i) => [i, ...Array(n).fill(0)])
  for (let j = 0; j <= n; j++) d[0][j] = j
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1,
        d[i - 1][j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1))
    }
  }
  return d[m][n]
}

const BATCH = 10

export default function DictionaryPage({ onNavigate }) {
  const ws = useWorkspace()
  const [dict, setDict] = useState(null)
  const [loadErr, setLoadErr] = useState(null)
  const [msg, setMsg] = useState(null)          // string | JSX
  const [warnings, setWarnings] = useState([])
  const [settings, setSettings] = useState(null)
  const [actor, setActorState] = useState(() => {
    try { return localStorage.getItem('gg_steward') || '' } catch { return '' }
  })
  const [advice, setAdvice] = useState({})
  const [reviewing, setReviewing] = useState(false)
  const [prog, setProg] = useState(null)        // {done, total}
  const cancelRef = useRef(false)
  const [fold, setFold] = useState(null)        // {pairs, governed}
  const [foldBusy, setFoldBusy] = useState(false)
  const [pack, setPack] = useState(null)        // /api/export-pack response
  const [resolutions, setResolutions] = useState({})
  const [rowsShown, setRowsShown] = useState(() => {
    try { return parseInt(localStorage.getItem('gg_td_rows'), 10) || 7 } catch { return 7 }
  })
  const [newTerm, setNewTerm] = useState({ name: '', sens: 'LOW', aliases: '', tags: '' })
  const [newTag, setNewTag] = useState({ name: '', floor: '' })
  const [newRule, setNewRule] = useState({ pattern: '', tags: '' })
  const [audit, setAudit] = useState(null)
  const [auditErr, setAuditErr] = useState(null)

  const setActor = (v) => {
    const a = (v || '').trim()
    setActorState(v)
    try { localStorage.setItem('gg_steward', a) } catch { /* private mode */ }
  }

  const load = () => {
    setLoadErr(null)
    apiGet('/api/tagdict').then(setDict).catch((e) => setLoadErr(e.message))
  }
  const loadAudit = () => {
    apiGet('/api/audit?n=100')
      .then((d) => { setAudit(d); setAuditErr(null) })
      .catch((e) => setAuditErr(e.message))
  }

  useEffect(() => {
    load()
    loadAudit()
    apiGet('/api/settings').then(setSettings).catch(() => setSettings({}))
  }, [])

  const setRows = (n) => {
    setRowsShown(n)
    try { localStorage.setItem('gg_td_rows', String(n)) } catch { /* private mode */ }
  }
  const boxStyle = { maxHeight: `${rowsShown * 29 + 40}px` }

  /* ---------- review actions (approve / durable retire / fold-to-alias) ---------- */

  async function review(kind, names, action, target, doneMsg) {
    try {
      const d = await apiPost('/api/tagdict/review', {
        kind, names, action, target, actor: actor.trim(),
      })
      setDict(d)
      loadAudit()
      if (doneMsg) setMsg(doneMsg)
      return d
    } catch (e) {
      setMsg(`Review failed: ${e.message}`)
      return null
    }
  }

  function approveAll(kind) {
    const items = kind === 'term' ? dict.terms || [] : dict.tags || []
    const names = items.filter((t) => t.status === 'pending').map((t) => (kind === 'term' ? t.term : t.tag))
    if (!names.length) return
    if (!window.confirm(
      `Approve ALL ${names.length} pending ${kind}${names.length === 1 ? '' : 's'} into the governed vocabulary?\n\n` +
      'Everything approved governs the Registry and exports into the domain pack — where it ' +
      'reseeds every future install. Approve only what belongs; rejecting noise is safe (a real ' +
      'concept re-proposes itself on the next scan, with evidence). Tip: run AI review first for ' +
      'per-item advice, and mistakes can be undone per item with ✕ / ⤵ on the tables below.')) return
    review(kind, names, 'approve', undefined,
      `Approved ${names.length} ${kind}${names.length > 1 ? 's' : ''}.`)
  }

  async function alias(name, target) {
    const d = await review('term', [name], 'alias', target,
      `"${name}" folded into "${target}" as an alias.`)
    if (d) setAdvice((a) => { const n = { ...a }; delete n[name]; return n })
  }

  function termFold(t) {
    const target = window.prompt(
      `Fold "${t.term}" into which governed term?\n\n"${t.term}" becomes an ALIAS of the target — ` +
      'future scans map its columns there automatically. Durable across reseeds.', '')
    if (!target || !target.trim()) return
    alias(t.term, target.trim())
  }

  function termRetire(t) {
    if (!window.confirm(
      `Retire term "${t.term}" from the governed vocabulary?\n\nThis is DURABLE: a tombstone keeps ` +
      'it retired through reloads and Reseeds, and the next Export domain pack will offer to ' +
      'remove it from the installed pack too. A future scan that finds real evidence can ' +
      're-propose it as pending — approving it then lifts the tombstone. Recorded in the audit trail.')) return
    review('term', [t.term], 'reject', undefined, `Rejected term "${t.term}".`)
  }

  function tagRetire(t) {
    if (!window.confirm(
      `Retire tag "${t.tag}" from the governed allow-list?\n\nDurable across reseeds (tombstoned); ` +
      'the next Export domain pack will offer to remove it from the pack. A rule that still emits ' +
      'it will re-add it with a warning. Recorded in the audit trail.')) return
    review('tag', [t.tag], 'reject', undefined, `Rejected tag "${t.tag}".`)
  }

  function retireEmpty(names) {
    if (!names.length) return
    if (!window.confirm(
      `Retire ${names.length} empty company tag(s) from the governed vocabulary?\n\n${names.join(', ')}` +
      '\n\nThe generic baseline is untouched; a tag still emitted by a rule will be re-added with a warning.')) return
    review('tag', names, 'reject', undefined, `Retired ${names.length} empty company tag(s).`)
  }

  /* ---------- AI review of the pending queue (batched, cancellable) ---------- */

  async function aiReview() {
    if (reviewing) return
    const names = (dict.terms || [])
      .filter((t) => t.status === 'pending' && t.layer !== 'generic')
      .map((t) => t.term)
    if (!names.length) {
      setMsg('Nothing pending to review.')
      return
    }
    setReviewing(true)
    cancelRef.current = false
    setAdvice({})
    setProg({ done: 0, total: names.length })
    const acc = {}
    let done = 0
    let usedLlm = false
    try {
      for (let i = 0; i < names.length && !cancelRef.current; i += BATCH) {
        const d = await apiPost('/api/tagdict/ai-review', {
          model: settings?.model || null, compute: settings?.compute,
          names: names.slice(i, i + BATCH),
        })
        Object.assign(acc, d.advice || {})
        usedLlm = usedLlm || !!d.used_llm
        done = Math.min(i + BATCH, names.length)
        setAdvice({ ...acc })                // recommendations appear batch by batch
        setProg({ done, total: names.length })
      }
      const n = Object.keys(acc).length
      const offline = usedLlm ? '' : ' (Ollama offline — duplicate check only)'
      setMsg(n
        ? `AI reviewed ${done} candidate(s)${cancelRef.current ? ' (cancelled early)' : ''} — ${n} recommendation(s)${offline}.`
        : `Reviewed ${done} candidate(s) — no recommendations${offline}.`)
    } catch (e) {
      setMsg(`AI review failed: ${e.message}`)
    } finally {
      setReviewing(false)
      cancelRef.current = false
      setProg(null)
    }
  }

  /* ---------- AI fold advisor across the governed vocabulary ---------- */

  async function foldAdvisor() {
    setFoldBusy(true)
    try {
      setFold(await apiPost('/api/tagdict/fold-advisor', {}))
    } catch (e) {
      setMsg(`Fold advisor failed: ${e.message}`)
    } finally {
      setFoldBusy(false)
    }
  }

  async function foldAll() {
    const pairs = (fold?.pairs || []).filter((p) => p.confidence === 'high')
    if (!pairs.length) return
    if (!window.confirm(
      `Fold all ${pairs.length} high-confidence twin(s) into their canonical terms?\n\n` +
      'Each twin becomes an ALIAS of its canonical — durable across reseeds, one audit entry per ' +
      'fold. Review-band suggestions are NOT included. If any canonical name looked wrong in the ' +
      'list, dismiss that pair first.')) return
    let done = 0
    let last = null
    for (const p of pairs) {
      try {
        const d = await apiPost('/api/tagdict/review', {
          kind: 'term', names: [p.fold], action: 'alias', target: p.keep, actor: actor.trim(),
        })
        if (d) { last = d; done += 1 }
      } catch { /* keep folding the rest */ }
    }
    if (last) setDict(last)
    setFold(null)
    loadAudit()
    setMsg(`Folded ${done} twin(s) into their canonical terms — aliases now resolve those names on every future scan.`)
  }

  const dismissPair = (i) =>
    setFold((f) => ({ ...f, pairs: f.pairs.filter((_, k) => k !== i) }))

  /* ---------- local add term / tag / rule (Save to persist) ---------- */

  function addTerm() {
    if (!dict) return
    const name = newTerm.name.trim()
    if (!name) { setMsg('Enter a term.'); return }
    if ((dict.terms || []).some((t) => t.term === name)) { setMsg('Term already exists.'); return }
    const split = (s) => s.split(';').map((x) => x.trim()).filter(Boolean)
    const terms = [...(dict.terms || []), {
      term: name, layer: 'company', status: 'approved', sensitivity: newTerm.sens,
      aliases: split(newTerm.aliases), tags: split(newTerm.tags), count: 0,
    }].sort((a, b) => a.term.localeCompare(b.term))
    setDict({ ...dict, terms, term_count: terms.length })
    setNewTerm({ name: '', sens: 'LOW', aliases: '', tags: '' })
    setMsg(`Added "${name}" — Save to persist.`)
  }

  function addTag() {
    if (!dict) return
    const name = newTag.name.trim()
    if (!name) { setMsg('Enter a tag.'); return }
    if ((dict.tags || []).some((t) => t.tag === name)) { setMsg('Tag already exists.'); return }
    const tags = [...(dict.tags || []), {
      tag: name, label: name, layer: 'company', status: 'approved',
      sensitivity_floor: newTag.floor || null, count: 0, examples: [],
    }].sort((a, b) => a.tag.localeCompare(b.tag))
    setDict({ ...dict, tags, tag_count: tags.length })
    setNewTag({ name: '', floor: '' })
    setMsg(`Added "${name}" — Save to persist.`)
  }

  function addRule() {
    if (!dict) return
    const pattern = newRule.pattern.trim()
    const tags = newRule.tags.split(';').map((x) => x.trim()).filter(Boolean)
    if (!pattern || !tags.length) { setMsg('Enter a pattern and at least one tag.'); return }
    try { new RegExp(pattern, 'i') } catch { setMsg('Invalid regex.'); return }
    const rules = [...(dict.rules || []), { pattern, tags, source: 'steward' }]
    // ensure the rule's tags exist in the vocabulary
    const allTags = [...(dict.tags || [])]
    tags.forEach((t) => {
      if (!allTags.some((x) => x.tag === t)) allTags.push({ tag: t, label: t, count: 0, examples: [] })
    })
    allTags.sort((a, b) => a.tag.localeCompare(b.tag))
    setDict({ ...dict, rules, rule_count: rules.length, tags: allTags, tag_count: allTags.length })
    setNewRule({ pattern: '', tags: '' })
    setMsg('Added rule — Save to persist.')
  }

  /* ---------- save / reseed / export ---------- */

  // summary rows → the raw dictionary document the save endpoint expects
  function toDoc() {
    const tags = {}
    ;(dict.tags || []).forEach((t) => {
      tags[t.tag] = { label: t.label || t.tag, layer: t.layer || 'company' }
      if (t.layer !== 'generic' && t.status && t.status !== 'generic') tags[t.tag].status = t.status
      if (t.sensitivity_floor) tags[t.tag].sensitivity_floor = t.sensitivity_floor
    })
    const terms = {}
    ;(dict.terms || []).forEach((t) => {
      terms[t.term] = {
        aliases: t.aliases || [], sensitivity: t.sensitivity || 'LOW',
        tags: t.tags || [], layer: t.layer || 'company',
      }
      if (t.layer !== 'generic' && t.status && t.status !== 'generic') terms[t.term].status = t.status
    })
    return {
      schema: dict.schema, domain: dict.domain, tags, terms,
      rules: dict.rules || [], category_tags: dict.category_tags || {},
    }
  }

  async function saveDict() {
    if (!dict) return
    setMsg('Saving…')
    try {
      const res = await apiPost('/api/tagdict', { dictionary: toDoc(), actor: actor.trim() })
      const w = res.warnings || []
      setDict(res)
      setWarnings(w)
      loadAudit()
      setMsg(w.length ? `Saved with ${w.length} guard-rail note${w.length > 1 ? 's' : ''}.` : 'Saved.')
    } catch (e) {
      setMsg(`Save failed: ${e.message}`)
    }
  }

  async function reset() {
    if (!window.confirm(
      'Reseed the tag dictionary from the domain pack + defaults?\n\n' +
      'Kept: steward-APPROVED company terms/tags and company rules (the governed set).\n' +
      'Discarded: PENDING scan-grown items and accreted usage counts.\n' +
      'A timestamped backup of the current dictionary file is taken first.')) return
    setMsg('Reseeding…')
    try {
      const d = await apiPost('/api/tagdict/reset', { actor: actor.trim() })
      setDict(d)
      loadAudit()
      const k = d.kept || {}
      setMsg(`Reseeded — preserved ${k.terms || 0} approved term(s), ${k.tags || 0} tag(s), ${k.rules || 0} rule(s).`)
    } catch (e) {
      setMsg(`Reset failed: ${e.message}`)
    }
  }

  /* ---------- domain-pack export (merge + conflict review + apply) ---------- */

  async function exportPack(apply, res = resolutions) {
    if (apply && !window.confirm(
      'Apply the refreshed pack to this app?\n\nThis overwrites the installed domain_pack.json ' +
      '(a timestamped backup is kept) and reseeds the dictionary from it. Approved company ' +
      'terms/tags and company rules SURVIVE the reseed; pending scan-noise is discarded.')) return
    try {
      const d = await apiPost('/api/export-pack', {
        rows: ws.rows || [], apply: !!apply, resolutions: res,
      })
      setPack(d)
      setMsg(null)
      if (d.applied) load()
    } catch (e) {
      setMsg(`Pack export failed: ${e.message}`)
    }
  }

  // tick a conflict row → take the scan's value; regenerate so download + Apply reflect it
  function packResolve(c, useScan) {
    const next = { ...resolutions, [`${c.key}::${c.name}`]: useScan ? 'scan' : 'pack' }
    setResolutions(next)
    exportPack(false, next)
  }

  /* ---------- derived views ---------- */

  if (loadErr) {
    return (
      <section className="card">
        <h2>Term &amp; Tag dictionary</h2>
        <div className="error">Failed to load the dictionary: {loadErr}</div>
        <div className="actions"><button className="ghost" onClick={load}>Retry</button></div>
      </section>
    )
  }
  if (!dict) return <p className="loading">Loading the governed vocabulary…</p>

  const pendingTerms = (dict.terms || []).filter((t) => t.status === 'pending')
  const pendingTags = (dict.tags || []).filter((t) => t.status === 'pending')
  const packVal = (x) => {
    const s = typeof x === 'string' ? x : JSON.stringify(x)
    return s.length > 80 ? `${s.slice(0, 77)}…` : s
  }
  const conflicts = pack?.report?.conflicts || []
  const reportBits = pack
    ? Object.entries(pack.report || {})
        .filter(([k, v]) => typeof v === 'number' && v > 0 && k !== 'scan_overrides')
        .map(([k, v]) => `${k} +${v}`)
        .join(' · ')
    : ''

  return (
    <>
      <div className="page-head">
        <h1>Term &amp; Tag dictionary</h1>
        <p className="psub">
          The company vocabulary that governs tagging and term naming — a <b>generic baseline</b>{' '}
          plus your <b>company layer</b>, grown from scans and steward-approved. It feeds the
          Registry, so the Policy Generator stays inside the same allow-list. Per-glossary term
          review stays on the{' '}
          <button className="nav" onClick={() => onNavigate('review')}>Review</button> page; this
          page governs the vocabulary those tags come from.
        </p>
      </div>

      <FlywheelExplainer />

      <section className="card">
        <header>
          <h2>Governed vocabulary <span>terms first, then the tag allow-list — both grow from your scans</span></h2>
          <label className="check">
            show
            <select value={rowsShown} onChange={(e) => setRows(parseInt(e.target.value, 10) || 7)}
                    title="Rows visible before the vocabulary tables scroll — remembered in this browser">
              <option>7</option><option>15</option><option>30</option><option>60</option>
            </select>
            rows
          </label>
        </header>
        <p className="summary">
          {dict.domain || '—'} · <b>{dict.term_count || 0}</b> terms ({dict.generic_terms || 0} generic,{' '}
          {dict.governed_terms || 0} governed) · <b>{dict.tag_count || 0}</b> tags ({dict.generic_tags || 0} generic,{' '}
          {dict.governed_tags || 0} governed) · <b>{dict.rule_count || 0}</b> rules
          {dict.sources?.length ? ` · grown from: ${dict.sources.join(', ')}` : ' · not yet grown from a scan'}
        </p>
        {warnings.length > 0 && (
          <div className="flag warn">
            <b>Guard-rails applied:</b>
            {warnings.map((w, i) => <div key={i}>· {w}</div>)}
          </div>
        )}

        {(pendingTerms.length > 0 || pendingTags.length > 0) && (
          <div className="pending-wrap">
            <b>Pending steward review</b>{' '}
            <span className="notes">new items found by scans — they don't govern the Registry until approved</span>
            {prog && (
              <>
                <div className="progress-track">
                  <div className="progress-bar" style={{ width: `${Math.round((prog.done / prog.total) * 100)}%` }} />
                </div>
                <p className="summary">
                  {cancelRef.current
                    ? 'Finishing current batch…'
                    : `AI reviewing pending terms — ${prog.done}/${prog.total} (${Math.round((prog.done / prog.total) * 100)}%)`}
                  {' '}
                  <button className="ghost mini" disabled={cancelRef.current}
                          onClick={() => { cancelRef.current = true }}>
                    Cancel
                  </button>
                </p>
              </>
            )}
            {pendingTerms.length > 0 && (
              <div style={{ marginTop: '.5rem' }}>
                <b>Terms ({pendingTerms.length})</b>{' '}
                <button className="ghost mini" onClick={() => approveAll('term')}>Approve all</button>{' '}
                <button className="ghost mini" onClick={aiReview} disabled={reviewing}
                        title="Advise per candidate: a deterministic near-duplicate check against the governed vocabulary, then the local AI judges the rest from the captured context (category, definition, sources). Advice only — you still click.">
                  {reviewing ? 'Reviewing…' : 'AI review'}
                </button>{' '}
                <span className="notes">approve only what belongs in the company vocabulary — reject scan noise</span>
                {pendingTerms.map((t) => {
                  const adv = advice[t.term]
                  const advLabel = adv
                    ? { approve: 'Approve', reject: 'Reject', alias: `Alias of ${adv.target || ''}` }[adv.action]
                    : ''
                  return (
                    <div className="pending-item" key={t.term}>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <b>{t.term}</b>
                        <span className="meta">
                          {[t.category ? `category ${t.category}` : '',
                            t.sensitivity ? `sensitivity ${t.sensitivity}` : '',
                            t.confidence ? `conf ${t.confidence}` : '',
                            t.tags?.length ? `tags ${t.tags.join('; ')}` : '',
                            t.sources?.length ? `seen in ${t.sources.join('; ')}` : '',
                          ].filter(Boolean).join(' · ')}
                        </span>
                        {t.definition && <div className="defn">{t.definition}</div>}
                        {adv && (
                          <div className="ai-line">
                            <span className="badge accent">AI</span> Recommended: <b>{advLabel}</b>
                            {adv.reason ? <> — {adv.reason}</> : null}
                          </div>
                        )}
                      </div>
                      {adv?.action === 'alias' && adv.target && (
                        <button className="ghost mini" title={`Fold into "${adv.target}" as an alias`}
                                onClick={() => alias(t.term, adv.target)}>
                          → alias
                        </button>
                      )}
                      <button className="ghost mini" title="Approve — starts governing"
                              onClick={() => review('term', [t.term], 'approve', undefined, `Approved term "${t.term}".`)}>
                        ✓
                      </button>
                      <button className="ghost mini" title="Reject — discard"
                              onClick={() => review('term', [t.term], 'reject', undefined, `Rejected term "${t.term}".`)}>
                        ✕
                      </button>
                    </div>
                  )
                })}
              </div>
            )}
            {pendingTags.length > 0 && (
              <div style={{ marginTop: '.5rem' }}>
                <b>Tags ({pendingTags.length})</b>{' '}
                <button className="ghost mini" onClick={() => approveAll('tag')}>Approve all</button>
                <div>
                  {pendingTags.map((t) => (
                    <span className="chip" key={t.tag}>
                      {t.tag}
                      <button className="ghost mini" title="Approve — starts governing"
                              onClick={() => review('tag', [t.tag], 'approve', undefined, `Approved tag "${t.tag}".`)}>
                        ✓
                      </button>
                      <button className="ghost mini" title="Reject — discard"
                              onClick={() => review('tag', [t.tag], 'reject', undefined, `Rejected tag "${t.tag}".`)}>
                        ✕
                      </button>
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        <h3 className="subhead">
          1 · Terms — canonical business terms; aliases resolve divergent names to one term{' '}
          <button className="ghost mini" onClick={foldAdvisor} disabled={foldBusy}
                  title="Advise alias folds across the governed vocabulary: names are expanded through the pack's abbreviations (mbr → Member) and compared by similarity — identical expansions are near-certain twins; close matches are flagged for review. The unabbreviated spelling is proposed as the canonical. Advice only — you click each fold.">
            {foldBusy ? 'Analyzing…' : 'AI fold advisor'}
          </button>
        </h3>
        <div className="vocab-box" style={boxStyle}>
          <table>
            <thead>
              <tr><th>Term</th><th>Layer</th><th>Sensitivity</th><th>Aliases</th><th>Tags</th><th className="num">Used</th></tr>
            </thead>
            <tbody>
              {(dict.terms || []).length === 0 && (
                <tr><td colSpan="6" className="notes">No terms yet.</td></tr>
              )}
              {(dict.terms || []).map((t) => (
                <tr key={t.term}>
                  <td>
                    <b>{t.term}</b>
                    {t.layer === 'company' && (
                      <span className="vocab-actions">
                        <button className="ghost mini"
                                title="Fold into another governed term — this name becomes an ALIAS of the target (durable across reseeds)"
                                onClick={() => termFold(t)}>
                          ⤵
                        </button>
                        <button className="ghost mini"
                                title="Retire from the governed vocabulary. Durable: a tombstone keeps it retired through reloads and Reseeds, and Export domain pack will offer to remove it from the installed pack. A future scan with real evidence can re-propose it as pending."
                                onClick={() => termRetire(t)}>
                          ✕
                        </button>
                      </span>
                    )}
                  </td>
                  <td><LayerBadge status={t.status} /></td>
                  <td><SevBadge s={t.sensitivity || 'LOW'} /></td>
                  <td className="notes">{(t.aliases || []).join('; ')}</td>
                  <td className="notes">{(t.tags || []).join('; ')}</td>
                  <td className="num">{t.count || 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {fold && (
          <div style={{ marginTop: '.5rem' }}>
            {fold.pairs.length === 0 && (
              <p className="summary">
                No fold candidates among the {fold.governed || 0} governed company terms — every
                name is distinct even after abbreviation expansion.
              </p>
            )}
            {fold.pairs.length > 0 && (
              <>
                <p className="summary">
                  <b>{fold.pairs.length} fold candidate(s)</b> — each click folds the twin into the
                  canonical term as an alias (durable; audit-logged).{' '}
                  {fold.pairs.filter((p) => p.confidence === 'high').length > 1 && (
                    <button className="ghost mini" onClick={foldAll}
                            title="Fold every HIGH-confidence pair (identical after abbreviation expansion) in one pass. Review-band suggestions are never included. Glance at the canonical names first — fold-all trusts the advisor's pick of which spelling survives; dismiss (✕) any pair whose canonical looks wrong before clicking.">
                      Fold all {fold.pairs.filter((p) => p.confidence === 'high').length} high-confidence
                    </button>
                  )}
                </p>
                {fold.pairs.map((p, i) => (
                  <div className="fold-row" key={`${p.fold}→${p.keep}`}>
                    <span className={`fold-conf ${p.confidence === 'high' ? 'high' : 'review'}`}>
                      {p.confidence === 'high' ? 'fold' : 'review'}
                    </span>
                    <span style={{ flex: 1 }}>
                      fold <b>{p.fold}</b> into <b>{p.keep}</b> <span className="notes">— {p.reason}</span>
                    </span>
                    <button className="ghost mini"
                            onClick={() => { alias(p.fold, p.keep); dismissPair(i) }}>
                      Fold ⤵
                    </button>
                    <button className="ghost mini" title="Dismiss this suggestion"
                            onClick={() => dismissPair(i)}>
                      ✕
                    </button>
                  </div>
                ))}
              </>
            )}
          </div>
        )}
        <div className="dict-inline-form">
          <label>
            Add term
            <input type="text" placeholder="e.g. Backflow Device ID" value={newTerm.name}
                   onChange={(e) => setNewTerm((v) => ({ ...v, name: e.target.value }))} />
          </label>
          <label>
            Sensitivity
            <select value={newTerm.sens} onChange={(e) => setNewTerm((v) => ({ ...v, sens: e.target.value }))}>
              <option>LOW</option><option>MEDIUM</option><option>HIGH</option>
            </select>
          </label>
          <label>
            Aliases <span className="muted">;-sep</span>
            <input type="text" placeholder="BFD ID;Backflow ID" value={newTerm.aliases}
                   onChange={(e) => setNewTerm((v) => ({ ...v, aliases: e.target.value }))} />
          </label>
          <label>
            Tags <span className="muted">;-sep</span>
            <input type="text" placeholder="asset;identifier" value={newTerm.tags}
                   onChange={(e) => setNewTerm((v) => ({ ...v, tags: e.target.value }))} />
          </label>
          <button className="ghost mini" onClick={addTerm}>Add term</button>
        </div>

        <h3 className="subhead">2 · Tags — the controlled allow-list tagging draws from</h3>
        <div className="vocab-box" style={boxStyle}>
          <table>
            <thead>
              <tr><th>Tag</th><th>Layer</th><th>Floor</th><th className="num">Used</th><th>Example terms</th></tr>
            </thead>
            <tbody>
              {(dict.tags || []).length === 0 && (
                <tr><td colSpan="5" className="notes">No tags yet.</td></tr>
              )}
              {(dict.tags || []).map((t) => (
                <tr key={t.tag}>
                  <td>
                    <b>{t.tag}</b>
                    {t.layer === 'company' && (
                      <span className="vocab-actions">
                        <button className="ghost mini"
                                title="Retire from the allow-list. Durable across reseeds (tombstoned); Export domain pack will offer to remove it from the pack. A rule that still emits it re-adds it with a warning."
                                onClick={() => tagRetire(t)}>
                          ✕
                        </button>
                      </span>
                    )}
                  </td>
                  <td><LayerBadge status={t.status} /></td>
                  <td>{t.sensitivity_floor ? <SevBadge s={t.sensitivity_floor} /> : <span className="notes">—</span>}</td>
                  <td className="num">{t.count || 0}</td>
                  <td className="notes">{(t.examples || []).join(', ')}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="dict-inline-form">
          <label>
            Add tag
            <input type="text" placeholder="e.g. chargeback" value={newTag.name}
                   onChange={(e) => setNewTag((v) => ({ ...v, name: e.target.value }))} />
          </label>
          <label>
            Sensitivity floor
            <select value={newTag.floor} onChange={(e) => setNewTag((v) => ({ ...v, floor: e.target.value }))}>
              <option value="">none</option><option>LOW</option><option>MEDIUM</option><option>HIGH</option>
            </select>
          </label>
          <button className="ghost mini" onClick={addTag}>Add tag</button>
        </div>

        <h3 className="subhead">3 · Rules — name/term regex patterns that emit governed tags automatically on every scan</h3>
        <div className="vocab-box" style={boxStyle}>
          <table>
            <thead>
              <tr><th>Pattern</th><th>Emits tags</th><th>Layer</th></tr>
            </thead>
            <tbody>
              {(dict.rules || []).length === 0 && (
                <tr><td colSpan="3" className="notes">No rules yet — add one below, or seed them from the domain pack.</td></tr>
              )}
              {(dict.rules || []).map((r, i) => (
                <tr key={i}>
                  <td><code>{r.pattern || ''}</code></td>
                  <td className="notes">{(r.tags || []).join('; ')}</td>
                  <td><LayerBadge status={r.layer === 'generic' ? 'generic' : 'approved'} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="dict-inline-form">
          <label>
            Rule pattern <span className="muted">regex on name/term</span>
            <input type="text" placeholder="chargeback|dispute|reversal" value={newRule.pattern}
                   onChange={(e) => setNewRule((v) => ({ ...v, pattern: e.target.value }))} />
          </label>
          <label>
            Rule tags <span className="muted">;-separated</span>
            <input type="text" placeholder="fraud;payments" value={newRule.tags}
                   onChange={(e) => setNewRule((v) => ({ ...v, tags: e.target.value }))} />
          </label>
          <button className="ghost mini" onClick={addRule}>Add rule</button>
        </div>

        <div className="actions">
          <label className="check" title="Recorded on every approve/reject and dictionary save in the governance audit trail.">
            Acting as
            <input type="text" placeholder="steward name" value={actor} style={{ width: '150px' }}
                   className="text" onChange={(e) => setActor(e.target.value)} />
          </label>
          <button className="primary" onClick={saveDict}>Save dictionary</button>
          <button className="ghost" onClick={load}>Reload</button>
          <a className="badge accent" href="/api/tagdict/export.json">⬇ Export JSON</a>
          <button className="ghost" onClick={() => exportPack(false)}
                  title="Generate a domain pack from what the scans learned: table mappings, abbreviations, the governed company vocabulary, and curated_seeds carrying the induced value patterns / reference lists — detection seeds specific to THIS company. Merges over the installed pack; where the scan disagrees with the pack, each conflict is listed for you to decide (curated seeds default to the fresher scan evidence). Review, then commit to the scenario repo.">
            Export domain pack
          </button>
          <button className="ghost" onClick={reset}
                  title="Reseed from the domain pack + built-in defaults. Approved company items and rules are kept; pending items are discarded; a backup file is taken first.">
            Reseed
          </button>
          {typeof msg === 'string' ? <span className="summary">{msg}</span> : msg}
        </div>

        {pack && (
          <div style={{ marginTop: '.8rem' }}>
            <p className="summary">
              Domain pack generated{pack.merged_over ? ' (merged over the installed pack)' : ''}:{' '}
              <b>{pack.learned}</b> learned addition(s){reportBits ? ` — ${reportBits}` : ''}
              {' '}
              <button className="ghost mini"
                      onClick={() => downloadBlob(JSON.stringify(pack.pack, null, 2), 'domain_pack.json')}>
                ⬇ download domain_pack.json
              </button>
              {!pack.applied && (
                <>
                  {' '}
                  <button className="ghost mini" onClick={() => exportPack(true)}>Apply to this app</button>{' '}
                  <span className="notes">writes the pack + reseeds the dictionary (approved items survive)</span>
                </>
              )}
              {(!ws.rows || !ws.rows.length) && (
                <span className="notes"> (no scan rows loaded — table mappings and curated seeds need a scanned glossary)</span>
              )}
            </p>
            {pack.applied && (
              <p className="summary ok">
                ✓ Applied: pack written to <code>{pack.pack_path || ''}</code>
                {pack.pack_backup ? ' (backup kept)' : ''} and the dictionary reseeded from it.
                Also commit the file to the scenario's domain_pack/ folder so the next install
                starts from it.
              </p>
            )}
            {conflicts.length > 0 && (
              <>
                <p className="summary">
                  <b>{conflicts.length} disagreement(s)</b> — the scan proposes a different value
                  than the installed pack. Tick a row to take the scan's value, untick to keep the
                  pack's (curated seeds default to the scan — they're machine-derived evidence,
                  fresher data wins):
                </p>
                <div className="conflict-list">
                  {conflicts.map((c, i) => (
                    <label key={`${c.key}::${c.name}`}>
                      <input type="checkbox"
                             checked={(resolutions[`${c.key}::${c.name}`] || c.use) === 'scan'}
                             onChange={(e) => packResolve(c, e.target.checked)} />
                      <span>
                        <code>{c.key}</code> · <b>{c.name}</b> — pack: <code>{packVal(c.pack)}</code>{' '}
                        → scan: <code>{packVal(c.scan)}</code>
                      </span>
                    </label>
                  ))}
                </div>
              </>
            )}
          </div>
        )}
      </section>

      <FacetCard dict={dict} onRetireEmpty={retireEmpty} />
      <AuditCard audit={audit} auditErr={auditErr} onRefresh={loadAudit} />
    </>
  )
}

/* ---------- the seed → flywheel explainer ---------- */

// How the dictionary grows — the domain-pack flywheel, told for stewards.
// Same collapsed-summary pattern as the Home page's "full working cycle"
// panel (details.card > summary + ol.workcycle), collapsed by default.
function FlywheelExplainer() {
  return (
    <details className="card">
      <summary>How the dictionary grows — seed, scan, export, flywheel</summary>
      <div className="fw-cycle" aria-hidden="true">
        <span className="fw-step">Seed<small>domain pack</small></span>
        <span className="fw-arrow">→</span>
        <span className="fw-step">Scan &amp; review<small>steward approves</small></span>
        <span className="fw-arrow">→</span>
        <span className="fw-step">Export<small>refreshed pack</small></span>
        <span className="fw-arrow">→</span>
        <span className="fw-step">Flywheel<small>apply · commit</small></span>
        <span className="fw-arrow loop" title="the refreshed pack seeds the next cycle">⟲</span>
      </div>
      <ol className="workcycle">
        <li>
          <b>Seed.</b> A hand-authored <b>domain pack</b> — a generic starter vocabulary for
          your industry — seeds the dictionary's <b>generic baseline</b> layer: starter terms,
          tag rules, category keywords and abbreviations. No pack installed? Fine — the
          built-in generic defaults still route the obvious columns.
        </li>
        <li>
          <b>Scan &amp; review.</b> Every scan learns from your <b>real data</b> — value
          patterns, reference lists, and candidate terms and tags arrive as <i>pending</i>.
          You approve what belongs into the <b>company layer</b>; rejected noise stays out
          (a real concept re-proposes itself on the next scan, with evidence).
        </li>
        <li>
          <b>Export.</b> <b>Export domain pack</b> (below) merges the reviewed state back
          into the pack: table mappings, learned abbreviations, the approved vocabulary, and{' '}
          <code>curated_seeds</code> carrying the induced regexes and reference lists. Where
          fresh scan evidence disagrees with the installed pack, each conflict is listed for
          you to decide — curated seeds default to the fresher scan; your durable retires
          default to removal from the pack.
        </li>
        <li>
          <b>Flywheel.</b> <b>Apply</b> the refreshed pack to this app and <b>commit</b> it
          to the scenario repo — every future install starts from evidence instead of
          guesses, and each cycle refines the pack further.
        </li>
      </ol>
      <p className="hint-line">
        Bootstrapping a new company? Run <b>packless</b>: one scan → review → export, and
        with no installed pack to merge over, that first export <i>is</i> your base pack.
      </p>
    </details>
  )
}

/* ---------- search facet preview + health flags ---------- */

function FacetCard({ dict, onRetireEmpty }) {
  const gov = (dict.tags || []).filter((t) => t.status === 'generic' || t.status === 'approved')
  const sorted = [...gov].sort((a, b) => (b.count || 0) - (a.count || 0))
  const max = Math.max(1, ...gov.map((t) => t.count || 0))
  const pendingCount = dict.pending_tags || 0

  // flags: empty governed tags + fragmenting near-duplicates
  const empties = sorted.filter((t) => (t.count || 0) === 0).map((t) => t.tag)
  const norm = (s) => s.toLowerCase().replace(/[^a-z0-9]/g, '')
  const groups = {}
  gov.forEach((t) => {
    const k = norm(t.tag)
    ;(groups[k] = groups[k] || []).push(t.tag)
  })
  const fragExact = Object.values(groups).filter((g) => g.length > 1)
  const names = gov.map((t) => t.tag)
  const fragNear = []
  const seen = new Set()
  for (let i = 0; i < names.length; i++) {
    for (let j = i + 1; j < names.length; j++) {
      const a = norm(names[i])
      const b = norm(names[j])
      if (a === b) continue
      if (Math.abs(a.length - b.length) <= 1 && Math.min(a.length, b.length) >= 4 && lev(a, b) === 1) {
        const key = [names[i], names[j]].sort().join('¦')
        if (!seen.has(key)) {
          seen.add(key)
          fragNear.push([names[i], names[j]])
        }
      }
    }
  }
  // only COMPANY tags can be retired (the generic baseline is protected), and only
  // once the dictionary has grown from a scan — freshly reseeded counters are all
  // zero by definition, and a retire is DURABLE, so the bulk button would invite
  // gutting the curated pack.
  const layerOf = {}
  ;(dict.tags || []).forEach((t) => { layerOf[t.tag] = t.layer })
  const companyEmpties = empties.filter((t) => layerOf[t] !== 'generic')
  const grown = !!(dict.sources && dict.sources.length)
  const fragments = [...fragExact.map((g) => g.join(' / ')), ...fragNear.map((p) => p.join(' / '))]

  return (
    <section className="card">
      <h2>Search facet preview <span>how your governed tags will look as OpenSearch facets</span></h2>
      <p className="hint-line">
        Each governed tag becomes a search facet in PDC (a filter on{' '}
        <code>attributes.tags.name</code>). This previews the bucket sizes from reviewed usage —
        so you can retire empty tags and fix fragmenting near-duplicates <b>before</b> methods
        deploy and the facet fills with divergent values. Terms filter cleanly on their own facet
        (<code>businessTerms.name</code>); tags are the cross-cutting one worth keeping tidy.
      </p>
      {gov.length === 0 && <p className="summary">No governed tags yet.</p>}
      {gov.length > 0 && (
        <>
          {fragments.length > 0 && (
            <div className="flag warn">
              <b>⚠ May fragment the facet</b> — these split into separate buckets a single filter
              won't merge: {fragments.map((p, i) => <code key={i} style={{ marginRight: '.4rem' }}>{p}</code>)}
              Consolidate to one tag (add the other as a rule that emits it).
            </div>
          )}
          {empties.length > 0 && (
            <div className="flag info">
              <b>{empties.length} governed tag{empties.length > 1 ? 's' : ''} with no reviewed usage</b>{' '}
              — empty facet bucket{empties.length > 1 ? 's' : ''}:{' '}
              {empties.slice(0, 12).map((t, i) => <code key={i} style={{ marginRight: '.4rem' }}>{t}</code>)}
              {empties.length > 12 ? '…' : ''}
              <br />
              "Usage" here is <b>reviewed usage inside this app</b> (accreted on every scan), not
              live PDC data — counts reset with a dictionary reseed and rebuild on the next
              scan+review. All tags empty usually just means "freshly reseeded". Retire only what
              stays empty after a full scan of every source.{' '}
              {companyEmpties.length > 0 && (grown
                ? (
                  <button className="ghost mini" onClick={() => onRetireEmpty(companyEmpties)}
                          title={`Remove the ${companyEmpties.length} empty COMPANY-layer tag(s) from the vocabulary. Durable (tombstoned across reseeds); Export domain pack will offer to remove them from the pack. The generic baseline can't be removed; a tag a rule still emits is re-added with a warning.`}>
                    Retire {companyEmpties.length} empty company tag{companyEmpties.length > 1 ? 's' : ''}
                  </button>
                )
                : (
                  <span className="notes">
                    (bulk retire appears after the dictionary has grown from a scan — freshly
                    reseeded counters are all zero and prove nothing)
                  </span>
                ))}
            </div>
          )}
          {fragments.length === 0 && empties.length === 0 && (
            <div className="flag ok">✓ No empty or fragmenting governed tags — the facet looks clean.</div>
          )}
          <div style={{ maxHeight: '300px', overflow: 'auto' }}>
            {sorted.map((t) => {
              const c = t.count || 0
              const empty = c === 0
              return (
                <div className="facet-row" key={t.tag}>
                  <div className={`facet-name${empty ? ' empty' : ''}`} title={(t.examples || []).join(', ')}>
                    {t.tag}
                    {t.sensitivity_floor && <> <SevBadge s={t.sensitivity_floor} /></>}
                  </div>
                  <div className="facet-track">
                    <div className={`facet-fill${empty ? ' empty' : ''}`}
                         style={{ width: `${empty ? 2 : Math.round((c / max) * 100)}%` }} />
                  </div>
                  <div className="facet-count">{empty ? 'empty' : `${c} ${c === 1 ? 'term' : 'terms'}`}</div>
                </div>
              )
            })}
          </div>
          {pendingCount > 0 && (
            <p className="summary">
              <b>{pendingCount}</b> pending tag{pendingCount > 1 ? 's are' : ' is'} not in the facet
              yet — approve above to include {pendingCount > 1 ? 'them' : 'it'}.
            </p>
          )}
        </>
      )}
    </section>
  )
}

/* ---------- governance audit trail ---------- */

function AuditCard({ audit, auditErr, onRefresh }) {
  return (
    <section className="card">
      <header>
        <h2>Governance audit trail <span>who changed the vocabulary, and when</span></h2>
        <div className="actions" style={{ marginTop: 0 }}>
          <button className="ghost mini" onClick={onRefresh}>Refresh</button>
          <a className="badge accent" href="/api/audit/export.json">⬇ Export audit JSON</a>
        </div>
      </header>
      <p className="hint-line">
        An append-only record of dictionary saves and pending approve/reject decisions —
        timestamp and actor on each. A compact summary is embedded in the Registry at export, so
        the governed vocabulary carries its own provenance to the Policy Generator. Set{' '}
        <b>Acting as</b> above so entries are attributed.
      </p>
      {auditErr && <div className="error">Failed to load audit: {auditErr}</div>}
      {!audit && !auditErr && <p className="loading">Loading…</p>}
      {audit && (
        <>
          <div className="table-scroll" style={{ maxHeight: '280px', overflowY: 'auto' }}>
            <table>
              <thead>
                <tr><th>When (UTC)</th><th>Actor</th><th>Action</th><th>Detail</th></tr>
              </thead>
              <tbody>
                {(audit.entries || []).length === 0 && (
                  <tr><td colSpan="4" className="notes">No governance actions recorded yet.</td></tr>
                )}
                {(audit.entries || []).map((e, i) => (
                  <tr key={i}>
                    <td className="notes" style={{ whiteSpace: 'nowrap' }}>
                      {(e.ts || '').replace('T', ' ').replace(/(\+00:00|Z)$/, '')}
                    </td>
                    <td><b>{e.actor || ''}</b></td>
                    <td><code>{e.action || ''}</code></td>
                    <td className="notes" style={{ wordBreak: 'break-word' }}>
                      {Object.keys(e)
                        .filter((k) => !['ts', 'actor', 'action'].includes(k))
                        .map((k) => `${k}: ${Array.isArray(e[k]) ? e[k].join(', ') : e[k]}`)
                        .join(' · ')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {audit.summary?.count > 0 && (
            <p className="summary">
              {audit.summary.count} entr{audit.summary.count === 1 ? 'y' : 'ies'} total.
            </p>
          )}
        </>
      )}
    </section>
  )
}
