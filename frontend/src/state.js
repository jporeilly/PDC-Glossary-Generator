// Shared workspace state — the single source of truth for the loaded glossary
// (the review grid the whole workflow revolves around). Module-level store, no
// context provider: pages read it with useWorkspace() and mutate it through
// the exported actions, mirroring the old UI's global ROWS/CUR_GLOSS.
//
// Autosave: any mutation marks the workspace dirty and schedules a debounced
// save; a 30-second interval sweeps up anything the debounce missed. Saves go
// to the old UI's endpoint (POST /api/glossaries) and only run once the
// glossary has an id or a name — a scratch grid is never persisted silently.

import { useCallback, useEffect, useRef, useState, useSyncExternalStore } from 'react'
import { apiGet, apiPost } from './api.js'

const ws = {
  id: null,          // saved-glossary id (null until first save)
  name: '',          // the saved-glossary display name
  glossaryName: '',  // the PDC glossary name used at generate time
  rows: [],          // review-grid rows (Category/Term/Definition/… per column)
  discovery: null,   // data-discovery profile captured with the glossary
  docsDiscovery: null, // bucket profile — rendered on the Files page
  governance: null,  // Govern page's buildGovernance() output (stewardship,
                     // ratings, per-category overrides) — legacy `governance` key
  categoriesConfirmed: null,  // the KEYSTONE: {at, categories} once the steward
                              // approves the settled taxonomy on Review
  reviewCompleted: null,      // {at} once the steward marks the Review stage done
                              // (saved + Dictionary synced at that moment)
  dirty: false,
  saving: false,
  savedAt: null,
  saveError: null,
  pdcSession: null,  // session-only PDC connectivity: {connected, base, user, at}
                     // — set by pages after a real authenticated PDC round-trip,
                     // shown as the sidebar's "PDC ·" status dot. NEVER persisted
                     // in the glossary save body.
}

let snapshot = { ...ws }
const listeners = new Set()

function emit() {
  snapshot = { ...ws }
  listeners.forEach((fn) => fn())
}

export function getWorkspace() {
  return snapshot
}

export function subscribe(fn) {
  listeners.add(fn)
  return () => listeners.delete(fn)
}

// React hook — re-renders the component whenever the workspace changes.
export function useWorkspace() {
  return useSyncExternalStore(subscribe, getWorkspace)
}

/* ---------- session-scoped page UI state ----------
   App renders only the active page, so an inactive page unmounts and its local
   useState resets — navigate Review → Dictionary → Review and the filters, the
   open editor row, duplicate-resolution state and scroll would all be gone even
   though the rows above survive. This module-level cache keeps a page's
   transient UI for the session (cleared on a full reload, like the rows). Keys
   are namespaced per page, e.g. 'review.filters'. */

const uiCache = new Map()

export function getUi(key, fallback = null) {
  return uiCache.has(key) ? uiCache.get(key) : fallback
}

// Subscribers per cache key: a background loop that outlives its page writes
// through setUi, and the REMOUNTED page needs to repaint when it does — the
// new mount's state setter is not the one the old loop captured.
const uiSubs = new Map()

export function setUi(key, value) {
  uiCache.set(key, value)
  const subs = uiSubs.get(key)
  if (subs) subs.forEach((fn) => fn(value))
}

export function subscribeUi(key, fn) {
  let subs = uiSubs.get(key)
  if (!subs) uiSubs.set(key, (subs = new Set()))
  subs.add(fn)
  return () => subs.delete(fn)
}

// Drop every cached UI value under a namespace — call when the underlying data
// is replaced (e.g. a different glossary is opened) so stale filters/resolution
// state can't bleed across.
export function clearUi(prefix) {
  for (const k of [...uiCache.keys()]) if (k.startsWith(prefix)) uiCache.delete(k)
}

// useState whose value survives unmount/remount within the session. Same API as
// useState (value + setter, functional updates supported); the value is mirrored
// into uiCache under `key` so the next mount restores it.
export function usePersistentState(key, initial) {
  const [v, setV] = useState(() =>
    uiCache.has(key) ? uiCache.get(key) : (typeof initial === 'function' ? initial() : initial))
  const set = useCallback((next) => {
    setV((prev) => {
      const val = typeof next === 'function' ? next(prev) : next
      uiCache.set(key, val)
      return val
    })
  }, [key])
  // external writes (setUi from a loop that outlived its page) repaint this
  // mount too — identical values bail out in React, so no update loops
  useEffect(() => subscribeUi(key, (val) => setV(val)), [key])
  return [v, set]
}

/* ---------- resumable jobs ----------
   A long AI run must survive the page that started it: the app renders only
   the active page, so navigating away unmounts the component and a plain
   await loses the response ("state is not held if i browse other pages?").
   The run itself lives on the BACKEND as a job; this hook keeps the job id
   in the session cache and re-attaches the poll on whichever mount comes
   back. Close the page, browse, come back - the result lands when ready. */

export function useResumableJob(cacheKey, { onDone, onError, onLost, onBusy, onTick } = {}) {
  const [job, setJob] = usePersistentState(cacheKey, null)
  const cbs = useRef(null)
  cbs.current = { onDone, onError, onLost, onBusy, onTick }
  useEffect(() => {
    if (!job?.id) return undefined
    let dead = false
    cbs.current.onBusy?.(true, job)
    const tick = async () => {
      let j
      try {
        j = await apiGet(`/api/jobs/${job.id}`)
      } catch {
        // the backend forgot the job (restart) - tell the page, honestly
        if (!dead) { setJob(null); cbs.current.onBusy?.(false, job); cbs.current.onLost?.(job) }
        return
      }
      if (dead) return
      if (j.status === 'done') {
        setJob(null); cbs.current.onBusy?.(false, job)
        cbs.current.onDone?.(j.result, job)
      } else if (j.status === 'error') {
        setJob(null); cbs.current.onBusy?.(false, job)
        cbs.current.onError?.(j.detail || 'unknown error', job)
      } else {
        cbs.current.onTick?.(j, job)
        setTimeout(tick, 900)
      }
    }
    tick()
    return () => { dead = true }
  }, [job?.id])   // eslint-disable-line react-hooks/exhaustive-deps
  return {
    running: !!job?.id,
    startedAt: job?.started || null,
    start: async (name, body, meta = {}) => {
      const d = await apiPost(`/api/jobs/${name}`, body)
      setJob({ id: d.job, started: Date.now(), ...meta })
      return d.job
    },
  }
}

/* ---------- mutations (each marks dirty + schedules the autosave) ---------- */

export function setRows(rows, { dirty = true } = {}) {
  ws.rows = rows
  if (dirty) markDirty()
  else emit()
}

export function patchRow(index, patch) {
  ws.rows = ws.rows.map((r, i) => (i === index ? { ...r, ...patch } : r))
  markDirty()
}

export function setGlossaryMeta({ name, glossaryName } = {}) {
  if (name != null) {
    ws.name = name
    // The PDC glossary name (used at export) defaults to the saved-glossary
    // name so the Govern "Glossary name" field isn't blank — still editable,
    // and an explicit glossaryName below always wins.
    if (!ws.glossaryName) ws.glossaryName = name
  }
  if (glossaryName != null) ws.glossaryName = glossaryName
  markDirty()
}

export function setCategoriesConfirmed(v) {
  // The keystone survives with the workspace: {at, categories} — or null to
  // withdraw it. Downstream pages read it instead of guessing whether the
  // taxonomy has settled.
  ws.categoriesConfirmed = v || null
  markDirty()
}

export function setReviewCompleted(v) {
  ws.reviewCompleted = v || null
  markDirty()
}

export function setDocsDiscovery(d) {
  // the object-store profile belongs to the page that browses files, so it
  // rides the workspace rather than one page's local state
  ws.docsDiscovery = d || null
  markDirty()
}

export function setDiscovery(discovery) {
  ws.discovery = discovery
  markDirty()
}

// The Govern page keeps this current whenever its inputs change; the Apply
// page's Generate includes it in POST /api/generate. Persisted in the save
// body under the same `governance` key the legacy UI uses, so saved
// glossaries stay interoperable between the two UIs. No-ops on an identical
// value so re-renders don't churn the autosave.
export function setGovernance(governance) {
  if (JSON.stringify(governance ?? null) === JSON.stringify(ws.governance ?? null)) return
  ws.governance = governance ?? null
  markDirty()
}

// Record (or clear, with null) the app-session PDC connection for the sidebar
// status row. Call it only after a round-trip that genuinely proved
// connectivity (e.g. a minted token or an authenticated /api/pdc/* read).
// Deliberately does NOT markDirty: the session is not glossary state and must
// never reach the save body or trigger an autosave.
export function setPdcSession(session) {
  ws.pdcSession = session
    ? {
        connected: true,
        base: session.base || '',
        user: session.user || '',
        at: session.at || Date.now(),
      }
    : null
  emit()
}

export function clearWorkspace() {
  ws.id = null; ws.name = ''; ws.glossaryName = ''
  ws.rows = []; ws.discovery = null; ws.docsDiscovery = null; ws.governance = null
  ws.categoriesConfirmed = null; ws.reviewCompleted = null
  ws.dirty = false; ws.savedAt = null; ws.saveError = null
  clearUi('review.')
  emit()
}

export function markDirty() {
  ws.dirty = true
  emit()
  scheduleSave()
}

/* ---------- load / save (the old UI's endpoints) ---------- */

// Open a saved glossary: GET /api/glossaries/{id} -> {id, name, rows, …}.
export async function openGlossary(id) {
  const g = await apiGet(`/api/glossaries/${id}`)
  ws.id = g.id
  ws.name = g.name || ''
  // Fall back to the saved-glossary name so the Govern "Glossary name" field is
  // pre-filled instead of blank when the glossary was saved without an explicit
  // PDC glossary name.
  ws.glossaryName = g.glossary_name || g.name || ''
  ws.rows = g.rows || []
  ws.discovery = g.discovery || null
  ws.docsDiscovery = g.docs_discovery || null
  ws.governance = g.governance || null
  ws.categoriesConfirmed = g.categories_confirmed || null
  ws.reviewCompleted = g.review_completed || null
  ws.dirty = false
  ws.savedAt = g.savedAt || null
  ws.saveError = null
  clearUi('review.')   // a different glossary — its filters/resolutions don't apply
  emit()
  return g
}

// Persist the workspace: POST /api/glossaries (save-or-overwrite by id).
export async function save() {
  if (wiped || !ws.rows.length || !canAutosave()) return null
  ws.saving = true
  emit()
  try {
    const r = await apiPost('/api/glossaries', {
      id: ws.id || undefined,
      name: ws.name || ws.glossaryName || 'Untitled glossary',
      glossary_name: ws.glossaryName || undefined,
      rows: ws.rows,
      governance: ws.governance || undefined,
      discovery: ws.discovery || undefined,
    docs_discovery: ws.docsDiscovery || undefined,
      docs_discovery: ws.docsDiscovery || undefined,
      categories_confirmed: ws.categoriesConfirmed || undefined,
      review_completed: ws.reviewCompleted || undefined,
    })
    ws.id = r.id
    ws.savedAt = r.savedAt
    ws.dirty = false
    ws.saveError = null
    return r
  } catch (err) {
    ws.saveError = err.message
    return null
  } finally {
    ws.saving = false
    emit()
  }
}

function canAutosave() {
  return !!(ws.id || ws.name)
}

/* ---------- autosave plumbing ---------- */

const DEBOUNCE_MS = 2000
const AUTOSAVE_MS = 30000
let saveTimer = null

// Set by a factory reset. The workspace lives in TAB MEMORY, so a wipe that
// only deletes files would be undone by the next autosave (2s debounce, 30s
// timer, or the pagehide beacon) writing the same glossary straight back —
// the reset would appear to work and the estate would return. Once wiped,
// this process saves nothing again until it reloads.
let wiped = false
export function markWiped() {
  wiped = true
  clearTimeout(saveTimer)
}

export function scheduleSave(delay = DEBOUNCE_MS) {
  if (wiped || !canAutosave()) return
  clearTimeout(saveTimer)
  saveTimer = setTimeout(() => { save() }, delay)
}

setInterval(() => {
  if (!wiped && ws.dirty && ws.rows.length && !ws.saving) save()
}, AUTOSAVE_MS)

/* ---------- leaving the page ----------
   The workspace lives in tab memory and the autosave only runs for a NAMED
   glossary, on a 2s debounce. Without an exit flush, "Add to glossary"
   followed by a reload silently lost the merge — the recurring "the JDBC
   scan didn't add its terms" report. On the way out: flush a pending save
   with sendBeacon (it survives page teardown, where a normal fetch is
   killed); if the grid holds rows that CAN'T autosave yet (no name), ask
   the browser for the leave-confirmation instead. */
window.addEventListener('pagehide', () => {
  // a wiped process must not beacon its old workspace back on the way out —
  // that would resurrect the estate the reset just deleted
  if (wiped || !ws.dirty || !ws.rows.length || !canAutosave()) return
  const body = new Blob([JSON.stringify({
    id: ws.id || undefined,
    name: ws.name || ws.glossaryName || 'Untitled glossary',
    glossary_name: ws.glossaryName || undefined,
    rows: ws.rows,
    governance: ws.governance || undefined,
    discovery: ws.discovery || undefined,
    categories_confirmed: ws.categoriesConfirmed || undefined,
    review_completed: ws.reviewCompleted || undefined,
  })], { type: 'application/json' })
  if (navigator.sendBeacon('/api/glossaries', body)) ws.dirty = false
})
window.addEventListener('beforeunload', (e) => {
  if (ws.dirty && ws.rows.length && !canAutosave()) {
    e.preventDefault()
    e.returnValue = ''   // legacy Chrome shows the prompt only with returnValue set
  }
})
