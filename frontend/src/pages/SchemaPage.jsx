import { useEffect, useState } from 'react'
import { apiGet, apiPost } from './../api.js'
import './schema.css'

// Schema page — the schema browser, split out of Connect as its own
// Connect-child page: pick a saved database/DDL connection (or paste a
// CREATE TABLE script), browse tables with PK/FK badges, click a table to
// inspect every column, review the relationships, and write the script's
// missing PRIMARY/FOREIGN KEY constraints to the live database (dry-run
// first, then per-statement apply status).

/* ---------- small shared helpers (kept in step with ConnectPage's copies;
   the .chk / .csv-box / .key-badge styles live in index.css) ---------- */

// POST /api/schema body for a saved connection (same dispatch as /api/scan).
function scanBody(c) {
  if (c.type === 'db') return { source: 'db', conn: c.config }
  if (c.type === 'minio') return { source: 'minio', minio: c.config }
  return { source: 'ddl', ddl_path: (c.config || {}).path }
}

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

export default function SchemaPage({ onNavigate }) {
  const [conns, setConns] = useState(null)
  const [connsError, setConnsError] = useState(null)
  const [connId, setConnId] = useState('')
  const [graph, setGraph] = useState(null)
  const [ddlText, setDdlText] = useState('')
  const [keysOnly, setKeysOnly] = useState(false)
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)
  const [openTable, setOpenTable] = useState(null)
  const [keysOut, setKeysOut] = useState(null)   // {mode:'plan'|'applied', data} | {error}

  useEffect(() => {
    apiGet('/api/connections')
      .then((b) => setConns(b.connections ?? []))
      .catch((e) => { setConns([]); setConnsError(e.message) })
  }, [])

  const opts = (conns || []).filter((c) => c.type === 'db' || c.type === 'ddl')
  const selected = opts.find((c) => c.id === (connId || opts[0]?.id))
  const hasObjectStore = (conns || []).some((c) => c.type === 'minio')

  async function load(body, label) {
    setBusy(true)
    setMsg(label)
    try {
      const d = await apiPost('/api/schema', body)
      setGraph(d)
      setMsg('')
    } catch (err) {
      setMsg(err.message)
    } finally {
      setBusy(false)
    }
  }

  const loadConn = () => selected
    ? load(scanBody(selected), 'Scanning schema…')
    : setMsg('Add a database or DDL connection on the Connect page first.')
  const loadSql = () => ddlText.trim()
    ? load({ source: 'ddl', ddl_text: ddlText.trim() }, 'Parsing SQL…')
    : setMsg('Paste a CREATE TABLE script first.')

  // Write PK/FK constraints from the pasted script to the selected live database.
  async function keys(dryRun) {
    if (!selected || selected.type !== 'db') {
      setKeysOut({ error: 'Select a database connection in the dropdown above — that’s the database the keys get written to.' })
      return
    }
    setKeysOut({ mode: 'loading' })
    const body = { conn: selected.config, dry_run: dryRun }
    if (ddlText.trim()) body.ddl_text = ddlText.trim()
    try {
      const d = await apiPost('/api/apply-keys', body)
      setKeysOut({ mode: dryRun ? 'plan' : 'applied', data: d })
    } catch (err) {
      setKeysOut({ error: err.message })
    }
  }

  const summary = graph ? schemaSummaryCheck(graph) : null

  return (
    <>
      <div className="page-head">
        <h1>Schema</h1>
        <p className="psub">
          Browse a database or DDL connection's tables with their primary and foreign
          keys, and write missing constraints back so PDC's ingest can read them.
          Connections are managed on the Connect page.
        </p>
      </div>

      <section className="card">
        <h2>Schema browser <span>tables, columns and foreign-key relationships</span></h2>
        <p className="hint-line">
          Load a schema and click a table to inspect every column with its references.
          {opts.length === 0 && (hasObjectStore
            ? ' Your object/document store has no relational schema — add the database connection on the Connect page, or paste its CREATE TABLE script below.'
            : ' Add a database or DDL connection on the Connect page, or paste a CREATE TABLE script below.')}
        </p>
        {connsError && <div className="error">{connsError}</div>}
        <div className="actions" style={{ marginTop: 0 }}>
          <select value={connId || opts[0]?.id || ''} onChange={(e) => setConnId(e.target.value)}
                  disabled={!opts.length} style={{ minWidth: 240 }}>
            {opts.length
              ? opts.map((c) => <option key={c.id} value={c.id}>{c.name || c.type}</option>)
              : <option value="">No database/DDL connection</option>}
          </select>
          <button className="primary" onClick={loadConn} disabled={busy || !opts.length}>Load schema</button>
          {!opts.length && conns != null && (
            <button className="ghost" onClick={() => onNavigate('connect')}>Add a connection →</button>
          )}
          {graph && (
            <label className="check">
              <input type="checkbox" checked={keysOnly} onChange={(e) => setKeysOnly(e.target.checked)} /> Keys only
            </label>
          )}
          {msg && <span className="summary">{msg}</span>}
        </div>

        <details style={{ marginTop: '.9rem' }}>
          <summary className="hint-line" style={{ cursor: 'pointer' }}>
            or diagram a CREATE TABLE script directly (reads PK/FK from the SQL — handy if the live connection can't see constraints)
          </summary>
          <textarea className="csv-box" rows={6} spellCheck={false} value={ddlText}
                    onChange={(e) => setDdlText(e.target.value)}
                    placeholder="Paste your CREATE TABLE statements here, then click Diagram SQL…" />
          <div className="actions">
            <button className="ghost" onClick={loadSql} disabled={busy}>Diagram SQL</button>
            <button className="ghost" onClick={() => keys(true)}
                    title="Add the PRIMARY KEY / FOREIGN KEY constraints from this script to the selected database, so PDC and the scan can read them. No data is changed.">
              Set PK/FK in database…
            </button>
          </div>
          <KeysPanel out={keysOut} onApply={() => keys(false)} />
        </details>

        {summary && <CheckPanel check={summary} />}

        {graph && (
          <>
            <div className="schema-grid">
              {graph.tables.map((t) => {
                const cols = keysOnly ? t.columns.filter((c) => c.pk || c.fk) : t.columns
                return (
                  <div className="schema-tbl" key={t.name} onClick={() => setOpenTable(t)}
                       title="Click to inspect every column">
                    <div className="st-head">
                      <b>{t.name}</b>
                      <span className="st-counts">{t.pk_count}PK·{t.fk_count}FK·{t.col_count}c</span>
                    </div>
                    {cols.slice(0, 14).map((c) => (
                      <div className="schema-col-row" key={c.name}>
                        <span className={`key-badge ${c.pk ? 'pk' : c.fk ? 'fk' : 'sp'}`}>
                          {c.pk ? 'PK' : c.fk ? 'FK' : ''}
                        </span>
                        <span className="cn">{c.name}</span>
                        <span className="ct">{c.type || ''}</span>
                      </div>
                    ))}
                    {cols.length > 14 && <div className="notes">… {cols.length - 14} more</div>}
                  </div>
                )
              })}
            </div>
            {graph.relationships?.length > 0 && (
              <>
                <h3 className="subhead">Relationships</h3>
                <div className="table-scroll">
                  <table>
                    <thead><tr><th>From</th><th>Column</th><th></th><th>To</th><th>Column</th><th></th></tr></thead>
                    <tbody>
                      {graph.relationships.map((r, i) => (
                        <tr key={i}>
                          <td><b>{r.from}</b></td><td><code>{r.from_col}</code></td>
                          <td>→</td>
                          <td><b>{r.to}</b></td><td><code>{r.to_col || ''}</code></td>
                          <td>{r.resolved
                            ? <span className="badge good">resolved</span>
                            : <span className="badge warning">outside this scan</span>}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </>
        )}

        {openTable && (
          <Modal wide title={`${openTable.name} — ${openTable.col_count} columns · ${openTable.pk_count} PK · ${openTable.fk_count} FK`}
                 onClose={() => setOpenTable(null)}>
            <div className="table-scroll">
              <table>
                <thead><tr><th>Column</th><th>Type</th><th>Null</th><th>References</th></tr></thead>
                <tbody>
                  {openTable.columns.map((c) => (
                    <tr key={c.name}>
                      <td>
                        {c.pk && <span className="key-badge pk" style={{ marginRight: '.35rem' }}>PK</span>}
                        {c.fk && <span className="key-badge fk" style={{ marginRight: '.35rem' }}>FK</span>}
                        {c.name}
                      </td>
                      <td><code>{c.type || ''}</code></td>
                      <td className="notes">{c.notnull ? 'NOT NULL' : ''}</td>
                      <td className="notes">{c.fk && c.ref_table ? `${c.ref_table}.${c.ref_col || ''}` : ''}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Modal>
        )}
      </section>
    </>
  )
}

// Same verdict logic as the old UI's renderSchemaSummary, expressed as a check.
function schemaSummaryCheck(d) {
  const cols = d.tables.reduce((a, t) => a + t.col_count, 0)
  const pks = d.tables.reduce((a, t) => a + t.pk_count, 0)
  const fks = d.tables.reduce((a, t) => a + t.fk_count, 0)
  const unresolved = d.relationships.filter((r) => !r.resolved).length
  const noKeys = d.table_count > 0 && pks === 0 && fks === 0
  const issues = []
  if (noKeys) {
    issues.push({ tone: 'bad', text: 'No primary or foreign keys were found in the live catalog. The constraints may exist but be invisible to this connection’s user — or the tables were created without them. Paste the CREATE TABLE script to read the keys straight from the SQL, or connect with an owner/superuser and reload.' })
  } else if (unresolved) {
    issues.push({ tone: 'warn', text: `${unresolved} foreign key(s) reference a table outside this scan.` })
  }
  return {
    title: 'Schema', tone: noKeys ? 'bad' : unresolved ? 'warn' : 'ok',
    rows: [
      { label: 'Schema', value: d.schema_name || '—' },
      { label: 'Tables', value: String(d.table_count) },
      { label: 'Columns', value: String(cols) },
      { label: 'Keys', value: `${pks} PK · ${fks} FK` },
      { label: 'Relationships', value: String(d.rel_count) },
    ],
    issues,
    verdict: noKeys ? 'Schema read, but without keys there are no relationships to show.'
      : d.table_count ? 'Click a table to see all columns with PK/FK and references.'
      : 'No tables found in this source.',
  }
}

function KeysPanel({ out, onApply }) {
  if (!out) return null
  if (out.mode === 'loading') return <p className="loading">Checking which keys are missing…</p>
  if (out.error) return <div className="error">{out.error}</div>
  const d = out.data
  if (out.mode === 'plan' && !d.pending) {
    return <CheckPanel check={{
      title: 'Keys in database', tone: 'ok',
      rows: [{ label: 'Schema', value: d.schema }, { label: 'Already set', value: `${d.skipped_pk} PK · ${d.skipped_fk} FK` }],
      verdict: 'Every key from the script is already present in the database — nothing to add.',
    }} />
  }
  const stmts = (d.statements || []).map((s, i) => (
    <div className="key-stmt" key={i}>
      <span className={`key-badge ${s.kind}`}>{s.kind.toUpperCase()}</span>
      <code title={s.sql}>{s.sql}</code>
      {s.status && s.status !== 'pending' && (
        <span className={`kstat ${s.status}`}>{s.status}{s.message ? `: ${s.message}` : ''}</span>
      )}
    </div>
  ))
  if (out.mode === 'plan') {
    return (
      <>
        <CheckPanel check={{
          title: 'Keys to add', tone: 'warn',
          rows: [
            { label: 'Schema', value: d.schema },
            { label: 'To add', value: `${d.pk_planned} PK · ${d.fk_planned} FK` },
            { label: 'Already set', value: `${d.skipped_pk} PK · ${d.skipped_fk} FK` },
          ],
          verdict: 'Review the statements below, then apply. This writes constraints only — no rows are changed.',
        }} />
        <div>{stmts}</div>
        <div className="actions">
          <button className="primary" onClick={onApply}>
            Apply {d.pending} change{d.pending > 1 ? 's' : ''} to the database
          </button>
        </div>
      </>
    )
  }
  const errs = (d.statements || []).filter((s) => s.status === 'error')
  return (
    <>
      <CheckPanel check={{
        title: 'Keys written', tone: errs.length ? 'warn' : 'ok',
        rows: [
          { label: 'Schema', value: d.schema },
          { label: 'Applied', value: String(d.applied) },
          { label: 'Errors', value: String(d.errors) },
        ],
        issues: errs.length ? [{ tone: 'warn', text: `${errs.length} statement(s) failed — usually orphan values that violate a foreign key.` }] : [],
        verdict: errs.length
          ? 'Some keys were added. Fix the flagged rows and re-run for the rest, then re-ingest the source in PDC.'
          : 'All keys written. Re-run Metadata Ingest on this source in PDC so it reads the new primary and foreign keys.',
      }} />
      <div>{stmts}</div>
    </>
  )
}
