import { useRef, useState } from 'react'
import { apiPost } from './../api.js'
import { usePersistentState } from './../state.js'

/* Ask the docs — the docs-grounded chat drawer (spec backlog 10; W21 upload).
   Grounded or refuse: every answer comes from the shipped documentation and
   cites its sections; when no local model is reachable the same question
   degrades to a cited doc SEARCH — stated honestly, never silently. The
   current page rides along so its own sections rank first.

   Field-shaped (2026-08-24):
   - "takes far too long to respond": the drawer now shows the RETRIEVED
     SECTIONS instantly (one fast ai:false round-trip) and fills in the
     composed answer when the model returns — the wait has something to read;
   - "upload for example the Glossary so that it can check the format,
     repair": Check a file runs the deterministic import-contract validator
     (line-numbered findings, mechanical repairs downloadable) and its
     findings join the chat context, so "what's wrong with my file?" answers
     from the actual findings;
   - "delete chat and keep chat history": the thread persists across
     open/close and page hops, the last exchanges ride along as context for
     follow-ups, and Clear wipes it deliberately. */
export default function DocsChat({ page }) {
  const [open, setOpen] = useState(false)
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState(false)
  const [thread, setThread] = usePersistentState('docschat.thread', [])  // [{q, out, composing} | {file, check}]
  const [fileCtx, setFileCtx] = usePersistentState('docschat.fileCtx', null) // {name, note}
  const fileRef = useRef(null)
  const bodyRef = useRef(null)

  const scrollDown = () =>
    setTimeout(() => { bodyRef.current?.scrollTo(0, bodyRef.current.scrollHeight) }, 50)

  function historyPairs() {
    // the last answered exchanges, oldest first — context for follow-ups
    return thread.filter((m) => m.q && m.out && !m.out.error)
      .slice(-3).map((m) => ({ q: m.q, a: m.out.answer || '' }))
  }

  async function ask() {
    const question = q.trim()
    if (!question || busy) return
    setBusy(true)
    setQ('')
    const base = { question, page, history: historyPairs(),
                   ...(fileCtx ? { file_context: fileCtx.note } : {}) }
    try {
      // phase 1 — retrieval only: instant, so the sections show while the
      // model works instead of a long silent wait
      const fast = await apiPost('/api/ask', { ...base, ai: false })
      setThread((t) => [...t.slice(-19), { q: question, out: fast, composing: true }])
      scrollDown()
      // phase 2 — the composed answer replaces the placeholder when it lands
      const full = await apiPost('/api/ask', { ...base, ai: true })
      setThread((t) => t.map((m) => (m.q === question && m.composing
        ? { q: question, out: full } : m)))
      scrollDown()
    } catch (e) {
      setThread((t) => {
        const held = t.filter((m) => !(m.q === question && m.composing))
        return [...held, { q: question, out: { error: e.message } }]
      })
    } finally {
      setBusy(false)
    }
  }

  async function checkFile(f) {
    if (!f) return
    setBusy(true)
    try {
      const content = await f.text()
      const res = await apiPost('/api/check-file', { name: f.name, content })
      setThread((t) => [...t.slice(-19), { file: f.name, check: res }])
      setFileCtx({ name: f.name, note: res.context_note })
      scrollDown()
    } catch (e) {
      setThread((t) => [...t, { file: f.name, check: null, out: { error: e.message } }])
    } finally {
      setBusy(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  function downloadRepaired(name, text) {
    const a = document.createElement('a')
    a.href = URL.createObjectURL(new Blob([text], { type: 'application/x-ndjson' }))
    a.download = name.replace(/\.jsonl?$/i, '') + '.repaired.jsonl'
    a.click()
    URL.revokeObjectURL(a.href)
  }

  return (
    <>
      <button className="ghost" onClick={() => setOpen((o) => !o)}
              title="Ask the documentation — answers come from the shipped GUIDE / WALKTHROUGH / REFERENCE / CHANGELOG and cite their sections; without a local model this is a doc search. Also checks an uploaded glossary JSONL against the import contract."
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
            {thread.length > 0 && (
              <button className="ghost" onClick={() => { setThread([]); setFileCtx(null) }}
                      title="Delete this conversation. Until then it persists across pages and reopenings, and the last exchanges ride along as context for follow-up questions.">
                Clear
              </button>
            )}
            <button className="ghost" onClick={() => setOpen(false)} aria-label="Close">✕</button>
          </div>
          <div ref={bodyRef} style={{ flex: 1, overflowY: 'auto', padding: '.9rem 1rem' }}>
            {thread.length === 0 && (
              <p className="notes">
                Ask how the app works — “why do my dictionaries fire but not my
                patterns?”, “how do I factory reset?” — or <b>Check a file</b> to
                validate a glossary JSONL against the import contract (line-numbered
                findings; mechanical fixes come back as a repaired download).
                Every answer cites its source; if the docs don’t answer, it says so
                instead of guessing.
              </p>
            )}
            {thread.map((m, i) => (
              <div key={i} style={{ marginBottom: '1rem' }}>
                {m.file && (
                  <>
                    <p style={{ fontWeight: 650, margin: '0 0 .3rem' }}>⇪ {m.file}</p>
                    {m.check ? (
                      <>
                        <p className="summary" style={{ whiteSpace: 'pre-wrap' }}>{m.check.summary}</p>
                        {(m.check.findings || []).slice(0, 12).map((f, j) => (
                          <div key={j} className={`notes${f.severity === 'error' ? ' warn' : ''}`}>
                            {f.line ? `line ${f.line}: ` : ''}[{f.severity}] {f.message}
                          </div>
                        ))}
                        {(m.check.findings || []).length > 12 && (
                          <p className="notes">… and {(m.check.findings || []).length - 12} more — ask about them below.</p>
                        )}
                        {m.check.repaired && (
                          <button className="ghost sm" style={{ marginTop: '.4rem' }}
                                  onClick={() => downloadRepaired(m.file, m.check.repaired)}
                                  title="The file with every mechanical repair applied (BOM, blank lines, tag casing, fqdn drift, resourceId). Identity is never rewritten — errors listed above still need fixing at the source.">
                            ⬇ Download repaired file
                          </button>
                        )}
                        <p className="notes" style={{ marginTop: '.3rem' }}>
                          the findings now ride along as context — ask “what’s wrong with my file?”
                        </p>
                      </>
                    ) : m.out?.error ? <p className="summary warn">{m.out.error}</p> : null}
                  </>
                )}
                {m.q && (
                  <>
                    <p style={{ fontWeight: 650, margin: '0 0 .3rem' }}>{m.q}</p>
                    {m.out.error && <p className="summary warn">{m.out.error}</p>}
                    {!m.out.error && m.out.answer && (
                      <p className="summary" style={{ whiteSpace: 'pre-wrap' }}>{m.out.answer}</p>
                    )}
                    {!m.out.error && !m.out.answer && m.composing && (
                      /* while composing, NAME the sections — the field verdict
                         on showing their bodies was "dont need to show the
                         detailed request"; the answer that replaces this is
                         the readable version of the same material */
                      <>
                        <p className="notes">composing the answer from:</p>
                        {(m.out.hits || []).slice(0, 3).map((h, j) => (
                          <p key={j} className="notes" style={{ margin: '.15rem 0' }}>
                            <code>{h.doc} § {h.heading}</code>
                          </p>
                        ))}
                      </>
                    )}
                    {!m.out.error && !m.out.answer && !m.composing && (
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
                    {!m.out.error && !m.composing && (m.out.cited || []).length > 0 && (
                      <p className="notes" style={{ marginTop: '.3rem' }}>
                        sources: {m.out.cited.map((c, j) => (
                          <code key={j} style={{ marginRight: '.35rem' }}>{c.doc} § {c.heading}</code>
                        ))}
                      </p>
                    )}
                  </>
                )}
              </div>
            ))}
            {busy && <p className="notes">reading the docs…</p>}
          </div>
          <div style={{ display: 'flex', gap: '.5rem', padding: '.8rem 1rem',
                        borderTop: '1px solid var(--border)', alignItems: 'center' }}>
            <input ref={fileRef} type="file" accept=".jsonl,.json" style={{ display: 'none' }}
                   onChange={(e) => checkFile(e.target.files?.[0])} />
            <button className="ghost" disabled={busy} onClick={() => fileRef.current?.click()}
                    title="Upload a glossary-import JSONL (e.g. a Generate export, hand-edited or from elsewhere). Deterministic check against the import contract — no model involved — with mechanical repairs as a download, and the findings join the chat as context."
                    aria-label="Check a file">
              ⇪ Check a file
            </button>
            <input className="text" style={{ flex: 1 }} value={q}
                   placeholder={fileCtx ? `ask about ${fileCtx.name} or the docs…` : 'how do I…?'}
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
