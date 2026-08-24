import { useRef, useState } from 'react'
import { apiPost } from './../api.js'

/* Ask the docs — the docs-grounded chat drawer (spec backlog 10).
   Grounded or refuse: every answer comes from the shipped documentation and
   cites its sections; when no local model is reachable the same question
   degrades to a cited doc SEARCH — stated honestly, never silently. The
   current page rides along so its own sections rank first. */
export default function DocsChat({ page }) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState(false)
  const [thread, setThread] = useState([])   // [{q, out}]
  const bodyRef = useRef(null)

  async function ask() {
    const question = q.trim()
    if (!question || busy) return
    setBusy(true)
    try {
      const out = await apiPost('/api/ask', { question, page })
      setThread((t) => [...t, { q: question, out }])
      setQ('')
      setTimeout(() => { bodyRef.current?.scrollTo(0, bodyRef.current.scrollHeight) }, 50)
    } catch (e) {
      setThread((t) => [...t, { q: question, out: { error: e.message } }])
    } finally {
      setBusy(false)
    }
  }

  return (
    <>
      <button className="ghost" onClick={() => setOpen((o) => !o)}
              title="Ask the documentation — answers come from the shipped GUIDE / WALKTHROUGH / REFERENCE / CHANGELOG and cite their sections; without a local model this is a doc search."
              aria-expanded={open}>
        ? Ask the docs
      </button>
      {open && (
        <div role="dialog" aria-label="Ask the docs"
             style={{ position: 'fixed', top: 0, right: 0, bottom: 0, width: 'min(430px, 92vw)',
                      background: 'var(--surface-1)', borderLeft: '1px solid var(--border)',
                      display: 'flex', flexDirection: 'column', zIndex: 60,
                      boxShadow: '-6px 0 24px rgba(0,0,0,.18)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '.6rem',
                        padding: '.8rem 1rem', borderBottom: '1px solid var(--border)' }}>
            <b>Ask the docs</b>
            <span className="notes">grounded in this build's documentation</span>
            <span style={{ flex: 1 }} />
            <button className="ghost" onClick={() => setOpen(false)} aria-label="Close">✕</button>
          </div>
          <div ref={bodyRef} style={{ flex: 1, overflowY: 'auto', padding: '.9rem 1rem' }}>
            {thread.length === 0 && (
              <p className="notes">
                Ask how the app works — “why do my dictionaries fire but not my
                patterns?”, “how do I factory reset?”, “since when do ratings carry
                a rater?”. Every answer cites the doc section it came from; if the
                docs don’t answer, it says so instead of guessing.
              </p>
            )}
            {thread.map((m, i) => (
              <div key={i} style={{ marginBottom: '1rem' }}>
                <p style={{ fontWeight: 650, margin: '0 0 .3rem' }}>{m.q}</p>
                {m.out.error && <p className="summary warn">{m.out.error}</p>}
                {!m.out.error && m.out.answer && (
                  <p className="summary" style={{ whiteSpace: 'pre-wrap' }}>{m.out.answer}</p>
                )}
                {!m.out.error && !m.out.answer && (
                  <>
                    <p className="notes">
                      No local model reachable — showing the matching sections instead
                      (configure Ollama on Settings for composed answers).
                    </p>
                    {(m.out.hits || []).slice(0, 3).map((h, j) => (
                      <div key={j} className="notes" style={{ margin: '.35rem 0' }}>
                        <b>{h.doc} — {h.heading}</b>
                        <div style={{ whiteSpace: 'pre-wrap' }}>{h.text.slice(0, 500)}{h.text.length > 500 ? '…' : ''}</div>
                      </div>
                    ))}
                  </>
                )}
                {!m.out.error && (m.out.cited || []).length > 0 && (
                  <p className="notes" style={{ marginTop: '.3rem' }}>
                    sources: {m.out.cited.map((c, j) => (
                      <code key={j} style={{ marginRight: '.35rem' }}>{c.doc} § {c.heading}</code>
                    ))}
                  </p>
                )}
              </div>
            ))}
            {busy && <p className="notes">reading the docs…</p>}
          </div>
          <div style={{ display: 'flex', gap: '.5rem', padding: '.8rem 1rem',
                        borderTop: '1px solid var(--border)' }}>
            <input className="text" style={{ flex: 1 }} value={q}
                   placeholder="how do I…?"
                   onChange={(e) => setQ(e.target.value)}
                   onKeyDown={(e) => { if (e.key === 'Enter') ask() }} />
            <button className="primary" onClick={ask} disabled={busy || !q.trim()}>
              {busy ? 'Asking…' : 'Ask'}
            </button>
          </div>
        </div>
      )}
    </>
  )
}
