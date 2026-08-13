// Source connections — the app-side credentials that power the DIRECT paths:
// the Schema page's live browser/ER/keys, the Files page's bucket browser,
// Seed data, and scanning a source PDC has not profiled. Moved OUT of Connect
// ("the Connect page should just deal with PDC connections") so each kind
// lives with the only page that still needs it: databases on Schema,
// document stores on Files. PDC-first remains the primary path — these are
// the browsers' keys, not the glossary's.
import { useEffect, useRef, useState } from 'react'
import { apiGet, apiPost, apiDelete } from './../api.js'
import { getWorkspace, setRows, setDiscovery, setDocsDiscovery } from './../state.js'
import { mergeBySource } from './../rowmerge.js'

function mergeIntoWorkspace(newRows) {
  const { rows, added, dup } = mergeBySource(getWorkspace().rows, newRows)
  setRows(rows)
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



/* Defaults for the connection form: ports and engine names are safe to
 * assume; hosts, accounts and buckets are not. allow_sample_data stays OFF
 * by default deliberately - it is the switch that lets the one writing
 * operation (Seed data) run at all. */
const DB_DEFAULTS = {
  engine: 'postgresql', host: '', port: '5432', database: '',
  schema: 'public', user: '', password: '', ssl: false, profile: true,
  allow_sample_data: false,
}
const MINIO_DEFAULTS = {
  endpoint: '', bucket: '', access_key: '', secret_key: '',
  prefix: '', secure: false, level: 'file', profile_dq: false, content_terms: true,
}
const DDL_DEFAULTS = { path: '' }

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
          <label className="check danger-check" style={{ alignSelf: 'end', paddingBottom: '.45rem' }}
                 title="TRAINING AND DEMO DATABASES ONLY. Lets the Seed data button write fabricated rows into this database's EMPTY tables. A production estate has empty tables too — a new feature's, an audit table not yet written to — and they would be filled.">
            <input type="checkbox" checked={!!db.allow_sample_data}
                   onChange={(e) => setDb({ ...db, allow_sample_data: e.target.checked })} />
            allow sample data <span className="danger-chip">writes</span>
          </label>
        </div>
      )}

      {type === 'minio' && (
        <div className="form-grid" style={{ marginTop: '1rem' }}>
          <label>
            Endpoint
            <input type="text" value={minio.endpoint} onChange={(e) => onEndpoint(e.target.value)}
                   placeholder="[PDC SERVER]:9000  (the S3 API port, not the console)" />
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
                 title="Parse each content-profilable object's declared columns (CSV headers, JSON/JSONL record paths) into candidate terms — the same shape PDC's own scanner catalogs, with values profiled exactly like database columns. Purely mechanical: whatever the files declare, no estate assumptions.">
            <input type="checkbox" checked={minio.content_terms !== false}
                   onChange={(e) => setMinio({ ...minio, content_terms: e.target.checked })} /> Terms from file contents (columns)
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

      <details className="uth">
        <summary>Connection types &amp; what each button does</summary>
        <div className="uth-body">
          <dl className="uth-dl">
            <dt>Database (live scan)</dt>
            <dd>
              Connects to PostgreSQL, MySQL, SQL Server or Oracle with a least-privilege read-only
              user and introspects schema, keys and comments.
            </dd>
            <dt>Object store (MinIO/S3)</dt>
            <dd>
              Browses a bucket over the S3 API and treats each file as a document term. Use the
              host or VM address for the endpoint, never <code>localhost</code> — MinIO needs
              path-style addressing and <code>localhost</code> resolves inside the wrong container.
            </dd>
            <dt>DDL file</dt>
            <dd>
              Parses a <code>CREATE TABLE</code> script when the live database is out of reach.
              Same suggestions, no connection — but no values either, so confidence is name-based.
            </dd>
          </dl>
          <dl className="uth-dl">
            <dt>Test</dt>
            <dd>Validates the details before saving. The source stays unusable until it passes.</dd>
            <dt>Discover</dt>
            <dd>
              Reads values as well as structure, so confidence, sensitivity and data quality rest
              on evidence rather than column names. <b>Profiles only</b> — it never adds rows to
              the review grid.
            </dd>
            <dt>Add to glossary</dt>
            <dd>
              <b>The one action that writes the review grid.</b> Scans this source and merges its
              terms in by source identity — the first source starts the glossary, later sources
              join it, and scanning one source never touches another&apos;s rows. This is how one
              glossary spans a database <i>and</i> a document store. Working order:
              Test → Discover → Add.
            </dd>
            <dt>Seed data</dt>
            <dd>
              <b>The one button that writes, and it is for training and demo databases only.</b>{' '}
              It inserts fabricated rows so a lab database has values to profile — confidence and
              sensitivity are name-based without them. Never point it at a system of record.
              <br />
              It fills <b>empty tables only</b>; anything already holding data is left alone. That
              is thinner protection than it sounds, because a <b>production</b> estate has empty
              tables too — a new feature's, an audit table not yet written to — and those would be
              filled. So three things gate it: the connection must be ticked{' '}
              <b>allow sample data</b> (off by default, enforced server-side), a read-only dry run
              names the exact tables first, and you type the database name to confirm.
              <br />
              Everything else on this page is read-only.
            </dd>
          </dl>
        </div>
      </details>

      <details className="uth">
        <summary>Under the hood — what a database scan runs</summary>
        <div className="uth-body">
          <p>
            All of it is <code>SELECT</code> against catalog views your account can already read.
            Nothing is created, altered or dropped.
          </p>
          <ol className="uth-steps">
            <li>
              <b>Structure</b> — <code>information_schema.columns</code> for names, types,
              nullability and ordinal position. Oracle uses its own dictionary views
              (<code>all_tab_columns</code>) since it has no <code>information_schema</code>.
            </li>
            <li>
              <b>Keys</b> — <code>table_constraints</code> joined to{' '}
              <code>key_column_usage</code> for primary and foreign keys; PostgreSQL reads{' '}
              <code>pg_index</code> and <code>pg_constraint</code> directly, which is cheaper and
              catches constraints the standard views omit. Relationships travel to the Registry
              even for columns pruned from the glossary — a surrogate key is rarely a business
              term, but the relationship is still a fact worth keeping.
            </li>
            <li>
              <b>Comments</b> — column comments where the platform stores them, used as a first
              draft of a definition before anything is generated.
            </li>
            <li>
              <b>Discover only</b> — per column, <code>COUNT(*)</code>,{' '}
              <code>COUNT(DISTINCT col)</code> and a bounded sample of values. From those come
              uniqueness, density, the induced value pattern and the reference lists that seed the
              Policy Generator's dictionaries. Sampling is capped, so this reads a slice, not a
              table.
            </li>
          </ol>
          <p className="uth-note">
            Values are used to compute statistics and are not stored. What lands in the glossary is
            the derived pattern and the counts — not the rows.
          </p>
        </div>
      </details>

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
      if (adding || getWorkspace().rows.length > 0) {
        // Scanning source X must NEVER delete source Y's rows: the plain Scan
        // used to REPLACE the whole workspace, so "JDBC added, then Scan on
        // Documents" silently wiped the JDBC cohort before Add was ever
        // clicked (field-caught). A non-empty grid always merges — identity
        // is source-based so rescans refresh evidence instead of duplicating
        // — and a from-scratch grid is what Reset all is for.
        const { added, dup } = mergeIntoWorkspace(d.rows || [])
        say('good', `${adding ? 'Added' : 'Merged'} ${added} term(s)${dup ? ` · ${dup} existing term(s) gained this source's columns & evidence` : ''} — other sources' rows are untouched (Reset all first for a from-scratch grid).`)
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

  // The only operation on this page that writes to a database, so it asks twice
  // and shows its work in between.
  //
  // A plain confirm() was the whole protection here. "Only empty tables" reads as
  // safe and is not: a production estate has empty tables, and they would be
  // filled with fabricated rows. So: a read-only dry run names the exact tables,
  // then the operator types the database name — which cannot be done by reflex on
  // the wrong connection. The server independently refuses unless the connection
  // itself is marked allow_sample_data.
  async function seed() {
    setBusy(true)
    say('', 'Checking which tables would be written…')
    let plan
    try {
      plan = await apiPost('/api/seed', { conn: c.config, rows: 200, dry_run: true })
    } catch (err) {
      setBusy(false)
      say('bad', `Could not read the schema: ${err.message}`)
      return
    }
    setBusy(false)

    const targets = plan.targets || []
    if (!targets.length) {
      say('good', `Nothing to seed — every table in ${plan.schema} already has rows.`)
      return
    }
    const dbName = plan.database || c.config?.database || ''
    const names = targets.map((t) => t.table)
    const shown = names.slice(0, 12).join(', ') + (names.length > 12 ? `, +${names.length - 12} more` : '')
    const typed = window.prompt(
      `This will INSERT 200 fabricated rows into ${names.length} empty table(s) ` +
      `in "${dbName}" (schema ${plan.schema}):

${shown}

` +
      `Tables that already hold data are left alone.

` +
      `Type the database name to confirm:`, '')
    if (typed == null) return
    if (typed.trim() !== dbName) {
      say('bad', `Not seeded — you typed "${typed.trim()}", the database is "${dbName}".`)
      return
    }

    setBusy(true)
    say('', `Seeding ${names.length} table(s)…`)
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

  // An object store with no bucket is export-only (the lab MinIO target for
  // Send to lab): there is nothing to read, so scanning it just 400s on
  // "Invalid bucket name" — offer Test/Edit only.
  const exportOnly = c.type === 'minio' && !(c.config || {}).bucket
  const exportOnlyWhy = 'This connection has no bucket — it is an export target only. Add a bucket in Edit to scan it.'

  return (
    <div className="conn-card">
      <div className="conn-head">
        <b>{c.name}</b>
        <span className="badge neutral">{CONN_TYPE_LABEL[c.type] || c.type}</span>
        {exportOnly && <span className="badge neutral" title={exportOnlyWhy}>export only</span>}
      </div>
      <div className="conn-det">{connDetail(c)}</div>
      {/* ONE grid writer, buttons in the working order: Test → Discover →
          Add to glossary. The separate "Scan" button is gone — after 1.36.55
          made non-empty grids always merge, Scan and Add were the same
          behavior wearing two names, and the replace-flavored one had already
          wiped a grid ("surely the order would be Scan → Discover → Add, so
          nothing interferes with adding to Glossary" — the product owner's
          collapse, shipped). */}
      <div className="acts">
        <button className="ghost connect-sm" disabled={busy} onClick={test}
                title="Validate the connection details — read-only, touches nothing.">Test</button>
        {c.type !== 'ddl' && (
          <button className="ghost connect-sm" disabled={busy || exportOnly} onClick={discover}
                  title={exportOnly ? exportOnlyWhy : (c.type === 'minio'
                    ? 'Profile the bucket: file counts, sizes, types and folders. '
                    : 'Deeper profiling (distribution, uniqueness, patterns) so confidence and Data Quality are evidence-based. ')
                    + 'Profiles ONLY — it never adds rows; Add to glossary is the one action that writes the grid.'}>Discover</button>
        )}
        <button className="primary connect-sm" disabled={busy || exportOnly} onClick={() => scan('add')}
                title={exportOnly ? exportOnlyWhy
                  : 'The ONE action that writes the review grid: scans this source and merges its terms in — the first source starts the glossary, later sources join it, and no source ever touches another source\'s rows. Working order: Test → Discover → Add.'}>Add to glossary</button>
        {c.type === 'db' && (
          <button className="ghost connect-sm" disabled={busy} onClick={seed}
                  title="Populate empty/all tables with realistic sample data (writes rows).">Seed data</button>
        )}
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


/* ---------- the per-page panel ---------- */
export function SourceConnections({ kind, onNavigate }) {
  const [conns, setConns] = useState(null)
  const [connsError, setConnsError] = useState(null)
  const [editing, setEditing] = useState(null)
  const formRef = useRef(null)

  const refresh = () =>
    apiGet('/api/connections')
      .then((b) => setConns(b.connections ?? []))
      .catch((e) => { setConns([]); setConnsError(e.message) })
  useEffect(() => { refresh() }, [])

  const mine = (conns || []).filter((c) => (kind === 'db' ? c.type !== 'minio' : c.type === 'minio'))

  async function discoverDb(conn) {
    const d = await apiPost('/api/discover', { conn: conn.config })
    setDiscovery(d)
    return d
  }
  async function discoverDocs(conn, include = '', exclude = '') {
    const d = await apiPost('/api/discover-docs', { conn: { ...conn.config, include, exclude } })
    setDocsDiscovery({ ...d, name: conn.name })
    return d
  }
  function startEdit(conn) {
    setEditing(conn)
    formRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }

  return (
    <>
      <ConnectionCards conns={mine} error={connsError} onNavigate={onNavigate}
                       onEdit={startEdit} onChanged={setConns}
                       onDiscoverDb={discoverDb} onDiscoverDocs={discoverDocs} />
      <details ref={formRef} className="card" open={!!editing}>
        <summary>
          <b>{editing ? 'Edit connection' : 'Add a source connection directly'}</b>
          <span className="notes"> · advanced — only when PDC has not profiled the source;
            harvest on Connect is the primary path</span>
        </summary>
        <ConnectionForm editing={editing} onCancel={() => setEditing(null)}
                        onSaved={(list) => { setConns(list); setEditing(null) }} />
      </details>
    </>
  )
}
