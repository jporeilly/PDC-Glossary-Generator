import { useEffect, useState } from 'react'
import { apiGet, apiPost } from './../api.js'
import { DocsPanel } from './../components/DiscoveryPanels.jsx'
import { setDocsDiscovery, useWorkspace } from './../state.js'
import './files.css'

// Files page — the S3/MinIO object browser, split out of Connect as its own
// Connect-child page: pick a saved document-store connection, navigate the
// bucket's folders with a breadcrumb, and click a file for metadata, tags and
// an inline preview (docx HTML, text, PDF/image via a blob URL) plus download.

/* ---------- small shared helpers (kept in step with ConnectPage's copies) ---------- */

const fmtBytes = (b) => {
  if (b == null) return '—'
  const u = ['B', 'KB', 'MB', 'GB', 'TB']
  let i = 0
  let n = Number(b) || 0
  while (n >= 1024 && i < u.length - 1) { n /= 1024; i++ }
  return (i ? n.toFixed(n < 10 ? 1 : 0) : n) + ' ' + u[i]
}

const fmtDate = (iso) => {
  if (!iso) return ''
  const d = new Date(iso)
  if (isNaN(d)) return ''
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' }) +
    ', ' + d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
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

const FILE_ICON = {
  pdf: '📕', csv: '📊', tsv: '📊', xlsx: '📈', xls: '📈', parquet: '🧱',
  json: '🧾', jsonl: '🧾', ndjson: '🧾', xml: '🧾', txt: '📄', md: '📝', log: '📄',
  sql: '🗄️', html: '🌐', htm: '🌐', png: '🖼️', jpg: '🖼️', jpeg: '🖼️', gif: '🖼️',
  svg: '🖼️', zip: '🗜️', gz: '🗜️',
}
const fileIcon = (ext) => FILE_ICON[(ext || '').toLowerCase()] || '📄'

/* ================================================================== */

export default function FilesPage({ onNavigate }) {
  // The bucket profile — file-type and folder charts — renders HERE, beside
  // the files it describes, instead of on the page that triggered the scan.
  const ws = useWorkspace()
  const [conns, setConns] = useState(null)
  const [connsError, setConnsError] = useState(null)
  const [connId, setConnId] = useState('')
  const [data, setData] = useState(null)
  const [msg, setMsg] = useState('')
  const [busy, setBusy] = useState(false)
  const [openFile, setOpenFile] = useState(null)

  useEffect(() => {
    apiGet('/api/connections')
      .then((b) => setConns(b.connections ?? []))
      .catch((e) => { setConns([]); setConnsError(e.message) })
  }, [])

  const opts = (conns || []).filter((c) => c.type === 'minio')
  const selected = opts.find((c) => c.id === (connId || opts[0]?.id))

  async function browse(prefix) {
    if (!selected) { setMsg('Add a MinIO/S3 connection on the Connect page first.'); return }
    setBusy(true)
    setMsg('Loading…')
    try {
      const d = await apiPost('/api/list-objects', { minio: selected.config, prefix: prefix || '' })
      setData(d)
      setMsg('')
    } catch (err) {
      setMsg(`Could not list objects: ${err.message}`)
    } finally {
      setBusy(false)
    }
  }

  const crumbParts = data?.prefix ? data.prefix.split('/') : []

  return (
    <>
      <div className="page-head">
        <h1>Files</h1>
        <p className="psub">
          Browse a MinIO/S3 bucket — navigate folders, see sizes and types, and click a
          file to view its metadata, tags and a quick preview. Connections are managed
          on the Connect page.
        </p>
      </div>

      <section className="card">
        <h2>File browser <span>folders, objects and previews</span></h2>
        {connsError && <div className="error">{connsError}</div>}

        <details className="uth">
          <summary>Under the hood — browsing the object store (S3 API)</summary>
          <div className="uth-body">
            <p>
              Plain S3, spoken directly to the endpoint on the connection — no PDC in the middle,
              so this works before a bucket has ever been catalogued and is the quickest way to
              confirm credentials and contents are what you think.
            </p>
            <ol className="uth-steps">
              <li>
                <b>Listing</b> — <code>list_objects_v2</code> with the current prefix and a
                delimiter, paginated. The delimiter is what produces folders: S3 has none, only
                keys containing <code>/</code>, so what you see as a tree is common prefixes.
              </li>
              <li>
                <b>Preview</b> — <code>get_object</code> for the chosen key, read as a bounded
                slice rather than the whole object, so opening a large file costs the first part
                of it and no more.
              </li>
              <li>
                <b>Tags</b> — <code>get_object_tagging</code> where the store supports it. MinIO
                often does not, which is not an error: the column simply stays empty.
              </li>
            </ol>
            <p className="uth-note">
              Read-only throughout — nothing on this page writes, deletes or re-tags an object.
              Use the VM's <b>IP address</b> as the endpoint — not <code>localhost</code>, and not
              a hostname. A hostname makes the S3 SDK switch to virtual-hosted addressing and
              prepend the bucket (<code>bucket.your-host</code>), which resolves nowhere;
              an IP forces the path-style addressing MinIO needs.
            </p>
          </div>
        </details>
        <div className="actions" style={{ marginTop: 0 }}>
          <select value={connId || opts[0]?.id || ''} onChange={(e) => { setConnId(e.target.value); setData(null) }}
                  disabled={!opts.length} style={{ minWidth: 240 }}>
            {opts.length
              ? opts.map((c) => <option key={c.id} value={c.id}>{c.name || 'MinIO'} — {(c.config || {}).bucket || ''}</option>)
              : <option value="">No MinIO/S3 connection — add one on the Connect page</option>}
          </select>
          <button className="primary" onClick={() => browse('')} disabled={busy || !opts.length}>Browse</button>
          {!opts.length && conns != null && (
            <button className="ghost" onClick={() => onNavigate('connect')}>Add a connection →</button>
          )}
          {msg && <span className="summary">{msg}</span>}
        </div>

        {data && (
          <>
            <div className="fb-bar">
              <div className="fb-crumbs">
                <button onClick={() => browse('')}>🪣 {data.bucket || 'bucket'}</button>
                {crumbParts.map((p, i) => (
                  <span key={i}>
                    <span className="sep">/</span>
                    {i === crumbParts.length - 1
                      ? <span className="cur">{p}</span>
                      : <button onClick={() => browse(crumbParts.slice(0, i + 1).join('/'))}>{p}</button>}
                  </span>
                ))}
              </div>
              <span className="fb-stat">
                {data.folder_count} folder{data.folder_count !== 1 ? 's' : ''} ·{' '}
                {data.file_count} file{data.file_count !== 1 ? 's' : ''} ·{' '}
                {fmtBytes(data.total_bytes)}{data.truncated ? ' · truncated' : ''}
              </span>
            </div>
            <div className="fb-list">
              <div className="fb-row head">
                <span /><span>Name</span><span className="fb-type">Type</span>
                <span className="fb-sz">Size</span><span className="fb-md">Modified</span>
              </div>
              {data.folders.length === 0 && data.files.length === 0 && (
                <div className="fb-empty">This folder is empty.</div>
              )}
              {data.folders.map((f) => (
                <div className="fb-row dir" key={f.prefix} onClick={() => browse(f.prefix)}>
                  <span>📁</span>
                  <span className="fb-name">{f.name}</span>
                  <span className="fb-type">folder</span><span className="fb-sz" /><span className="fb-md" />
                </div>
              ))}
              {data.files.map((f) => (
                <div className="fb-row file" key={f.key}>
                  <span>{fileIcon(f.ext)}</span>
                  <span className="fb-name" title={f.name} onClick={() => setOpenFile(f)}>{f.name}</span>
                  <span className="fb-type">{f.ext || '—'}</span>
                  <span className="fb-sz">{fmtBytes(f.size)}</span>
                  <span className="fb-md">{fmtDate(f.modified)}</span>
                </div>
              ))}
            </div>
          </>
        )}

        {openFile && selected && (
          <FileModal file={openFile} conn={selected} onClose={() => setOpenFile(null)} />
        )}
      </section>

      {ws.docsDiscovery && (
        <DocsPanel docs={{ name: ws.docsDiscovery.name || 'this store',
                           data: ws.docsDiscovery }}
                   onRefilter={async (include, exclude) => {
                     const conn = (conns || []).find((c) => c.id === connId)
                     if (!conn) return
                     const d = await apiPost('/api/discover-docs', {
                       conn: { ...conn.config, include, exclude },
                     })
                     setDocsDiscovery({ ...d, name: conn.name })
                   }} />
      )}
    </>
  )
}

// Fetch a whole object as a blob URL (PDF/image preview, downloads). Raw fetch:
// /api/object-bytes streams binary, which the JSON wrapper can't carry.
async function objectBlobUrl(conn, key) {
  const res = await fetch('/api/object-bytes', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ minio: conn.config, key }),
  })
  if (!res.ok) {
    const j = await res.json().catch(() => null)
    throw new Error((j && j.error) || 'Could not load file')
  }
  return URL.createObjectURL(await res.blob())
}

function FileModal({ file, conn, onClose }) {
  const [detail, setDetail] = useState(null)
  const [error, setError] = useState(null)
  const [blobUrl, setBlobUrl] = useState(null)
  const [blobError, setBlobError] = useState(null)

  useEffect(() => {
    let gone = false
    let url = null
    apiPost('/api/object', { minio: conn.config, key: file.key })
      .then((d) => {
        if (gone) return
        setDetail(d)
        if (['pdf', 'image'].includes(d.preview_kind)) {
          objectBlobUrl(conn, file.key)
            .then((u) => { if (gone) URL.revokeObjectURL(u); else { url = u; setBlobUrl(u) } })
            .catch((e) => { if (!gone) setBlobError(e.message) })
        }
      })
      .catch((e) => { if (!gone) setError(e.message) })
    return () => { gone = true; if (url) URL.revokeObjectURL(url) }
  }, [conn, file])

  async function download() {
    try {
      const u = await objectBlobUrl(conn, file.key)
      const a = document.createElement('a')
      a.href = u
      a.download = file.name || file.key.split('/').pop()
      document.body.appendChild(a); a.click(); a.remove()
      setTimeout(() => URL.revokeObjectURL(u), 4000)
    } catch (e) {
      setBlobError(`Download failed: ${e.message}`)
    }
  }

  const d = detail
  const kind = d?.preview_kind || 'none'
  const tags = d ? (d.tags || []).concat(Object.entries(d.metadata || {}).map(([k, v]) => ({ key: k, value: v }))) : []

  return (
    <Modal wide title={`${fileIcon(file.ext)} ${file.name}`} onClose={onClose}>
      {error && <div className="error">{error}</div>}
      {!d && !error && <p className="loading">Loading…</p>}
      {d && (
        <>
          <div className="obj-meta">
            <b>Size</b> {fmtBytes(d.size)} · <b>Type</b> {d.content_type || file.ext || '—'} ·{' '}
            <b>Modified</b> {fmtDate(d.modified)}
          </div>
          <div className="obj-meta"><b>Key</b> {d.key}</div>
          {tags.length > 0 && (
            <div className="obj-tags">
              {tags.map((t, i) => <span className="badge neutral" key={i}>{t.key}: {t.value}</span>)}
            </div>
          )}
          <div className="actions">
            <button className="ghost" onClick={download}>Download</button>
            {['pdf', 'image'].includes(kind) && blobUrl && (
              <button className="ghost" onClick={() => window.open(blobUrl, '_blank')}>Open in new tab</button>
            )}
          </div>
          {blobError && <div className="error">{blobError}</div>}
          {kind === 'pdf' && (blobUrl
            ? <iframe className="obj-frame" src={blobUrl} title={file.name} />
            : !blobError && <p className="loading">Rendering…</p>)}
          {kind === 'image' && (blobUrl
            ? <img className="obj-img" src={blobUrl} alt={file.name} />
            : !blobError && <p className="loading">Rendering…</p>)}
          {kind === 'docx' && (d.html
            // Backend-rendered Word preview (mammoth) — same trust as the old UI.
            ? <div className="obj-docx" dangerouslySetInnerHTML={{ __html: d.html }} />
            : <p className="hint-line">Couldn't render this Word document{d.docx_error ? `: ${d.docx_error}` : ' (install mammoth for best results)'}. Use Download.</p>)}
          {kind === 'text' && d.preview != null && (
            <>
              <div className="obj-preview">{d.preview}</div>
              {d.preview_truncated && <p className="hint-line">… preview truncated</p>}
            </>
          )}
          {kind === 'none' && <p className="hint-line">No inline preview for this file type — use Download.</p>}
        </>
      )}
    </Modal>
  )
}
