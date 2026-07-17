import { useEffect, useRef, useState } from 'react'
import { apiGet, apiPost, apiDelete, runJob } from './../api.js'
import { getWorkspace, setRows, setDiscovery, setPdcSession, useWorkspace } from './../state.js'
import './connect.css'

// Connect page — the React port of the old UI's Connections page: the PDC
// bulk loader, harvest-from-PDC, the saved-connection manager (database /
// MinIO-S3 / DDL), read-only scans that seed the review grid, and deeper
// discovery profiling. The schema browser (PK/FK apply-keys) and the S3
// object browser live on their own child pages — SchemaPage / FilesPage.

/* ---------- small shared helpers ---------- */

const fmtBytes = (b) => {
  if (b == null) return '—'
  const u = ['B', 'KB', 'MB', 'GB', 'TB']
  let i = 0
  let n = Number(b) || 0
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++ }
  return (i ? n.toFixed(n < 10 ? 1 : 0) : n) + ' ' + u[i]
}

const pct = (x) => Math.round((x || 0) * 100) + '%'

const rowKey = (r) => `${r.Category}|${String(r.Term || '').toLowerCase()}`

// Merge scanned/harvested rows into the shared workspace, deduping on
// Category|Term exactly like the old UI's "Add to glossary" path.
function mergeIntoWorkspace(newRows) {
  const cur = getWorkspace().rows
  if (!cur.length) {
    setRows(newRows)
    return { added: newRows.length, dup: 0 }
  }
  const have = new Set(cur.map(rowKey))
  const out = [...cur]
  let added = 0
  let dup = 0
  for (const nr of newRows) {
    const k = rowKey(nr)
    if (have.has(k)) { dup++; continue }
    have.add(k)
    out.push(nr)
    added++
  }
  setRows(out)
  return { added, dup }
}

// POST /api/scan body for a saved connection (same dispatch as the old UI).
function scanBody(c) {
  if (c.type === 'db') return { source: 'db', conn: c.config }
  if (c.type === 'minio') return { source: 'minio', minio: c.config }
  return { source: 'ddl', ddl_path: (c.config || {}).path }
}

function connDetail(c) {
  const f = c.config || {}
  if (c.type === 'db') return `${f.engine} · ${f.host}:${f.port}/${f.database} · ${f.user}`
  if (c.type === 'minio') return `${f.endpoint}/${f.bucket}${f.prefix ? '/' + f.prefix : ''}`
  return f.path || ''
}

const CONN_TYPE_LABEL = { db: 'Database', minio: 'Document store', ddl: 'DDL file' }

// The backend's reusable "result + verdict" check shape:
// {title, tone: ok|warn|bad, rows:[{label,value}], issues:[{tone,text}], verdict}
function CheckPanel({ check }) {
  if (!check) return null
  const icon = check.tone === 'bad' ? '✕' : check.tone === 'warn' ? '⚠' : '✓'
  return (
    <div className={`chk ${check.tone || 'ok'}`}>
      <div className="chk-title">{icon} {check.title || 'Check'}</div>
      {check.rows?.length > 0 && (
        <div className="chk-rows">
          {check.rows.map((r) => <span key={r.label}><b>{r.label}:</b> {String(r.value)}</span>)}
        </div>
      )}
      {(check.issues || []).map((i, n) => (
        <div key={n} className={`chk-issue ${i.tone === 'bad' ? 'bad' : 'warn'}`}>{i.text}</div>
      ))}
      {check.verdict && <div className="verdict">{check.verdict}</div>}
    </div>
  )
}

function MiniBar({ frac }) {
  return <span className="mini"><i style={{ width: pct(frac) }} /></span>
}

// Escape-to-close modal shell on the shared .modal-* classes.
function Modal({ title, wide, onClose, children }) {
  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className={`modal${wide ? ' wide' : ''}`} role="dialog" aria-modal="true"
           onClick={(e) => e.stopPropagation()}>
        <header>
          <h3>{title}</h3>
          <button className="ghost" onClick={onClose} aria-label="Close">✕</button>
        </header>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  )
}

/* ================================================================== */

export default function ConnectPage({ onNavigate }) {
  const ws = useWorkspace()
  const [conns, setConns] = useState(null)
  const [connsError, setConnsError] = useState(null)
  // One PDC sign-in shared by the bulk loader, harvest and the glossary check
  // (the old UI duplicated these fields per card; the token is never persisted).
  const [pdc, setPdc] = useState({ base: '', user: '', pass: '', token: '', ver: 'v2', verify: false })
  const [editing, setEditing] = useState(null)      // connection being edited in the form
  const [profile, setProfile] = useState(null)      // {name, data} from /api/discover
  const [docs, setDocs] = useState(null)            // {connId, name, data} from /api/discover-docs
  const formRef = useRef(null)

  const refreshConns = () =>
    apiGet('/api/connections')
      .then((b) => setConns(b.connections ?? []))
      .catch((e) => { setConns([]); setConnsError(e.message) })

  useEffect(() => {
    refreshConns()
    // Prefill the PDC base URL from settings (same fallback the old UI used).
    apiGet('/api/settings')
      .then((s) => { if (s.pdc_base) setPdc((p) => (p.base ? p : { ...p, base: s.pdc_base })) })
      .catch(() => {})
  }, [])

  async function discoverDb(conn) {
    const d = await apiPost('/api/discover', { conn: conn.config })
    setProfile({ name: conn.name, data: d })
    setDiscovery(d) // captured with the glossary — the workspace's discovery profile
    return d
  }

  async function discoverDocs(conn, include = '', exclude = '') {
    const d = await apiPost('/api/discover-docs', {
      conn: { ...conn.config, include, exclude },
    })
    setDocs({ connId: conn.id, name: conn.name, data: d })
    return d
  }

  function startEdit(conn) {
    setEditing(conn)
    formRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return (
    <>
      <div className="page-head">
        <h1>Connect</h1>
        <p className="psub">
          Each data source is its own saved connection. Scan one to start a glossary,
          then <b>Add to glossary</b> from others to span structured and unstructured sources.
          {ws.rows.length > 0 && <> Loaded now: <b>{ws.rows.length}</b> candidate term(s).</>}
        </p>
      </div>

      <BulkLoadCard pdc={setPdcProxy(pdc, setPdc)} onConnectionsChanged={setConns} />
      <HarvestCard pdc={setPdcProxy(pdc, setPdc)} onConnectionsChanged={refreshConns}
                   onNavigate={onNavigate} glossaryName={ws.glossaryName} />

      <div ref={formRef}>
        <ConnectionForm editing={editing} onCancel={() => setEditing(null)}
                        onSaved={(list) => { setConns(list); setEditing(null) }} />
      </div>

      <ConnectionCards conns={conns} error={connsError} onNavigate={onNavigate}
                       onEdit={startEdit} onChanged={setConns}
                       onDiscoverDb={discoverDb} onDiscoverDocs={discoverDocs} />

      {profile && <ProfilePanel profile={profile} onNavigate={onNavigate} />}
      {docs && (
        <DocsPanel docs={docs}
                   onRefilter={(inc, exc) => {
                     const c = (conns || []).find((x) => x.id === docs.connId)
                     return c ? discoverDocs(c, inc, exc) : Promise.resolve()
                   }} />
      )}
    </>
  )
}

// Bundle the auth state + setter so the two PDC cards share one sign-in.
function setPdcProxy(pdc, setPdc) {
  return { ...pdc, set: (patch) => setPdc((p) => ({ ...p, ...patch })) }
}

// The request body every /api/pdc/* endpoint expects.
function pdcAuthBody(pdc) {
  return {
    base_url: pdc.base.trim(), username: pdc.user, password: pdc.pass,
    token: pdc.token.trim(), version: (pdc.ver || 'v2').trim(),
    realm: 'pdc', verify_tls: pdc.verify,
  }
}

function pdcAuthReady(pdc) {
  if (!pdc.base.trim()) return 'Enter your PDC base URL.'
  if (!(pdc.token.trim() || (pdc.user && pdc.pass)))
    return 'Enter a PDC username and password, or paste a bearer token.'
  return null
}

function PdcAuthFields({ pdc }) {
  return (
    <>
      <div className="form-grid">
        <label>
          PDC base URL
          <input type="text" placeholder="https://192.168.1.200 (server root)"
                 value={pdc.base} onChange={(e) => pdc.set({ base: e.target.value })} />
        </label>
        <label>
          Username
          <input type="text" autoComplete="off" value={pdc.user}
                 onChange={(e) => pdc.set({ user: e.target.value })} />
        </label>
        <label>
          Password
          <input type="password" autoComplete="new-password" value={pdc.pass}
                 onChange={(e) => pdc.set({ pass: e.target.value })} />
        </label>
        <label>
          API version
          <select value={pdc.ver} onChange={(e) => pdc.set({ ver: e.target.value })}>
            <option>v2</option><option>v3</option><option>v1</option>
          </select>
        </label>
        <label className="check" style={{ alignSelf: 'end', paddingBottom: '.45rem' }}>
          <input type="checkbox" checked={pdc.verify}
                 onChange={(e) => pdc.set({ verify: e.target.checked })} /> Verify TLS
        </label>
      </div>
      <div className="form-grid" style={{ marginTop: '.8rem' }}>
        <label style={{ gridColumn: '1 / -1' }}>
          Bearer token <span className="muted">optional — use instead of username / password</span>
          <input type="text" autoComplete="off" placeholder="eyJhbGciOi…" value={pdc.token}
                 onChange={(e) => pdc.set({ token: e.target.value })} />
        </label>
      </div>
    </>
  )
}

/* ================= PDC bulk connection loader ================= */

const BL_BADGE = {
  OK: 'good', RECREATED: 'good', EXISTS: 'accent',
  DRY: 'neutral', SKIP: 'neutral', SENT: 'warning', FAIL: 'serious',
}

function BulkLoadCard({ pdc, onConnectionsChanged }) {
  const [csv, setCsv] = useState('')
  const [opts, setOpts] = useState({ ingest: true, replace: false, internal: false })
  const [msg, setMsg] = useState('')
  const [running, setRunning] = useState(false)
  const [progress, setProgress] = useState(null)   // {done, total}
  const [table, setTable] = useState(null)          // {dryRun, rows: {index: result}}
  const [inspectName, setInspectName] = useState('')
  const [inspectOut, setInspectOut] = useState(null)
  const [importPanel, setImportPanel] = useState(false)
  const fileRef = useRef(null)

  function loadFile(file) {
    if (!file) return
    const r = new FileReader()
    r.onload = () => setCsv(String(r.result || ''))
    r.readAsText(file)
  }

  // Export the app's saved connections as a loader-ready CSV: fill the box and
  // download it. Raw fetch: the endpoint answers text/csv, not JSON.
  async function exportExisting() {
    setMsg('Exporting your saved connections…')
    try {
      const res = await fetch('/api/connections/export.csv')
      if (!res.ok) {
        const e = await res.json().catch(() => ({}))
        throw new Error(e.error || `HTTP ${res.status}`)
      }
      const text = await res.text()
      const n = text.split(/\r?\n/).filter((l) => l.trim()).length - 1
      setCsv(text)
      const a = document.createElement('a')
      a.href = URL.createObjectURL(new Blob([text], { type: 'text/csv' }))
      a.download = 'connections.csv'
      document.body.appendChild(a); a.click(); a.remove()
      setMsg(n > 0
        ? `Exported ${n} saved connection(s) — CSV filled above and downloaded (includes credentials, treat as sensitive).`
        : 'No saved connections to export yet — build one in the New connection panel below first.')
    } catch (err) {
      setMsg(`Export failed: ${err.message}`)
    }
  }

  async function inspect() {
    setInspectOut('Reading PDC…')
    try {
      const d = await apiPost('/api/pdc/source-config', {
        ...pdcAuthBody(pdc), resource_name: inspectName.trim(),
      })
      setInspectOut(d.count ? JSON.stringify(d.sources, null, 2)
        : 'No matching source — check the name (or leave blank to list all).')
    } catch (err) {
      setInspectOut(`Failed: ${err.message}`)
    }
  }

  // Run the loader through the background-job twin of /api/pdc/bulk-load:
  // POST /api/jobs/bulk-load → poll; each NDJSON event lands in job.events.
  async function run(dry) {
    if (!pdc.base.trim()) { setMsg('PDC base URL is required.'); return }
    if (!csv.trim()) { setMsg('Paste or choose a CSV first.'); return }
    setRunning(true)
    setTable({ dryRun: dry, rows: {} })
    setProgress({ done: 0, total: 0 })
    setMsg(dry ? 'Building payloads…' : 'Loading… creating, testing and ingesting each source.')
    const payload = {
      ...pdcAuthBody(pdc), csv, dry_run: !!dry,
      options: { ingest: opts.ingest, wait: true, replace_existing: opts.replace, internal_scan: opts.internal },
    }
    try {
      const result = await runJob('bulk-load', payload, (job) => {
        setProgress({ done: job.done, total: job.total })
        const rows = {}
        for (const ev of job.events || []) {
          if (ev.event === 'row_start') rows[ev.index] ??= { resourceName: ev.resourceName, working: true }
          else if (ev.event === 'row') rows[ev.index] = ev.result
        }
        setTable({ dryRun: dry, rows })
      })
      setMsg(result?.dry_run
        ? `Dry run complete — ${result.total} payload(s) built, nothing sent.`
        : `Done — ${result?.ok ?? 0} ok, ${result?.failed ?? 0} failed of ${result?.total ?? 0}.`)
    } catch (err) {
      setMsg(`Error: ${err.message}`)
    } finally {
      setRunning(false)
      setProgress(null)
    }
  }

  const rowIdx = table ? Object.keys(table.rows).map(Number).sort((a, b) => a - b) : []

  return (
    <section className="card">
      <h2>Bulk-load data sources into PDC <span>setup step — runs before the glossary</span></h2>
      <p className="hint-line">
        Register many sources in PDC at once from a CSV. For each row the app <b>creates</b> the
        data source, then triggers a <b>metadata ingest</b> scoped to it and waits for the job.
        Use <code>kind</code> = <code>postgres</code>, <code>mysql</code>, <code>oracle</code>,{' '}
        <code>minio</code>/<code>s3</code> or <code>azure_blob</code>. Secrets are sent to PDC only
        and never saved by the app. A source that already exists shows as{' '}
        <span className="badge accent">EXISTS</span> — re-scanned, not re-created.
      </p>
      <p className="hint-line">
        Ingests that report OK but find nothing: set <code>schemaNames</code> to the schema your
        tables actually live in; object stores need <code>container</code>, a reachable{' '}
        <code>endpoint</code> and files in the bucket. Scope scans with{' '}
        <code>includePatterns</code>/<code>excludePatterns</code> (semicolon-separated globs).
      </p>

      <PdcAuthFields pdc={pdc} />

      <div className="form-grid" style={{ marginTop: '.8rem' }}>
        <label style={{ gridColumn: '1 / -1' }}>
          CSV <span className="muted">paste rows, or choose a file (e.g. the shipped datasources.csv)</span>
          <textarea className="csv-box" rows={5} spellCheck={false} value={csv}
                    onChange={(e) => setCsv(e.target.value)}
                    placeholder="kind,resourceName,host,port,databaseName,userName,password,endpoint,accessKey,secretKey,container,path,schemaNames,description" />
        </label>
      </div>

      <div className="actions">
        <button className="ghost" onClick={() => fileRef.current?.click()}>Choose CSV file…</button>
        <input ref={fileRef} type="file" accept=".csv" style={{ display: 'none' }}
               onChange={(e) => { loadFile(e.target.files[0]); e.target.value = '' }} />
        <button className="ghost" onClick={exportExisting}
                title="Turn the connections you saved by hand into a loader-ready CSV — credentials included.">
          Export existing ↓
        </button>
        <button className="ghost" onClick={() => setImportPanel(true)}
                title="Import this CSV into the app's own connections — the ones the Test and live-scan panels here and the Schema and Files pages use.">
          Add to app connections
        </button>
        <label className="check"><input type="checkbox" checked={opts.ingest}
               onChange={(e) => setOpts({ ...opts, ingest: e.target.checked })} /> ingest metadata</label>
        <label className="check" title="If a source already exists in PDC, delete and recreate it so corrected CSV values take effect.">
          <input type="checkbox" checked={opts.replace}
                 onChange={(e) => setOpts({ ...opts, replace: e.target.checked })} /> recreate if exists</label>
        <label className="check" title="EXPERIMENTAL: scan object stores via PDC's internal /api/start-job endpoint — not part of the public API.">
          <input type="checkbox" checked={opts.internal}
                 onChange={(e) => setOpts({ ...opts, internal: e.target.checked })} /> scan object stores (internal API ⚠)</label>
        <span style={{ flex: 1 }} />
        <button className="ghost" disabled={running} onClick={() => run(true)}>Dry run</button>
        <button className="primary" disabled={running} onClick={() => run(false)}>Create &amp; ingest →</button>
      </div>

      {msg && <p className="summary">{msg}</p>}
      {progress && progress.total > 0 && (
        <div className="progress-track">
          <div className="progress-bar" style={{ width: `${Math.round((progress.done / progress.total) * 100)}%` }} />
        </div>
      )}

      {table && rowIdx.length > 0 && (
        <div className="table-scroll" style={{ marginTop: '.8rem' }}>
          <table>
            <thead><tr><th>Resource</th><th>create</th><th>ingest</th><th>job</th><th>note</th></tr></thead>
            <tbody>
              {rowIdx.map((i) => {
                const r = table.rows[i]
                return (
                  <tr key={i}>
                    <td>{r.resourceName || ''}</td>
                    {r.working
                      ? <td colSpan={3} className="notes">working…</td>
                      : ['create', 'ingest', 'job'].map((k) => (
                          <td key={k}>{r[k]
                            ? <span className={`badge ${BL_BADGE[r[k]] || 'neutral'}`}>{r[k]}</span>
                            : <span className="notes">—</span>}</td>
                        ))}
                    <td className="notes">{r.note || r.error || ''}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}

      <div className="actions" style={{ marginTop: '1rem' }}>
        <span className="muted" style={{ fontSize: '.82rem' }}>Diagnose object-store type:</span>
        <input type="text" className="text" placeholder="a working source name (blank = all)"
               value={inspectName} onChange={(e) => setInspectName(e.target.value)}
               style={{ flex: '0 1 260px' }} />
        <button className="ghost" onClick={inspect}
                title="Create one source by hand in the PDC UI, then read its stored databaseType / serviceType / fileSystemType here — the exact values the loader must send. Secrets redacted.">
          Inspect PDC source config
        </button>
      </div>
      {inspectOut != null && <pre className="inspect-out">{inspectOut}</pre>}

      {importPanel && (
        <ImportCsvPanel csv={csv} onClose={() => setImportPanel(false)}
                        onImported={(list, added, updated) => {
                          onConnectionsChanged(list)
                          setImportPanel(false)
                          setMsg(`Added ${added}, updated ${updated} app connection(s) — now usable by the live scans below and the Schema and Files pages.`)
                        }} />
      )}
    </section>
  )
}

// "Add to app connections": preview the loader CSV as app-connection candidates
// (POST /api/connections/import-csv {preview:true}), let the user remap
// Docker-internal hosts/ports and tick which to import, then import.
function ImportCsvPanel({ csv, onClose, onImported }) {
  const [cands, setCands] = useState(null)
  const [sel, setSel] = useState(new Set())
  const [query, setQuery] = useState('')
  const [remap, setRemap] = useState('')
  const [msg, setMsg] = useState(null)
  const remapTimer = useRef(null)

  async function preview(remapVal, keepSel) {
    if (!csv.trim()) { setMsg('Paste or choose a CSV first (the same one you bulk-load).'); return }
    try {
      const d = await apiPost('/api/connections/import-csv', { csv, preview: true, remap: remapVal })
      const list = d.candidates || []
      setCands(list)
      if (!keepSel) setSel(new Set(list.filter((c) => c.ok).map((c) => c.name)))
      setMsg(`${d.count} connection(s) — set a reachability remap if the app runs outside Docker, tick which to import.`)
    } catch (err) {
      setMsg(err.message)
    }
  }

  useEffect(() => { preview('', false) }, [])   // eslint-disable-line react-hooks/exhaustive-deps

  function onRemap(v) {
    setRemap(v)
    clearTimeout(remapTimer.current)
    remapTimer.current = setTimeout(() => preview(v, true), 300)
  }

  const shown = (cands || []).filter((c) =>
    !query || `${c.name} ${c.type || ''} ${c.summary || ''}`.toLowerCase().includes(query.toLowerCase()))

  function toggleAll(on) {
    const next = new Set(sel)
    shown.filter((c) => c.ok).forEach((c) => { on ? next.add(c.name) : next.delete(c.name) })
    setSel(next)
  }

  async function importSelected() {
    if (!sel.size) { setMsg('Tick at least one connection to import.'); return }
    try {
      const d = await apiPost('/api/connections/import-csv', { csv, only: [...sel], remap })
      onImported(d.connections || [], d.added ?? 0, d.updated ?? 0)
    } catch (err) {
      setMsg(err.message)
    }
  }

  return (
    <Modal title="Import into app connections" onClose={onClose}>
      <p className="hint-line">
        Tick which to add — these become the app's own saved connections, used by the
        Test and live-scan panels here and the Schema and Files pages. Separate from
        PDC registration.
      </p>
      <div className="list-tools">
        <label className="field" style={{ flex: 1 }} title="Rewrite Docker-internal hosts/ports to addresses reachable from where the app runs. The PDC-side CSV is unchanged.">
          App reachability remap
          <input type="text" placeholder="cscu-postgres=localhost, 5432=5433" value={remap}
                 onChange={(e) => onRemap(e.target.value)} className="text" />
        </label>
      </div>
      <div className="list-tools">
        <input type="text" placeholder="Filter…" value={query} onChange={(e) => setQuery(e.target.value)} />
        <label className="check">
          <input type="checkbox" onChange={(e) => toggleAll(e.target.checked)} /> All shown
        </label>
        <span className="muted" style={{ fontSize: '.8rem' }}>
          {sel.size ? `${sel.size} selected` : 'none selected'}
        </span>
      </div>
      {cands == null && <p className="loading">Reading the CSV…</p>}
      {cands != null && (
        <div className="src-list">
          {shown.map((c) => (
            <label key={c.name} className={`src-row${c.ok ? '' : ' off'}`} style={{ cursor: c.ok ? 'pointer' : 'default' }}>
              <input type="checkbox" disabled={!c.ok} checked={sel.has(c.name)}
                     onChange={(e) => {
                       const next = new Set(sel)
                       e.target.checked ? next.add(c.name) : next.delete(c.name)
                       setSel(next)
                     }} />
              <span className="src-name"><b>{c.name}</b>{c.type && <span className="muted"> {c.type}</span>}</span>
              <span className="src-fqdn" title={c.summary || c.reason || ''}>
                {c.ok ? (c.summary || '') : `skip — ${c.reason || ''}`}
              </span>
            </label>
          ))}
          {shown.length === 0 && <p className="hint-line" style={{ padding: '.6rem' }}>No matches.</p>}
        </div>
      )}
      {msg && <p className="summary">{msg}</p>}
      <div className="actions">
        <button className="primary" onClick={importSelected}>Import selected →</button>
        <button className="ghost" onClick={onClose}>Cancel</button>
      </div>
    </Modal>
  )
}

/* ================= Harvest from PDC ================= */

const hvKey = (s) => s.fqdn || s.id

function HarvestCard({ pdc, onConnectionsChanged, onNavigate, glossaryName }) {
  const [sources, setSources] = useState(null)
  const [sel, setSel] = useState(new Set())
  const [query, setQuery] = useState('')
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)
  const [notes, setNotes] = useState({})       // per-source status: key -> {tone, text}
  const [scanCards, setScanCards] = useState([])  // pdc_summary result cards
  const [glossName, setGlossName] = useState('')
  const [glossMsg, setGlossMsg] = useState('')

  const note = (k, tone, text) => setNotes((n) => ({ ...n, [k]: { tone, text } }))

  async function listSources() {
    const bad = pdcAuthReady(pdc)
    if (bad) { setMsg(bad); return }
    setMsg('Reading PDC catalog for sources…')
    setBusy(true)
    try {
      const d = await apiPost('/api/pdc/data-sources', pdcAuthBody(pdc))
      // an authenticated catalog read is proof of connectivity — sidebar PDC dot
      setPdcSession({ base: pdc.base.trim(), user: pdc.user })
      setSources(d.data_sources || [])
      setSel(new Set())
      setNotes({})
      setMsg(d.count
        ? `PDC has ${d.count} schema/source(s). Filter, tick the ones you want, and harvest — no re-created connections, no secrets.`
        : 'PDC returned no schemas — has the source been scanned/ingested?')
    } catch (err) {
      setMsg(`Could not read the catalog: ${err.message}`)
    } finally {
      setBusy(false)
    }
  }

  async function testSource(s) {
    const k = hvKey(s)
    note(k, '', 'Testing…')
    try {
      const d = await apiPost('/api/pdc/source-test', {
        ...pdcAuthBody(pdc), data_source_id: s.fqdn || s.id, data_source_name: s.name || s.id,
      })
      note(k, d.ok ? 'good' : 'bad', (d.ok ? '✓ ' : '⚠ ') + (d.message || d.error || 'no response'))
    } catch (err) {
      note(k, 'bad', `Test failed: ${err.message}`)
    }
  }

  // PDC source -> saved app connection (prefills everything except the secret;
  // re-adding an existing connection keeps its saved secret).
  async function toConnection(s) {
    const k = hvKey(s)
    note(k, '', 'Reading the PDC record…')
    try {
      const d = await apiPost('/api/pdc/source-to-connection', {
        ...pdcAuthBody(pdc), data_source_name: s.name || s.id,
      })
      onConnectionsChanged()
      const bits = [`✓ ${d.updated ? 'updated' : 'saved'} as app connection "${d.connection.name}"`]
      if (d.kept_secret) bits.push('kept your saved secret')
      else if (d.needs) bits.push(`set the ${d.needs} on its card below — or import your loader CSV (Bulk loader → Add to app connections), which carries the credentials`)
      if (d.warning) bits.push(d.warning)
      note(k, 'good', bits.join(' · '))
    } catch (err) {
      note(k, 'bad', `Failed: ${err.message}`)
    }
  }

  async function harvestOne(s, collectCards) {
    const k = hvKey(s)
    note(k, '', 'Harvesting…')
    const d = await apiPost('/api/pdc/harvest', {
      ...pdcAuthBody(pdc), data_source_id: s.fqdn || s.id, data_source_name: s.name || s.id,
    })
    if (d.pdc_summary) collectCards.push(d.pdc_summary)
    const { added } = mergeIntoWorkspace(d.rows || [])
    const gov = d.scanned?.already_governed || 0
    note(k, 'good', `✓ added ${added} term(s)${gov ? ` · ${gov} already governed in PDC` : ''}`)
    return { added, gov }
  }

  async function harvestSelected() {
    const chosen = (sources || []).filter((s) => sel.has(hvKey(s)))
    if (!chosen.length) { setMsg('Tick one or more sources to harvest.'); return }
    setBusy(true)
    const cards = []
    const failed = []
    let added = 0
    let gov = 0
    let done = 0
    for (const s of chosen) {
      setMsg(`Harvesting "${s.name || s.id}" (${done + 1}/${chosen.length})…`)
      try {
        const r = await harvestOne(s, cards)
        added += r.added; gov += r.gov
      } catch (err) {
        failed.push(`${s.name || s.id}: ${err.message}`)
        note(hvKey(s), 'bad', err.message)
      }
      done++
    }
    setScanCards(cards)
    setBusy(false)
    setMsg(`Harvested ${added} new term(s) from ${chosen.length - failed.length} source(s)` +
      (gov ? ` · ${gov} already governed in PDC` : '') +
      (failed.length ? ` — ${failed.length} failed: ${failed.join('; ').slice(0, 300)}` : '') +
      '. Review them on the Review page.')
  }

  async function checkGlossary() {
    const name = (glossName || glossaryName || '').trim()
    if (!name) { setGlossMsg('Enter a glossary name first.'); return }
    const bad = pdcAuthReady(pdc)
    if (bad) { setGlossMsg(bad); return }
    setGlossMsg('Checking PDC…')
    try {
      const d = await apiPost('/api/pdc/glossary-exists', { ...pdcAuthBody(pdc), glossary_name: name })
      setPdcSession({ base: pdc.base.trim(), user: pdc.user }) // authenticated round-trip succeeded
      if (d.exact) setGlossMsg(`⚠ A glossary named "${d.name}" already exists in PDC — importing creates a duplicate. Update it in place instead.`)
      else if (d.exists) setGlossMsg(`A similar glossary exists in PDC: "${d.name}". Your name differs, so import will create a new one.`)
      else setGlossMsg(`✓ No glossary named "${name}" in PDC — import will create it fresh.`)
    } catch (err) {
      setGlossMsg(`Check failed: ${err.message}`)
    }
  }

  const shown = (sources || []).filter((s) =>
    !query || `${s.name || ''} ${s.type || ''} ${s.fqdn || ''}`.toLowerCase().includes(query.toLowerCase()))

  function toggleAll(on) {
    const next = new Set(sel)
    shown.forEach((s) => { on ? next.add(hvKey(s)) : next.delete(hvKey(s)) })
    setSel(next)
  }

  return (
    <section className="card">
      <h2>Harvest from PDC <span>no direct DB access</span></h2>
      <p className="hint-line">
        Build the glossary from what PDC has <b>already cataloged</b> — no re-created connections,
        no secrets. List the sources PDC holds, then per source: <b>Test</b> (read-only — what did
        PDC actually ingest?), <b>→ Connection</b> (save it as an app connection, minus the secret)
        and <b>Harvest</b> (pull its terms into the glossary), or tick several and harvest together.
        Terms PDC already governs are flagged so you don't overwrite existing work.
      </p>

      <PdcAuthFields pdc={pdc} />

      <div className="actions">
        <button className="ghost" onClick={listSources} disabled={busy}>List data sources</button>
        {sources != null && sel.size > 0 && (
          <button className="primary" onClick={harvestSelected} disabled={busy}>Harvest selected →</button>
        )}
        <span className="muted" style={{ fontSize: '.8rem' }}>
          {sel.size ? `${sel.size} selected` : sources != null ? 'none selected' : ''}
        </span>
      </div>

      {sources != null && sources.length > 0 && (
        <>
          <div className="list-tools">
            <input type="text" placeholder="Filter sources by name / type / fqdn…"
                   value={query} onChange={(e) => setQuery(e.target.value)} />
            <label className="check">
              <input type="checkbox" onChange={(e) => toggleAll(e.target.checked)} /> Select all shown
            </label>
            <span className="muted" style={{ fontSize: '.8rem' }}>{shown.length} of {sources.length} shown</span>
          </div>
          <div className="src-list">
            {shown.map((s) => {
              const k = hvKey(s)
              const n = notes[k]
              return (
                <div key={k}>
                  <div className="src-row">
                    <input type="checkbox" checked={sel.has(k)}
                           onChange={(e) => {
                             const next = new Set(sel)
                             e.target.checked ? next.add(k) : next.delete(k)
                             setSel(next)
                           }} />
                    <span className="src-name">
                      <b>{s.name || s.id || '(unnamed source)'}</b>
                      {s.type && <span className="muted" style={{ fontSize: '.75rem' }}> {s.type}</span>}
                    </span>
                    {s.fqdn && <span className="src-fqdn" title={s.fqdn}>{s.fqdn}</span>}
                    <button className="ghost connect-sm" onClick={() => testSource(s)}
                            title="Read-only: what has PDC actually ingested for this source?">Test</button>
                    {(!s.type || String(s.type).toUpperCase() === 'RESOURCE') && (
                      <button className="ghost connect-sm" onClick={() => toConnection(s)}
                              title="Save this PDC source as an app connection for a direct live scan — prefills everything except the secret">→ Connection</button>
                    )}
                    <button className="ghost connect-sm"
                            onClick={() => {
                              const cards = []
                              harvestOne(s, cards)
                                .then(() => setScanCards(cards))
                                .catch((err) => note(hvKey(s), 'bad', `Harvest failed: ${err.message}`))
                            }}
                            title="Add this source's terms to the glossary">Harvest</button>
                  </div>
                  {n && <div className={`src-note ${n.tone}`}>{n.text}</div>}
                </div>
              )
            })}
            {shown.length === 0 && <p className="hint-line" style={{ padding: '.6rem' }}>No sources match that filter.</p>}
          </div>
        </>
      )}

      {msg && <p className="summary">{msg}</p>}
      {scanCards.map((ps, i) => <PdcScanCard key={i} ps={ps} />)}
      {getWorkspace().rows.length > 0 && scanCards.length > 0 && (
        <div className="actions">
          <button className="ghost" onClick={() => onNavigate('review')}>Review terms →</button>
        </div>
      )}

      <h3 className="subhead">Pre-flight: glossary name in PDC</h3>
      <div className="actions" style={{ marginTop: '.4rem' }}>
        <input type="text" className="text" placeholder={glossaryName || 'glossary name'}
               value={glossName} onChange={(e) => setGlossName(e.target.value)}
               style={{ flex: '0 1 260px' }} />
        <button className="ghost" onClick={checkGlossary}
                title="Does a glossary with this name already exist in PDC? Importing over it creates a duplicate.">
          Check in PDC
        </button>
        {glossMsg && <span className="summary">{glossMsg}</span>}
      </div>
    </section>
  )
}

// One line of PDC's own scan & discovery results for a harvested source.
function PdcScanCard({ ps }) {
  if (!ps) return null
  const dist = ps.sens_dist || {}
  const order = ['HIGH', 'MEDIUM', 'LOW']
  const distTxt = Object.keys(dist).length
    ? ' (' + order.filter((k) => dist[k]).map((k) => `${k[0]}:${dist[k]}`)
        .concat(Object.keys(dist).filter((k) => !order.includes(k)).map((k) => `${k}:${dist[k]}`))
        .join(' ') + ')'
    : ''
  const ent = ps.columns ? `${ps.tables} table(s) · ${ps.columns} column(s)` : `${ps.files} file(s)`
  const total = ps.columns || ps.files || 0
  return (
    <div className="pdc-scan-card">
      <b>{ps.source || ''}</b> — PDC scan &amp; discovery results:{' '}
      ingested <b>{ent}</b> · identified <b>{ps.identified || 0}</b>/{total}{distTxt} ·{' '}
      trust-scored <b>{ps.trust_scored || 0}</b> · term-linked <b>{ps.term_linked || 0}</b> ·{' '}
      tagged <b>{ps.tagged || 0}</b>
      {!ps.identified && total > 0 &&
        <span className="muted"> — 0 identified usually means Profiling / Data Identification hasn't run on this source in PDC yet</span>}
    </div>
  )
}

/* ================= connection form (new / edit) ================= */

const DB_DEFAULTS = {
  engine: 'postgresql', host: 'localhost', port: '5433', database: 'public',
  schema: 'public', user: 'pdc_user', password: '', ssl: false, profile: true,
}
const MINIO_DEFAULTS = {
  endpoint: '192.168.1.200:9000', bucket: 'documents', access_key: '', secret_key: '',
  prefix: '', secure: false, level: 'file', profile_dq: false,
}
const DDL_DEFAULTS = { path: '/mnt/user-data/uploads/01-schema-and-data.sql' }

function ConnectionForm({ editing, onSaved, onCancel }) {
  const [name, setName] = useState('')
  const [type, setType] = useState('db')
  const [db, setDb] = useState(DB_DEFAULTS)
  const [minio, setMinio] = useState(MINIO_DEFAULTS)
  const [ddl, setDdl] = useState(DDL_DEFAULTS)
  const [msg, setMsg] = useState('')

  useEffect(() => {
    if (!editing) return
    const f = editing.config || {}
    setName(editing.name || '')
    setType(editing.type || 'db')
    if (editing.type === 'db') {
      setDb({ ...DB_DEFAULTS, ...f, profile: f.profile !== false })
    } else if (editing.type === 'minio') {
      setMinio({ ...MINIO_DEFAULTS, ...f, level: f.level !== 'folder' ? 'file' : 'folder' })
    } else {
      setDdl({ path: f.path || '' })
    }
    setMsg('')
  }, [editing])

  function reset() {
    setName(''); setType('db')
    setDb(DB_DEFAULTS); setMinio(MINIO_DEFAULTS); setDdl(DDL_DEFAULTS)
    setMsg('')
    onCancel()
  }

  const config = () => (type === 'db' ? db : type === 'minio' ? minio : ddl)

  // Keep the endpoint's scheme and the TLS tick in lockstep (boto3 obeys the
  // scheme): typing a scheme sets the tick; toggling the tick rewrites it.
  function onEndpoint(v) {
    const next = { ...minio, endpoint: v }
    if (/^https:\/\//i.test(v)) next.secure = true
    else if (/^http:\/\//i.test(v)) next.secure = false
    setMinio(next)
  }
  function onSecure(checked) {
    const next = { ...minio, secure: checked }
    if (/^https?:\/\//i.test(minio.endpoint || '')) {
      next.endpoint = minio.endpoint.replace(/^https?:\/\//i, checked ? 'https://' : 'http://')
    }
    setMinio(next)
  }

  async function save() {
    if (!name.trim()) { setMsg('Name required'); return }
    try {
      const d = await apiPost('/api/connections', {
        id: editing?.id, name: name.trim(), type, config: config(),
      })
      onSaved(d.connections || [])
      setName(''); setDb(DB_DEFAULTS); setMinio(MINIO_DEFAULTS); setDdl(DDL_DEFAULTS)
      setMsg('Saved.')
    } catch (err) {
      setMsg(err.message)
    }
  }

  async function testForm() {
    if (type === 'ddl') { setMsg('DDL — scan to validate.'); return }
    setMsg('Testing…')
    try {
      const d = type === 'minio'
        ? await apiPost('/api/test-minio', { minio: config() })
        : await apiPost('/api/test-connection', { conn: config() })
      setMsg((d.ok ? '✓ ' : '✗ ') + (d.message || '') + (d.server_version ? ` — ${d.server_version}` : ''))
    } catch (err) {
      setMsg(`✗ ${err.message}`)
    }
  }

  return (
    <section className="card">
      <h2>{editing ? `Edit: ${editing.name}` : 'New connection'}</h2>
      <div className="form-grid">
        <label>
          Name
          <input type="text" placeholder="PostgreSQL" value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        <label>
          Type
          <select value={type} onChange={(e) => setType(e.target.value)}>
            <option value="db">Database (live scan)</option>
            <option value="minio">Document store (MinIO/S3)</option>
            <option value="ddl">DDL file (path)</option>
          </select>
        </label>
      </div>

      {type === 'db' && (
        <div className="form-grid" style={{ marginTop: '1rem' }}>
          <label>
            Engine
            <select value={db.engine} onChange={(e) => setDb({ ...db, engine: e.target.value })}>
              <option value="postgresql">PostgreSQL</option>
              <option value="sqlserver">SQL Server</option>
              <option value="mysql">MySQL / MariaDB</option>
              <option value="oracle">Oracle</option>
            </select>
          </label>
          <label>Host<input type="text" value={db.host} onChange={(e) => setDb({ ...db, host: e.target.value })} /></label>
          <label>Port<input type="text" value={db.port} onChange={(e) => setDb({ ...db, port: e.target.value })} /></label>
          <label>Database<input type="text" value={db.database} onChange={(e) => setDb({ ...db, database: e.target.value })} /></label>
          <label>Schema<input type="text" value={db.schema} onChange={(e) => setDb({ ...db, schema: e.target.value })} /></label>
          <label>User<input type="text" value={db.user} onChange={(e) => setDb({ ...db, user: e.target.value })} /></label>
          <label>Password<input type="password" autoComplete="off" value={db.password} onChange={(e) => setDb({ ...db, password: e.target.value })} /></label>
          <label className="check" style={{ alignSelf: 'end', paddingBottom: '.45rem' }}>
            <input type="checkbox" checked={db.ssl} onChange={(e) => setDb({ ...db, ssl: e.target.checked })} /> SSL required
          </label>
          <label className="check" style={{ alignSelf: 'end', paddingBottom: '.45rem' }}
                 title="Sample real column values on scan to determine sensitivity, PII and CDE from the data itself — not just the column name. Slower; needs rows in the tables.">
            <input type="checkbox" checked={db.profile} onChange={(e) => setDb({ ...db, profile: e.target.checked })} /> Profile data (sample values)
          </label>
        </div>
      )}

      {type === 'minio' && (
        <div className="form-grid" style={{ marginTop: '1rem' }}>
          <label>
            Endpoint
            <input type="text" value={minio.endpoint} onChange={(e) => onEndpoint(e.target.value)}
                   placeholder="192.168.1.200:9000" />
          </label>
          <label>Bucket<input type="text" value={minio.bucket} onChange={(e) => setMinio({ ...minio, bucket: e.target.value })} /></label>
          <label>Access key<input type="text" autoComplete="off" value={minio.access_key} onChange={(e) => setMinio({ ...minio, access_key: e.target.value })} /></label>
          <label>Secret key<input type="password" autoComplete="off" value={minio.secret_key} onChange={(e) => setMinio({ ...minio, secret_key: e.target.value })} /></label>
          <label>Prefix <span className="muted">optional</span>
            <input type="text" placeholder="(whole bucket)" value={minio.prefix} onChange={(e) => setMinio({ ...minio, prefix: e.target.value })} /></label>
          <label className="check" style={{ alignSelf: 'end', paddingBottom: '.45rem' }}>
            <input type="checkbox" checked={minio.secure} onChange={(e) => onSecure(e.target.checked)} /> TLS (https)
          </label>
          <label className="check" style={{ alignSelf: 'end', paddingBottom: '.45rem' }}
                 title="Apply business term, sensitivity and rating to each leaf file (so Trust Score lands on the files you see in PDC) rather than the folder.">
            <input type="checkbox" checked={minio.level === 'file'}
                   onChange={(e) => setMinio({ ...minio, level: e.target.checked ? 'file' : 'folder' })} /> Granularity: each file (leaf objects)
          </label>
          <label className="check" style={{ alignSelf: 'end', paddingBottom: '.45rem' }}
                 title="Read each object (CSV/JSON/JSONL/XML/text) and compute a Data Quality score from its content — the fourth Trust Score input.">
            <input type="checkbox" checked={minio.profile_dq}
                   onChange={(e) => setMinio({ ...minio, profile_dq: e.target.checked })} /> Data Quality: score from file content
          </label>
        </div>
      )}

      {type === 'ddl' && (
        <div className="form-grid" style={{ marginTop: '1rem' }}>
          <label style={{ gridColumn: '1 / -1' }}>
            DDL file path <span className="muted">a CREATE TABLE script on the server — same suggestions, no live connection needed</span>
            <input type="text" value={ddl.path} onChange={(e) => setDdl({ path: e.target.value })} />
          </label>
        </div>
      )}

      <div className="actions">
        <button className="primary" onClick={save}>Save connection</button>
        <button className="ghost" onClick={testForm}>Test</button>
        {editing && <button className="ghost" onClick={reset}>Cancel edit</button>}
        {msg && <span className="summary">{msg}</span>}
      </div>
    </section>
  )
}

/* ================= saved connection cards ================= */

function ConnectionCards({ conns, error, onEdit, onChanged, onDiscoverDb, onDiscoverDocs, onNavigate }) {
  return (
    <section className="card">
      <header>
        <h2>Saved connections <span>scan · discover · test</span></h2>
      </header>
      {error && <div className="error">{error}</div>}
      {conns == null && <p className="loading">Loading…</p>}
      {conns?.length === 0 && (
        <p className="hint-line">No saved connections yet. Add one above — or import the bulk-loader CSV.</p>
      )}
      {conns?.length > 0 && (
        <div className="conn-grid">
          {conns.map((c) => (
            <ConnCard key={c.id} conn={c} onEdit={onEdit} onChanged={onChanged}
                      onDiscoverDb={onDiscoverDb} onDiscoverDocs={onDiscoverDocs}
                      onNavigate={onNavigate} />
          ))}
        </div>
      )}
    </section>
  )
}

function ConnCard({ conn, onEdit, onChanged, onDiscoverDb, onDiscoverDocs, onNavigate }) {
  const [status, setStatus] = useState(null)   // {tone, text}
  const [check, setCheck] = useState(null)
  const [busy, setBusy] = useState(false)
  const c = conn

  const say = (tone, text) => setStatus({ tone, text })

  async function test() {
    if (c.type === 'ddl') { say('', 'DDL file — scan to validate.'); return }
    say('', 'Testing…')
    try {
      const d = c.type === 'minio'
        ? await apiPost('/api/test-minio', { minio: c.config })
        : await apiPost('/api/test-connection', { conn: c.config })
      say(d.ok ? 'good' : 'bad',
        (d.ok ? '✓ ' : '✗ ') + (d.message || '') +
        (d.server_version ? ` — ${d.server_version}` : '') +
        (d.objects != null ? ` · ${d.objects}+ obj` : ''))
    } catch (err) {
      say('bad', `✗ ${err.message}`)
    }
  }

  async function scan(mode) {
    const adding = mode === 'add' && getWorkspace().rows.length > 0
    setBusy(true)
    say('', adding ? 'Scanning to add…' : 'Scanning…')
    try {
      const d = await apiPost('/api/scan', scanBody(c))
      if (adding) {
        const { added, dup } = mergeIntoWorkspace(d.rows || [])
        say('good', `Added ${added} term(s)${dup ? ` (${dup} dup)` : ''}.`)
        setCheck(null)
      } else {
        setRows(d.rows || [])
        say('good', `Scanned — ${(d.rows || []).length} candidate term(s). Review and prune them next.`)
        setCheck(d.check || null)
      }
    } catch (err) {
      say('bad', `Scan failed: ${err.message}`)
    } finally {
      setBusy(false)
    }
  }

  async function discover() {
    setBusy(true)
    say('', c.type === 'minio' ? 'Scanning bucket…' : 'Profiling data…')
    try {
      if (c.type === 'minio') {
        const d = await onDiscoverDocs(c)
        say('good', `Scanned ${(d.summary?.files || 0).toLocaleString()} files — see Document discovery below.`)
      } else {
        const d = await onDiscoverDb(c)
        say('good', `Profiled ${d.summary?.tables ?? 0} tables — see Column profiling below.`)
      }
    } catch (err) {
      say('bad', `Discover failed: ${err.message}`)
    } finally {
      setBusy(false)
    }
  }

  async function seed() {
    if (!window.confirm('Seed realistic sample data into this database? This writes rows to empty/under-filled tables.')) return
    setBusy(true)
    say('', 'Seeding sample data…')
    try {
      const d = await apiPost('/api/seed', { conn: c.config, rows: 200 })
      say('good', `Seeded: ${(d.inserted || []).map((x) => `${x.table} +${x.rows}`).join(', ') || 'nothing (already populated)'}.`)
      await onDiscoverDb(c).catch(() => {})
    } catch (err) {
      say('bad', `Seed failed: ${err.message}`)
    } finally {
      setBusy(false)
    }
  }

  async function remove() {
    if (!window.confirm(`Delete connection "${c.name}"? This removes it from the app only — nothing in PDC is touched.`)) return
    try {
      const d = await apiDelete(`/api/connections/${c.id}`)
      onChanged(d.connections || [])
    } catch (err) {
      say('bad', err.message)
    }
  }

  return (
    <div className="conn-card">
      <div className="conn-head">
        <b>{c.name}</b>
        <span className="badge neutral">{CONN_TYPE_LABEL[c.type] || c.type}</span>
      </div>
      <div className="conn-det">{connDetail(c)}</div>
      <div className="acts">
        <button className="primary connect-sm" disabled={busy} onClick={() => scan('replace')}
                title="Reads the source and starts a fresh glossary from it (replaces the current candidate terms).">Scan</button>
        <button className="ghost connect-sm" disabled={busy} onClick={() => scan('add')}
                title="Scans this source and merges its terms into the existing glossary.">Add to glossary</button>
        {c.type !== 'ddl' && (
          <button className="ghost connect-sm" disabled={busy} onClick={discover}
                  title={c.type === 'minio'
                    ? 'Profile the bucket: file counts, sizes, types and folders.'
                    : 'Deeper profiling (distribution, uniqueness, patterns) so confidence and Data Quality are evidence-based.'}>Discover</button>
        )}
        {c.type === 'db' && (
          <button className="ghost connect-sm" disabled={busy} onClick={seed}
                  title="Populate empty/all tables with realistic sample data (writes rows).">Seed data</button>
        )}
        <button className="ghost connect-sm" disabled={busy} onClick={test}>Test</button>
        <button className="ghost connect-sm" onClick={() => onEdit(c)}>Edit</button>
        <button className="ghost connect-sm" onClick={remove}>Delete</button>
      </div>
      {status && <div className={`conn-status ${status.tone}`}>{status.text}</div>}
      <CheckPanel check={check} />
      {check && (
        <div className="actions" style={{ marginTop: '.6rem' }}>
          <button className="ghost connect-sm" onClick={() => onNavigate('review')}>Review terms →</button>
        </div>
      )}
    </div>
  )
}

/* ================= column profiling (database discovery) ================= */

const SENS_CLS = { HIGH: 'sens-hi', MEDIUM: 'sens-md', LOW: 'sens-lo' }

function ProfilePanel({ profile, onNavigate }) {
  const d = profile.data
  const s = d.summary || {}
  const tiles = [
    ['Tables', s.tables], ['Columns', s.columns],
    ['Total rows', (s.rows || 0).toLocaleString()],
    ['Database size', fmtBytes(s.db_bytes || 0)],
    ['PII columns', s.pii], ['CDE columns', s.cde],
    ['Classified', s.classified != null ? s.classified : '—'],
    ['Avg complete', s.avg_completeness != null ? pct(s.avg_completeness) : '—'],
    ['Keys (PK·FK)', `${s.pk_cols || 0}·${s.fk_cols || 0}`],
    ['Empty tables', s.empty],
  ]
  const sev = s.sensitivity || {}
  return (
    <section className="card">
      <header>
        <h2>Column profiling <span>{profile.name} — schema {d.schema}</span></h2>
        <button className="ghost" onClick={() => onNavigate('review')}>Review terms →</button>
      </header>
      <p className="hint-line">
        Per-column data profile — completeness, cardinality, detected type, sensitivity, PII and
        CDE — to compare against PDC's profiling. Captured with the glossary when you save it.
      </p>
      <div className="tiles">
        {tiles.map(([l, v]) => (
          <div className="tile" key={l}><div className="value">{String(v ?? '—')}</div><div className="label">{l}</div></div>
        ))}
      </div>
      <p className="summary">
        <b>Sensitivity:</b>{' '}
        <span className="sens-hi">HIGH {sev.HIGH || 0}</span> ·{' '}
        <span className="sens-md">MEDIUM {sev.MEDIUM || 0}</span> ·{' '}
        <span className="sens-lo">LOW {sev.LOW || 0}</span>
        {s.largest_tables?.length > 0 && (
          <>
            {'  |  '}<b>Largest:</b>{' '}
            {s.largest_tables.slice(0, 4).map((t) =>
              `${t.name} (${(t.rows || 0).toLocaleString()} rows, ${fmtBytes(t.bytes || 0)})`).join(' · ')}
          </>
        )}
      </p>
      {(d.tables || []).map((t) => (
        <details className="ptbl-wrap" key={t.name}>
          <summary>
            <b>{t.name}</b>
            {t.empty && <span className="badge warning">EMPTY — needs data</span>}
            <span className="rc">
              {(t.rows || 0).toLocaleString()} rows · {t.columns.length} cols{t.bytes ? ` · ${fmtBytes(t.bytes)}` : ''}
            </span>
          </summary>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Column</th><th>Type</th><th>Complete</th><th className="num">Distinct</th>
                  <th className="num">Unique</th><th>Sensitivity</th><th>PII</th><th>CDE</th>
                  <th>Detected</th><th>Examples</th>
                </tr>
              </thead>
              <tbody>
                {t.columns.map((col) => (
                  <tr key={col.column}>
                    <td>
                      <b>{col.column}</b>
                      {col.pk && <span className="key-badge pk" style={{ marginLeft: '.35rem' }}>PK</span>}
                      {col.fk && <span className="key-badge fk" style={{ marginLeft: '.35rem' }}>FK</span>}
                    </td>
                    <td><code>{col.type}</code></td>
                    <td><MiniBar frac={col.completeness} />{pct(col.completeness)}</td>
                    <td className="num">{(col.distinct || 0).toLocaleString()}</td>
                    <td className="num">{pct(col.uniqueness)}</td>
                    <td><span className={SENS_CLS[col.sensitivity] || ''}>{col.sensitivity}</span></td>
                    <td>{col.pii ? <span className="badge neutral">{col.pii}</span> : '—'}</td>
                    <td>{col.cde === 'Yes' ? '✓' : '—'}</td>
                    <td>{col.kind ? <span className="badge neutral">{col.kind}</span> : ''}</td>
                    <td className="notes"><code>{(col.examples || []).join(', ') || '—'}</code></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </details>
      ))}
    </section>
  )
}

/* ================= document discovery (bucket profile) ================= */

function DocsPanel({ docs, onRefilter }) {
  const d = docs.data
  const s = d.summary || {}
  const [include, setInclude] = useState(d.include || '')
  const [exclude, setExclude] = useState(d.exclude || '')
  const [busy, setBusy] = useState(false)
  const maxCount = Math.max(1, ...(d.by_type || []).map((t) => t.count))
  const maxFolder = Math.max(1, ...(d.by_folder || []).map((f) => f.bytes))

  async function refilter() {
    setBusy(true)
    try { await onRefilter(include.trim(), exclude.trim()) } finally { setBusy(false) }
  }

  return (
    <section className="card">
      <h2>Document discovery <span>{docs.name} — bucket {d.bucket}{d.prefix ? ` / ${d.prefix}` : ''}</span></h2>
      <p className="hint-line">
        Bucket contents at a glance — file counts and sizes, breakdown by file type and folder,
        plus the largest and most recent objects.
      </p>
      <div className="form-grid">
        <label>Include<input type="text" placeholder="e.g. *.pdf, inspections/* (blank = all)"
               value={include} onChange={(e) => setInclude(e.target.value)} /></label>
        <label>Exclude<input type="text" placeholder="e.g. *.md"
               value={exclude} onChange={(e) => setExclude(e.target.value)} /></label>
        <div className="field" style={{ alignSelf: 'end', flexDirection: 'row', alignItems: 'center', gap: '.7rem', paddingBottom: '.2rem' }}>
          <button className="ghost connect-sm" onClick={refilter} disabled={busy}>Apply filter</button>
          <span className="muted" style={{ fontSize: '.8rem' }}>
            {s.filtered ? `${s.filtered.toLocaleString()} object(s) filtered out` : 'No filter applied'}
          </span>
        </div>
      </div>
      <div className="tiles" style={{ marginTop: '1rem' }}>
        {[['Files', (s.files || 0).toLocaleString()], ['Total size', fmtBytes(s.bytes || 0)],
          ['File types', s.types], ['Folders', s.folders], ['Avg size', fmtBytes(s.avg_bytes || 0)],
        ].map(([l, v]) => (
          <div className="tile" key={l}><div className="value">{String(v ?? '—')}</div><div className="label">{l}</div></div>
        ))}
      </div>
      <div className="grid-2">
        <div>
          <h3 className="subhead">By file type</h3>
          <div className="type-bars">
            {(d.by_type || []).map((t) => (
              <div className="type-bar" key={t.ext}>
                <span><code>{t.ext}</code></span>
                <span className="tb-track"><span className="tb-fill" style={{ width: pct(t.count / maxCount), display: 'block' }} /></span>
                <span className="tb-num">{t.count.toLocaleString()} · {fmtBytes(t.bytes)}</span>
              </div>
            ))}
            {(d.by_type || []).length === 0 && <p className="hint-line">none</p>}
          </div>
        </div>
        <div>
          <h3 className="subhead">By folder</h3>
          <div className="table-scroll">
            <table>
              <thead><tr><th>Folder</th><th className="num">Files</th><th></th><th className="num">Size</th></tr></thead>
              <tbody>
                {(d.by_folder || []).map((f) => (
                  <tr key={f.name}>
                    <td><b>{f.name}</b></td>
                    <td className="num">{f.count.toLocaleString()}</td>
                    <td><MiniBar frac={f.bytes / maxFolder} /></td>
                    <td className="num">{fmtBytes(f.bytes)}</td>
                  </tr>
                ))}
                {(d.by_folder || []).length === 0 && <tr><td colSpan={4} className="notes">none</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
        <div>
          <h3 className="subhead">Largest objects</h3>
          <div className="table-scroll">
            <table><tbody>
              {(d.largest || []).map((o) => (
                <tr key={o.key}>
                  <td className="cell-clip" title={o.key}><code>{o.key}</code></td>
                  <td className="num">{fmtBytes(o.bytes)}</td>
                </tr>
              ))}
              {(d.largest || []).length === 0 && <tr><td className="notes">none</td></tr>}
            </tbody></table>
          </div>
        </div>
        <div>
          <h3 className="subhead">Most recent</h3>
          <div className="table-scroll">
            <table><tbody>
              {(d.newest || []).map((o) => (
                <tr key={o.key}>
                  <td className="cell-clip" title={o.key}><code>{o.key}</code></td>
                  <td className="num">{(o.modified || '').slice(0, 10)}</td>
                </tr>
              ))}
              {(d.newest || []).length === 0 && <tr><td className="notes">none</td></tr>}
            </tbody></table>
          </div>
        </div>
      </div>
    </section>
  )
}
