// Estate Report — the closing page: the estate's governance stated, and the
// Policy-Generator handoff contract VERIFIED from facts on disk (registry
// parsed + id-matched, receipts, freshness) — never from ticked boxes.
// Field-commissioned: "a final page like a report summary … with some pretty
// summary graphs" + "checks that all the required estate docs are in place
// ready for Policy Generator".
import { useEffect, useState } from 'react'
import { apiPost } from './../api.js'
import { useWorkspace } from './../state.js'
import './report.css'

function downloadBlob(content, filename, type = 'text/html') {
  const url = URL.createObjectURL(new Blob([content], { type }))
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

const SENS_COLORS = { HIGH: 'var(--status-critical, #c62828)', MEDIUM: '#e08a00', LOW: 'var(--status-good, #2e7d32)' }

// horizontal bar list — the app's own idiom, no chart library
function Bars({ items, colorFor }) {
  const max = Math.max(1, ...items.map((i) => i.count))
  return (
    <div className="rp-bars">
      {items.map((i) => (
        <div className="rp-bar" key={i.name}>
          <span className="rp-barlbl" title={i.name}>{i.name}</span>
          <span className="rp-bartrack">
            <span className="rp-barfill" style={{ width: `${(i.count / max) * 100}%`,
                                                  background: colorFor ? colorFor(i.name) : 'var(--accent)' }} />
          </span>
          <b className="rp-barval">{i.count}</b>
        </div>
      ))}
    </div>
  )
}

// one full-width stacked bar for the sensitivity mix
function Stacked({ mix }) {
  const total = Object.values(mix).reduce((a, b) => a + b, 0) || 1
  const order = ['HIGH', 'MEDIUM', 'LOW']
  return (
    <div className="rp-stack" role="img"
         aria-label={order.map((k) => `${k} ${mix[k] || 0}`).join(', ')}>
      {order.filter((k) => mix[k]).map((k) => (
        <span key={k} className="rp-stackseg"
              style={{ width: `${((mix[k] || 0) / total) * 100}%`, background: SENS_COLORS[k] }}
              title={`${k}: ${mix[k]}`} />
      ))}
    </div>
  )
}

export default function ReportPage({ onNavigate }) {
  const ws = useWorkspace()
  const [rep, setRep] = useState(null)
  const [err, setErr] = useState(null)
  // Refresh used to give ZERO feedback — recomputing over unchanged facts
  // looks identical, which read as "Refresh doesn't work" (field-caught).
  // Now the button shows busy and stamps the time of the last compile.
  const [busy, setBusy] = useState(false)
  const [refreshedAt, setRefreshedAt] = useState(null)
  const glossaryName = (ws.glossaryName || ws.name || '').trim()

  const load = () => {
    setErr(null)
    setBusy(true)
    apiPost('/api/estate-report', { rows: ws.rows || [], glossary_name: glossaryName,
                                    governance: ws.governance || undefined })
      .then((d) => { setRep(d); setRefreshedAt(new Date().toLocaleTimeString()) })
      .catch((e) => setErr(e.message))
      .finally(() => setBusy(false))
  }
  useEffect(() => { load() }, [])   // eslint-disable-line react-hooks/exhaustive-deps

  if (err) return <section className="card"><h2>Estate report</h2><p className="warn">{err}</p></section>
  if (!rep) return <section className="card"><h2>Estate report</h2><p className="hint-line">Compiling…</p></section>

  const s = rep.stats
  const chips = [
    ['Terms kept', s.terms_kept], ['Dropped', s.terms_dropped],
    ['Categories', (s.categories || []).length],
    ['PII', s.pii], ['CDE', s.cde], ['LLM-enriched', s.enriched],
    ['With value evidence', s.with_evidence], ['Table-level', s.table_terms],
  ]

  const exportHtml = () => {
    const esc = (t) => String(t).replace(/&/g, '&amp;').replace(/</g, '&lt;')
    const bar = (i, max) =>
      `<div style="display:flex;align-items:center;gap:8px;margin:2px 0">
         <span style="width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap">${esc(i.name)}</span>
         <span style="flex:1;background:#eee;border-radius:4px"><span style="display:block;height:10px;border-radius:4px;background:#CC0000;width:${(i.count / max) * 100}%"></span></span>
         <b>${i.count}</b></div>`
    const maxCat = Math.max(1, ...(s.categories || []).map((c) => c.count))
    const html = `<!doctype html><meta charset="utf-8"><title>Estate report — ${esc(s.glossary)}</title>
<body style="font:14px/1.5 system-ui,Segoe UI,sans-serif;max-width:900px;margin:2rem auto;padding:0 1rem;color:#222">
<h1 style="border-bottom:3px solid #CC0000;padding-bottom:.3rem">Estate report — ${esc(s.glossary)}</h1>
<p>${chips.map(([l, v]) => `<b>${v}</b> ${esc(l)}`).join(' · ')}</p>
<h2>Terms by category</h2>${(s.categories || []).map((c) => bar(c, maxCat)).join('')}
<h2>Sensitivity</h2><p>${Object.entries(s.sensitivity || {}).map(([k, v]) => `<b>${esc(k)}</b> ${v}`).join(' · ')}</p>
<h2>Top tags</h2><p>${(s.tags_top || []).map((t) => `${esc(t.tag)} (${t.count})`).join(' · ')}</p>
${s.detection ? `<h2>Detection coverage</h2>
<p><b>${s.detection.patterns}</b> Data Pattern(s) (${esc(Object.entries(s.detection.patterns_by_seed || {}).map(([k, v]) => `${v} ${k}`).join(', '))}) ·
<b>${s.detection.dictionaries}</b> dictionar(ies) · <b>${s.detection.mapping_only}</b> mapping-only by design (links are first-class detection for dates/names/free measures) ·
<b>${s.detection.skipped}</b> skip(s):</p>
<p style="color:#555">${(s.detection.skip_groups || []).map((g) => `${esc(g.reason)} — ${g.count}`).join('<br>')}</p>` : ''}
${s.evidence ? `<h2>Evidence depth</h2>
<p>${s.evidence.pattern} format(s) · ${s.evidence.enum} vocabular(ies) · ${s.evidence.kind} recognised kind(s) · ${s.evidence.range} numeric range(s) (DQ, never identification) · ${s.evidence.signature} signature(s) · ${s.evidence.none} with no value evidence (links/vocabularies govern those)</p>` : ''}
${s.dq ? `<h2>Data-quality readiness</h2>
<p>${s.dq.format_checks} format · ${s.dq.allowed_value_checks} allowed-values · ${s.dq.range_checks} range check(s), every one traced to sampled data. Quality scored on ${s.dq.quality_scored} column(s)${s.dq.quality_mean != null ? ` (mean ${s.dq.quality_mean})` : ''}${s.dq.quality_low ? `, ${s.dq.quality_low} below 70` : ''}.</p>` : ''}
${(s.labels || []).length ? `<h2>Label families</h2>
<p>${s.labels.map((k) => `<b>${esc(k.key)}</b>: ${(k.values || []).map((v) => `${esc(v.value)} (${v.count})`).join(', ')}`).join('<br>')}</p>` : ''}
${s.sources ? `<h2>Estate footprint</h2>
<p>${s.sources.columns} column(s) across ${s.sources.tables} table(s)/file(s) in ${s.sources.schemas} schema(s)/store(s); ${s.sources.document_columns} document column(s).</p>` : ''}
${s.governance ? `<h2>Stewardship</h2>
<p>${s.governance.present ? `default steward: ${s.governance.default_steward ? 'set' : 'NOT SET'} · ${s.governance.category_overrides} category override(s)${(s.governance.label_keys || []).length ? ` · label keys: ${esc(s.governance.label_keys.join(', '))}` : ''}` : 'not set'}</p>` : ''}
<h2>Handoff contract — Policy Generator</h2>
<table style="border-collapse:collapse;width:100%">${(rep.contract || []).map((c) =>
  `<tr style="border-bottom:1px solid #ddd"><td style="padding:4px 8px">${c.ok ? '✅' : '❌'}</td>
   <td style="padding:4px 8px"><b>${esc(c.label)}</b></td>
   <td style="padding:4px 8px">${esc(c.detail || '')}</td>
   <td style="padding:4px 8px;color:#666">${esc(c.at || '')}</td></tr>`).join('')}</table>
<p style="font-weight:600;color:${rep.ready ? '#2e7d32' : '#c62828'}">${esc(rep.verdict || '')}</p>
<p style="color:#666">Generated ${new Date().toISOString().slice(0, 19).replace('T', ' ')} · PDC Glossary Generator</p>
</body>`
    const slug = (s.glossary || 'estate').toLowerCase().replace(/[^a-z0-9]+/g, '-')
    downloadBlob(html, `estate-report-${slug}.html`)
  }

  return (
    <>
      <section className="card">
        <h2>Estate report <span>{s.glossary} — the governance this run produced</span></h2>
        <p className={`summary ${rep.ready ? 'ok' : 'warn'}`}>
          {rep.ready ? '✓ ' : '⚠ '}{rep.verdict}
        </p>
        {(rep.contract || []).filter((c) => c.stale).map((c) => (
          <p key={c.key} className="hint-line">
            ⚠ <b>{c.label}</b> is stale — {String(c.detail || '').split('· ').pop()}{' '}
            <button className="nav" onClick={() => onNavigate('apply')}>Regenerate on Apply →</button>
            {' '}(Refresh only re-reads the facts; it cannot un-stale an artifact.)
          </p>
        ))}
        <div className="actions">
          <button className="ghost" onClick={load} disabled={busy}>
            {busy ? '↻ Compiling…' : '↻ Refresh'}
          </button>
          <button className="primary" onClick={exportHtml}
                  title="One self-contained HTML file — the per-estate report to commit next to the pack (print it for PDF).">
            ⬇ Export report (HTML)
          </button>
          {refreshedAt && <span className="notes">compiled {refreshedAt}</span>}
        </div>
        <p className="summary">
          {chips.map(([l, v]) => <span key={l} className="badge" style={{ marginRight: '.4rem' }}>{l} <b>{v}</b></span>)}
        </p>

        <h3 className="subhead">Terms by category</h3>
        <Bars items={(s.categories || []).map((c) => ({ name: c.name, count: c.count }))} />

        <h3 className="subhead">Sensitivity mix</h3>
        <Stacked mix={s.sensitivity || {}} />
        <p className="notes">
          {Object.entries(s.sensitivity || {}).map(([k, v]) => `${k} ${v}`).join(' · ')}
          {' '}· confidence: {Object.entries(s.confidence || {}).map(([k, v]) => `${k} ${v}`).join(' · ')}
        </p>

        <h3 className="subhead">Top tags</h3>
        <Bars items={(s.tags_top || []).map((t) => ({ name: t.tag, count: t.count }))} />

        {s.detection && (
          <>
            <h3 className="subhead">Detection coverage</h3>
            <p className="hint-line">
              How each kept term will be FOUND in the estate. <b>{s.detection.patterns}</b> Data
              Pattern(s) ({Object.entries(s.detection.patterns_by_seed || {})
                .map(([k, v]) => `${v} ${k}`).join(', ')}) and{' '}
              <b>{s.detection.dictionaries}</b> dictionar(ies) detect by value evidence;{' '}
              <b>{s.detection.mapping_only}</b> term(s) are governed by their term↔column links
              by design — dates, names and free measures, whose content shape cannot discriminate
              (the industry posture; links are first-class detection, not a gap). <b>{s.detection.skipped}</b> skip(s)
              remain, each with its reason:
            </p>
            <Bars items={(s.detection.skip_groups || []).map((g) => ({ name: g.reason, count: g.count }))} />
          </>
        )}

        {s.evidence && (
          <>
            <h3 className="subhead">Evidence depth</h3>
            <p className="hint-line">
              What profiling actually induced, facet by facet: <b>{s.evidence.pattern}</b> value
              format(s), <b>{s.evidence.enum}</b> reference vocabular(ies), <b>{s.evidence.kind}</b>{' '}
              recognised kind(s) (email/ZIP/date…), <b>{s.evidence.range}</b> numeric range(s)
              (ranges drive data-quality checks, never identification), <b>{s.evidence.signature}</b>{' '}
              shape signature(s). <b>{s.evidence.none}</b> kept term(s) carry no value evidence —
              typically table-level records and document terms, which are governed by links and
              vocabularies instead.
            </p>
          </>
        )}

        {s.dq && (
          <>
            <h3 className="subhead">Data-quality readiness</h3>
            <p className="hint-line">
              The drafted bundle re-expresses the same evidence as DQ expectations:{' '}
              <b>{s.dq.format_checks}</b> format check(s), <b>{s.dq.allowed_value_checks}</b>{' '}
              allowed-values check(s), <b>{s.dq.range_checks}</b> range check(s) — every one traces
              to sampled data, none invented. The scan quality-scored <b>{s.dq.quality_scored}</b>{' '}
              column(s){s.dq.quality_mean != null && <> (mean <b>{s.dq.quality_mean}</b>)</>}
              {s.dq.quality_low > 0 && <>, of which <b className="warn">{s.dq.quality_low}</b> score
              below 70 — worth a look before they feed the Trust Score</>}.
            </p>
          </>
        )}

        {(s.labels || []).length > 0 && (
          <>
            <h3 className="subhead">Label families</h3>
            <p className="hint-line">
              Governed key/value classifications derived from this review — created in PDC and
              stamped onto columns from the Apply page's Data labels card. A tag answers
              “is this in the set?”; a label answers “which one is it?”.
            </p>
            {s.labels.map((k) => (
              <p className="notes" key={k.key}>
                <b>{k.key}</b> — {(k.values || []).map((v) => `${v.value} (${v.count})`).join(' · ')}
              </p>
            ))}
          </>
        )}

        {s.sources && (
          <>
            <h3 className="subhead">Estate footprint</h3>
            <p className="hint-line">
              The kept terms bind to <b>{s.sources.columns}</b> physical column(s) across{' '}
              <b>{s.sources.tables}</b> table(s)/file(s) in <b>{s.sources.schemas}</b> schema(s)
              or store(s); <b>{s.sources.document_columns}</b> of those columns live in documents
              (CSV/JSON/PDF in the object store) rather than database tables.
            </p>
          </>
        )}

        {s.governance && (
          <>
            <h3 className="subhead">Stewardship</h3>
            <p className="hint-line">
              {s.governance.present ? (
                <>Stewardship is set: {s.governance.default_steward
                  ? <>a <b>default Business Steward</b> covers every category</>
                  : <b className="warn">no default steward — terms may export unowned</b>}
                {s.governance.category_overrides > 0 && <>, with <b>{s.governance.category_overrides}</b>{' '}
                  per-category override(s)</>}
                {(s.governance.label_keys || []).length > 0 && <>; kept label keys:{' '}
                  {s.governance.label_keys.join(', ')}</>}.</>
              ) : (
                <>No stewardship set yet — the Govern page binds steward/owner/custodian, and it
                bakes into the export.</>
              )}
            </p>
          </>
        )}
      </section>

      <section className="card">
        <h2>Handoff contract <span>Policy Generator — verified from disk, not ticks</span></h2>
        <div className="table-scroll">
          <table>
            <thead><tr><th></th><th>Artifact</th><th>State</th><th>When</th></tr></thead>
            <tbody>
              {(rep.contract || []).map((c) => (
                <tr key={c.key}>
                  <td>{c.ok ? '✅' : '❌'}</td>
                  <td><b>{c.label}</b>{c.stale && <span className="badge warning" style={{ marginLeft: '.35rem' }}>stale</span>}</td>
                  <td>{c.detail}{c.path && <div className="notes"><code>{c.path}</code></div>}</td>
                  <td className="notes">{c.at || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!rep.ready && (
          <p className="hint-line">
            Missing or stale artifacts are minted where they live: <b>Generate JSONL</b> and{' '}
            <b>Draft policies</b> on the <button className="nav" onClick={() => onNavigate('apply')}>Apply →</button> page,
            the <b>domain pack</b> on the <button className="nav" onClick={() => onNavigate('dictionary')}>Dictionary →</button> page.
          </p>
        )}
      </section>
    </>
  )
}
