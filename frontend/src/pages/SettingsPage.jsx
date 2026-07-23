import { useEffect, useRef, useState } from 'react'
import ThemeSelect from './../components/ThemeSelect.jsx'
import { apiGet, apiPost, runJob } from './../api.js'

// Curated model suggestions (same list the old UI seeds its dropdown with);
// the live /api/models list is layered on top as "Installed".
const MODELS = [
  { tag: 'llama3.2:3b', size: '~2.0 GB', rec: true },
  { tag: 'qwen2.5:3b', size: '~1.9 GB' },
  { tag: 'phi3:mini', size: '~2.3 GB' },
  { tag: 'gemma2:2b', size: '~1.6 GB' },
  { tag: 'mistral', size: '~4.1 GB' },
  { tag: 'llama3.1', size: '~4.9 GB' },
]

const CUSTOM = '__custom__'

// Settings page: state snapshot, local LLM (Ollama URL / model / pull /
// compute / enrichment tuning), hardware detection, database drivers and
// appearance. Everything persists through POST /api/settings — a saved value
// overrides the corresponding env var, a cleared one falls back to it.
export default function SettingsPage({ version }) {
  const [settings, setSettings] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    apiGet('/api/settings').then(setSettings).catch((e) => setError(e.message))
  }, [])

  // Persist a partial settings patch; the backend merges and applies LLM
  // config changes immediately (no restart).
  async function saveField(patch) {
    setSettings((s) => ({ ...s, ...patch }))
    try {
      await apiPost('/api/settings', patch)
    } catch (err) {
      setError(err.message)
    }
  }

  if (error && !settings) return <div className="error">{error}</div>
  if (!settings) return <p className="loading">Loading settings…</p>

  return (
    <div className="settings">
      <div className="page-head">
        <h1>Settings</h1>
        <p className="psub">Configure the local LLM, hardware, backups and appearance.</p>
      </div>
      {error && <div className="error">{error}</div>}

      <div className="set-grid">
        <SnapshotCard />
        <LlmCard settings={settings} saveField={saveField} />
        <LabStoreCard />
        <DetectCard />
        <DriversCard />

        <section className="card">
          <h2>Appearance</h2>
          <div className="form-grid">
            <label>
              Color theme
              <ThemeSelect />
            </label>
          </div>
        </section>

        <section className="card">
          <h2>About</h2>
          <dl>
            <dt>Version</dt><dd>{version}</dd>
            <dt>Service</dt><dd>PDC Glossary Generator — local-first, single user</dd>
            <dt>Hand-off</dt><dd>authors classification-registry/1 for the Policy Generator</dd>
            <dt>PDC</dt><dd>validated against Pentaho Data Catalog 11.0.0 (public API v3)</dd>
          </dl>
        </section>
      </div>
    </div>
  )
}

/* ---------- state snapshot: backup / restore the app's persisted files ---------- */

function SnapshotCard() {
  const [msg, setMsg] = useState('')
  const fileRef = useRef(null)

  async function restore(file) {
    if (!file) return
    if (!window.confirm(
      `Restore app state from "${file.name}"?\n\nThis overwrites the current settings, ` +
      'connections, saved glossaries, dictionary, roster, audit trail, Registries and ' +
      'installed pack. Each overwritten file is backed up beside itself first.')) return
    setMsg('Restoring…')
    try {
      const res = await fetch('/api/state-restore', {
        method: 'POST',
        headers: { 'Content-Type': 'application/zip' },
        body: file,
      })
      const d = await res.json()
      if (d.error) {
        setMsg(`Restore failed: ${d.error}`)
        return
      }
      const vnote = d.snapshot_version && d.snapshot_version !== d.running_version
        ? ` · snapshot from v${d.snapshot_version}, running v${d.running_version} (state formats self-heal on load)`
        : ''
      setMsg(`Restored ${d.restored.length} file(s)` +
        (d.skipped.length ? `, skipped ${d.skipped.length} unrecognized` : '') +
        (d.backed_up ? ` · ${d.backed_up} previous file(s) backed up` : '') +
        `${vnote} — reload the page to pick everything up.`)
    } catch (err) {
      setMsg(`Restore failed: ${err.message}`)
    }
  }

  return (
    <section className="card span2">
      <h2>State snapshot <span>backup &amp; restore everything this app knows</span></h2>
      <p className="hint-line">
        Connections, settings, saved glossaries, the governed Term &amp; Tag dictionary,
        roster, audit trail, Registries and the installed domain pack — one zip. The
        working review grid autosaves server-side once named, but Save glossary before a
        snapshot so it's inside <code>glossaries.json</code>.
      </p>
      <div className="actions">
        <button className="ghost" onClick={() => { window.location.href = '/api/state-snapshot' }}>
          ⬇ Download snapshot
        </button>
        <button className="primary" onClick={() => fileRef.current?.click()}>Restore from snapshot…</button>
        <input ref={fileRef} type="file" accept=".zip" style={{ display: 'none' }}
               onChange={(e) => { restore(e.target.files[0]); e.target.value = '' }} />
        {msg && <span className="summary">{msg}</span>}
      </div>
    </section>
  )
}

/* ---------- local LLM (Ollama): URL, model, pull, compute, tuning ---------- */

function LlmCard({ settings, saveField }) {
  const [installed, setInstalled] = useState([])
  const [testMsg, setTestMsg] = useState(null)
  const [pull, setPull] = useState(null)   // {phase, pct, label} while pulling

  const model = settings.model || 'llama3.2:3b'
  const isCurated = MODELS.some((m) => m.tag === model)
  const [custom, setCustom] = useState(isCurated || !model ? '' : model)
  const selectValue = installed.includes(model) || isCurated ? model : model ? CUSTOM : 'llama3.2:3b'

  const refreshModels = () =>
    apiGet('/api/models')
      .then((b) => setInstalled(b.models ?? []))
      .catch(() => {})

  useEffect(() => { refreshModels() }, [])

  async function testConnection(patch = {}) {
    setTestMsg('Testing connection…')
    if (Object.keys(patch).length) await saveField(patch)
    try {
      const m = patch.model ?? model
      const s = await apiGet(`/api/llm-status?model=${encodeURIComponent(m)}`)
      setTestMsg(s.online
        ? `✓ Connected to ${s.url}` + (s.model_present === false
            ? ` — model ${s.model} not pulled (use Pull selected model)`
            : ` · model ${s.model} ready`)
        : `✗ Offline at ${s.url}${s.error ? ` — ${s.error}` : ''}. In Docker, set the URL to http://host.docker.internal:11434.`)
    } catch (err) {
      setTestMsg(`✗ Test failed: ${err.message}`)
    }
  }

  // Pull the selected model through the background-job twin of /api/pull-model:
  // POST /api/jobs/pull-model -> poll /api/jobs/{id}; the latest event carries
  // {phase, status, completed, total, percent}.
  async function pullModel() {
    setPull({ phase: 'starting', pct: 0, label: `Pulling ${model}…` })
    try {
      await runJob('pull-model', { model }, (job) => {
        const ev = job.events[job.events.length - 1] || {}
        const pct = ev.percent ?? (job.total ? Math.round((job.done / job.total) * 100) : 0)
        setPull({ phase: job.phase, pct, label: ev.status || job.phase || 'Pulling…' })
      })
      setPull({ phase: 'success', pct: 100, label: 'Model ready.' })
      refreshModels()
      testConnection()
    } catch (err) {
      setPull({ phase: 'error', pct: 0, label: `Pull failed: ${err.message}` })
    }
  }

  function onModelChange(v) {
    if (v === CUSTOM) {
      setCustom('')
      return
    }
    setCustom('')
    saveField({ model: v })
    testConnection({ model: v })
  }

  const numeric = (v, parse) => (v === '' ? '' : parse(v))

  return (
    <section className="card span2">
      <h2>Local LLM <span>Ollama — enrichment, QA and the AI agents</span></h2>
      <div className="form-grid">
        <label>
          Ollama URL
          <input type="text" placeholder="http://localhost:11434"
                 defaultValue={settings.ollama_url || ''}
                 onBlur={(e) => testConnection({ ollama_url: e.target.value.trim() })} />
        </label>
        <label>
          Timeout (s)
          <input type="number" min="1" step="1" placeholder="30"
                 defaultValue={settings.llm_timeout ?? ''}
                 onBlur={(e) => saveField({ llm_timeout: numeric(e.target.value, parseFloat) })} />
        </label>
        <label>
          Model
          <select value={selectValue} onChange={(e) => onModelChange(e.target.value)}>
            {installed.length > 0 && (
              <optgroup label="Installed (ready to use)">
                {installed.map((t) => <option key={t} value={t}>{t}</option>)}
              </optgroup>
            )}
            <optgroup label="Suggested — not yet pulled">
              {MODELS.filter((m) => !installed.includes(m.tag)).map((m) => (
                <option key={m.tag} value={m.tag}>
                  {m.tag} · {m.size}{m.rec ? ' · recommended' : ''}
                </option>
              ))}
            </optgroup>
            <option value={CUSTOM}>Custom…</option>
          </select>
        </label>
        {selectValue === CUSTOM && (
          <label>
            Custom model
            <input type="text" placeholder="e.g. gemma2:2b" value={custom}
                   onChange={(e) => setCustom(e.target.value)}
                   onBlur={() => custom.trim() && (saveField({ model: custom.trim() }), testConnection({ model: custom.trim() }))} />
          </label>
        )}
        <label>
          GPU offload
          <span className="seg">
            {[['auto', 'Auto'], ['gpu', 'Max'], ['cpu', 'Off']].map(([c, l]) => (
              <button key={c} type="button" className={(settings.compute || 'auto') === c ? 'on' : undefined}
                      onClick={() => saveField({ compute: c })}>
                {l}
              </button>
            ))}
          </span>
        </label>
      </div>
      <div className="actions">
        <button className="primary" onClick={() => testConnection()}>Test connection</button>
        <button className="primary" onClick={pullModel} disabled={pull != null && pull.phase !== 'error' && pull.phase !== 'success'}>
          Pull selected model
        </button>
        {testMsg && <span className="summary">{testMsg}</span>}
      </div>
      {pull && (
        <>
          <div className="progress-track"><div className="progress-bar" style={{ width: `${pull.pct}%` }} /></div>
          <p className="summary">{pull.label}{pull.pct ? ` · ${pull.pct}%` : ''}</p>
        </>
      )}
      <p className="hint-line">
        Saved here, the URL <b>overrides</b> the <code>OLLAMA_URL</code> environment
        variable — no restart needed. Clear a field to fall back to the environment default.
      </p>
      <h3 className="subhead">Enrichment tuning</h3>
      <div className="form-grid">
        <label>
          Company
          <input type="text" placeholder="your organization"
                 defaultValue={settings.company || ''}
                 onBlur={(e) => saveField({ company: e.target.value.trim() })} />
          <span className="muted">used in enrichment prompts</span>
        </label>
        <label>
          Enrich workers (1–16)
          <input type="number" min="1" max="16" step="1" placeholder="4"
                 defaultValue={settings.llm_workers ?? ''}
                 onBlur={(e) => saveField({ llm_workers: numeric(e.target.value, (v) => parseInt(v, 10)) })} />
        </label>
        <label>
          Batch size (1–20)
          <input type="number" min="1" max="20" step="1" placeholder="6"
                 defaultValue={settings.llm_batch ?? ''}
                 onBlur={(e) => saveField({ llm_batch: numeric(e.target.value, (v) => parseInt(v, 10)) })} />
        </label>
      </div>
      <p className="hint-line">
        These override <code>GLOSSARY_COMPANY</code>, <code>LLM_WORKERS</code> and{' '}
        <code>LLM_BATCH</code> at runtime. Higher workers/batch = faster enrichment but
        heavier on the GPU.
      </p>
    </section>
  )
}

/* ---------- lab object store (MinIO) — the "Send to lab" export target ----------
   Configures a single dedicated MinIO/S3 connection (id 'lab-minio') that the
   Apply page's "Send to lab" uploads to. Test uses the bucket-agnostic
   reachability check so it goes green on valid endpoint+credentials even before
   the export bucket exists. */

const EMPTY_LAB = { endpoint: '', access_key: '', secret_key: '', bucket: '', secure: false }

function LabStoreCard() {
  const [cfg, setCfg] = useState(null)
  const [connId, setConnId] = useState(null)
  const [status, setStatus] = useState(null)   // {state:'checking'|'ok'|'bad', message}
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    apiGet('/api/connections').then((d) => {
      const stores = (d.connections || []).filter((c) => ['minio', 's3'].includes(String(c.type || '').toLowerCase()))
      const lab = stores.find((c) => c.id === 'lab-minio')
        || stores.find((c) => String(c.name || '').toLowerCase() === 'lab minio')
      if (lab) {
        setConnId(lab.id)
        setCfg({ ...EMPTY_LAB, ...(lab.config || {}) })
        check({ ...EMPTY_LAB, ...(lab.config || {}) })
      } else {
        setCfg({ ...EMPTY_LAB })
      }
    }).catch(() => setCfg({ ...EMPTY_LAB }))
  }, [])  // eslint-disable-line react-hooks/exhaustive-deps

  const set = (patch) => setCfg((c) => ({ ...c, ...patch }))

  // Keep the endpoint scheme and the HTTPS box in sync so they can't disagree
  // (a leading https:// in the URL used to silently win over an un-ticked box).
  const onEndpoint = (v) => {
    const m = /^(https?):\/\//i.exec(v.trim())
    set(m ? { endpoint: v, secure: m[1].toLowerCase() === 'https' } : { endpoint: v })
  }
  const onSecure = (checked) => {
    const next = (cfg?.endpoint || '').replace(/^https?:\/\//i, checked ? 'https://' : 'http://')
    set({ secure: checked, endpoint: next })
  }
  // Nudge on the two lab mistakes: the console port, or an S3 URL with no port.
  const ep = (cfg?.endpoint || '').trim()
  const epWarn = /:9001(\/|$)/.test(ep) ? 'That’s the web console port — the S3 API is on :9000.'
    : (ep && !/:\d+/.test(ep)) ? 'No port given — the lab S3 API is on :9000 (e.g. http://pentaho.io:9000).'
    : ''

  async function check(config) {
    setStatus({ state: 'checking', message: 'Checking…' })
    try {
      const d = await apiPost('/api/lab-minio-status', { config })
      setStatus({ state: d.ok ? 'ok' : 'bad', message: d.message || (d.ok ? 'Connected' : 'Not connected') })
    } catch (e) {
      setStatus({ state: 'bad', message: e.message })
    }
  }

  async function save() {
    setBusy(true)
    try {
      const d = await apiPost('/api/connections', { id: connId || 'lab-minio', name: 'Lab MinIO', type: 'minio', config: cfg })
      setConnId((d.connection && d.connection.id) || 'lab-minio')
      await check(cfg)
    } catch (e) {
      setStatus({ state: 'bad', message: e.message })
    }
    setBusy(false)
  }

  if (!cfg) return <section className="card span2"><h2>Lab object store (MinIO)</h2><p className="loading">Loading…</p></section>

  return (
    <section className="card span2">
      <h2>Lab object store <span>MinIO — the “Send to lab” export target</span></h2>
      <p className="hint-line">
        Where <b>Apply → Send to lab</b> uploads the generated JSONL / policies so you can grab
        them on the demo VM. The <b>S3 API is on <code>:9000</code></b> — <code>:9001</code> is the
        web console only, and <code>mc</code> also talks to <code>:9000</code>.
      </p>
      <div className="form-grid">
        <label>
          Endpoint
          <input type="text" placeholder="http://pentaho.io:9000" value={cfg.endpoint}
                 onChange={(e) => onEndpoint(e.target.value)} />
          {epWarn && <span className="warn" style={{ fontSize: '.78rem' }}>{epWarn}</span>}
        </label>
        <label>
          <span>Bucket <span className="muted">(optional)</span></span>
          <input type="text" placeholder="pdc-exports (created on first use)" value={cfg.bucket}
                 onChange={(e) => set({ bucket: e.target.value })} />
        </label>
        <label>
          Access key
          <input type="text" autoComplete="off" value={cfg.access_key}
                 onChange={(e) => set({ access_key: e.target.value })} />
        </label>
        <label>
          Secret key
          <input type="password" autoComplete="off" value={cfg.secret_key}
                 onChange={(e) => set({ secret_key: e.target.value })} />
        </label>
        <label className="check">
          <input type="checkbox" checked={!!cfg.secure}
                 onChange={(e) => onSecure(e.target.checked)} />
          Use HTTPS (TLS) — leave off for a plain-HTTP lab MinIO on :9000
        </label>
      </div>
      <div className="actions">
        <button className="ghost" onClick={() => check(cfg)} disabled={!cfg.endpoint}>Test connection</button>
        <button className="primary" onClick={save} disabled={busy || !cfg.endpoint}>{busy ? 'Saving…' : 'Save lab store'}</button>
        {status && (
          <span className="conn" style={{ fontSize: '.85rem' }}>
            <span className={`dot ${status.state === 'ok' ? 'ok' : status.state === 'checking' ? 'checking' : 'bad'}`} />
            {status.message}
          </span>
        )}
      </div>
    </section>
  )
}

/* ---------- hardware detection (GET /api/detect) ---------- */

function DetectCard() {
  const [report, setReport] = useState(null)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  const detect = () => {
    setBusy(true)
    setError(null)
    apiGet('/api/detect')
      .then(setReport)
      .catch((e) => setError(e.message))
      .finally(() => setBusy(false))
  }

  useEffect(() => { detect() }, [])

  const tiles = report ? [
    { value: report.platform, label: 'platform' },
    { value: report.ram_gb != null ? `${report.ram_gb} GB` : '—', label: 'RAM' },
    { value: report.gpu_count ? `${report.vram_gb ?? '?'} GB` : 'none', label: report.gpu_name || 'GPU VRAM' },
    { value: report.ollama.running ? (report.ollama.version || 'up') : 'down', label: `Ollama · ${report.ollama.base_url}` },
    { value: report.ollama.installed_models.length, label: 'models installed' },
  ] : []

  return (
    <section className="card span2">
      <header>
        <h2>Hardware &amp; Ollama detection <span>what this host can run</span></h2>
        <button className="ghost" onClick={detect} disabled={busy}>{busy ? 'Detecting…' : 'Re-detect'}</button>
      </header>
      {error && <div className="error">{error}</div>}
      {!report && !error && <p className="loading">Detecting…</p>}
      {report && (
        <>
          <div className="tiles">
            {tiles.map((t) => (
              <div className="tile" key={t.label}>
                <div className="value">{String(t.value)}</div>
                <div className="label">{t.label}</div>
              </div>
            ))}
          </div>
          <p className="hint-line">
            <b>Recommended model:</b> <code>{report.recommendation.model}</code> —{' '}
            {report.recommendation.reason}
          </p>
          {Object.keys(report.recommendation.env_suggestions || {}).length > 0 && (
            <p className="hint-line">
              Suggested environment:{' '}
              {Object.entries(report.recommendation.env_suggestions).map(([k, v]) => (
                <code key={k} style={{ marginRight: '.6rem' }}>{k}={v}</code>
              ))}
            </p>
          )}
        </>
      )}
    </section>
  )
}

/* ---------- database drivers (GET /api/drivers) ---------- */

function DriversCard() {
  const [drivers, setDrivers] = useState(null)

  useEffect(() => {
    apiGet('/api/drivers').then((b) => setDrivers(b.drivers ?? [])).catch(() => setDrivers([]))
  }, [])

  return (
    <section className="card span2">
      <h2>Database drivers <span>live scans use Python drivers</span></h2>
      {drivers == null && <p className="loading">Checking…</p>}
      {drivers?.length > 0 && (
        <div className="table-scroll">
          <table>
            <thead>
              <tr><th>Engine</th><th>Python driver</th><th>Status</th><th>Install</th><th>PDC JDBC jar</th></tr>
            </thead>
            <tbody>
              {drivers.map((d) => (
                <tr key={d.module}>
                  <td>{d.label}</td>
                  <td><code>{d.module}</code></td>
                  <td>
                    {d.present
                      ? <span className="badge good">installed{d.version ? ` ${d.version}` : ''}</span>
                      : <span className="badge warning">not installed</span>}
                  </td>
                  <td><code>{d.install}</code></td>
                  <td className="notes">{d.jdbc_hint}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
