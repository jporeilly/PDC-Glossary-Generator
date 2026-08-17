// Apply page — the port of the old UI's "Resolve Term IDs" page
// (static/js/09-apply.js + 08-resolve-dups.js exportDataElements/resolve, and
// templates/index.html #page-apply): generate & export the glossary JSONL,
// authenticate against PDC once, pull the term↔column links, resolve and stamp
// real term ids (with fuzzy + AI matching for renamed terms), then apply with a
// dry-run preview before any write — sensitivity, CDE, verified-lineage,
// rating, table/folder rollups and Trust Score follow. Long work runs through
// the background-job twins (runJob → POST /api/jobs/* + poll), never the
// legacy SSE streams.
import { useEffect, useRef, useState } from 'react'
import { apiGet, apiPost, runJob } from './../api.js'
import { patchRow, setPdcSession, usePersistentState, useResumableJob, useWorkspace } from './../state.js'
import './apply.css'

const truthy = (v) => ['y', 'yes', 'true', '1'].includes(String(v ?? 'Y').toLowerCase())

function downloadBlob(content, filename, type = 'application/json') {
  const url = URL.createObjectURL(new Blob([content], { type }))
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  setTimeout(() => URL.revokeObjectURL(url), 5000)
}

// status → badge (color always pairs with a label)
function StatusBadge({ s }) {
  const map = {
    planned: ['accent', 'planned'],
    applied: ['good', 'applied ✓'],
    'file-level': ['good', 'files ✓'],
    'not-found': ['warning', 'not found'],
    error: ['serious', 'error'],
    pending: ['neutral', '—'],
  }
  const [cls, label] = map[s] || ['neutral', s || '—']
  return <span className={`badge ${cls}`}>{label}</span>
}

const ShortId = ({ id }) => (id ? <code title={id}>{String(id).slice(0, 8)}…</code> : '—')

// backend "check" payloads ({title, rows, issues, tone, verdict})
function CheckBlock({ check }) {
  if (!check) return null
  const icon = check.tone === 'bad' ? '✕' : check.tone === 'warn' ? '⚠' : '✓'
  return (
    <div className="summary">
      <b>{icon} {check.title}</b>
      {(check.rows || []).map((r) => <span key={r.label}> · {r.label}: <b>{r.value}</b></span>)}
      {(check.issues || []).map((i, k) => (
        <div key={k} className={i.tone === 'bad' ? 'warn' : undefined}>
          · {i.text}
          {/* offenders on their OWN line, each carrying its location —
              "Status" inline at the end of a three-line sentence still sent
              the steward hunting ("the build check is still not clear") */}
          {(i.terms || []).length > 0 && (
            <div style={{ margin: '.2rem 0 .35rem 1.1rem', display: 'flex',
                          flexWrap: 'wrap', gap: '.35rem' }}>
              {i.terms.map((t) => <code key={t.label}>{t.label}</code>)}
            </div>
          )}
        </div>
      ))}
      {check.verdict && <div>{check.verdict}</div>}
    </div>
  )
}

export default function ApplyPage({ onNavigate }) {
  const ws = useWorkspace()
  const [settings, setSettings] = useState(null)
  // "all pages should be able to maintain their state if another page is
  // selected and you go back" — results and inputs ride the session cache
  // (usePersistentState); busy flags and anything refetched on mount stay
  // transient. Auth lives under 'pdc.' so a glossary switch (which clears
  // 'apply.') keeps the sign-in.
  const [conn, setConn] = usePersistentState('pdc.applyConn', {
    base: '', ver: 'v3', realm: 'pdc', user: '', pass: '', token: '', verify: false,
  })
  const [de, setDe] = usePersistentState('apply.de', null) // /api/data-elements response; Resolve stamps ids into de.json

  useEffect(() => {
    apiGet('/api/settings')
      .then((s) => {
        setSettings(s)
        setConn((c) => ({
          ...c,
          base: s.pdc_base != null ? s.pdc_base : c.base,
          realm: s.pdc_realm || c.realm,
          ver: s.pdc_ver || c.ver,
          verify: s.pdc_verify != null ? !!s.pdc_verify : c.verify,
        }))
      })
      .catch(() => setSettings({}))
  }, [])

  const glossaryName = ws.glossaryName || settings?.glossary_name || 'Business Glossary'

  // the shared PDC connection fields used by resolve / apply / profiling / compare
  const authBody = () => ({
    base_url: conn.base.trim(),
    version: conn.ver,
    realm: (conn.realm || 'pdc').trim(),
    username: conn.user,
    password: conn.pass,
    token: conn.token.trim(),
    verify_tls: conn.verify,
  })

  // persist the non-secret connection fields exactly like the old savePdcConn()
  const saveConn = (patch) => {
    setConn((c) => {
      const next = { ...c, ...patch }
      apiPost('/api/settings', {
        pdc_base: next.base.trim(),
        pdc_realm: (next.realm || 'pdc').trim(),
        pdc_ver: next.ver,
        pdc_verify: next.verify,
      }).catch(() => {})
      return next
    })
  }

  return (
    <>
      <div className="page-head">
        <h1>Resolve Term IDs</h1>
        <p className="psub">
          Push the glossary you built to your PDC instance over the public API — authenticate
          once, resolve term IDs, then apply with a dry-run. The glossary itself is imported in
          PDC's UI; everything here writes the term↔column links, sensitivity, CDE,
          verified-lineage and rating onto the columns.
        </p>
      </div>

      <details className="uth">
        <summary>Under the hood — generating the JSONL</summary>
        <div className="uth-body">
          <p>
            Entirely local. Nothing is sent anywhere: this turns the reviewed grid into the file
            PDC's <b>Business Glossary → Import</b> expects, and you can read it before it goes.
          </p>
          <ol className="uth-steps">
            <li>
              <b>One line per object</b>, in dependency order — a <code>glossary</code> line, then a{' '}
              <code>category</code> per distinct category, then a <code>term</code> per kept row.
              Each carries its stewardship, sensitivity, rating and tags.
            </li>
            <li>
              <b>Ids are derived, not requested.</b> Every <code>_id</code> is a{' '}
              <code>UUID5</code> of the glossary name plus the object's name, so the same inputs
              produce the same ids on any machine with no PDC round-trip. That is what makes a
              re-import update in place rather than duplicate.
            </li>
            <li>
              <b>The Registry is written alongside</b> —{' '}
              <code>registries/registry.&lt;glossary&gt;.json</code>, one row per concept with its
              term, governed tags, rule-derived sensitivity and category, plus the detection seeds
              (value patterns, reference lists) and PK/FK facts the Policy Generator reads. The
              JSONL is the deliverable; the Registry is the asset that keeps the glossary and the
              identification methods from diverging.
            </li>
          </ol>
          <p className="uth-note">
            Terms export as <b>Draft</b> — proposals until a Business Steward approves them in PDC.
            And the import <b>replaces the whole glossary</b>, which is safe precisely because the
            ids are deterministic: same names in, same ids out.
          </p>
        </div>
      </details>

      <details className="card">
        <summary>Why generate &amp; import the glossary <i>before</i> you resolve?</summary>
        <p className="hint-line">
          A business-term link only binds to its glossary when it carries <b>both</b> an{' '}
          <code>id</code> and a <code>glossaryId</code> — and those identifiers don't exist until
          the term itself exists inside PDC. The term is created when you <b>import the generated
          JSONL</b> (PDC's <b>Business Glossary → Import</b>). So the order is forced by PDC's
          data model:
        </p>
        <p className="hint-line">
          <b>Govern → Generate JSONL → Import in PDC → Resolve → Apply.</b> <b>Resolve</b>{' '}
          searches PDC for each term by name and stamps the real <code>id</code>/<code>glossaryId</code>{' '}
          back onto your links; <b>Apply</b> then PATCHes those resolved links (plus sensitivity,
          CDE, lineage and rating) onto the column entities. Skip the import and Resolve finds
          nothing — the columns would get a name-only term with no glossary behind it (the "—"
          you see in PDC).
        </p>
      </details>

      {/* Connection FIRST: the Generate card's own preflight (the PDC tree
          check) and everything below need the session — clicking top-down
          hit "base URL required" before the sign-in card had even been seen
          (field-caught: "PDC Connection should be before Generate JSONL"). */}
      <ConnectionCard conn={conn} setConn={setConn} saveConn={saveConn} />
      <GenerateCard rows={ws.rows} glossaryName={glossaryName} governance={ws.governance}
                    settings={settings} onNavigate={onNavigate} authBody={authBody} />
      <DataElementsCard rows={ws.rows} glossaryName={glossaryName} de={de} setDe={setDe} />
      <ResolveCard de={de} setDe={setDe} authBody={authBody} glossaryName={glossaryName}
                   rows={ws.rows} settings={settings} />
      <LabelsCard rows={ws.rows} authBody={authBody} />
      {/* Discovery BEFORE Apply: PDC only mints file-column entities when its
          own Data Discovery runs, so applying first reported every document
          column "not found" (field-caught: "surely this step should come
          before"). The card also now says the honest thing — the APP profiled
          these files at scan time; PDC has not. */}
      <ProfilingCard de={de} authBody={authBody} />
      <ApplyCard de={de} authBody={authBody} glossaryName={glossaryName} rows={ws.rows} conn={conn} />
      {ws.discovery?.tables?.length > 0 && (
        <CompareCard discovery={ws.discovery} authBody={authBody} />
      )}
    </>
  )
}

/* ---------- step 0: generate the import JSONL (+ Registry) and draft policies ---------- */

function GenerateCard({ rows, glossaryName, governance, settings, onNavigate, authBody }) {
  const keptRows = rows.filter((r) => truthy(r.Keep))
  const kept = keptRows.length
  // Stewardship is optional and nothing gates it: the JSONL exports, PDC accepts
  // it, and every term arrives owned by nobody. That is the governance the
  // glossary exists to establish, so its absence is worth a sentence here rather
  // than a discovery in a review meeting three weeks later.
  // A term exports UNOWNED only if the governance that actually bakes the
  // JSONL (category override → default steward) yields nobody for it, and no
  // stamped row-level steward exists either. The old check read r.Steward —
  // a field nothing writes — so it warned on all 114 terms seconds after
  // Govern stamped all 114 (field-caught).
  const gDef = String((governance && governance.default && governance.default.businessSteward) || '').trim()
  const gCats = (governance && governance.categories) || {}
  const unowned = keptRows.filter((r) =>
    !gDef
    && !String(((gCats[r.Category] || {}).businessSteward) || '').trim()
    && !String(r.Business_Steward_ID || r.Business_Steward || '').trim()).length
  const [gen, setGen] = usePersistentState('apply.gen', null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  // PDC-tree preflight: what does PDC hold under this glossary that the
  // export no longer carries? Imports update terms in place but never REMOVE
  // categories, so earlier eras linger in the tree unless deleted first
  // (field-caught: three naming generations in one glossary).
  const [tree, setTree] = usePersistentState('apply.tree', null)
  const [treeBusy, setTreeBusy] = useState(false)

  async function checkTree() {
    setTreeBusy(true)
    setTree(null)
    setError(null)   // a prior failure must not outlive its retry — the
                     // banner sat next to "✓ tree matches" (field-caught)
    try {
      const cats = [...new Set(keptRows.map((r) => r.Category).filter(Boolean))]
      setTree(await apiPost('/api/pdc/glossary-tree-check', {
        ...authBody(), glossary: glossaryName.trim(), categories: cats,
      }))
    } catch (e) {
      setError(e.message)
    } finally {
      setTreeBusy(false)
    }
  }
  const [draft, setDraft] = usePersistentState('apply.draft', null)
  const [draftBusy, setDraftBusy] = useState(false)
  // live narration while the draft job runs — {phase, done, total, detail}
  const [draftProg, setDraftProg] = useState(null)
  const [draftAi, setDraftAi] = usePersistentState('apply.draftAi', true)
  // the draft runs as a RESUMABLE job: navigate away mid-draft and the poll
  // re-attaches on return, the result landing in the session-cached `draft`
  const draftJob = useResumableJob('apply.draftJob', {
    onBusy: (b) => setDraftBusy(b),
    onTick: (j) => setDraftProg(j),
    onDone: (result, job) => { setDraft({ ...result, _job: job.id }); setDraftProg(null) },
    onError: (e) => { setError(e); setDraftProg(null) },
    onLost: () => setDraftProg(null),
  })
  // In-place detection flips — "is there an easy way to flip without having
  // to go back and forth between pages?" The draft's own mapping-only and
  // skip lists carry the flip button, the row updates right here (same
  // autosaving mutation Review uses), and the next Draft honours it.
  const [flipped, setFlipped] = usePersistentState('apply.flipped', {})   // {term: '' (Auto) | 'mapping_only'}
  function flipTerm(term, intent) {
    const i = rows.findIndex((r) => String(r.Term || '').trim() === term)
    if (i < 0) return
    patchRow(i, { Detection_Intent: intent })
    setFlipped((f) => ({ ...f, [term]: intent }))
  }
  const flipCount = Object.keys(flipped).length
  // "Send to lab": upload the artifact to the lab MinIO over a saved connection
  const [labConns, setLabConns] = useState([])
  const [labConn, setLabConn] = usePersistentState('pdc.labConn', '')
  const [labBusy, setLabBusy] = useState(false)
  const [labMsg, setLabMsg] = useState(null)
  const [labStatus, setLabStatus] = useState(null)  // {state:'checking'|'ok'|'bad', message}

  useEffect(() => {
    apiGet('/api/connections')
      .then((d) => {
        const stores = (d.connections || []).filter((c) => ['minio', 's3'].includes(String(c.type || '').toLowerCase()))
        setLabConns(stores)
        // prefer the dedicated lab store (Settings) when present, else the first
        const lab = stores.find((c) => c.id === 'lab-minio')
          || stores.find((c) => String(c.name || '').toLowerCase() === 'lab minio')
          || stores[0]
        // default only when nothing is picked — a session-cached pick from a
        // previous visit must survive the remount
        if (lab) setLabConn((cur) => cur || lab.id || lab.name)
      })
      .catch(() => {})
  }, [])

  // Live connectivity for the status dot: re-check whenever the selected lab
  // connection changes (and on first load once it's set).
  useEffect(() => {
    if (!labConn) { setLabStatus(null); return undefined }
    let stale = false
    setLabStatus({ state: 'checking', message: 'Checking lab MinIO…' })
    apiPost('/api/lab-minio-status', { connection: labConn })
      .then((d) => { if (!stale) setLabStatus({ state: d.ok ? 'ok' : 'bad', message: d.message || (d.ok ? 'Connected' : 'Not connected') }) })
      .catch((e) => { if (!stale) setLabStatus({ state: 'bad', message: e.message }) })
    return () => { stale = true }
  }, [labConn])

  async function sendToLab(kind) {
    setLabBusy(true)
    setLabMsg(null)
    try {
      let payload
      if (kind === 'jsonl') {
        payload = {
          filename: `${gen.stats?.glossary || 'glossary-import'}.jsonl`,
          text: gen.jsonl, content_type: 'application/x-ndjson',
        }
      } else {
        // the policies bundle is binary — stream it from the draft job when
        // one ran (it carries the AI polish; re-drafting here would lose it),
        // else regenerate deterministically, then base64 it over
        const res = draft?._job
          ? await fetch(`/api/jobs/${draft._job}/zip`)
          : await fetch('/api/draft-policies', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ rows, glossary_name: glossaryName, format: 'zip' }),
            })
        if (!res.ok) throw new Error(res.statusText)
        const buf = new Uint8Array(await res.arrayBuffer())
        let bin = ''
        for (let i = 0; i < buf.length; i += 0x8000) bin += String.fromCharCode(...buf.subarray(i, i + 0x8000))
        payload = { filename: 'drafted-policies.zip', b64: btoa(bin), content_type: 'application/zip' }
      }
      const d = await apiPost('/api/lab-export', { ...payload, connection: labConn })
      setLabMsg(
        <span className="ok">
          ✓ Sent to lab MinIO ({d.connection}) — <code>{d.bucket}/{d.key}</code> · on the VM:
          MinIO console <code>:9001</code> or <code>mc cp</code> to <code>~/Downloads</code>.
        </span>,
      )
    } catch (e) {
      setLabMsg(<span className="warn">Send to lab failed: {e.message}</span>)
    } finally {
      setLabBusy(false)
    }
  }

  // ghost export button (Generate/Draft stay the drivers) + a picker when
  // several MinIO/S3 connections are saved, plus a live connectivity dot
  const labExportControls = (kind) => {
    const st = labStatus?.state
    const dotCls = st === 'ok' ? 'ok' : st === 'checking' ? 'checking' : st === 'bad' ? 'bad' : 'muted'
    const label = !labConns.length ? 'no lab store configured'
      : st === 'ok' ? 'lab MinIO connected'
      : st === 'checking' ? 'checking…'
      : st === 'bad' ? 'lab MinIO not connected'
      : 'lab MinIO'
    return (
      <>
        {labConns.length > 1 && (
          <select value={labConn} onChange={(e) => setLabConn(e.target.value)}
                  title="Which saved MinIO/S3 connection receives the export">
            {labConns.map((c) => <option key={c.id || c.name} value={c.id || c.name}>{c.name}</option>)}
          </select>
        )}
        <button className="ghost" onClick={() => sendToLab(kind)}
                disabled={labBusy || !labConns.length}
                title={labConns.length
                  ? (st === 'bad' ? (labStatus?.message || 'Lab MinIO not reachable')
                     : 'Upload to the lab MinIO (bucket pdc-exports, created if missing) so you can grab it on the VM')
                  : 'Configure the lab MinIO in Settings first'}>
          {labBusy ? 'Sending…' : '⇪ Send to lab (MinIO)'}
        </button>
        <span className="conn" style={{ fontSize: '.82rem' }} title={labStatus?.message || 'lab MinIO connectivity'}>
          <span className={`dot ${dotCls}`} />{label}
        </span>
        {(st === 'bad' || !labConns.length) && (
          <button className="nav" onClick={() => onNavigate('settings')}
                  title="Open Settings → Lab object store to set the endpoint / credentials">
            Configure →
          </button>
        )}
      </>
    )
  }

  async function generate() {
    setBusy(true)
    setError(null)
    try {
      // include the Govern page's stewardship (shared workspace) when set —
      // same `governance` key the legacy UI sends to POST /api/generate
      setGen(await apiPost('/api/generate', {
        rows, glossary_name: glossaryName,
        ...(governance ? { governance } : {}),
      }))
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  async function draftPolicies() {
    setError(null)
    setFlipped({})   // the new draft reads the flipped rows — staged marks are spent
    setDraftProg({ phase: 'starting', done: 0, total: 0, detail: '' })
    try {
      // Resumable job, not an awaited poll: the AI polish is one model call
      // per rule and can run for minutes — leave the page and the poll
      // re-attaches on return, the result landing in the cached draft. The
      // job id rides along so the bundle downloads from the job WITH the
      // polish.
      await draftJob.start('draft-policies', {
        rows, glossary_name: glossaryName, ai: draftAi,
        // the steward's kept label keys ride into the bundle's labels.json
        label_keys: governance?.labelKeys || [],
        model: settings?.model || null, compute: settings?.compute,
      })
    } catch (e) {
      setError(e.message)
      setDraftProg(null)
    }
  }

  // the zip bundle is binary, so this one download bypasses the JSON wrapper.
  // A job-drafted bundle streams from the job — it carries the AI polish;
  // re-POSTing would re-draft deterministically and silently lose the hints.
  async function downloadDraftZip() {
    setError(null)
    try {
      const res = draft?._job
        ? await fetch(`/api/jobs/${draft._job}/zip`)
        : await fetch('/api/draft-policies', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ rows, glossary_name: glossaryName, format: 'zip' }),
          })
      if (!res.ok) throw new Error(res.statusText)
      downloadBlob(await res.blob(), 'drafted-policies.zip', 'application/zip')
    } catch (e) {
      setError(`Draft bundle failed: ${e.message}`)
    }
  }

  return (
    <section className="card">
      <h2>Generate import JSONL <span>kept terms → PDC Business Glossary → Import (also writes the Registry)</span></h2>
      <p className="hint-line">
        Exports the <b>{kept}</b> kept term(s) as import-ready JSONL and authors the Registry for
        the Policy Generator. Stewardship set on the <b>Govern</b> page is saved with the
        workspace and {governance ? <b>is baked into this export</b> : <>baked in once set —
        none is set yet, so this exports the reviewed grid as-is</>}.
      </p>
      {unowned > 0 && (
        <div className="notice-warn">
          <b>{unowned} of {kept} term(s) will export with no steward.</b> The file imports
          cleanly and PDC will not object — the terms simply arrive owned by nobody, which is
          the governance a glossary exists to establish.
          {' '}
          <button className="linkish" onClick={() => onNavigate?.('govern')}>
            Set stewardship on Govern →
          </button>
          <br />
          Fine for a draft you are circulating for comment. Not fine for the version someone
          will be asked to defend.
        </div>
      )}
      <div className="actions" style={{ marginTop: 0 }}>
        <button className="ghost" disabled={treeBusy || !glossaryName.trim() || !authBody}
                onClick={checkTree}
                title="Read the categories PDC currently holds under this glossary and compare them with this export. Imports update terms in place but never REMOVE categories, so folders from earlier imports linger unless deleted in PDC first. Uses the PDC connection card above — sign in there first.">
          {treeBusy ? 'Checking PDC tree…' : 'Check PDC tree for lingering categories'}
        </button>
        {tree && !tree.exists && (
          <span className="notes">glossary “{glossaryName.trim()}” is not in PDC yet — the first import creates it clean.</span>
        )}
        {tree && tree.exists && tree.lingering.length === 0 && (
          <span className="notes">✓ PDC&apos;s tree matches this export{tree.partial ? ' (large tree — the scan may be partial)' : ''}.</span>
        )}
      </div>
      {tree && tree.exists && tree.lingering.length > 0 && (
        <div className="notice-warn">
          <b>{tree.lingering.length} categor{tree.lingering.length === 1 ? 'y' : 'ies'} in PDC
          that this export no longer carries:</b> {tree.lingering.join(' · ')}.
          Import updates terms in place but never removes categories — these folders will
          linger in PDC&apos;s tree. Delete them (or the whole glossary) in PDC before
          importing, or accept the residue deliberately.
          {tree.partial ? ' Large tree — the scan may be partial.' : ''}
        </div>
      )}
      {error && <div className="error">{error}</div>}
      <div className="actions">
        <button className="primary" onClick={generate} disabled={busy || kept === 0}
                title={kept ? 'Export the kept terms as PDC-importable JSONL' : 'Keep at least one term on the Review page first'}>
          {busy ? 'Generating…' : `Generate JSONL (${kept})`}
        </button>
        {gen && (
          <button className="ghost" onClick={() => downloadBlob(gen.jsonl, 'glossary-import.jsonl', 'application/x-ndjson')}>
            ⬇ Download {gen.stats?.glossary || 'glossary'}.jsonl
          </button>
        )}
        {gen && labExportControls('jsonl')}
        <button className="ghost" onClick={() => onNavigate('govern')}>← Govern &amp; stewardship</button>
      </div>
      {gen && (
        <p className="summary">
          <b>{gen.stats.lines}</b> line(s) — <b>{gen.stats.categories}</b> categories,{' '}
          <b>{gen.stats.terms}</b> terms · kept <b>{gen.stats.kept}</b> / dropped {gen.stats.dropped}
          {gen.registry && <> · Registry written to <code>{gen.registry}</code></>}
        </p>
      )}
      {gen?.check && <CheckBlock check={gen.check} />}

      <h3 className="subhead">Draft policies (AI)</h3>
      <p className="hint-line">
        The Policy Generator's first mile: induced value patterns become PDC Data Patterns,
        profiled reference lists become Dictionaries (+ values CSV). Deterministic core; with AI
        on, the local LLM polishes each rule's column regex and tag pick (guard-railed).
      </p>
      <div className="actions">
        <button className="ghost" onClick={draftPolicies} disabled={draftBusy || rows.length === 0}>
          {draftBusy ? 'Drafting…' : 'Draft policies'}
        </button>
        <label className="check">
          <input type="checkbox" checked={draftAi} onChange={(e) => setDraftAi(e.target.checked)} />
          AI polish (local LLM)
        </label>
        {draftProg && (
          <span className="notes" aria-live="polite">
            {draftProg.phase === 'polish'
              ? <>AI polish · rule <b>{draftProg.done}</b> of <b>{draftProg.total}</b>
                  {draftProg.detail ? <> — {draftProg.detail}</> : null}</>
              : draftProg.phase === 'seeds' ? 'collecting detection seeds…'
              : draftProg.phase === 'assemble' ? 'assembling rules & bundle…'
              : 'starting…'}
          </span>
        )}
        {draft && (
          <button className="ghost" onClick={downloadDraftZip}>⬇ Download bundle (zip)</button>
        )}
        {draft && labExportControls('zip')}
      </div>
      {labMsg && <p className="summary">{labMsg}</p>}
      {draft && (
        <div className="summary">
          <b>{draft.patterns.length}</b> data pattern(s), <b>{draft.dictionaries.length}</b>{' '}
          dictionar{draft.dictionaries.length === 1 ? 'y' : 'ies'}
          {(() => {
            const all = [...draft.patterns, ...draft.dictionaries]
            const cur = all.filter((x) => x.seed === 'curated').length
            const prof = all.filter((x) => x.seed !== 'curated').length
            return <> · <b>{prof}</b> custom (profiled){cur ? <> · <b>{cur}</b> from curated pack seeds</> : ''}</>
          })()}
          {draft.used_llm ? ' · AI-polished' : draftAi ? ' · Ollama offline — deterministic only' : ''}
          {draft.patterns.map((p) => (
            <div key={p.filename}>· pattern <code>{p.filename}</code> — {p.term} ({p.seed})</div>
          ))}
          {draft.dictionaries.map((d) => (
            <div key={d.filename}>· dictionary <code>{d.filename}</code> — {d.term} ({d.seed || 'profiled'}, values: <code>{d.values}</code>)</div>
          ))}
          {(draft.quality || []).length > 0 && (
            <div style={{ marginTop: '.35rem' }}>
              <b>{draft.quality.length}</b> DQ expectation rule{draft.quality.length !== 1 ? 's' : ''}
              <span className="muted"> — format / allowed-values / completeness / uniqueness checks derived from the same profile (Quality/ in the bundle); feed them to your DQ runner</span>
            </div>
          )}
          {(draft.quality || []).map((q) => (
            <div key={q.filename}>· dq <code>{q.filename}</code> — {q.term} ({q.checks} check{q.checks !== 1 ? 's' : ''})</div>
          ))}
          {(draft.mapping_only || []).length > 0 && (() => {
            const recs = draft.mapping_only.filter((m) => m.auto_candidate && flipped[m.term] === undefined)
            const sorted = [...draft.mapping_only].sort((a, b) => (b.auto_candidate ? 1 : 0) - (a.auto_candidate ? 1 : 0))
            return (
              <div className="notes" style={{ marginTop: '.5rem' }}>
                <b>{draft.mapping_only.length} term(s) mapping-only by design</b> — governed via
                their term↔column links; no detection method expected (dates, names, free numbers,
                flags). Flip one to <b>Auto</b> and the next draft mints a name-anchored rule
                (column-name identity + sanity shape; the range stays in DQ).
                {recs.length > 0 && (
                  <> ★ = a <b>recommended</b> flip — a bounded measure whose name carries its unit:{' '}
                    <button className="ghost mini"
                            title="Flip every starred term to Auto in one click — bounded measures with unit-bearing names (pH, lead ppb, turbidity ntu). The flip is still yours: this stages it, the next draft mints it."
                            onClick={() => recs.forEach((m) => flipTerm(m.term, ''))}>
                      ★ Flip all recommended ({recs.length})
                    </button>
                  </>
                )}
                <div style={{ marginTop: '.25rem' }}>
                  {sorted.map((m) => (
                    <span key={m.term} style={{ display: 'inline-flex', alignItems: 'center', gap: '.2rem', marginRight: '.55rem', whiteSpace: 'nowrap' }}>
                      {m.auto_candidate ? <span title="Recommended: bounded measure, unit-bearing name">★</span> : null}{m.term}
                      {flipped[m.term] === ''
                        ? <b title="Flipped — run Draft policies again to mint its rule">Auto ✓</b>
                        : <button className="ghost mini" title="Flip this term to Auto detection — the next draft mints a name-anchored rule."
                                  onClick={() => flipTerm(m.term, '')}>→ Auto</button>}
                    </span>
                  ))}
                </div>
              </div>
            )
          })()}
          {(draft.skipped || []).length > 0 && (
            <div className="notes" style={{ marginTop: '.5rem' }}>
              <b>{draft.skipped.length} term(s) skipped</b> — a rule needs a value <i>shape</i> (a
              profiled value pattern or a reference-value list), not just tags. Grouped by reason:
              {Object.entries((draft.skipped || []).reduce((m, s) => {
                const why = typeof s === 'string' ? s : (s.why || 'no detection seed on the row')
                const term = typeof s === 'string' ? s : s.term
                ;(m[why] = m[why] || []).push(term)
                return m
              }, {})).map(([why, terms]) => {
                // free-text / shapeless columns can go QUIET in place — the
                // structural groups (table-level, document, link-expected)
                // have nothing to flip
                const flippable = /induce no shape|no stable shape/.test(why)
                return (
                  <div key={why} style={{ marginTop: '.25rem' }}>· <b>{why}</b> —{' '}
                    {terms.map((t) => (
                      <span key={t} style={{ display: 'inline-flex', alignItems: 'center', gap: '.2rem', marginRight: '.55rem', whiteSpace: 'nowrap' }}>
                        {t}
                        {flippable && (flipped[t] === 'mapping_only'
                          ? <b title="Flipped — run Draft policies again and it moves to the quiet mapping-only line">Mapping-only ✓</b>
                          : <button className="ghost mini" title="Declare this term mapping-only — governed via its term↔column links; the next draft lists it quietly instead of as a skip."
                                    onClick={() => flipTerm(t, 'mapping_only')}>→ Mapping-only</button>)}
                      </span>
                    ))}
                  </div>
                )
              })}
            </div>
          )}
          {flipCount > 0 && (
            <p className="summary" style={{ marginTop: '.4rem' }}>
              <b>{flipCount} flip(s) staged</b> and saved to the grid — run <b>Draft policies</b> again
              to honour them, then send the fresh bundle to the lab.
            </p>
          )}
        </div>
      )}
    </section>
  )
}

/* ---------- the PDC connection panel (one sign-in for resolve / apply / profiling) ---------- */

function ConnectionCard({ conn, setConn, saveConn }) {
  const [busy, setBusy] = useState(false)
  const [info, setInfo] = useState(null) // {text} | {claims}

  async function getToken() {
    if (!conn.base.trim()) {
      setInfo({ text: 'Enter your PDC base URL first.' })
      return
    }
    if (!conn.user || !conn.pass) {
      setInfo({ text: 'Enter username and password to mint a token.' })
      return
    }
    setBusy(true)
    setInfo({ text: 'Authenticating…' })
    try {
      const d = await apiPost('/api/pdc-token', {
        base_url: conn.base.trim(), version: conn.ver,
        realm: (conn.realm || 'pdc').trim(),
        username: conn.user, password: conn.pass, verify_tls: conn.verify,
      })
      setConn((c) => ({ ...c, token: d.token || '' }))
      setInfo({ claims: d.claims || {} })
      // a minted token is proof of connectivity — light the sidebar's PDC dot
      setPdcSession({ base: conn.base.trim(), user: d.claims?.username || conn.user })
    } catch (e) {
      setInfo({ text: `Token failed: ${e.message}` })
      setPdcSession(null) // auth failed — drop any earlier session
    } finally {
      setBusy(false)
    }
  }

  const c = info?.claims
  const exp = c?.expires_in != null
    ? ` · expires in ${Math.floor(c.expires_in / 60)}m ${c.expires_in % 60}s`
    : ''

  return (
    <section className="card">
      <h2>PDC connection <span>one sign-in for resolve, apply &amp; profiling compare</span></h2>
      <p className="hint-line">
        Authenticate once here. The connection (base URL, realm, version, TLS) is <b>remembered</b>{' '}
        for next time; your password and the token are <b>never saved</b> — the token is held in
        memory for this session only and expires on its own.
      </p>
      <div className="form-grid apply-conngrid">
        <label>
          PDC base URL
          <input type="text" placeholder="https://[PDC SERVER]" value={conn.base}
                 onChange={(e) => setConn((v) => ({ ...v, base: e.target.value }))}
                 onBlur={(e) => saveConn({ base: e.target.value })} />
          <span className="muted">the server root — use the hostname, since PDC routes by vhost. Remembered for next time.</span>
        </label>
        <label>
          API version
          <select value={conn.ver} onChange={(e) => saveConn({ ver: e.target.value })}
                  title="PDC 11 serves v1, v2 and v3 side by side. v3 is its native version; v2 remains fully supported.">
            <option>v3</option><option>v2</option><option>v1</option>
          </select>
          <span className="muted">v3 is PDC 11's native version</span>
        </label>
        <label>
          Keycloak realm
          <input type="text" value={conn.realm}
                 onChange={(e) => setConn((v) => ({ ...v, realm: e.target.value }))}
                 onBlur={(e) => saveConn({ realm: e.target.value })} />
          <span className="muted">default pdc</span>
        </label>
        <label>
          Username
          <input type="text" autoComplete="off" value={conn.user}
                 onChange={(e) => setConn((v) => ({ ...v, user: e.target.value }))} />
          <span className="muted">a PDC admin account</span>
        </label>
        <label>
          Password
          <input type="password" autoComplete="off" value={conn.pass}
                 onChange={(e) => setConn((v) => ({ ...v, pass: e.target.value }))} />
          <span className="muted">never saved — used once to mint the token</span>
        </label>
        <label className="apply-connspan3">
          Bearer token
          <input type="text" placeholder="eyJhbGciOi…" autoComplete="off" value={conn.token}
                 onChange={(e) => setConn((v) => ({ ...v, token: e.target.value }))} />
          <span className="muted">optional — auto-filled by Get admin token; paste a JWT to skip login</span>
        </label>
      </div>
      <div className="actions">
        <label className="check">
          <input type="checkbox" checked={conn.verify}
                 onChange={(e) => saveConn({ verify: e.target.checked })} />
          verify TLS cert
        </label>
        <button className="primary" onClick={getToken} disabled={busy}
                title="Authenticate via Keycloak and drop a fresh JWT into the token field. Shows the account role and expiry.">
          {busy ? 'Authenticating…' : 'Get admin token'}
        </button>
        {info?.text && <span className="summary">{info.text}</span>}
        {c && (
          <span className="summary">
            Token minted. Signed in as <b>{c.username || '?'}</b> —{' '}
            {c.is_admin
              ? <span className="ok">admin ✓</span>
              : <span className="warn">not an admin role</span>}
            {exp}
            <span className="notes"> · roles: {(c.roles || []).slice(0, 6).join(', ') || '(no realm roles in token)'}</span>
          </span>
        )}
      </div>
    </section>
  )
}

/* ---------- step 1: Data Elements (term↔column links) ---------- */

function DataElementsCard({ rows, glossaryName, de, setDe }) {
  const [policy, setPolicy] = usePersistentState('apply.dePolicy', 'default')
  const [dq, setDq] = usePersistentState('apply.deDq', true)
  const [w, setW] = usePersistentState('apply.deWeights', { wc: 0.4, wu: 0.3, wv: 0.3 })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  async function pull(next = {}) {
    const p = next.policy ?? policy
    const q = next.dq ?? dq
    const wt = next.w ?? w
    setBusy(true)
    setError(null)
    try {
      const mapPolicy = p === 'strict' ? { min_confidence: 'high' } : p === 'all' ? { mode: 'all' } : null
      const d = await apiPost('/api/data-elements', {
        rows, glossary_name: glossaryName, lineage_verified: true, rating: 0,
        quality: q,
        quality_weights: { completeness: wt.wc, uniqueness: wt.wu, validity: wt.wv },
        map_policy: mapPolicy,
      })
      setDe(d)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const skipped = de?.breakdown?.skipped || []

  return (
    <section className="card">
      <h2>1 · Data Elements <span>term ↔ column links</span></h2>
      <p className="hint-line">
        The associations between each kept term and the physical columns it came from, keyed by
        schema/table/column — built from the glossary you reviewed. Also downloadable as CSV
        (bulk assign) or Trust-ready API JSON.
      </p>
      {error && <div className="error">{error}</div>}
      <div className="actions">
        <button className="primary" onClick={() => pull()} disabled={busy || rows.length === 0}>
          {busy ? 'Building links…' : 'Pull / refresh links from glossary'}
        </button>
        {de == null && <span className="summary">No links yet — build a glossary, then pull.</span>}
        {de != null && de.count === 0 && (
          <span className="summary warn">
            {de.skipped_terms
              ? <>No links — all <b>{de.skipped_terms}</b> kept term(s) were held back by the mapping policy. Loosen the policy, or set <b>Map</b> = Y on the rows you want linked.</>
              : 'No linkable columns in the kept terms — keep some terms on the Review page first.'}
          </span>
        )}
        {de != null && de.count > 0 && (
          <span className="summary">
            <b>{de.mapped_terms ?? de.terms}</b> terms mapped
            {de.skipped_terms ? <> · <b>{de.skipped_terms}</b> held back</> : null}
            {' · '}<b>{de.count}</b> links · <b>{de.elements}</b> data elements across{' '}
            <b>{de.tables}</b> tables
            {dq && de.quality_scored ? <> · <b>{de.quality_scored}</b> with DQ score</> : null}
          </span>
        )}
        {de?.count > 0 && (
          <>
            <button className="ghost mini" onClick={() => downloadBlob(de.csv, 'Data-Element-Links.csv', 'text/csv')}>
              ⬇ CSV (bulk assign)
            </button>
            <button className="ghost mini" onClick={() => downloadBlob(JSON.stringify(de.json, null, 2), 'Data-Elements-API.json')}>
              ⬇ JSON (Trust-ready, API)
            </button>
          </>
        )}
      </div>
      <div className="form-grid" style={{ marginTop: '.8rem' }}>
        <label>
          Mapping policy
          <select value={policy}
                  title="Which terms get linked to a data element. Selective avoids over-mapping low-value columns."
                  onChange={(e) => { setPolicy(e.target.value); pull({ policy: e.target.value }) }}>
            <option value="default">Selective — CDE, PII, High/Med confidence (recommended)</option>
            <option value="strict">Strict — CDE, PII, High confidence only</option>
            <option value="all">Map everything (legacy)</option>
          </select>
        </label>
        <label className="check" style={{ alignSelf: 'end' }}
               title="Write a 0-100 Data Quality score per column, computed from profiling. PDC records an externally-set value as a MANUAL quality metric.">
          <input type="checkbox" checked={dq}
                 onChange={(e) => { setDq(e.target.checked); pull({ dq: e.target.checked }) }} />
          Data Quality Score (from profiling)
        </label>
        {[['wc', 'Completeness'], ['wu', 'Uniqueness'], ['wv', 'Validity']].map(([k, label]) => (
          <label key={k}>
            {label} weight
            <input type="number" min="0" max="1" step="0.05" value={w[k]}
                   onChange={(e) => setW((v) => ({ ...v, [k]: parseFloat(e.target.value) || 0 }))}
                   onBlur={() => pull()} />
          </label>
        ))}
      </div>
      <p className="hint-line">
        Low-confidence, non-CDE, non-PII columns are held back. A per-row <b>Map</b> = Y/N always
        wins. DQ weights are renormalised per column over the dimensions that apply.
      </p>
      {skipped.length > 0 && (() => {
        // Two different populations were one list ("anything that ends with
        // Record is at the table level" — field-caught): conceptual
        // table-level terms are glossary-only BY DESIGN (the steward links
        // them to their tables in PDC by hand — they were never column-link
        // candidates), so they collapse to one line; only the terms the
        // POLICY held back are actionable and get the listing.
        const conceptual = skipped.filter((x) => /conceptual|no physical column/i.test(x.reason || ''))
        const actionable = skipped.filter((x) => !/conceptual|no physical column/i.test(x.reason || ''))
        return (
          <>
            {actionable.length > 0 && (
              <details>
                <summary>
                  <b>{actionable.length}</b> term(s) held back by the mapping policy — set <b>Map</b> = Y (or raise confidence) to link them
                </summary>
                <ul className="bucket-list">
                  {actionable.slice(0, 300).map((x, i) => (
                    <li key={i}><b>{x.term}</b> <span className="notes">({x.category || '—'})</span> — {x.reason}</li>
                  ))}
                </ul>
              </details>
            )}
            {conceptual.length > 0 && (
              <p className="hint-line">
                <b>{conceptual.length}</b> table-level record term(s) are glossary-only by design —
                created in the glossary for the steward to link to their <i>tables</i> in PDC
                (feeding the Trust Score), never to columns. Not held back; simply not column material.
              </p>
            )}
          </>
        )
      })()}
    </section>
  )
}

/* ---------- step 2: resolve term ids (job twin) + fuzzy/AI match ---------- */

function ResolveCard({ de, setDe, authBody, glossaryName, rows, settings }) {
  const [busy, setBusy] = useState(false)
  const [prog, setProg] = useState(null) // {pct, label}
  const [res, setRes] = usePersistentState('apply.resolveRes', null)
  const [error, setError] = useState(null)
  const [outstanding, setOutstanding] = usePersistentState('apply.resolveOutstanding', [])
  const [fuzzy, setFuzzy] = usePersistentState('apply.resolveFuzzy', null) // {name: {match, id, glossaryId, source, reason}}
  const [fuzzyBusy, setFuzzyBusy] = useState(false)
  const [bound, setBound] = usePersistentState('apply.resolveBound', []) // messages for successful binds

  async function resolve() {
    if (!de?.json) {
      setError('Pull the Data Elements first (step 1).')
      return
    }
    if (!authBody().base_url) {
      setError('Enter your PDC base URL above.')
      return
    }
    setBusy(true)
    setError(null)
    setRes(null)
    setFuzzy(null)
    setBound([])
    setProg({ pct: 0, label: 'Authenticating…' })
    try {
      const d = await runJob('resolve-terms',
        { ...authBody(), glossary_name: glossaryName, json: de.json },
        (job) => {
          const ev = job.events[job.events.length - 1] || {}
          if (ev.phase === 'term') {
            const t = ev.total || job.total || 1
            const pct = Math.round((ev.done / t) * 100)
            setProg({ pct, label: `Resolving term ${Math.min(ev.done + 1, t)} of ${t} (${pct}%)${ev.name ? ` · ${ev.name}` : ''}` })
          } else if (ev.phase === 'finishing') {
            setProg({ pct: 100, label: `Looked up ${ev.total} term(s) · stamping ids & checking unconfirmed names…` })
          }
        })
      setRes(d)
      setDe({ ...de, json: d.json })
      const unresolved = d.unresolved || []
      const unconf = (d.unconfirmed || []).filter((n) => !unresolved.includes(n))
      setOutstanding([...unresolved, ...unconf])
    } catch (e) {
      setError(`Resolve failed: ${e.message}`)
    } finally {
      setBusy(false)
      setProg(null)
    }
  }

  async function aiMatch() {
    if (!outstanding.length) return
    setFuzzyBusy(true)
    setError(null)
    try {
      const definitions = {}
      rows.forEach((r) => {
        if (r?.Term && r?.Definition && !definitions[r.Term]) definitions[r.Term] = r.Definition
      })
      const d = await apiPost('/api/resolve-fuzzy', {
        names: outstanding, definitions, ...authBody(), glossary_name: glossaryName,
        model: settings?.model || null, compute: settings?.compute,
      })
      setFuzzy({ matches: d.matches || {}, usedLlm: !!d.used_llm })
    } catch (e) {
      setError(`AI match failed: ${e.message}`)
    } finally {
      setFuzzyBusy(false)
    }
  }

  // Stamp the PDC term's id + glossaryId into every link carrying these names.
  function bind(names) {
    if (!fuzzy || !de?.json) return
    const byName = {}
    names.forEach((n) => {
      const f = fuzzy.matches[n]
      if (f?.match && f.id) byName[n] = f
    })
    if (!Object.keys(byName).length) return
    let count = 0
    const json = de.json.map((el) => {
      const bts = el.attributes?.businessTerms
      if (!bts?.some((bt) => byName[bt.name || ''])) return el
      return {
        ...el,
        attributes: {
          ...el.attributes,
          businessTerms: bts.map((bt) => {
            const f = byName[bt.name || '']
            if (!f) return bt
            count += 1
            return { ...bt, id: f.id, ...(f.glossaryId ? { glossaryId: f.glossaryId } : {}) }
          }),
        },
      }
    })
    setDe({ ...de, json })
    const rest = { ...fuzzy.matches }
    Object.keys(byName).forEach((n) => delete rest[n])
    setFuzzy({ ...fuzzy, matches: rest })
    setOutstanding((o) => o.filter((n) => !byName[n]))
    setBound((b) => [...b,
      Object.keys(byName).length === 1
        ? `Bound "${Object.keys(byName)[0]}" → "${byName[Object.keys(byName)[0]].match}" on ${count} link(s).`
        : `All matches bound (${count} link(s)) — the links are ready to Apply.`])
  }

  const matchNames = fuzzy ? Object.keys(fuzzy.matches) : []
  const matched = matchNames.filter((n) => fuzzy.matches[n]?.match)
  const allLinked = res && res.linked === res.links

  return (
    <section className="card">
      <h2>2 · Resolve term IDs <span>stamp real ids into the links</span></h2>
      <p className="hint-line">
        After the glossary is imported in PDC, look up each term's <code>id</code> and{' '}
        <code>glossaryId</code> and stamp them into the links so the write carries real ids.{' '}
        <b>Import → Resolve → Apply</b> — a term has no id until it exists.
      </p>
      {error && <div className="error">{error}</div>}
      <div className="actions">
        <button className="primary" onClick={resolve} disabled={busy}>
          {busy ? 'Resolving…' : 'Resolve & stamp IDs'}
        </button>
        {res?.json && (
          <button className="ghost" onClick={() => downloadBlob(JSON.stringify(de.json, null, 2), 'Data-Elements-API-resolved.json')}>
            ⬇ Download POST-ready JSON
          </button>
        )}
      </div>
      {prog && (
        <>
          <div className="progress-track"><div className="progress-bar" style={{ width: `${prog.pct}%` }} /></div>
          <p className="summary">{prog.label}</p>
        </>
      )}
      {res && (
        <div className="summary">
          {allLinked
            ? <b className="ok">✓ All {res.linked} term links are bound (id + glossaryId) — ready to Apply.</b>
            : <>Fully linked <b>{res.linked}</b> of {res.links} term links (id + glossaryId).</>}
          {' · '}<b>{res.matched_with_glossary}</b> of {res.terms} terms confirmed by PDC by name
          {res.linked > 0 && res.glossary_id && res.matched_with_glossary < res.matched && (
            <div className="ok">
              PDC's API doesn't return a term's glossaryId, so it was filled deterministically from
              the glossary you imported (<code>{res.glossary_id}</code>). These links are ready to Apply.
            </div>
          )}
          {(res.id_only || []).length > 0 && (
            <details className="nfwrap" open>
              <summary className="warn-sum">
                ⚠ {res.id_only.length} term(s) matched an id but PDC returned NO glossaryId — these
                will NOT link to a glossary (Apply treats them as unresolved)
              </summary>
              <div className="chip-list">{res.id_only.map((n) => <span key={n}>{n}</span>)}</div>
            </details>
          )}
          {(res.unresolved || []).length > 0 && (
            <details className="nfwrap" open>
              <summary>
                {res.unresolved.length} term(s) not found in PDC by name — renamed locally after import?
              </summary>
              <div className="chip-list">{res.unresolved.map((n) => <span key={n}>{n}</span>)}</div>
            </details>
          )}
          {(res.unconfirmed || []).filter((n) => !(res.unresolved || []).includes(n)).length > 0 && (
            <details className="nfwrap" open>
              <summary className="warn-sum">
                ⚠ {(res.unconfirmed || []).filter((n) => !(res.unresolved || []).includes(n)).length}{' '}
                term(s) could not be CONFIRMED in PDC by name — their links fall back to the
                deterministic import ids, which only exist if the term kept its name since import
                (renamed terms would Apply a dead id)
              </summary>
              <div className="chip-list">
                {(res.unconfirmed || []).filter((n) => !(res.unresolved || []).includes(n))
                  .map((n) => <span key={n}>{n}</span>)}
              </div>
            </details>
          )}
          {outstanding.length > 0 && (
            <div className="actions">
              <button className="ghost mini" onClick={aiMatch} disabled={fuzzyBusy}
                      title="Match each outstanding name against the terms that actually exist in PDC — name similarity first, then the local AI judging with the term's definition. Proposals only; you bind each match.">
                {fuzzyBusy ? 'Matching…' : `AI match in PDC (${outstanding.length})`}
              </button>
            </div>
          )}
          {fuzzy && (
            <div style={{ marginTop: '.5rem' }}>
              {matchNames.map((n) => {
                const f = fuzzy.matches[n] || {}
                return (
                  <div className="fuzzy-row" key={n}>
                    <b>{n}</b>
                    {f.match ? (
                      <>
                        → <b>{f.match}</b>
                        <span className={`badge ${f.source === 'ai' ? 'accent' : 'good'}`}>
                          {f.source === 'ai' ? 'AI' : f.reason || 'match'}
                        </span>
                        {f.source === 'ai' && <span className="notes">{f.reason || ''}</span>}
                        <button className="ghost mini" onClick={() => bind([n])}>Bind id</button>
                      </>
                    ) : (
                      <span className="notes">{f.reason || 'no match'}</span>
                    )}
                  </div>
                )
              })}
              {matched.length > 1 && (
                <button className="ghost mini" style={{ marginTop: '.4rem' }} onClick={() => bind(matched)}>
                  Bind all {matched.length} matches
                </button>
              )}
              <p className="notes">
                Binding stamps the PDC term's id + glossaryId into these links (your local name stays).{' '}
                {fuzzy.usedLlm ? '' : 'Ollama offline — similarity matches only. '}
                Then re-download the POST-ready JSON or go straight to Apply.
              </p>
            </div>
          )}
          {bound.map((m, i) => <div key={i} className="ok">{m}</div>)}
          <ProbeBlock probe={res.probe} kind="resolve" />
        </div>
      )}
    </section>
  )
}

// PDC probe diagnostics shared by Resolve and Apply results
function ProbeBlock({ probe, kind }) {
  if (!probe?.length) return null
  const anyHit = probe.some((p) => p.search_hits > 0 || p.filter_hits > 0)
  const anyGid = probe.some((p) => p.search_has_glossaryId)
  let verdict
  if (kind === 'resolve') {
    verdict = !anyHit
      ? 'PDC returned nothing for these names — either the glossary is not imported (In PDC: Glossary → Actions → Import → drop the JSONL → Submit, then re-resolve), or these terms were RENAMED locally after import — use AI match in PDC above to bind them without re-importing.'
      : anyGid
        ? 'PDC has these terms WITH a glossaryId, so they should link. If Apply still skips them, capture this probe — the field the glossaryId lands in may differ.'
        : 'PDC found these terms but exposes NO glossaryId on them (only an id). The term may be imported as a stand-alone/Unassigned term (no parent glossary). Re-import the JSONL so each term sits under the business glossary.'
  } else {
    verdict = anyHit
      ? 'PDC returned matches but none resolved to a glossary term with an id + glossaryId. Confirm the import created terms in the Glossary tree (not just a file), on this same PDC instance/realm.'
      : 'PDC returned nothing for these names — the glossary is not imported (or under a different name/instance). In PDC: Glossary → Actions → Import → drop the JSONL (Generate JSONL) → Submit, then re-apply.'
  }
  return (
    <details className="nfwrap" open={kind === 'apply'}>
      <summary>
        PDC probe — {kind === 'resolve'
          ? `confirmation diagnostics for the first ${probe.length} unconfirmed name(s)`
          : "why term links didn't resolve"}
      </summary>
      <div>
        {probe.map((p) => (
          <div className="probe-row" key={p.name}>
            <b>{p.name}</b> · search {p.search_hits} hit(s)
            {p.search_types?.length ? ` [${p.search_types.join(', ')}]` : ''}
            {p.search_has_glossaryId ? ' · glossaryId ✓' : ' · glossaryId ✗'}
            {p.bt_match ? ' · businessTerms ✓' : ''}
            {' · '}filter {p.filter_hits} hit(s)
            {p.filter_types?.length ? ` [${p.filter_types.join(', ')}]` : ''}
            {p.search_error ? ` · search error: ${p.search_error}` : ''}
          </div>
        ))}
        <div className="probe-verdict">{verdict}</div>
      </div>
    </details>
  )
}

/* ---------- step 3: apply to PDC (job twin) with dry-run first ---------- */

function ApplyCard({ de, authBody, glossaryName, rows, conn }) {
  const [opts, setOpts] = usePersistentState('apply.applyOpts', { dry: true, rollup: true, desc: 'fill', trust: false, skip: true })
  const [busy, setBusy] = useState(false)
  const [prog, setProg] = useState(null)
  const [res, setRes] = usePersistentState('apply.applyRes', null)
  const [error, setError] = useState(null)

  const setOpt = (patch) => setOpts((o) => {
    const next = { ...o, ...patch }
    if (next.dry) next.trust = false
    return next
  })

  async function apply() {
    if (!de?.json) {
      setError('Export the Data Elements JSON first (step 1).')
      return
    }
    if (!authBody().base_url) {
      setError('Enter your PDC base URL above.')
      return
    }
    // a term binds to its glossary only with BOTH id and glossaryId (stamped by Resolve)
    let unresolved = 0
    de.json.forEach((el) => (el.attributes?.businessTerms || []).forEach((bt) => {
      if (!(bt.id && bt.glossaryId)) unresolved += 1
    }))
    if (unresolved && !opts.dry) {
      const msg = opts.skip
        ? `${unresolved} term link(s) aren't resolved to a glossary yet. Apply will try to resolve them against PDC now; any that still can't be found will be SKIPPED (only sensitivity/CDE/lineage/rating get written). The result will show a PDC probe explaining why. Continue?`
        : `${unresolved} term link(s) have no glossary id. Apply will try to resolve them now; any it still can't find attach by NAME ONLY (Glossary shows "—"). Continue?`
      if (!window.confirm(msg)) return
    }
    setBusy(true)
    setError(null)
    setRes(null)
    const total = de.json.length
    setProg({ pct: 0, label: opts.dry ? 'Building dry-run preview…' : 'Applying to PDC…' })
    try {
      const d = await runJob('apply-to-pdc', {
        json: de.json, ...authBody(),
        dry_run: opts.dry, calculate_trust: opts.trust,
        apply_table_ratings: opts.rollup, desc_mode: opts.desc,
        rows, skip_unresolved_terms: opts.skip, glossary_name: glossaryName,
      }, (job) => {
        const ev = job.events[job.events.length - 1] || {}
        if (ev.phase === 'column') {
          const t = ev.total || total || 1
          const pct = Math.round((ev.done / t) * 100)
          setProg({ pct, label: `Resolving & patching column ${Math.min(ev.done + 1, t)} of ${t} (${pct}%)${ev.column ? ` · ${ev.column}` : ''}` })
        } else if (ev.phase === 'columns-done') {
          setProg({ pct: 100, label: `Patched ${ev.total} column(s) · finishing…` })
        } else if (ev.phase === 'tables') {
          setProg((p) => ({ ...(p || { pct: 100 }), label: `Rolling up ${ev.total} table rating(s)…` }))
        } else if (ev.phase === 'trust') {
          setProg((p) => ({ ...(p || { pct: 100 }), label: `Submitting Trust Score over ${ev.total} entity/entities…` }))
        }
      })
      setRes(d)
    } catch (e) {
      setError(`Apply failed: ${e.message}`)
    } finally {
      setBusy(false)
      setProg(null)
    }
  }

  return (
    <section className="card">
      <h2>4 · Apply to PDC <span>writes back — dry-run first · document columns need step 3 to have run</span></h2>
      <p className="hint-line">
        Resolve each kept column in PDC, <b>merge</b> the term plus sensitivity / CDE /
        verified-lineage / rating into whatever the column already carries, and <code>PATCH</code>{' '}
        it back. Existing terms are never dropped. Run a <b>dry-run</b> first to see every change
        before anything is written.
      </p>
      {error && <div className="error">{error}</div>}
      <div className="actions">
        <label className="check">
          <input type="checkbox" checked={opts.dry} onChange={(e) => setOpt({ dry: e.target.checked })} />
          Dry-run (preview, no writes)
        </label>
        <label className="check"
               title="Roll the column results up to their table / folder entities: mean rating & DQ, max sensitivity, verified lineage — and bind each table's own record term (+ description), the Trust Score's assigned-term input.">
          <input type="checkbox" checked={opts.rollup} onChange={(e) => setOpt({ rollup: e.target.checked })} />
          Roll up to tables &amp; folders
        </label>
        <label className="check"
               title="Write each entity's description from the steward's reviewed definition. 'Fill empty' never touches a description someone already wrote in PDC.">
          Descriptions
          <select value={opts.desc} onChange={(e) => setOpt({ desc: e.target.value })}>
            <option value="fill">fill empty</option>
            <option value="overwrite">overwrite</option>
            <option value="off">don't write</option>
          </select>
        </label>
        <label className="check">
          <input type="checkbox" checked={opts.trust} disabled={opts.dry}
                 onChange={(e) => setOpt({ trust: e.target.checked })} />
          Calculate Trust Score after apply
        </label>
        <label className="check"
               title="A term only links to its glossary once it carries a glossaryId (stamped by Resolve, after the glossary is imported into PDC). With this on, terms that haven't resolved are not written, so columns never get an unlinked, glossary-less term.">
          <input type="checkbox" checked={opts.skip} onChange={(e) => setOpt({ skip: e.target.checked })} />
          Only write glossary-linked terms
        </label>
        <button className="primary" onClick={apply} disabled={busy}>
          {busy ? (opts.dry ? 'Previewing…' : 'Applying…') : opts.dry ? 'Preview changes (dry-run)' : 'Apply to PDC'}
        </button>
      </div>
      {prog && (
        <>
          <div className="progress-track"><div className="progress-bar" style={{ width: `${prog.pct}%` }} /></div>
          <p className="summary">{prog.label}</p>
        </>
      )}
      {res && <ApplyResults d={res} />}
      {res && <ApiPeek res={res} conn={conn} trust={opts.trust} />}
    </section>
  )
}

function RateChip({ v }) {
  return v ? <span className="rate-chip" title={`Suggested rating ${v}/5`}>★ {v}</span> : null
}
function DqChip({ v }) {
  // null/undefined = the column was never profiled (or DQ was switched off in
  // step 1) — show an explicit "not profiled" chip, never a made-up score
  if (v == null) {
    return (
      <span className="dq-chip na"
            title="No Data Quality score — column not profiled (or the DQ score was disabled in step 1)">
        DQ —
      </span>
    )
  }
  return <span className="dq-chip" title={`Data Quality score ${v}/100`}>DQ {v}</span>
}

function ApplyResults({ d }) {
  const verb = d.dry_run ? 'planned' : 'written'
  return (
    <div style={{ marginTop: '.8rem' }}>
      <p className="summary">
        <b>{d.found}</b>/<b>{d.total}</b> columns resolved ·{' '}
        {d.dry_run ? <><b>{d.planned}</b> change(s) planned</> : <><b>{d.applied}</b> {verb}</>}
        {d.tables_rated ? <> · <b>{d.tables_rated}</b> table(s) rated</> : null}
        {d.objectstore_folders ? <> · <b>{d.objectstore_folders}</b> object-store folder(s) — files carry Trust Score directly</> : null}
        {d.terms_resolved_on_apply ? <> · <b>{d.terms_resolved_on_apply}</b> term link(s) auto-resolved</> : null}
        {d.not_found ? <> · <b className="warn">{d.not_found}</b> not found</> : null}
        {d.errors ? <> · <b className="warn">{d.errors}</b> error(s)</> : null}
        {d.trust && (d.trust.ok
          ? <> · trust: {d.trust.status || 'submitted'} ({d.trust.submitted})</>
          : <> · <span className="warn">trust: {d.trust.message || d.trust.status || 'unavailable'}</span></>)}
      </p>
      {(d.unresolved_terms || []).length > 0 && (
        <p className="summary warn">
          <b>{d.unresolved_terms.length}</b> term(s) not resolved to a glossary,{' '}
          {d.unresolved_terms_skipped
            ? 'skipped (not written — no glossary link)'
            : 'written by name only (Glossary shows "—")'}:{' '}
          {d.unresolved_terms.slice(0, 8).join(', ')}{d.unresolved_terms.length > 8 ? '…' : ''}.
          Import the glossary in PDC, then run Resolve.
        </p>
      )}
      <ProbeBlock probe={d.probe} kind="apply" />
      <div className="table-scroll" style={{ marginTop: '.6rem' }}>
        <table>
          <thead>
            <tr><th>Column</th><th>Status</th><th>Entity</th><th>Business terms (current → merged) · rating / PATCH</th></tr>
          </thead>
          <tbody>
            {(d.results || []).length === 0 && (
              <tr><td colSpan="4" className="notes">No columns.</td></tr>
            )}
            {(d.results || []).map((r, i) => {
              const cur = r.current_terms || []
              const mer = r.merged_terms || []
              const feat = r.body?.attributes?.features || {}
              return (
                <tr key={i}>
                  <td>
                    <div className="colname">{r.column}</div>
                    <div className="colfqdn">{r.fqdn || ''}</div>
                  </td>
                  <td><StatusBadge s={r.status} /></td>
                  <td><ShortId id={r.id} /></td>
                  <td className="termcell">
                    {mer.length
                      ? <>{cur.length ? `${cur.join(', ')} → ` : ''}<b>{mer.join(', ')}</b>
                          <RateChip v={feat.rating?.value} /> <DqChip v={feat.qualityScore} /></>
                      : '—'}
                    {/* What PDC holds NOW, beside what we are about to send. A
                        preview that only shows the outgoing body cannot tell you
                        whether the LAST apply's value actually stuck — and PDC
                        accepts a PATCH wholesale, so a silently-ignored field
                        looks identical to a successful write. */}
                    {r.current_features && (
                      <div className="notes">
                        in PDC now:{' '}
                        {/* qualityScore is the MANUAL metric an external writer sets —
                            this app's own score. PDC's Discovery-COMPUTED Data Quality
                            is a different metric and never lands here, so an unlabelled
                            "—" reads as "PDC has no quality" when it means "we never
                            wrote one". That misreading cost a whole debugging detour. */}
                        {[['rating', 'rating'], ['qualityScore', 'qualityScore (app-set)'],
                          ['sensitivity', 'sensitivity']].map(([k, label]) => {
                          const v = r.current_features[k]
                          const shown = v === null || v === undefined || v === '' ? '—' : String(v)
                          return <span key={k} style={{ marginRight: '.7rem' }}>{label} <b>{shown}</b></span>
                        })}
                      </div>
                    )}
                    {r.body && (
                      <details>
                        <summary>view PATCH body</summary>
                        <pre>{JSON.stringify(r.body, null, 2)}</pre>
                      </details>
                    )}
                    {r.message && <div className="notes warn">{r.message}</div>}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {(d.table_results || []).length > 0 && (
        <div className="table-scroll" style={{ marginTop: '.8rem' }}>
          <table>
            <thead>
              <tr><th>Table</th><th>Status</th><th>Entity</th><th>Rating &amp; DQ → table (feed Trust Score)</th></tr>
            </thead>
            <tbody>
              {d.table_results.map((t, i) => (
                <tr key={i}>
                  <td><div className="colname">{t.table}</div></td>
                  <td><StatusBadge s={t.status} /></td>
                  <td><ShortId id={t.id} /></td>
                  <td className="termcell">
                    {t.rating != null && <><RateChip v={t.rating} /> <span className="notes">mean of {t.from_columns}</span></>}
                    {t.quality != null && <> <DqChip v={t.quality} /> <span className="notes">mean of {t.quality_from}</span></>}
                    {t.rating == null && t.quality == null && '—'}
                    {t.message && (
                      <div className={`notes${t.status === 'error' || t.status === 'not-found' ? ' warn' : ''}`}>
                        {t.message}
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

// "Under the hood": the real PDC public-API choreography, built from the user's
// own connection settings and (after a dry-run) the actual planned PATCH bodies.
function ApiPeek({ res, conn, trust }) {
  const base = (conn.base.trim() || 'https://your-pdc-host').replace(/\/+$/, '')
  const v = conn.ver || 'v2'
  const realm = (conn.realm || 'pdc').trim()
  const user = conn.user.trim() || '<admin-user>'
  const pub = `${base}/api/public/${v}`
  const results = res.results || []

  const calls = []
  calls.push(['POST', `${base}/keycloak/realms/${realm}/protocol/openid-connect/token`,
    { 'Content-Type': 'application/x-www-form-urlencoded' },
    `grant_type=password&client_id=pdc-client&username=${user}&password=********`, false])
  const sterm = results.find((r) => (r.merged_terms || []).length)
  const termName = sterm?.merged_terms[0] || 'Customer Account Number'
  calls.push(['POST', `${pub}/search`,
    { Authorization: 'Bearer ********', 'Content-Type': 'application/json' },
    JSON.stringify({ searchTerm: termName, searchFacets: { type: ['term'] } }, null, 2), false])
  const fqdn = results.find((r) => r.fqdn)?.fqdn || 'public.public.customers.customer_account_number'
  calls.push(['POST', `${pub}/entities/filter?extended=true&size=500`,
    { Authorization: 'Bearer ********', 'Content-Type': 'application/json' },
    JSON.stringify({ filters: { fqdns: [fqdn] } }, null, 2), false])
  const pb = results.find((r) => r.body && r.id)
  const patchId = pb?.id || '<column-entity-id>'
  const patchBody = pb?.body
    || { attributes: { features: { sensitivity: 'HIGH', isCriticalDataElement: true, rating: { value: 5 } } } }
  calls.push(['PATCH', `${pub}/entities/${patchId}`,
    { Authorization: 'Bearer ********', 'Content-Type': 'application/json' },
    JSON.stringify(patchBody, null, 2), true])
  if (trust) {
    const ids = results.filter((r) => r.id).slice(0, 3).map((r) => r.id)
    calls.push(['POST', `${pub}/jobs/execute/calculate-trust-score`,
      { Authorization: 'Bearer ********', 'Content-Type': 'application/json' },
      JSON.stringify({ scope: ids.length ? ids : ['<entity-id>'] }, null, 2), false])
    calls.push(['GET', `${pub}/jobs/<job-id>/status`, { Authorization: 'Bearer ********' }, null, false])
  }

  return (
    <details className="nfwrap" style={{ marginTop: '.9rem' }}>
      <summary>Under the hood — the PDC API calls this makes</summary>
      <p className="hint-line">
        The exact public-API choreography behind Resolve and Apply, built from your connection
        settings (secrets masked). Copy any call to try it in curl/Postman.
      </p>
      {calls.map(([verb, url, headers, body, open], i) => {
        const raw = `${verb} ${url}\n${Object.entries(headers).map(([k, val]) => `${k}: ${val}`).join('\n')}${body ? `\n\n${body}` : ''}`
        return (
          <details className="apicall" key={i} open={open}>
            <summary>
              <span className={`verb ${verb.toLowerCase()}`}>{verb}</span>
              <span className="u">{url}</span>
              <button className="ghost mini"
                      onClick={(e) => { e.preventDefault(); navigator.clipboard?.writeText(raw) }}>
                Copy
              </button>
            </summary>
            <pre>{raw}</pre>
          </details>
        )
      })}
    </details>
  )
}

/* ---------- step 4: run PDC Data Discovery (profiling) on the document folders ---------- */

/* ---------- data labels in PDC (GraphQL custom properties) ---------- */
function LabelsCard({ rows, authBody }) {
  const ws = useWorkspace()
  const kept = ws.governance?.labelKeys || []
  const [busy, setBusy] = useState(false)
  const [res, setRes] = usePersistentState('apply.labelsRes', null)
  const [err, setErr] = useState(null)
  // the stamp flow: dry-run plan first, then the real write — same
  // propose → apply posture as the term-links Apply card. Resumable: leave
  // the page mid-stamp and the poll re-attaches, the report landing in the
  // session-cached `stamp`.
  const [stampBusy, setStampBusy] = useState(false)
  const [stampTick, setStampTick] = useState(null)
  const [stamp, setStamp] = usePersistentState('apply.labelsStamp', null) // last job result (plan or write)
  const [stampErr, setStampErr] = useState(null)
  const stampJob = useResumableJob('apply.stampJob', {
    onBusy: (b) => setStampBusy(b),
    onTick: (j) => setStampTick(j),
    onDone: (r) => { setStamp(r); setStampTick(null) },
    onError: (e) => { setStampErr(e); setStampTick(null) },
    onLost: () => setStampTick(null),
  })

  async function runStamp(dry) {
    setStampErr(null); setStampTick(null)
    if (!dry) setStamp(null)
    try {
      await stampJob.start('labels-stamp',
        { ...authBody(), keys: kept, rows, dry_run: dry })
    } catch (e) { setStampErr(e.message) }
  }

  const planReady = stamp?.dry_run && (stamp.planned || 0) > 0
  return (
    <section className="card">
      <h2>Data labels <span>create the kept label keys in PDC, then stamp them onto the columns</span></h2>
      <p className="hint-line">
        Writes each label key you kept on <b>Govern</b> into PDC as a <b>data label</b>
        (a custom property with a governed value set), with the values derived from this
        grid. Idempotent — existing labels are reported, never overwritten. <b>Stamp</b>
        then assigns each column its values (PII Type tier, access tier…) on the entity
        itself — merged, so labels this app never derived survive; preview first, and
        any family whose values drifted in PDC is reported, never guessed at.
      </p>
      <div className="actions">
        <button className="primary" disabled={busy || kept.length === 0}
                onClick={async () => {
                  setBusy(true); setErr(null); setRes(null)
                  try {
                    setRes(await apiPost('/api/pdc/labels-apply',
                      { ...authBody(), keys: kept, rows }))
                  } catch (e) { setErr(e.message) } finally { setBusy(false) }
                }}>
          {busy ? 'Creating…' : `Create ${kept.length || ''} label(s) in PDC`}
        </button>
        <button className="ghost" disabled={stampBusy || kept.length === 0}
                onClick={() => runStamp(true)}>
          {stampBusy && stamp?.dry_run !== false ? 'Planning…' : 'Preview stamp (dry run)'}
        </button>
        {planReady && (
          <button className="primary" disabled={stampBusy}
                  onClick={() => runStamp(false)}>
            {stampBusy ? 'Stamping…' : `Stamp ${stamp.planned} column(s)`}
          </button>
        )}
        {kept.length === 0 && <span className="notes">tick label keys on Govern first</span>}
        {err && <span className="warn">{err}</span>}
        {stampErr && <span className="warn">{stampErr}</span>}
        {stampBusy && stampTick && (
          <span className="notes">
            {stampTick.phase || 'working'} · {stampTick.done ?? 0}/{stampTick.total ?? '…'}
          </span>
        )}
      </div>
      {res && (
        <p className="summary ok">
          {res.created.length > 0 && <>created: {res.created.map((c) => <code key={c.key} style={{ marginRight: '.3rem' }}>{c.key} ({c.values.length})</code>)}</>}
          {res.existing.length > 0 && <> · already in PDC: {res.existing.map((s) => <code key={s.key} style={{ marginRight: '.3rem' }}>{s.key}</code>)}</>}
          {res.no_values.length > 0 && <> · no derived values on this grid: {res.no_values.join(', ')}</>}
        </p>
      )}
      {stamp && (
        <>
          <p className={`summary ${stamp.unresolved?.length || stamp.mismatches?.length || stamp.missing_families?.length ? '' : 'ok'}`}>
            {stamp.dry_run
              ? <><b>{stamp.planned}</b> of {stamp.total_columns} column(s) ready to stamp</>
              : <><b>{stamp.stamped}</b> of {stamp.total_columns} column(s) stamped ✓</>}
            {(stamp.missing_families?.length ?? 0) > 0 &&
              <> · not in PDC yet (run Create first): {stamp.missing_families.join(', ')}</>}
            {(stamp.unresolved?.length ?? 0) > 0 &&
              <> · no matching entity: {stamp.unresolved.slice(0, 4).join(', ')}{stamp.unresolved.length > 4 ? '…' : ''}</>}
          </p>
          {(stamp.mismatches?.length ?? 0) > 0 && (
            <p className="summary warn">
              value not in the PDC family (drifted — delete the label in PDC and re-Create, or fix its values):{' '}
              {stamp.mismatches.slice(0, 5).map((m, i) => (
                <code key={i} style={{ marginRight: '.3rem' }}>{m.key}={m.value} ({m.term})</code>
              ))}{stamp.mismatches.length > 5 ? '…' : ''}
            </p>
          )}
        </>
      )}
    </section>
  )
}

function ProfilingCard({ de, authBody }) {
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = usePersistentState('apply.profMsg', null)     // JSX | string
  const [check, setCheck] = usePersistentState('apply.profCheck', null)
  const [job, setJob] = useState(null)     // {job_id}
  const [jobMsg, setJobMsg] = usePersistentState('apply.profJobMsg', null)
  const [watch, setWatch] = usePersistentState('apply.profWatch', null) // {profiled, total}
  const cancelRef = useRef(false)

  useEffect(() => () => { cancelRef.current = true }, [])

  async function trigger() {
    if (!de?.json) {
      setMsg('Pull the Data Elements first (step 1).')
      return
    }
    if (!authBody().base_url) {
      setMsg('Enter your PDC base URL above.')
      return
    }
    const docs = de.json.filter((r) => ['OBJECT', 'FILE', 'DIRECTORY'].includes(String(r.type || '').toUpperCase()))
    if (!docs.length) {
      setMsg('No document/object-store records in this payload — this profiles MinIO files, not database columns.')
      return
    }
    setBusy(true)
    setMsg('Resolving document folders and starting Data Discovery…')
    setCheck(null)
    setJobMsg(null)
    try {
      const d = await apiPost('/api/trigger-profiling', { ...authBody(), json: de.json })
      setJob(d.job_id ? { job_id: d.job_id } : null)
      const sc = (d.scope || []).slice(0, 6).join(', ') + ((d.scope || []).length > 6 ? '…' : '')
      setMsg(
        <>
          Started Data Discovery on <b>{d.submitted}</b> target(s){sc ? ` (${sc})` : ''}
          {d.job_id ? <> · job <code>{String(d.job_id).slice(0, 8)}…</code></> : null}
          {d.activity ? ` · ${d.activity}` : ''}
          {/* a file-level fallback still returns SUCCESS, so nothing else in PDC
              or here would ever tell you the siblings went unprofiled */}
          {d.scope_warning ? <div className="notes warn">⚠ {d.scope_warning}</div> : null}
        </>,
      )
      setCheck(d.check)
      // v3's bulk endpoint returns no job id — poll the ENTITIES instead: their
      // profiledAt flips when discovery finishes. Works on every API version.
      // The job id (v1/v2) rides along so the watcher can also see the WORKER
      // finish — some file types (pdf/docx) never get a DQ, so their profiledAt
      // never flips and entity-polling alone would hang until the budget ran out.
      if (d.scope_ids?.length) {
        watchDiscovery(d.scope_ids, d.baseline || {}, d.scope || [], d.job_id || null)
      }
    } catch (e) {
      setMsg(`Profiling failed: ${e.message}`)
    } finally {
      setBusy(false)
    }
  }

  // Per-file wrap-up once the discovery worker has finished: ✓ profiled,
  // no-DQ-from-PDC (worker done but profiledAt never flipped — expected for
  // pdf/docx-style types PDC doesn't compute DQ for), or failed (worker errored).
  function finalReport(ids, labels, per, job, elapsed) {
    const status = String(job?.status || '').toUpperCase()
    const failed = ['FAILED', 'FAIL', 'ERROR', 'CANCELLED', 'CANCELED'].includes(status)
    const done = ids.filter((i) => per[i]).length
    return (
      <span>
        <b className={failed ? 'warn' : 'ok'}>
          {failed ? '⚠' : '✓'} Data Discovery worker finished ({status || 'COMPLETED'}) in {elapsed} —{' '}
          {done} of {ids.length} target(s) profiled.
        </b>
        <span className="watch-report">
          {ids.map((id, i) => (
            <span key={id} className="watch-file">
              <code>{labels[i] || `target ${i + 1}`}</code>
              {per[id]
                ? <span className="ok"> profiled ✓</span>
                : failed
                  ? <span className="warn"> failed{job?.error ? ` — ${job.error}` : ''}</span>
                  : <span className="notes"> no DQ from PDC (expected for this file type — pdf/docx and friends profile metadata only)</span>}
            </span>
          ))}
        </span>
        {done > 0 && (
          <span className="notes">
            Re-pull the Data Elements (step 1) or the app-vs-PDC side-by-side to see each
            profiled file's Data Quality — then re-Apply and recalculate Trust.
          </span>
        )}
      </span>
    )
  }

  async function watchDiscovery(ids, baseline, labels = [], jobId = null) {
    cancelRef.current = false
    setWatch({ profiled: 0, total: ids.length })
    const started = Date.now()
    const budgetMs = 10 * 60 * 1000
    const fmtElapsed = (ms) => {
      const s = Math.round(ms / 1000)
      return s >= 60 ? `${Math.floor(s / 60)}m ${s % 60}s` : `${s}s`
    }
    let last = 0
    let lastPer = {}
    let lastJob = null
    while (!cancelRef.current && Date.now() - started < budgetMs) {
      await new Promise((r) => setTimeout(r, 6000))
      if (cancelRef.current) break
      try {
        const d = await apiPost('/api/discovery-progress', {
          ...authBody(), ids, baseline, ...(jobId ? { job_id: jobId } : {}),
        })
        last = d.profiled
        lastPer = d.per || {}
        lastJob = d.job || lastJob
        setWatch({ profiled: d.profiled, total: d.total })
        const elapsed = fmtElapsed(Date.now() - started)
        if (d.done) {
          // every target's profiledAt flipped — the all-profiled happy path
          setWatch(null)
          setMsg(
            <b className="ok">
              ✓ Data Discovery complete — {d.total} of {d.total} profiled in {elapsed}. Re-pull
              the Data Elements (step 1) or the app-vs-PDC side-by-side to see each file's Data
              Quality — then re-Apply and recalculate Trust.
            </b>,
          )
          return
        }
        if (d.worker_done) {
          // terminal-aware finish: the WORKER is done even though some files never
          // profiled (PDC yields no DQ for some types) — report per file, don't hang
          setWatch(null)
          setMsg(finalReport(ids, labels, lastPer, d.job, elapsed))
          return
        }
      } catch {
        break
      }
    }
    setWatch(null)
    const elapsed = fmtElapsed(Date.now() - started)
    if (cancelRef.current) {
      setJobMsg(`Stopped watching after ${elapsed} — the job keeps running in PDC (Workers page); ${last} of ${ids.length} profiled so far.`)
    } else {
      setJobMsg(
        <>
          <b className="warn">Watch budget reached (10 min)</b> — stopped polling after {elapsed} with{' '}
          <b>{last}</b> of {ids.length} profiled{lastJob?.status ? <> · job last seen <b>{lastJob.status}</b></> : null}.
          The job may still be running — check PDC's Workers page, or Check job status here.
          Folders sometimes don't report per-entity timestamps; files PDC can't compute DQ for
          (pdf/docx) never flip to profiled at all.
        </>,
      )
    }
  }

  async function checkJob() {
    if (!job?.job_id) {
      setJobMsg('No profiling job to check yet.')
      return
    }
    try {
      const d = await apiPost('/api/job-status', { ...authBody(), job_id: job.job_id })
      const done = ['COMPLETED', 'SUCCESS', 'SUCCEEDED', 'FAILED', 'ERROR', 'CANCELLED']
        .includes(String(d.status || '').toUpperCase())
      setJobMsg(
        <>
          Job status: <b>{d.status || 'unknown'}</b>
          {d.activity ? ` · ${d.activity}` : ''}
          {d.duration ? ` · ${Math.round(d.duration)}s` : ''}
          {done
            ? ' — when COMPLETED, the files now carry PDC profiling + Data Quality.'
            : ' — still running; check again shortly.'}
        </>,
      )
    } catch (e) {
      setJobMsg(`Status check failed: ${e.message}`)
    }
  }

  return (
    <section className="card">
      <h2>3 · Profile documents in PDC <span>before Apply — fills the gaps PDC&apos;s Data Discovery hasn&apos;t covered</span></h2>
      <p className="hint-line">
        An estate registered through the <b>bulk loader</b> with <i>discover</i> ticked already
        had PDC run Data Discovery at setup — those file-column entities exist and file Data
        Quality is computed, and this step has nothing to do. It matters for the <b>gaps</b>:
        files added <i>since</i>, stores registered <i>without</i> discovery, or metadata-only
        ingests — those show <b>Profiled Status: SKIPPED</b>, carry no file Data Quality, and
        their columns don&apos;t exist as PDC entities, so Apply reports their terms{' '}
        <i>not found</i>. The check below finds exactly those objects and submits PDC&apos;s{' '}
        <b>Data Discovery</b> for them alone — let the jobs finish <i>before</i> Apply.
        (The app&apos;s own scan-time profiling is separate: it&apos;s where your grid&apos;s
        column terms and value evidence came from, whatever PDC has done.) Database columns
        aren&apos;t affected — they profile when you scan the database.
      </p>
      <div className="actions">
        <button className="primary" onClick={trigger} disabled={busy}>
          {busy ? 'Starting…' : 'Run Data Discovery on documents'}
        </button>
        {job?.job_id && <button className="ghost" onClick={checkJob}>Check job status</button>}
        {watch && (
          <button className="ghost mini" onClick={() => { cancelRef.current = true }}>Stop watching</button>
        )}
      </div>
      {watch && (
        <>
          <div className="progress-track">
            <div className="progress-bar"
                 style={{ width: `${watch.total ? Math.round((watch.profiled / watch.total) * 100) : 0}%` }} />
          </div>
          <p className="summary">PDC Data Discovery — {watch.profiled} of {watch.total} profiled…</p>
        </>
      )}
      {msg && <p className="summary">{msg}</p>}
      {jobMsg && <p className="summary">{jobMsg}</p>}
      <CheckBlock check={check} />
    </section>
  )
}

/* ---------- app vs PDC profiling compare ---------- */

function pdcStat(stats, names) {
  if (!stats || typeof stats !== 'object') return null
  const lk = {}
  Object.keys(stats).forEach((k) => { lk[k.toLowerCase()] = stats[k] })
  for (const n of names) {
    const v = lk[n.toLowerCase()]
    if (v != null && v !== '') return v
  }
  return null
}
const asNum = (v) => (typeof v === 'number' ? v : v != null && !isNaN(parseFloat(v)) ? parseFloat(v) : null)
const fmtPct = (v) => (v == null ? '—' : `${Math.round(v * 100)}%`)
const pctOrRaw = (v) => (v == null ? '—' : v <= 1 ? fmtPct(v) : v)

function CompareCard({ discovery, authBody }) {
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState(null)
  const [profiles, setProfiles] = usePersistentState('apply.compareProfiles', null)

  async function compare() {
    if (!authBody().base_url) {
      setMsg('Enter your PDC base URL above.')
      return
    }
    const cols = []
    discovery.tables.forEach((t) => t.columns.forEach((c) => cols.push({
      schemaName: discovery.schema, tableName: t.name, columnName: c.column, type: 'COLUMN',
    })))
    setBusy(true)
    setMsg(`Pulling PDC profiling for ${cols.length} columns…`)
    try {
      const d = await apiPost('/api/pdc-profiling', { columns: cols, ...authBody() })
      setProfiles(d.profiles || {})
      setMsg(
        <>
          PDC returned profiling for <b>{d.count}</b> of {d.requested} columns.
          {/* PDC profiles server-side, so where it measured something its numbers
              beat the app's own sampling — and for a pdf/docx, which the app
              cannot read at all, they are the only measurements there will be. */}
          {d.derived_quality
            ? <> A Data Quality score is derivable from PDC's own measurements for{' '}
                <b>{d.derived_quality}</b> of them — see <i>PDC DQ</i> below.</>
            : null}
        </>,
      )
    } catch (e) {
      setMsg(`Compare failed: ${e.message}`)
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="card">
      <h2>App vs PDC profiling <span>each cell shows app / PDC</span></h2>
      <p className="hint-line">
        Side-by-side of this app's scan profiling against PDC's own stats for the same columns —
        a quick sanity check that both see the same data.
      </p>
      <div className="actions">
        <button className="ghost" onClick={compare} disabled={busy}>
          {busy ? 'Comparing…' : 'Pull PDC profiling'}
        </button>
        {msg && <span className="summary">{msg}</span>}
      </div>
      {profiles && discovery.tables.map((t) => (
        <div key={t.name} style={{ marginTop: '.8rem' }}>
          <p className="summary"><b>{t.name}</b> <span className="notes">app / PDC</span></p>
          <div className="table-scroll">
            <table>
              <thead>
                <tr><th>Column</th><th>Complete</th><th>Distinct</th><th>Unique</th><th>PDC</th></tr>
              </thead>
              <tbody>
                {t.columns.map((c) => {
                  const p = profiles[`${discovery.schema}.${t.name}.${c.column}`]
                  const st = p ? p.stats || {} : null
                  if (!p) {
                    return (
                      <tr key={c.column} style={{ opacity: .55 }}>
                        <td><b>{c.column}</b></td>
                        <td>{fmtPct(c.completeness)} <span className="notes">/ —</span></td>
                        <td>{(c.distinct || 0).toLocaleString()} <span className="notes">/ —</span></td>
                        <td>{fmtPct(c.uniqueness)} <span className="notes">/ —</span></td>
                        <td className="notes">not in PDC</td>
                      </tr>
                    )
                  }
                  const pCard = asNum(pdcStat(st, ['cardinality', 'distinctCount', 'distinct', 'distinctValues']))
                  const pUniq = asNum(pdcStat(st, ['uniqueness', 'selectivity']))
                  const pDens = asNum(pdcStat(st, ['density', 'completeness', 'nonNullDensity']))
                  const pNull = asNum(pdcStat(st, ['nulls', 'nullCount', 'nullValues']))
                  return (
                    <tr key={c.column}>
                      <td><b>{c.column}</b></td>
                      <td>{fmtPct(c.completeness)} <span className="notes">/ {pctOrRaw(pDens)}</span></td>
                      <td>{(c.distinct || 0).toLocaleString()} <span className="notes">/ {pCard == null ? '—' : pCard.toLocaleString()}</span></td>
                      <td>{fmtPct(c.uniqueness)} <span className="notes">/ {pctOrRaw(pUniq)}</span></td>
                      <td className="notes">
                        {/* derived server-side from PDC's own stats, so it exists
                            even where the app could not sample the source */}
                        {p?.derived_quality != null
                          ? <>PDC DQ <b>{p.derived_quality}</b>{pNull != null ? ` · nulls ${pNull}` : ''}</>
                          : (pNull != null ? `nulls ${pNull}` : 'matched')}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </section>
  )
}
