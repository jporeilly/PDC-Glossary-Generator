import { Fragment, useEffect, useState } from 'react'
import Markdown from './components/Markdown.jsx'
import ThemeSelect from './components/ThemeSelect.jsx'
import HomePage from './pages/HomePage.jsx'
import ConnectPage from './pages/ConnectPage.jsx'
import SchemaPage from './pages/SchemaPage.jsx'
import FilesPage from './pages/FilesPage.jsx'
import ReviewPage from './pages/ReviewPage.jsx'
import GovernPage from './pages/GovernPage.jsx'
import ApplyPage from './pages/ApplyPage.jsx'
import DictionaryPage from './pages/DictionaryPage.jsx'
import SettingsPage from './pages/SettingsPage.jsx'
import { useWorkspace } from './state.js'
import { apiGet } from './api.js'

/* Nav icons — the suite's shared visual family (24 viewBox, 1.7 stroke),
   same set style as PDC-Insights' shell. */
const ICONS = {
  home: <path d="M4 13h6V4H4v9Zm0 7h6v-5H4v5Zm10 0h6V11h-6v9Zm0-16v5h6V4h-6Z" stroke="currentColor" strokeWidth="1.7" fill="none" />,
  connect: <><ellipse cx="12" cy="6" rx="7" ry="2.7" stroke="currentColor" strokeWidth="1.7" fill="none" /><path d="M5 6v12c0 1.5 3.1 2.7 7 2.7s7-1.2 7-2.7V6" stroke="currentColor" strokeWidth="1.7" fill="none" /><path d="M5 12c0 1.5 3.1 2.7 7 2.7s7-1.2 7-2.7" stroke="currentColor" strokeWidth="1.7" fill="none" /></>,
  schema: <><rect x="4" y="4.5" width="16" height="15" rx="2" stroke="currentColor" strokeWidth="1.7" fill="none" /><path d="M4 9.5h16M9.3 9.5v10M14.7 9.5v10" stroke="currentColor" strokeWidth="1.7" fill="none" /></>,
  files: <><path d="M13.5 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8.5L13.5 3Z" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" fill="none" /><path d="M13.5 3v5.5H19" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" fill="none" /></>,
  review: <><rect x="4" y="5" width="16" height="14" rx="2" stroke="currentColor" strokeWidth="1.7" fill="none" /><path d="M4 10h16M10 10v9" stroke="currentColor" strokeWidth="1.7" fill="none" /></>,
  govern: <><path d="M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6l7-3Z" stroke="currentColor" strokeWidth="1.7" strokeLinejoin="round" fill="none" /><path d="m9 12 2 2 4-4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" fill="none" /></>,
  apply: <><path d="M12 17V5m0 0-4.2 4.2M12 5l4.2 4.2" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" fill="none" /><path d="M4.5 19.5h15" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" fill="none" /></>,
  dictionary: <><path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" fill="none" /><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2Z" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" fill="none" /></>,
  settings: <><circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="1.7" fill="none" /><path d="M12 2v3m0 14v3M2 12h3m14 0h3M4.9 4.9l2.1 2.1m10 10 2.1 2.1M19.1 4.9 17 7m-10 10-2.1 2.1" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" fill="none" /></>,
}

function Ico({ id }) {
  return <svg className="nav-ico" viewBox="0 0 24 24">{ICONS[id]}</svg>
}

// The persistent workflow stepper — same stages as the old UI's #flow bar
// (Dictionary sits in the nav; it gates Govern but isn't its own stage here).
const STEPS = [
  { id: 'connect', label: 'Connect', hint: 'add sources & scan',
    tip: 'Add a connection per source — database, MinIO/S3 store or DDL file — then scan to suggest candidate terms.' },
  { id: 'review', label: 'Review', hint: 'prune candidate terms',
    tip: 'Every column becomes one candidate term. Edit definitions, sensitivity and tags inline, and prune the noise.' },
  { id: 'govern', label: 'Govern', hint: 'stewardship & ratings',
    tip: 'Set steward, owner, custodian, status and rating — saved with the workspace and baked into the JSONL at generate time.' },
  { id: 'apply', label: 'Apply', hint: 'generate, resolve & write',
    tip: 'Generate the import-ready JSONL (+ Registry), import it in PDC, resolve term ids, then apply the term↔column links with a dry-run first.' },
]

// Child pages rendered indented under a workflow step in the nav. They keep
// their parent as the active stepper stage (Schema/Files are Connect's).
const SUBPAGES = {
  connect: [
    { id: 'schema', label: 'Schema', tip: 'Browse a database or DDL connection\'s tables with PK/FK badges and relationships, and write missing keys back with a dry-run first.' },
    { id: 'files', label: 'Files', tip: 'Browse a MinIO/S3 bucket — folders, sizes, metadata, previews and downloads.' },
  ],
}
const PARENT_STEP = { schema: 'connect', files: 'connect' }

const PAGES = {
  home: HomePage,
  connect: ConnectPage,
  schema: SchemaPage,
  files: FilesPage,
  review: ReviewPage,
  govern: GovernPage,
  apply: ApplyPage,
  dictionary: DictionaryPage,
  settings: SettingsPage,
}

/* Breadcrumb trail per page (last segment bold) — mirrors the sidebar sections. */
const CRUMBS = {
  home: ['Home'],
  connect: ['Workflow', 'Connect'],
  schema: ['Workflow', 'Connect', 'Schema'],
  files: ['Workflow', 'Connect', 'Files'],
  review: ['Workflow', 'Review'],
  govern: ['Workflow', 'Govern'],
  apply: ['Workflow', 'Apply'],
  dictionary: ['Governance', 'Dictionary'],
  settings: ['Configure', 'Settings'],
}

export default function App() {
  const [page, setPage] = useState('home')
  const [version, setVersion] = useState('')
  const [company, setCompany] = useState('')
  const [llm, setLlm] = useState(null)
  const [showWhatsNew, setShowWhatsNew] = useState(false)
  const ws = useWorkspace()

  useEffect(() => {
    apiGet('/api/version')
      .then((v) => setVersion(v.version))
      .catch(() => {})
    apiGet('/api/settings')
      .then((s) => setCompany(s.company || ''))
      .catch(() => {})
  }, [])

  useEffect(() => {
    let stop = false
    const probe = () =>
      apiGet('/api/llm-status')
        .then((s) => { if (!stop) setLlm(s) })
        .catch(() => { if (!stop) setLlm({ online: false }) })
    probe()
    const t = setInterval(probe, 60000)
    return () => { stop = true; clearInterval(t) }
  }, [])

  const Page = PAGES[page]
  // Child pages (Schema/Files) keep their parent step active in the stepper.
  const stepPage = PARENT_STEP[page] || page
  const showStepper = STEPS.some((s) => s.id === stepPage)
  const stepIdx = STEPS.findIndex((s) => s.id === stepPage)
  const crumbs = CRUMBS[page]

  const llmOk = llm?.online && llm.model_present !== false
  const llmText = llm == null ? 'checking…'
    : llm.online
      ? (llm.model_present === false ? `${llm.model} not pulled` : `Ollama · ${llm.model}`)
      : 'offline'

  // Session-only PDC connectivity (ws.pdcSession) — flips live the moment a
  // page completes a real authenticated PDC round-trip. Detail: username if
  // we have one, else the base host.
  const pdc = ws.pdcSession
  const pdcHost = (pdc?.base || '').replace(/^https?:\/\//i, '').replace(/[/?#].*$/, '')
  const pdcDetail = pdc?.connected ? (pdc.user || pdcHost) : ''

  return (
    <div className="shell">
      <aside className="side">
        <div className="brand">
          <div className="brand-mark">
            <svg width="17" height="17" viewBox="0 0 24 24" fill="none">
              <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2Z"
                    stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <div>
            <div className="brand-name">Glossary <em>Generator</em></div>
            <div className="brand-sub">{company || 'Pentaho Data Catalog'}</div>
          </div>
          {version && (
            <button className="version-pill" onClick={() => setShowWhatsNew(true)}
                    title="What's new — the release notes for the build you're running">
              v{version}
            </button>
          )}
        </div>

        <nav className="nav">
          <button className={`nav-item${page === 'home' ? ' active' : ''}`}
                  title="Workflow overview, saved glossaries and best practices"
                  onClick={() => setPage('home')} aria-current={page === 'home' ? 'page' : undefined}>
            <Ico id="home" />Home
          </button>
          <div className="nav-label">Workflow</div>
          {STEPS.map((s) => (
            <Fragment key={s.id}>
              <button className={`nav-item${page === s.id ? ' active' : ''}`}
                      title={s.tip} onClick={() => setPage(s.id)}
                      aria-current={page === s.id ? 'page' : undefined}>
                <Ico id={s.id} />{s.label}
              </button>
              {(SUBPAGES[s.id] || []).map((sub) => (
                <button key={sub.id} className={`nav-item nav-sub${page === sub.id ? ' active' : ''}`}
                        title={sub.tip} onClick={() => setPage(sub.id)}
                        aria-current={page === sub.id ? 'page' : undefined}>
                  <Ico id={sub.id} />{sub.label}
                </button>
              ))}
            </Fragment>
          ))}
          <div className="nav-label">Governance</div>
          <button className={`nav-item${page === 'dictionary' ? ' active' : ''}`}
                  title="The governed Term & Tag dictionary — approve pending vocabulary, export the domain pack"
                  onClick={() => setPage('dictionary')}
                  aria-current={page === 'dictionary' ? 'page' : undefined}>
            <Ico id="dictionary" />Dictionary
          </button>
          <div className="nav-label">Configure</div>
          <button className={`nav-item${page === 'settings' ? ' active' : ''}`}
                  title="Local LLM, hardware, backups and appearance"
                  onClick={() => setPage('settings')}
                  aria-current={page === 'settings' ? 'page' : undefined}>
            <Ico id="settings" />Settings
          </button>
        </nav>

        <div className="side-foot">
          <div className="conn" title="Local LLM status — configure on the Settings page">
            <span className={`dot ${llmOk ? 'ok' : 'warn'}`} />
            LLM&nbsp;·&nbsp;<span className="mono">{llmText}</span>
          </div>
          <div className="conn"
               title={pdc?.connected
                 ? `Connected to PDC at ${pdc.base}${pdc.user ? ` as ${pdc.user}` : ''} — session only, cleared on reload`
                 : 'No PDC session yet — authenticate on the Apply page (PDC connection) or the Connect page (Harvest from PDC)'}>
            <span className={`dot${pdc?.connected ? ' ok' : ''}`}
                  style={pdc?.connected ? undefined : { background: 'var(--text-muted)', opacity: .45 }} />
            PDC&nbsp;·&nbsp;{pdc?.connected
              ? <>connected{pdcDetail ? <>&nbsp;·&nbsp;<span className="mono">{pdcDetail}</span></> : null}</>
              : <span className="mono">not connected</span>}
          </div>
          <div className="conn" title="The interactive OpenAPI docs for this app's backend">
            API&nbsp;·&nbsp;<a className="mono" href="/docs" target="_blank" rel="noreferrer">docs</a>
          </div>
          <ThemeSelect />
        </div>
      </aside>

      <div className="main">
        <header className="topbar">
          <div className="crumb">
            {crumbs.slice(0, -1).map((c, i) => <span key={i}>{c}&nbsp;/&nbsp;</span>)}
            <b>{crumbs[crumbs.length - 1]}</b>
          </div>
          <div className="topbar-spacer" />
        </header>

        <div className="content">
          {showStepper && (
            <ol className="stepper">
              {STEPS.map((s, i) => {
                const state = i < stepIdx ? 'done' : i === stepIdx ? 'active' : 'ready'
                return (
                  <li key={s.id} className={state}>
                    <button onClick={() => setPage(s.id)} title={s.tip}
                            aria-current={i === stepIdx ? 'step' : undefined}>
                      <span className="dot">{i < stepIdx ? '✓' : i + 1}</span>
                      <span className="step-text">
                        <span className="step-label">{s.label}</span>
                        <span className="step-hint">{s.hint}</span>
                      </span>
                    </button>
                    {i < STEPS.length - 1 && <span className="bar" aria-hidden="true" />}
                  </li>
                )
              })}
            </ol>
          )}
          <Page onNavigate={setPage} version={version} />
          {ws.saveError && (
            <div className="error">Autosave failed: {ws.saveError}</div>
          )}
        </div>
      </div>

      {showWhatsNew && (
        <WhatsNewModal onClose={() => setShowWhatsNew(false)} />
      )}
    </div>
  )
}

// Release notes for the running build (GET /api/whatsnew). If the changelog's
// leading version is newer than the running version, the checkout was updated
// without a restart — surface that as a stale-build warning.
function WhatsNewModal({ onClose }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState(null)

  useEffect(() => {
    apiGet('/api/whatsnew').then(setData).catch((e) => setError(e.message))
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  const stale = data?.releases?.length > 0 && data.releases[0].version !== data.version

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" role="dialog" aria-modal="true" aria-label="What's new"
           onClick={(e) => e.stopPropagation()}>
        <header>
          <h3>What's new{data?.version ? ` — running v${data.version}` : ''}</h3>
          <button className="ghost" onClick={onClose} aria-label="Close">✕</button>
        </header>
        <div className="modal-body">
          {error && <div className="error">{error}</div>}
          {!data && !error && <p className="loading">Loading release notes…</p>}
          {data && stale && (
            <div className="error">
              ⚠ The checkout's changelog leads with v{data.releases[0].version} but this
              process is running v{data.version} — the code was updated without a restart
              (or the pull didn't complete). Restart the app so they match.
            </div>
          )}
          {data && data.releases?.length === 0 && (
            <p className="hint-line">
              Release notes unavailable in this build (docs/CHANGELOG.md isn't shipped
              in e.g. the Docker image) — see CHANGELOG.md on GitHub.
            </p>
          )}
          {data?.releases?.map((r) => (
            <div className="wn-release" key={r.version}>
              <b>v{r.version}</b> <span className="notes">{r.date}</span>
              <Markdown text={r.body || ''} />
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
