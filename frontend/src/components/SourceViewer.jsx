import { useEffect, useState } from 'react'
import { apiGet } from './../api.js'

// The transparency viewer: read the code that actually runs.
//
// GET /api/source           -> [{file, note}]  (a whitelist, not the filesystem)
// GET /api/source?file=X    -> {file, note, content, lines}
//
// This endpoint has existed and been server-side tested since the Jinja UI, but
// nothing called it after that UI was removed at 1.35.0 — a whole feature live
// and unreachable. It matters in a workshop: "trust me" is a poor answer when
// someone asks what the app is about to run against their database.
//
// The backend serves a WHITELIST by relative path; runtime state (settings.json,
// people.json, anything holding a secret) is never exposed, and asking for one
// answers 404 rather than a redacted file — so nothing here has to guess what is
// safe to show.
export default function SourceViewer() {
  const [files, setFiles] = useState(null)   // null = not loaded yet
  const [pick, setPick] = useState('')
  const [src, setSrc] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  // Load the index only when the panel is first opened — this is reference
  // material, not something every visit to Home should pay for.
  const load = () => {
    if (files != null) return
    apiGet('/api/source')
      .then((d) => setFiles(d.files || []))
      .catch((e) => setError(e.message))
  }

  useEffect(() => {
    if (!pick) { setSrc(null); return }
    let live = true
    setBusy(true); setError('')
    apiGet(`/api/source?file=${encodeURIComponent(pick)}`)
      .then((d) => { if (live) setSrc(d) })
      .catch((e) => { if (live) setError(e.message) })
      .finally(() => { if (live) setBusy(false) })
    return () => { live = false }
  }, [pick])

  return (
    <details className="uth" onToggle={(e) => e.currentTarget.open && load()}>
      <summary>Under the hood — read the source that runs</summary>
      <div className="uth-body">
        <p>
          Every file below is part of the running app, served straight from disk.
          Nothing is paraphrased for this page, so what you read is what executes —
          useful when someone needs to know exactly what will touch their database
          before it does.
        </p>

        {error && <div className="error">{error}</div>}
        {files == null && !error && <p className="loading">Loading…</p>}

        {files != null && (
          <div className="srcv">
            <ul className="srcv-list">
              {files.map((f) => (
                <li key={f.file}>
                  <button
                    className={`srcv-item${pick === f.file ? ' is-on' : ''}`}
                    onClick={() => setPick(pick === f.file ? '' : f.file)}
                    aria-expanded={pick === f.file}>
                    <code>{f.file}</code>
                    <span className="srcv-note">{f.note}</span>
                  </button>
                </li>
              ))}
            </ul>

            {busy && <p className="loading">Reading…</p>}
            {src && !busy && (
              <div className="srcv-pane">
                <div className="srcv-head">
                  <code>{src.file}</code>
                  <span className="muted">{src.lines?.toLocaleString()} lines</span>
                  <button className="ghost" onClick={() => setPick('')}>Close</button>
                </div>
                {/* pre, not a highlighter: a syntax library would be a large
                    dependency for a reference panel, and the point here is
                    fidelity rather than colour. */}
                <pre className="srcv-code">{src.content}</pre>
              </div>
            )}
          </div>
        )}

        <p className="uth-note">
          Runtime state is deliberately absent — settings, the roster and anything
          carrying a credential are not on the whitelist and answer 404.
        </p>
      </div>
    </details>
  )
}
