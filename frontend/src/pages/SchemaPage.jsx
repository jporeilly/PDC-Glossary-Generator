import { useEffect, useRef, useState } from 'react'
import { apiGet, apiPost } from './../api.js'
import './schema.css'

// Schema page — the schema browser, split out of Connect as its own
// Connect-child page: pick a saved database/DDL connection (or paste a
// CREATE TABLE script), browse tables with PK/FK badges, click a table to
// inspect every column, review the relationships, and write the script's
// missing PRIMARY/FOREIGN KEY constraints to the live database (dry-run
// first, then per-statement apply status). A "Cards | ER diagram" toggle
// switches the browser between the card grid and a pan/zoom SVG ER canvas
// (auto-arranged, re-modelled from the legacy static/js/02-schema.js).

/* ---------- small shared helpers (kept in step with ConnectPage's copies;
   the .chk / .csv-box / .key-badge styles live in index.css) ---------- */

// POST /api/schema body for a saved connection (same dispatch as /api/scan).
function scanBody(c) {
  if (c.type === 'db') return { source: 'db', conn: c.config }
  if (c.type === 'minio') return { source: 'minio', minio: c.config }
  return { source: 'ddl', ddl_path: (c.config || {}).path }
}

const fmtSize = (n) => n >= 1048576 ? `${(n / 1048576).toFixed(1)} MB`
  : n >= 1024 ? `${(n / 1024).toFixed(1)} KB` : `${n} B`

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
  const [viewMode, setViewMode] = useState('cards') // 'cards' | 'er'
  const [scanSeq, setScanSeq] = useState(0)      // bumps per load → remounts ErDiagram
  const erStore = useRef({})                     // session-local ER positions/viewport
  const [ddlFile, setDdlFile] = useState(null)   // {name, size} of a dropped script
  const [dragOver, setDragOver] = useState(false)
  const [dropErr, setDropErr] = useState('')
  const fileRef = useRef(null)

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
      erStore.current = {}
      setScanSeq((s) => s + 1)
      // default to the ER canvas whenever there are edges to draw
      setViewMode((d.relationships || []).some((r) => r.resolved) ? 'er' : 'cards')
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
    : setMsg('Paste a CREATE TABLE script or drop a .sql file first.')

  // A dropped/browsed script file: read it, fill the DDL box and diagram it.
  function takeDdlFile(file) {
    setDropErr('')
    if (!file) return
    const textish = (file.type || '').startsWith('text/') || file.type === 'application/sql'
    if (!/\.(sql|ddl|txt)$/i.test(file.name) && !textish) {
      setDropErr(`"${file.name}" doesn't look like a SQL script — drop a .sql, .ddl or .txt file.`)
      return
    }
    const rd = new FileReader()
    rd.onload = () => {
      const text = String(rd.result || '').trim()
      if (!text) { setDropErr(`"${file.name}" is empty.`); return }
      setDdlText(text)
      setDdlFile({ name: file.name, size: file.size })
      load({ source: 'ddl', ddl_text: text }, `Parsing ${file.name}…`)
    }
    rd.onerror = () => setDropErr(`Could not read "${file.name}".`)
    rd.readAsText(file)
  }

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
            <div className="seg" role="group" aria-label="Schema view">
              <button className={viewMode === 'cards' ? 'on' : ''} onClick={() => setViewMode('cards')}>Cards</button>
              <button className={viewMode === 'er' ? 'on' : ''} onClick={() => setViewMode('er')}>ER diagram</button>
            </div>
          )}
          {graph && viewMode === 'cards' && (
            <label className="check">
              <input type="checkbox" checked={keysOnly} onChange={(e) => setKeysOnly(e.target.checked)} /> Keys only
            </label>
          )}
          {msg && <span className="summary">{msg}</span>}
        </div>

        <details style={{ marginTop: '.9rem' }}>
          <summary className="hint-line" style={{ cursor: 'pointer' }}>
            or diagram a CREATE TABLE script directly — drop a .sql file or paste the SQL (reads PK/FK from the script — handy if the live connection can't see constraints)
          </summary>
          <div className={`ddl-drop${dragOver ? ' drag' : ''}`} role="button" tabIndex={0}
               onDragOver={(e) => { e.preventDefault(); setDragOver(true) }}
               onDragLeave={() => setDragOver(false)}
               onDrop={(e) => { e.preventDefault(); setDragOver(false); takeDdlFile(e.dataTransfer.files?.[0]) }}
               onClick={() => fileRef.current?.click()}
               onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); fileRef.current?.click() } }}>
            <input ref={fileRef} type="file" accept=".sql,.ddl,.txt,text/plain" hidden
                   onChange={(e) => { takeDdlFile(e.target.files?.[0]); e.target.value = '' }} />
            {ddlFile
              ? <span className="ddl-file"><b>{ddlFile.name}</b> · {fmtSize(ddlFile.size)} — drop another file to replace it</span>
              : <span>Drop a <b>.sql</b> / <b>.ddl</b> / <b>.txt</b> script here, or click to browse</span>}
          </div>
          {dropErr && <div className="error">{dropErr}</div>}
          <div className="hint-line" style={{ marginTop: '.6rem' }}>or paste the script:</div>
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

        {graph && viewMode === 'er' && (
          <ErDiagram key={scanSeq} graph={graph} store={erStore.current}
                     onOpenTable={(name) => setOpenTable(graph.tables.find((t) => t.name === name) || null)} />
        )}

        {graph && viewMode === 'cards' && (
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

/* ================================================================== */
/* ---------- ER diagram view ----------
   React re-model of the legacy static/js/02-schema.js SVG engine: compact
   nodes (title + PK/FK rows only — the click-modal keeps the full column
   list), FK edges wired from the exact source column row to the target's
   PK row, a hand-rolled layered (Sugiyama-style) auto-layout, and
   pan/zoom/node-drag. Positions and the viewport live in the parent's
   session-local store so toggling Cards ⇄ ER doesn't lose a manual
   arrangement; a new scan resets everything. */

const ER = { W: 204, HEAD: 26, ROW: 17, PADB: 7, HGAP: 96, VGAP: 30, MARGIN: 24 }
const erClamp = (v, a, b) => Math.max(a, Math.min(b, v))
const erTrunc = (s, n) => (s && s.length > n ? s.slice(0, n - 1) + '…' : s)
const erKeyRows = (t) => t.columns.filter((c) => c.pk || c.fk)
const erHeight = (t) => ER.HEAD + Math.max(erKeyRows(t).length, 1) * ER.ROW + ER.PADB

// Layered auto-layout. Directed edges point from the FK (dependent) table to
// the table it references, and longest-path layering puts every table one
// layer right of everything it references — so the most-referenced hubs
// (e.g. accounts) settle in the leftmost layers and dependents fan out
// rightwards. Four barycenter sweeps then reorder each layer by the mean
// rank of its neighbours to cut edge crossings. Orphan tables (no resolved
// relationship at all) line up in a bottom row.
function erLayout(graph) {
  const known = new Set(graph.tables.map((t) => t.name))
  const rels = (graph.relationships || []).filter((r) => r.resolved && known.has(r.from) && known.has(r.to))
  const refs = {}, neigh = {}
  graph.tables.forEach((t) => { refs[t.name] = []; neigh[t.name] = new Set() })
  rels.forEach((r) => {
    if (r.from === r.to) { neigh[r.from].add(r.from); return } // self-loop: connected, but no layering pull
    refs[r.from].push(r.to)
    neigh[r.from].add(r.to)
    neigh[r.to].add(r.from)
  })
  const connected = graph.tables.filter((t) => neigh[t.name].size > 0)
  const orphans = graph.tables.filter((t) => neigh[t.name].size === 0)

  // longest-path layering; `visiting` breaks FK cycles (a back edge stops at 0)
  const layer = {}, visiting = {}
  const calc = (n) => {
    if (layer[n] != null) return layer[n]
    if (visiting[n]) return 0
    visiting[n] = true
    let l = 0
    for (const m of refs[n]) l = Math.max(l, calc(m) + 1)
    visiting[n] = false
    layer[n] = l
    return l
  }
  connected.forEach((t) => calc(t.name))
  const depth = connected.reduce((a, t) => Math.max(a, layer[t.name]), 0)
  const cols = Array.from({ length: depth + 1 }, () => [])
  connected.forEach((t) => cols[layer[t.name]].push(t))

  // barycenter sweeps: sort every layer by the mean rank of its neighbours
  const rank = {}
  cols.forEach((col) => col.forEach((t, i) => { rank[t.name] = i }))
  for (let s = 0; s < 4; s++) {
    cols.forEach((col) => {
      const bary = {}
      col.forEach((t) => {
        const nb = [...neigh[t.name]].filter((m) => m !== t.name)
        bary[t.name] = nb.length ? nb.reduce((a, m) => a + rank[m], 0) / nb.length : rank[t.name]
      })
      col.sort((a, b) => bary[a.name] - bary[b.name])
      col.forEach((t, i) => { rank[t.name] = i })
    })
  }

  // coordinates: layers left→right, each layer vertically centred
  const heights = cols.map((col) =>
    col.reduce((a, t) => a + erHeight(t), 0) + Math.max(0, col.length - 1) * ER.VGAP)
  const maxH = heights.reduce((a, h) => Math.max(a, h), 0)
  const pos = {}
  cols.forEach((col, li) => {
    let y = ER.MARGIN + (maxH - heights[li]) / 2
    col.forEach((t) => {
      pos[t.name] = { x: ER.MARGIN + li * (ER.W + ER.HGAP), y }
      y += erHeight(t) + ER.VGAP
    })
  })
  if (orphans.length) {
    let x = ER.MARGIN
    const y = ER.MARGIN + (connected.length ? maxH + ER.VGAP * 2 : 0)
    orphans.forEach((t) => { pos[t.name] = { x, y }; x += ER.W + 36 })
  }
  return pos
}

// One resolved FK edge: exact source column row → target PK row, falling back
// to the header centre when a column isn't among that node's key rows.
// `dup` bows parallel edges between the same table pair apart.
function erEdge(r, dup, pos, byName) {
  const fp = pos[r.from], tp = pos[r.to]
  const rowY = (tbl, p, name, wantPk) => {
    const rows = erKeyRows(tbl)
    let i = name ? rows.findIndex((c) => c.name === name) : -1
    if (i < 0 && wantPk) i = rows.findIndex((c) => c.pk)
    return i >= 0 ? p.y + ER.HEAD + i * ER.ROW + ER.ROW / 2 : p.y + ER.HEAD / 2
  }
  const y1 = rowY(byName[r.from], fp, r.from_col, false)
  const y2 = rowY(byName[r.to], tp, r.to_col, true)
  const label = `${r.from}.${r.from_col} → ${r.to}`
  const tip = r.to_col ? `${label}.${r.to_col}` : label
  if (r.from === r.to) {                    // self-referencing FK: loop out the right side
    const x = fp.x + ER.W
    const o = 46 + dup * 14
    const yb = y1 === y2 ? y2 + ER.ROW : y2 // same row referenced: bow down one row
    return { label, tip, d: `M ${x} ${y1} C ${x + o} ${y1}, ${x + o} ${yb}, ${x} ${yb}`,
             lx: x + o + 4, ly: (y1 + yb) / 2 - 4 }
  }
  const fromLeft = fp.x + ER.W / 2 <= tp.x + ER.W / 2
  const x1 = fromLeft ? fp.x + ER.W : fp.x
  const x2 = fromLeft ? tp.x : tp.x + ER.W
  const o = Math.max(40, Math.abs(x2 - x1) * 0.4) + dup * 14
  const c1 = fromLeft ? x1 + o : x1 - o
  const c2 = fromLeft ? x2 - o : x2 + o
  return { label, tip, d: `M ${x1} ${y1} C ${c1} ${y1}, ${c2} ${y2}, ${x2} ${y2}`,
           lx: (x1 + 3 * c1 + 3 * c2 + x2) / 8, ly: (y1 + y2) / 2 - 4 } // cubic midpoint
}

function ErDiagram({ graph, store, onOpenTable }) {
  const wrapRef = useRef(null)
  const dragRef = useRef(null)
  const [pos, setPos] = useState(store.pos || null)
  const [view, setView] = useState(store.view || { x: 0, y: 0, z: 1 })
  const [sel, setSel] = useState(null)

  const byName = {}
  graph.tables.forEach((t) => { byName[t.name] = t })
  const rels = (graph.relationships || []).filter((r) => r.resolved && byName[r.from] && byName[r.to])

  // keep the parent's session store current so Cards ⇄ ER keeps arrangements
  useEffect(() => { store.pos = pos; store.view = view }, [store, pos, view])

  const fit = (p = pos) => {
    const el = wrapRef.current
    if (!el || !p || !graph.tables.length) return
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity
    graph.tables.forEach((t) => {
      const q = p[t.name]
      if (!q) return
      x0 = Math.min(x0, q.x); y0 = Math.min(y0, q.y)
      x1 = Math.max(x1, q.x + ER.W); y1 = Math.max(y1, q.y + erHeight(t))
    })
    const w = el.clientWidth, h = el.clientHeight
    const bw = Math.max(1, x1 - x0), bh = Math.max(1, y1 - y0)
    const z = erClamp(Math.min((w - 48) / bw, (h - 48) / bh, 1.1), 0.2, 2.5)
    setView({ z, x: (w - bw * z) / 2 - x0 * z, y: (h - bh * z) / 2 - y0 * z })
  }

  useEffect(() => {                         // first open of this scan: arrange + fit
    if (!pos) {
      const p = erLayout(graph)
      setPos(p)
      fit(p)
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const rearrange = () => {
    const p = erLayout(graph)
    setPos(p)
    setSel(null)
    fit(p)
  }

  const zoomAt = (f, mx, my) => setView((v) => {
    const z = erClamp(v.z * f, 0.2, 2.5), k = z / v.z
    return { z, x: mx - (mx - v.x) * k, y: my - (my - v.y) * k }
  })
  const zoomBtn = (f) => {
    const el = wrapRef.current
    if (el) zoomAt(f, el.clientWidth / 2, el.clientHeight / 2)
  }

  useEffect(() => {                         // wheel zoom needs a non-passive listener
    const el = wrapRef.current
    if (!el) return
    const onWheel = (e) => {
      e.preventDefault()
      const r = el.getBoundingClientRect()
      zoomAt(e.deltaY < 0 ? 1.12 : 1 / 1.12, e.clientX - r.left, e.clientY - r.top)
    }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => el.removeEventListener('wheel', onWheel)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {                         // drag a node / pan the background
    const move = (e) => {
      const d = dragRef.current
      if (!d) return
      const dx = e.clientX - d.sx, dy = e.clientY - d.sy
      if (Math.abs(dx) + Math.abs(dy) > 3) d.moved = true
      if (d.kind === 'pan') setView((v) => ({ ...v, x: d.ox + dx, y: d.oy + dy }))
      else setPos((p) => ({ ...p, [d.name]: { x: d.ox + dx / d.z, y: d.oy + dy / d.z } }))
    }
    const up = () => {
      const d = dragRef.current
      dragRef.current = null
      if (d && d.kind === 'node' && !d.moved) onOpenTable(d.name) // click = open modal
    }
    window.addEventListener('pointermove', move)
    window.addEventListener('pointerup', up)
    return () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('pointerup', up)
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const bgDown = (e) => {
    if (e.button !== 0) return
    dragRef.current = { kind: 'pan', sx: e.clientX, sy: e.clientY, ox: view.x, oy: view.y }
    setSel(null)
  }
  const nodeDown = (e, name) => {
    if (e.button !== 0 || !pos?.[name]) return
    e.stopPropagation()
    dragRef.current = { kind: 'node', name, sx: e.clientX, sy: e.clientY,
                        ox: pos[name].x, oy: pos[name].y, z: view.z, moved: false }
    setSel(name)
  }
  const related = (name) => name === sel ||
    rels.some((r) => (r.from === sel && r.to === name) || (r.to === sel && r.from === name))

  const dupSeen = {}
  const edges = pos ? rels.map((r) => {
    const k = `${r.from}→${r.to}`
    const i = dupSeen[k] || 0
    dupSeen[k] = i + 1
    return { r, ...erEdge(r, i, pos, byName) }
  }) : []

  return (
    <div className="er-wrap" ref={wrapRef}>
      <svg onPointerDown={bgDown} role="img" aria-label="Entity-relationship diagram">
        <defs>
          <marker id="er-arrow" markerWidth="9" markerHeight="8" refX="8" refY="4"
                  orient="auto" markerUnits="userSpaceOnUse">
            <path className="er-arrowhead" d="M0,0 L8,4 L0,8" />
          </marker>
        </defs>
        {pos && (
          <g transform={`translate(${view.x},${view.y}) scale(${view.z})`}>
            {edges.map((e, i) => {
              const hot = sel && (e.r.from === sel || e.r.to === sel)
              return (
                <g key={i} className={`er-rel${hot ? ' hot' : ''}${sel && !hot ? ' dim' : ''}`}>
                  <path className="er-edge" markerEnd="url(#er-arrow)" d={e.d}>
                    <title>{e.tip}</title>
                  </path>
                  {view.z >= 0.55 && (
                    <text className="er-elabel" x={e.lx} y={e.ly} textAnchor="middle">{e.label}</text>
                  )}
                </g>
              )
            })}
            {graph.tables.map((t) => {
              const p = pos[t.name]
              if (!p) return null
              const rows = erKeyRows(t)
              const cls = sel ? (t.name === sel ? ' sel' : related(t.name) ? '' : ' dim') : ''
              return (
                <g key={t.name} className={`er-node${cls}`} transform={`translate(${p.x},${p.y})`}
                   onPointerDown={(e) => nodeDown(e, t.name)}>
                  <title>Click to inspect every column</title>
                  <rect className="er-box" width={ER.W} height={erHeight(t)} rx="8" />
                  <line className="er-sep" x1="1" x2={ER.W - 1} y1={ER.HEAD} y2={ER.HEAD} />
                  <text className="er-title" x="10" y="17">{erTrunc(t.name, 24)}</text>
                  <text className="er-count" x={ER.W - 8} y="17" textAnchor="end">{t.col_count}c</text>
                  {rows.map((c, i) => (
                    <g key={c.name} transform={`translate(0,${ER.HEAD + i * ER.ROW})`}>
                      <text className={`er-key ${c.pk ? 'pk' : 'fk'}`} x="10" y="12">{c.pk ? 'PK' : 'FK'}</text>
                      <text className="er-col" x="34" y="12">{erTrunc(c.name, 25)}</text>
                    </g>
                  ))}
                  {rows.length === 0 && (
                    <text className="er-none" x="10" y={ER.HEAD + 12}>no key columns</text>
                  )}
                </g>
              )
            })}
          </g>
        )}
      </svg>
      <div className="er-tools">
        <button onClick={() => zoomBtn(1 / 1.2)} title="Zoom out" aria-label="Zoom out">−</button>
        <span className="er-zoom">{Math.round(view.z * 100)}%</span>
        <button onClick={() => zoomBtn(1.2)} title="Zoom in" aria-label="Zoom in">+</button>
        <button onClick={() => fit()} title="Fit the whole diagram in view">Fit</button>
        <button onClick={rearrange} title="Re-run the automatic layout">Re-arrange</button>
      </div>
      <div className="er-hint">
        Drag the background to pan · scroll to zoom · drag a table to move it · click one for all columns
      </div>
    </div>
  )
}
