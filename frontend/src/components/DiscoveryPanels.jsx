// Discovery result panels — shared so they render where the data belongs:
// the database profile on the SCHEMA page (tables), the bucket profile on the
// FILES page (charts). They used to live only on Connect, beside the button
// that produced them ("can those be displayed for schema - tables and Files -
// charts?"). Pure presentation: the pages own the data and the actions.
import { useState } from 'react'

const fmtBytes = (b) => {
  if (b == null) return '—'
  const u = ['B', 'KB', 'MB', 'GB', 'TB']
  let i = 0
  let n = Number(b) || 0
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++ }
  return (i ? n.toFixed(n < 10 ? 1 : 0) : n) + ' ' + u[i]
}

const pct = (x) => Math.round((x || 0) * 100) + '%'

const FTYPE_COLORED = new Set(['pdf', 'docx', 'doc', 'csv', 'tsv', 'xlsx', 'xls', 'json', 'xml', 'txt', 'md'])

const ftypeClass = (ext) => {
  const e = (ext || '').toLowerCase()
  return `ftype ftype-${FTYPE_COLORED.has(e) ? e : 'other'}`
}

const extOf = (key) => {
  const b = (key || '').split('/').pop()
  const i = b.lastIndexOf('.')
  return i > 0 ? b.slice(i + 1).toLowerCase() : ''
}

const splitKey = (key) => {
  const i = (key || '').lastIndexOf('/')
  return i >= 0 ? [key.slice(0, i + 1), key.slice(i + 1)] : ['', key || '']
}

function MiniBar({ frac }) {
  return <span className="mini"><i style={{ width: pct(frac) }} /></span>
}

/* ================= column profiling (database discovery) ================= */

const SENS_CLS = { HIGH: 'sens-hi', MEDIUM: 'sens-md', LOW: 'sens-lo' }

export function ProfilePanel({ profile, onNavigate }) {
  const d = profile.data
  const s = d.summary || {}
  const harvested = d.source === 'harvest'
  const tiles = [
    ['Tables', s.tables], ['Columns', s.columns],
    ['Total rows', (s.rows || 0).toLocaleString()],
    ...(harvested ? [] : [['Database size', fmtBytes(s.db_bytes || 0)]]),
    ...(s.profiled != null ? [['With evidence', `${s.profiled}/${s.columns || 0}`]] : []),
    ['PII columns', s.pii], ['CDE columns', s.cde],
    ['Classified', s.classified != null ? s.classified : '—'],
    ['Avg complete', s.avg_completeness != null ? pct(s.avg_completeness) : '—'],
    ['Keys (PK·FK)', `${s.pk_cols || 0}·${s.fk_cols || 0}`],
    ['Empty tables', s.empty],
  ]
  const sev = s.sensitivity || {}
  const conf = s.confidence || {}
  // Which tables need the steward's eye: weak terms, and how much of the
  // table arrived with profiling evidence behind it.
  const weak = (d.tables || [])
    .map((t2) => ({ name: t2.name,
                    low: t2.low_confidence || 0,
                    cols: (t2.columns || []).length,
                    profiled: t2.profiled_columns }))
    .filter((x) => x.low > 0)
    .sort((a, b) => b.low - a.low)
    .slice(0, 8)
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
      {(conf.High || conf.Medium || conf.Low || s.profiled != null) && (
        <div className="disc-grid" style={{ marginBottom: '.6rem' }}>
          <div className="disc-box">
            <div className="disc-head"><h3>Term confidence</h3>
              <span className="disc-count">{(conf.High || 0) + (conf.Medium || 0) + (conf.Low || 0)}</span></div>
            {['High', 'Medium', 'Low'].map((k) => {
              const tot = Math.max(1, (conf.High || 0) + (conf.Medium || 0) + (conf.Low || 0))
              return (
                <div key={k} className="disc-row">
                  <span className="disc-lbl">{k}</span>
                  <MiniBar frac={(conf[k] || 0) / tot} />
                  <span className="disc-val">{conf[k] || 0}</span>
                </div>
              )
            })}
          </div>
          <div className="disc-box">
            <div className="disc-head"><h3>Tables with low-confidence terms</h3>
              <span className="disc-count">{weak.length}</span></div>
            {weak.map((w) => (
              <div key={w.name} className="disc-row">
                <span className="disc-lbl" title={w.name}>{w.name}</span>
                <MiniBar frac={w.cols ? w.low / w.cols : 0} />
                <span className="disc-val">{w.low}/{w.cols}</span>
              </div>
            ))}
            {weak.length === 0 && <p className="hint-line">none — every term carries medium or better</p>}
          </div>
        </div>
      )}
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

export function DocsPanel({ docs, onRefilter }) {
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
      <div className="discovery-grid">
        <div className="disc-panel">
          <div className="disc-head"><h3>By file type</h3><span className="disc-count">{(d.by_type || []).length}</span></div>
          <div className="type-bars">
            {(d.by_type || []).map((t) => (
              <div className={`type-bar ${ftypeClass(t.ext)}`} key={t.ext}>
                <span><code>{t.ext}</code></span>
                <span className="tb-track"><span className="tb-fill" style={{ width: pct(t.count / maxCount), display: 'block' }} /></span>
                <span className="tb-num"><b>{t.count.toLocaleString()}</b> · {fmtBytes(t.bytes)}</span>
              </div>
            ))}
            {(d.by_type || []).length === 0 && <p className="hint-line">none</p>}
          </div>
        </div>
        <div className="disc-panel">
          <div className="disc-head"><h3>By folder</h3><span className="disc-count">{(d.by_folder || []).length}</span></div>
          <div className="folder-list">
            {(d.by_folder || []).map((f) => (
              <div className="folder-row" key={f.name}>
                <span className="fr-name" title={f.name}>{f.name}</span>
                <span className="fr-count">{f.count.toLocaleString()}</span>
                <span className="fr-track"><span className="fr-fill" style={{ width: pct(f.bytes / maxFolder), display: 'block' }} /></span>
                <span className="fr-size">{fmtBytes(f.bytes)}</span>
              </div>
            ))}
            {(d.by_folder || []).length === 0 && <p className="hint-line">none</p>}
          </div>
        </div>
        <div className="disc-panel">
          <div className="disc-head"><h3>Largest objects</h3><span className="disc-sub">by size</span></div>
          <div className="obj-list">
            {(d.largest || []).map((o) => {
              const [dir, name] = splitKey(o.key)
              return (
                <div className={`obj-row ${ftypeClass(extOf(o.key))}`} key={o.key} title={o.key}>
                  <span className="ext-dot" />
                  <span className="obj-key"><span className="obj-dir">{dir}</span><span className="obj-name">{name}</span></span>
                  <span className="obj-meta">{fmtBytes(o.bytes)}</span>
                </div>
              )
            })}
            {(d.largest || []).length === 0 && <p className="hint-line">none</p>}
          </div>
        </div>
        <div className="disc-panel">
          <div className="disc-head"><h3>Most recent</h3><span className="disc-sub">by date</span></div>
          <div className="obj-list">
            {(d.newest || []).map((o) => {
              const [dir, name] = splitKey(o.key)
              return (
                <div className={`obj-row ${ftypeClass(extOf(o.key))}`} key={o.key} title={o.key}>
                  <span className="ext-dot" />
                  <span className="obj-key"><span className="obj-dir">{dir}</span><span className="obj-name">{name}</span></span>
                  <span className="obj-meta">{(o.modified || '').slice(0, 10)}</span>
                </div>
              )
            })}
            {(d.newest || []).length === 0 && <p className="hint-line">none</p>}
          </div>
        </div>
      </div>
    </section>
  )
}
