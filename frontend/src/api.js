// Fetch wrapper for the Glossary Generator backend (glossary_generator/api.py).
// Every error path there returns {"error": msg} — never FastAPI's {"detail"} —
// so that is the one shape we surface. A few legacy routes answer 200 with an
// {error} body; treat those as failures too.

async function request(path, options = {}) {
  let res
  try {
    res = await fetch(path, options)
  } catch {
    throw new Error('Cannot reach the Glossary Generator backend.')
  }
  const ct = res.headers.get('content-type') || ''
  const body = ct.includes('json') ? await res.json().catch(() => null) : null
  if (!res.ok) throw new Error((body && body.error) || `${res.status} ${res.statusText}`)
  if (body && body.error) throw new Error(body.error)
  return body
}

export const apiGet = (path) => request(path)
export const apiDelete = (path) => request(path, { method: 'DELETE' })
export const apiPost = (path, body) =>
  request(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body ?? {}),
  })

/* ---------- non-JSON responses (text / binary downloads) ----------
   Same error contract as request(): a failed call surfaces the backend's
   {"error": msg} when present, else "status statusText". apiText GETs a
   text body (markdown, JSONL, CSV); apiBlob GETs — or POSTs, when a body
   is given — a binary payload (zip bundles, exports) for downloadBlob().  */

async function rawFetch(path, options) {
  let res
  try {
    res = await fetch(path, options)
  } catch {
    throw new Error('Cannot reach the Glossary Generator backend.')
  }
  if (!res.ok) {
    const ct = res.headers.get('content-type') || ''
    const body = ct.includes('json') ? await res.json().catch(() => null) : null
    throw new Error((body && body.error) || `${res.status} ${res.statusText}`)
  }
  return res
}

export const apiText = (path) => rawFetch(path).then((res) => res.text())
export const apiBlob = (path, body) =>
  rawFetch(path, body === undefined ? undefined : {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body ?? {}),
  }).then((res) => res.blob())

/* ---------- background jobs (the preferred pattern for long work) ----------
   POST /api/jobs/{resolve-terms|apply-to-pdc|bulk-load|pull-model} -> {job}
   GET  /api/jobs/{id} -> {status: running|done|error, done, total, phase,
                           detail, events, result}                            */

export const startJob = (name, body) => apiPost(`/api/jobs/${name}`, body)
export const pollJob = (id) => apiGet(`/api/jobs/${id}`)

// Start a job and poll it to completion. onTick(job) fires after every poll —
// use job.done/job.total/job.phase for progress and job.events for detail
// (pull-model events also carry {status, completed, total, percent}).
// Resolves with job.result; rejects with job.detail on error.
export async function runJob(name, body, onTick, interval = 700) {
  const { job } = await startJob(name, body)
  for (;;) {
    const j = await pollJob(job)
    if (onTick) onTick(j)
    if (j.status === 'done') return j.result ?? j
    if (j.status === 'error') throw new Error(j.detail || `Job ${name} failed`)
    await new Promise((r) => setTimeout(r, interval))
  }
}

/* ---------- NDJSON streaming (legacy twins) ----------
   The jobs endpoints above are the React-era path; this reader exists only if
   a page genuinely needs the byte-compatible streaming twin (/api/pull-model,
   /api/resolve-terms-stream, /api/apply-to-pdc-stream, /api/pdc/bulk-load).
   Calls onEvent(obj) per newline-delimited JSON event.                        */

export async function streamNdjson(path, body, onEvent) {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body ?? {}),
  })
  if (!res.ok || !res.body) {
    const j = await res.json().catch(() => null)
    throw new Error((j && j.error) || res.statusText)
  }
  const reader = res.body.getReader()
  const dec = new TextDecoder()
  let buf = ''
  for (;;) {
    const { value, done } = await reader.read()
    if (done) break
    buf += dec.decode(value, { stream: true })
    let nl
    while ((nl = buf.indexOf('\n')) >= 0) {
      const line = buf.slice(0, nl).trim()
      buf = buf.slice(nl + 1)
      if (line) onEvent(JSON.parse(line))
    }
  }
}
