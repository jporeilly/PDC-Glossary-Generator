import { useEffect, useRef, useState } from 'react'
import { apiGet, apiPost, apiDelete, runJob } from './../api.js'
import { getWorkspace, landScanRows, setDiscovery, setDocsDiscovery, setPdcSession, useWorkspace, usePersistentState } from './../state.js'
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

// File-type colour coding for the Document-discovery panels. Known extensions
// get a fixed hue (see .ftype-* in connect.css); anything else falls back to
// the muted default via .ftype-other.
const FTYPE_COLORED = new Set(['pdf', 'docx', 'doc', 'csv', 'tsv', 'xlsx', 'xls', 'json', 'xml', 'txt', 'md'])
const ftypeClass = (ext) => {
  const e = (ext || '').toLowerCase()
  return `ftype ftype-${FTYPE_COLORED.has(e) ? e : 'other'}`
}
// Extension of an object key ("a/b/report.pdf" -> "pdf"); "" when none.
const extOf = (key) => {
  const b = (key || '').split('/').pop()
  const i = b.lastIndexOf('.')
  return i > 0 ? b.slice(i + 1).toLowerCase() : ''
}
// Split a key into [dir-with-trailing-slash, filename] for the two-tone display.
const splitKey = (key) => {
  const i = (key || '').lastIndexOf('/')
  return i >= 0 ? [key.slice(0, i + 1), key.slice(i + 1)] : ['', key || '']
}

const splitCols = (s) => String(s || '').split(';').map((t) => t.trim()).filter(Boolean)

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
  // What the app is missing but would not otherwise mention. A missing domain
  // pack does not fail — the engine falls back to generic vocabulary and the
  // glossary comes out bland, which reads as the app underperforming rather
  // than as an input nobody supplied.
  const [ready, setReady] = useState(null)
  const [conns, setConns] = useState(null)
  const [connsError, setConnsError] = useState(null)
  // One PDC sign-in shared by the bulk loader, harvest and the glossary check
  // (the old UI duplicated these fields per card; the token is never persisted).
  //
  // Everything EXCEPT the password survives navigation. This was plain useState,
  // so leaving Connect unmounted the card and threw the token away — a page
  // change meant signing in again, four times in one debugging session. The
  // token lives in the session UI cache: an in-memory Map for the tab's
  // lifetime, never written to disk, which is exactly what "never persisted"
  // promises. The PASSWORD deliberately stays in component state so it dies with
  // the form — it is needed once to mint the token and should not outlive that.
  const [pdc, setPdc] = usePersistentState('connect.pdc',
    { base: '', user: '', token: '', ver: 'v2', verify: false })
  const [pdcPass, setPdcPass] = usePersistentState('pdc.pass', '')

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
    // Best-effort: a readiness check that fails must never keep the page from
    // loading — the point is to warn, not to gate.
    apiGet('/api/readiness').then(setReady).catch(() => {})
  }, [])

  return (
    <>
      {ready && !ready.domain_pack?.present && (
        <div className="notice-warn">
          <b>No domain pack.</b> Terms will use generic vocabulary, so{' '}
          <code>mbr_no</code> stays <i>Mbr No</i> rather than becoming{' '}
          <i>Member Number</i>, and categories come from generic keywords. The scan still
          works — the glossary is simply blander than it needs to be.
          <br />
          Nothing to do now: scan, review, then <b>export a pack</b> from the Dictionary page.
          It grows from rows you have already approved, and the next scan of this company
          starts where this one finished.
        </div>
      )}

      <div className="page-head">
        <h1>Connect</h1>
        <p className="psub">
          Each data source is its own saved connection. Scan one to start a glossary,
          then <b>Add to glossary</b> from others to span structured and unstructured sources.
          {ws.rows.length > 0 && <> Loaded now: <b>{ws.rows.length}</b> candidate term(s).</>}
        </p>
      </div>

      <BulkLoadCard pdc={setPdcProxy(pdc, setPdc, pdcPass, setPdcPass)} onConnectionsChanged={setConns} />
      <HarvestCard pdc={setPdcProxy(pdc, setPdc, pdcPass, setPdcPass)} onConnectionsChanged={refreshConns}
                   onNavigate={onNavigate} glossaryName={ws.glossaryName} />
      <ProfilingProbeCard rows={ws.rows} pdc={setPdcProxy(pdc, setPdc, pdcPass, setPdcPass)} />

      {/* Source connections moved to Schema (databases) and Files (object
          stores) — Connect deals only with PDC: bulk load, harvest, probe. */}




    </>
  )
}

// Bundle the auth state + setter so the two PDC cards share one sign-in.
// `pass` is threaded in separately: it lives in component state (dies on
// unmount) while the rest survives navigation, so callers can keep using
// pdc.pass / pdc.set({pass}) without knowing the difference.
function setPdcProxy(pdc, setPdc, pass, setPass) {
  return {
    ...pdc,
    pass,
    set: (patch) => {
      if ('pass' in patch) {
        setPass(patch.pass)
        const { pass: _drop, ...rest } = patch
        if (Object.keys(rest).length) setPdc((p) => ({ ...p, ...rest }))
        return
      }
      setPdc((p) => ({ ...p, ...patch }))
    },
  }
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
  const [tok, setTok] = useState(null)   // {tone, text} after a Get token click

  // Mint the bearer token from the username/password already typed above, so
  // the operator can confirm WHO they are before anything writes — and every
  // later call in the run (create, ingest, profile / discover) reuses it.
  async function getToken() {
    setTok({ tone: '', text: 'Authenticating…' })
    try {
      const d = await apiPost('/api/pdc-token', {
        base_url: pdc.base.trim(), username: pdc.user, password: pdc.pass,
        version: (pdc.ver || 'v2').trim(), realm: 'pdc', verify_tls: pdc.verify,
      })
      pdc.set({ token: d.token || '' })
      const c = d.claims || {}
      const who = c.username || c.preferred_username || pdc.user
      const roles = (c.roles || []).join(', ')
      const exp = c.expires_at || c.exp_human || ''
      setTok({ tone: 'good', text: `✓ token for ${who}${roles ? ` · ${roles}` : ''}${exp ? ` · expires ${exp}` : ''}` })
    } catch (err) {
      setTok({ tone: 'bad', text: `✗ ${err.message}` })
    }
  }

  return (
    <>
      <div className="form-grid">
        <label>
          PDC base URL
          <input type="text" placeholder="https://[PDC SERVER]"
                 value={pdc.base} onChange={(e) => pdc.set({ base: e.target.value })} />
          <span className="muted">the server root, not a path &mdash; use the hostname, since PDC routes by vhost</span>
        </label>
        <label>
          Username
          <input type="text" autoComplete="off" placeholder="PDC admin user"
                 value={pdc.user}
                 onChange={(e) => pdc.set({ user: e.target.value })} />
        </label>
        <label>
          Password
          <input type="password" autoComplete="new-password" placeholder="PDC admin password"
                 value={pdc.pass}
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
          Bearer token <span className="muted">optional — Get token fills it from the username / password above</span>
          <input type="text" autoComplete="off" placeholder="eyJhbGciOi…" value={pdc.token}
                 onChange={(e) => pdc.set({ token: e.target.value })} />
        </label>
      </div>
      <div className="actions" style={{ marginTop: '.5rem' }}>
        <button className="ghost connect-sm" onClick={getToken}
                disabled={!pdc.base.trim() || !(pdc.user && pdc.pass)}
                title="Authenticate to PDC now and keep the bearer token for this session — every call in the run (create, ingest, profile / discover) reuses it.">
          Get token
        </button>
        {pdc.token.trim() && (
          <button className="ghost connect-sm" onClick={() => { pdc.set({ token: '' }); setTok(null) }}
                  title="Forget the token and go back to username / password">Clear</button>
        )}
        {tok && <span className={tok.tone === 'bad' ? 'error' : 'summary'}>{tok.text}</span>}
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
  const [csv, setCsv] = usePersistentState('connect.blCsv', '')
  // profile defaults ON. Registering a source without analysing it leaves PDC
  // holding tables/files with no columns, statistics or sensitivity - which
  // looks like a broken load rather than a skipped step, because every badge
  // still reads OK. The sibling database form (DB_DEFAULTS) has always
  // defaulted profile true; these two are the same word on the same page and
  // disagreeing on it is what made this hard to spot.
  // Defaults, applied to any row whose CSV leaves the matching column blank.
  // Analysis splits by SOURCE TYPE, as PDC splits it: a database's tables go
  // through Data Profiling, an object store's files through Data Discovery.
  // The file-level switches are options ON that discovery pass, which is where
  // PDC's own Configure Process dialog puts them.
  const [opts, setOpts] = usePersistentState('connect.blOpts', {
    ingest: true, replace: false,
    profile: true,                                     // databases -> Data Profiling
    discover: true, profileFiles: true, header: true, docMeta: true,  // object stores
    skipDays: 0,                                       // 0 = no age restriction
  })
  const [msg, setMsg] = useState('')
  const [running, setRunning] = useState(false)
  const [progress, setProgress] = useState(null)   // {done, total}
  const [table, setTable] = usePersistentState('connect.blTable', null)          // {dryRun, rows: {index: result}}
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
      options: { ingest: opts.ingest, wait: true, replace_existing: opts.replace,
                 profile: opts.profile, discover: opts.discover,
                 profile_files: opts.profileFiles, header_row: opts.header,
                 doc_metadata: opts.docMeta, skip_recent_days: opts.skipDays },
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
      // a real (non-dry) run authenticated against PDC before touching any row —
      // light the sidebar PDC dot (dry runs build payloads locally, no auth)
      if (result && !result.dry_run) setPdcSession({ base: pdc.base.trim(), user: pdc.user })
    } catch (err) {
      setMsg(`Error: ${err.message}`)
    } finally {
      setRunning(false)
      setProgress(null)
    }
  }

  const rowIdx = table ? Object.keys(table.rows).map(Number).sort((a, b) => a - b) : []

  // Sources that registered fine but were never analysed. Counted only where
  // the create succeeded, so a row that failed earlier reports its own error
  // instead of being blamed on profiling. A grey SKIP badge in the table reads
  // as "nothing to do here"; the consequence needs saying in words.
  const profileSkipped = table && !table.dryRun
    ? rowIdx.filter((i) => {
        const r = table.rows[i] || {}
        return !r.working && r.profile === 'SKIP' &&
               ['OK', 'EXISTS', 'RECREATED'].includes(r.create)
      }).length
    : 0

  return (
    <section className="card">
      <h2>Bulk-load data sources into PDC <span>setup step — runs before the glossary</span></h2>
      <p className="hint-line">
        Register many sources in PDC at once from a CSV. For each row the app <b>creates</b> the
        data source, triggers a <b>metadata ingest</b> scoped to it and waits for the job, then
        <b> analyses</b> it — Data Profiling over a database's tables, a file scan plus Data
        Discovery over an object store's files. Without that last step PDC lists the tables and
        files but knows nothing inside them; untick <b>profile</b> (databases) or <b>discover</b>
        (object stores) to skip it.
        Use <code>kind</code> = <code>postgres</code>, <code>mysql</code>, <code>oracle</code>,{' '}
        <code>minio</code>/<code>s3</code> or <code>azure_blob</code>. Secrets are sent to PDC only
        and never saved by the app. A source that already exists shows as{' '}
        <span className="badge accent">EXISTS</span> — re-scanned, not re-created.
      </p>
      <p className="hint-line">
        Ingests that report OK but find nothing: set <code>schemaNames</code> to the schema your
        tables actually live in; object stores need <code>container</code>, a reachable{' '}
        <code>endpoint</code> and files in the bucket. <b>Endpoints are reached by PDC's workers,
        not by this machine</b> — use the VM's IP (<code>http://[VM IP]:9000</code>),
        never a hostname: the S3 SDK prepends the bucket to a hostname
        (<code>bucket.host</code>), which resolves nowhere. Scope scans with{' '}
        <code>includePatterns</code>/<code>excludePatterns</code> (semicolon-separated globs).
      </p>

      <details className="uth">
        <summary>Under the hood — bulk-loading data sources (PDC Public API)</summary>
        <div className="uth-body">
          <p>Per CSV row, in order. Everything below is one HTTP call you could make yourself.</p>
          <ol className="uth-steps">
            <li>
              <code>POST /api/public/{'{v}'}/data-sources</code> — create the source. The row's{' '}
              <code>kind</code> chooses the connector and its <code>databaseType</code>: an object
              store is created as <code>AWS</code> (not <code>AWS_S3</code>, which leaves PDC's
              Edit form blank).
              {' '}<b>Already there?</b> The create is skipped and the existing id reused —{' '}
              <span className="badge accent">EXISTS</span>. With <b>recreate if exists</b> the
              create is attempted <i>first</i>: only a name conflict authorises the delete, so a
              row with a bad body can never destroy a working source.
            </li>
            <li>
              <b>Databases</b> — <code>POST /jobs/execute/metadata/ingest</code> scoped to the new
              id, then <code>GET /jobs/{'{id}'}/status</code> until it reaches a terminal state.
            </li>
            <li>
              <b>Object stores</b> — the public API exposes no file-scan trigger, so this uses
              PDC's <i>internal</i> <code>POST /api/start-job</code> with{' '}
              <code>{'{name:"METADATA_INGEST", type:"START", data:{…}}'}</code> — the same call the
              catalog's own <b>Scan Files</b> button makes. Undocumented and version-fragile, which
              is why it is behind the <b>discover</b> switch. The scan carries the file options:{' '}
              <code>withProfile</code>, <code>headerExists</code>, <code>withDocMetadata</code>.
              <br />
              <span className="uth-note">
                PDC routes its internal API by <b>hostname</b>: on a bare IP this 401s with a
                perfectly valid token while the public API works, so only the file scan fails.
              </span>
            </li>
            <li>
              <b>Analysis</b> — <code>POST /api/public/v3/entities/filter</code> to collect the
              source's entity ids (filtered server-side on <code>resourceIds</code>, cursor
              followed across pages), then{' '}
              <code>POST /jobs/execute/data-profiling</code> over a database's <code>TABLE</code>{' '}
              entities, or <code>data-discovery</code> over an object store's{' '}
              <code>FOLDER</code>/<code>FILE</code> entities.
            </li>
          </ol>
          <p className="uth-note">
            Secrets travel to PDC and are never written to the app's own state. A dry run builds
            every payload and sends nothing — the echo comes back with credentials redacted.
          </p>
        </div>
      </details>

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
        <span style={{ flex: 1 }} />
        <button className="ghost" disabled={running} onClick={() => run(true)}>Dry run</button>
        <button className="primary" disabled={running} onClick={() => run(false)}>Create &amp; ingest →</button>
      </div>

      {/* Options sit on their own rows BELOW the buttons, split by what they act
          on. A CSV column of the same name overrides these per row, so one bucket
          can be registered twice — a structured row scoped to *.csv and an
          unstructured row scoped to *.pdf — each scanned appropriately. These are
          the defaults for any row that leaves the column blank. */}
      <div className="bl-opts">
        <span className="bl-optlbl">Load</span>
        <label className="check" title="Register each source in PDC and run a metadata ingest scoped to it.">
          <input type="checkbox" checked={opts.ingest}
                 onChange={(e) => setOpts({ ...opts, ingest: e.target.checked })} /> ingest metadata</label>
        <label className="check" title="If a source already exists in PDC, delete and recreate it so corrected CSV values take effect.">
          <input type="checkbox" checked={opts.replace}
                 onChange={(e) => setOpts({ ...opts, replace: e.target.checked })} /> recreate if exists</label>
      </div>

      <div className="bl-opts">
        <span className="bl-optlbl" title="Database sources — PDC runs Data Profiling over their tables.">Structured</span>
        <label className="check" title="Run PDC's Data Profiling over a database's tables after the ingest — distributions, uniqueness, patterns: the evidence the glossary's data-quality and identification work is built on. Adds a few minutes per source. CSV column: profile">
          <input type="checkbox" checked={opts.profile}
                 onChange={(e) => setOpts({ ...opts, profile: e.target.checked })} /> profile</label>
      </div>

      <div className="bl-opts">
        <span className="bl-optlbl" title="Object-store sources — PDC runs Data Discovery over their files. A bucket holds both documents and structured files, so the options below apply within this pass.">Unstructured</span>
        <label className="check" title="Run PDC's Data Discovery over an object store's files, which also runs the file scan first (PDC's own Scan Files call) since Discovery analyses what that scan catalogs. CSV column: discover">
          <input type="checkbox" checked={opts.discover}
                 onChange={(e) => setOpts({ ...opts, discover: e.target.checked })} /> discover</label>
        <label className="check" title="PDC's 'Profile structured and semi-structured files' — read the columns of the csv/json/parquet files inside the bucket. Off, they are catalogued with no columns at all. CSV column: profileFiles">
          <input type="checkbox" checked={opts.profileFiles} disabled={!opts.discover}
                 onChange={(e) => setOpts({ ...opts, profileFiles: e.target.checked })} /> profile files</label>
        <label className="check" title="Treat each structured file's first row as column names. Off, PDC reads it as data and names the columns Column-0, Column-1, … — which looks like real structure but is not. CSV column: header">
          <input type="checkbox" checked={opts.header} disabled={!opts.discover || !opts.profileFiles}
                 onChange={(e) => setOpts({ ...opts, header: e.target.checked })} /> first row is a header</label>
        <label className="check" title="Extract each document's own properties — owner, page count, paragraph count. Office and PDF files. CSV column: docMetadata">
          <input type="checkbox" checked={opts.docMeta} disabled={!opts.discover}
                 onChange={(e) => setOpts({ ...opts, docMeta: e.target.checked })} /> document metadata</label>
        <label className="check bl-days" title="PDC's 'Files Modified / Accessed More Than N Day(s) Ago'. 0 scans everything. Raise it to skip files touched recently — a landing area still being written to, for instance. CSV column: skipRecentDays">
          skip files newer than
          <input type="number" min="0" max="365" value={opts.skipDays} disabled={!opts.discover}
                 onChange={(e) => setOpts({ ...opts, skipDays: Math.max(0, Number(e.target.value) || 0) })}
                 aria-label="Skip files newer than this many days" />
          days
        </label>
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
            <thead><tr><th>Resource</th><th>create</th><th>ingest</th><th>job</th><th>profile / discover</th><th>note</th></tr></thead>
            <tbody>
              {rowIdx.map((i) => {
                const r = table.rows[i]
                return (
                  <tr key={i}>
                    <td>{r.resourceName || ''}</td>
                    {r.working
                      ? <td colSpan={4} className="notes">working…</td>
                      : ['create', 'ingest', 'job', 'profile'].map((k) => (
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

      {profileSkipped > 0 && (
        <p className="summary" style={{ marginTop: '.8rem' }}>
          <b className="warn">{profileSkipped} source(s) registered but not analysed.</b>{' '}
          PDC has their tables and files, but no columns, statistics or sensitivity —
          a database source needs Data Profiling and an object store needs its file
          scan plus Data Discovery. Tick <b>profile / discover</b> above and run again
          to fill them in; existing sources show as <span className="badge accent">EXISTS</span>{' '}
          and are re-used, not duplicated.
        </p>
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
          <input type="text" placeholder="db-host=localhost, 5432=5433" value={remap}
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

/* ---------- diagnostic: what does PDC's own profiling expose? ----------
   The architecture question: if PDC already ingested and profiled the estate
   (bulk loader), Harvest should be the primary path and the app should not
   need source credentials at all ("shouldn't you always use Harvest from
   PDC?"). Harvest reads entity metadata — structure + governance, but no
   VALUE evidence, which is what mints Dictionaries, Data Patterns, DQ
   expectations and the deterministic PII calls. This probe answers it with
   the catalog's own payload rather than argument. */
function ProfilingProbeCard({ rows, pdc }) {
  // Same entry point as Harvest: list PDC's data sources, pick one, and let
  // the catalog say which columns it holds ("its from the List data sources
  // in Harvest from PDC") — no hand-typed paths.
  const [sources, setSources] = usePersistentState('connect.probeSources', null)
  const [ds, setDs] = usePersistentState('connect.probeDs', '')
  const [res, setRes] = usePersistentState('connect.probeRes', null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)

  const listSources = async () => {
    setBusy(true); setErr(null)
    try {
      const d = await apiPost('/api/pdc/data-sources', pdcAuthBody(pdc))
      setSources(d.data_sources || [])
      if ((d.data_sources || []).length && !ds) {
        const f = d.data_sources[0]
        setDs(f.id || f.name || '')
      }
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  const probe = async () => {
    setBusy(true); setErr(null); setRes(null)
    try {
      const picked = (sources || []).find((s) => (s.id || s.name) === ds) || {}
      setRes(await apiPost('/api/pdc/profiling-probe', {
        ...pdcAuthBody(pdc),
        // scope EXACTLY like harvest does — fqdn first, then id: scoping by
        // id alone found no columns under a document source, which read as
        // "PDC has no profiling" when PDC plainly had 57 terms' worth
        data_source_id: picked.fqdn || picked.id || '', data_source_name: picked.name || '',
        rows: rows || [],
      }))
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }

  return (
    <details className="card">
      <summary>
        <b>Diagnostic — what does PDC&apos;s profiling expose?</b>
        <span className="notes"> · decides whether Harvest alone can feed the policy engine</span>
      </summary>
      <p className="hint-line">
        Harvest reads what PDC cataloged: structure, types, keys, and the governance
        PDC already holds — but not <i>values</i>. Dictionaries, Data Patterns, DQ
        expectations and the deterministic PII/sensitivity calls all come from value
        evidence. This asks PDC for its own <code>profilingInfo</code> on a few columns
        and reports what is actually in it: aggregate stats only, or distinct values and
        patterns too. If it carries values, a PDC-only path (no source credentials) is
        viable and Harvest becomes the primary route.
      </p>
      <div className="actions">
        <button className="ghost" onClick={listSources} disabled={busy}>
          {busy && !sources ? 'Listing…' : 'List data sources'}
        </button>
        {sources && sources.length > 0 && (
          <select value={ds} onChange={(e) => setDs(e.target.value)}
                  title="The PDC data source to probe — the catalog supplies its columns">
            {sources.map((s) => (
              <option key={s.id || s.name} value={s.id || s.name}>
                {s.name}{s.type ? ` · ${s.type}` : ''}
              </option>
            ))}
          </select>
        )}
        <button className="primary" onClick={probe} disabled={busy || !ds}>
          {busy && sources ? 'Probing…' : 'Probe PDC profiling'}
        </button>
        {sources && sources.length === 0 && (
          <span className="notes">PDC returned no sources — has the estate been ingested?</span>
        )}
        {err && <span className="warn">{err}</span>}
      </div>
      {res && (
        <>
          <p className={`summary ${res.capabilities?.values || res.capabilities?.patterns ? 'ok' : 'warn'}`}>
            {res.verdict}
          </p>
          <p className="summary">
            <span className="badge" style={{ marginRight: '.4rem' }}
                  title="Columns this probe asked about (it samples the first few by design) and how many PDC answered for — the id route replies for every column under the same parent, so the second number is often larger.">
              asked <b>{res.columns_found ?? 0}</b>
              {typeof res.profiled_returned === 'number' && res.profiled_returned !== res.columns_found
                ? <> · PDC answered for <b>{res.profiled_returned}</b></>
                : null}
            </span>
            {res.probe_via && (
              <span className="badge" style={{ marginRight: '.4rem' }}
                    title="How the profiling was requested: by resolving the parent table's name, or directly by the entities' own ids. If the id route finds profiling the name route missed, the gap was ours.">
                via {res.probe_via}
              </span>
            )}
            {['stats', 'values', 'patterns'].map((k) => (
              <span key={k} className={`badge ${res.capabilities?.[k] ? 'good' : 'warning'}`}
                    style={{ marginRight: '.4rem' }}>
                {k}: {res.capabilities?.[k] ? 'present' : 'absent'}
              </span>
            ))}
          </p>
          {res.labels && (
            <details style={{ marginTop: '.4rem' }}>
              <summary>
                <b>Labels &amp; custom properties</b>
                <span className="notes"> — {res.labels_verdict}</span>
              </summary>
              {res.labels.label_like_keys?.length > 0 && (
                <p className="summary">label-like keys:{' '}
                  {res.labels.label_like_keys.map((k) => <code key={k} style={{ marginRight: '.3rem' }}>{k}</code>)}
                </p>
              )}
              <p className="notes">attributes on a real entity: {(res.labels.attribute_keys || []).join(', ') || '—'}</p>
              <pre className="code-block" style={{ maxHeight: '240px', overflow: 'auto' }}>{res.labels.sample}</pre>
            </details>
          )}
          {res.file_sample && (
            <details style={{ marginTop: '.4rem' }}>
              <summary>
                <b>Raw FILE entity</b>
                <span className="notes"> — the arbiter for sizes and dates: whatever key the
                  catalog stores them under appears HERE, or the catalog does not hold them</span>
              </summary>
              <pre className="code-block" style={{ maxHeight: '260px', overflow: 'auto' }}>{res.file_sample}</pre>
            </details>
          )}
          {Object.entries(res.columns || {}).map(([k, v]) => (
            <details key={k} style={{ marginTop: '.4rem' }}>
              <summary><code>{k}</code> <span className="notes">keys: {v.keys.join(', ') || '—'}
                {v.value_like_keys?.length ? ` · value-like: ${v.value_like_keys.join(', ')}` : ''}</span></summary>
              <pre className="code-block" style={{ maxHeight: '260px', overflow: 'auto' }}>{v.raw}</pre>
            </details>
          ))}
        </>
      )}
    </details>
  )
}

/* ================= Harvest from PDC ================= */

const hvKey = (s) => s.fqdn || s.id

function HarvestCard({ pdc, onConnectionsChanged, onNavigate, glossaryName }) {
  const [sources, setSources] = usePersistentState('connect.hvSources', null)
  const [sel, setSel] = usePersistentState('connect.hvSel', () => new Set())
  const [query, setQuery] = usePersistentState('connect.hvQuery', '')
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)
  const [notes, setNotes] = usePersistentState('connect.hvNotes', {})       // per-source status: key -> {tone, text}
  const [scanCards, setScanCards] = usePersistentState('connect.hvCards', [])  // pdc_summary result cards
  const [glossName, setGlossName] = usePersistentState('connect.hvGloss', '')
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
  // toConnection removed: PDC returns credentials ENCRYPTED (userName /
  // accessId come back as 'AES/GCM/NoPadding|…'), so a connection built from
  // a PDC record could never authenticate — it arrived broken and looked like
  // the app's fault. Harvest is the path; when a direct scan is genuinely
  // needed, import the loader CSV, which carries real credentials.

  async function harvestOne(s, collectCards) {
    const k = hvKey(s)
    note(k, '', 'Harvesting…')
    const d = await apiPost('/api/pdc/harvest', {
      ...pdcAuthBody(pdc), data_source_id: s.fqdn || s.id, data_source_name: s.name || s.id,
    })
    if (d.pdc_summary) collectCards.push(d.pdc_summary)
    // a harvest fills the discovery views too — the Schema page's per-table
    // results and the Files page's charts work on the PDC-only path, not just
    // after a direct scan
    if (d.discovery) setDiscovery(d.discovery)
    if (d.docs_discovery) setDocsDiscovery({ ...d.docs_discovery, name: s.name || s.id })
    // landScanRows carries the empty-grid guard: a harvest landing while the
    // settled glossary sits unloaded offers to fold into it instead of
    // silently forking a raw twin (field-caught). Non-empty grids merge as
    // before; in a multi-source harvest only the first landing can ask.
    const res = await landScanRows(d.rows || [])
    const gov = d.scanned?.already_governed || 0
    note(k, 'good', `✓ ${res.mode === 'folded' ? `loaded "${res.name}" · ` : ''}added ${res.added} term(s)${res.dup ? ` · ${res.dup} merged into existing` : ''}${gov ? ` · ${gov} already governed in PDC` : ''}`)
    return { added: res.added, gov }
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
        PDC actually ingest?)
        and <b>Harvest</b> (pull its terms into the glossary), or tick several and harvest together.
        Terms PDC already governs are flagged so you don't overwrite existing work.
      </p>

      <details className="uth">
        <summary>Under the hood — reading PDC's catalog</summary>
        <div className="uth-body">
          <p>
            This route touches <b>no</b> database and <b>no</b> object store, and needs no
            credential for either. Everything comes from what PDC has already catalogued, so it
            works where the source itself is unreachable from your machine — a warehouse behind a
            firewall, a bucket you have no keys for.
          </p>
          <ol className="uth-steps">
            <li>
              <b>List data sources</b> — <code>POST /api/public/{'{v}'}/data-sources/filter</code>,
              returning each source's id, name and type.
            </li>
            <li>
              <b>Harvest</b> — <code>POST /api/public/v3/entities/filter</code>, paged by cursor,
              reshaped into what the suggester consumes:
              <ul>
                <li>a database's <code>COLUMN</code> entities → tables and columns</li>
                <li>an object store's <code>FILE</code> entities → document rows</li>
              </ul>
              The same pass overlays what PDC <i>already governs</i> — sensitivity, trust score and
              existing business terms — keyed to each row's source column, which is how governed
              terms arrive flagged instead of being silently proposed again.
            </li>
            <li>
              <b>Test</b> (read-only) and <b>Save connection</b> reuse the stored source's config
              via <code>/api/pdc/source-test</code> and{' '}
              <code>/api/pdc/source-to-connection</code> — the app never sees the secret, so a
              harvested connection is saved <i>without</i> one and must be completed by hand before
              it can do a live scan.
            </li>
          </ol>
          <p className="uth-note">
            What you get is only as good as PDC's own scan: harvest a source PDC ingested but never
            profiled and you get names and types with no statistics behind them.
          </p>
        </div>
      </details>

      <PdcAuthFields pdc={pdc} />

      <div className="actions">
        <button className="primary" onClick={listSources} disabled={busy}>List data sources</button>
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
      {scanCards.length > 0
        && scanCards.every((ps) => !((ps.identified || 0) + (ps.trust_scored || 0)
                                     + (ps.term_linked || 0) + (ps.tagged || 0))) && (
        <p className="notes">
          No classifications in PDC yet — <b>Data Identification</b> stamps sensitivity, and
          trust scores and term links follow it. Harvest still brings the structure and the
          values PDC profiled; there is simply nothing governed to overlay.
        </p>
      )}
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
        <button className="primary" onClick={checkGlossary}
                title="Does a glossary with this name already exist in PDC? Importing over it creates a duplicate.">
          Check in PDC
        </button>
        {glossMsg && <span className="summary">{glossMsg}</span>}
      </div>
    </section>
  )
}

// One COMPACT line of what PDC holds for a harvested source. The governance
// counts only earn their place when there IS governance: repeating "0
// identified means Data Identification has not run" under every source told
// the steward something they already knew, three lines at a time
// (field-caught). When nothing is classified anywhere, the parent says so
// once instead.
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
  const governed = (ps.identified || 0) + (ps.trust_scored || 0) + (ps.term_linked || 0) + (ps.tagged || 0)
  return (
    <div className="pdc-scan-card">
      <b>{ps.source || ''}</b> — PDC holds <b>{ent}</b>
      {governed > 0 ? (
        <>
          {ps.identified ? <> · classified <b>{ps.identified}</b>/{total}{distTxt}</> : null}
          {ps.trust_scored ? <> · trust-scored <b>{ps.trust_scored}</b></> : null}
          {ps.term_linked ? <> · term-linked <b>{ps.term_linked}</b></> : null}
          {ps.tagged ? <> · tagged <b>{ps.tagged}</b></> : null}
          <span className="muted"> — harvest overlays this existing work so you don&apos;t overwrite it.</span>
        </>
      ) : (
        <span className="muted"> · no classifications yet</span>
      )}
    </div>
  )
}

/* ================= connection form (new / edit) ================= */

