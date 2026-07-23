// Shared workspace state — the single source of truth for the loaded glossary
// (the review grid the whole workflow revolves around). Module-level store, no
// context provider: pages read it with useWorkspace() and mutate it through
// the exported actions, mirroring the old UI's global ROWS/CUR_GLOSS.
//
// Autosave: any mutation marks the workspace dirty and schedules a debounced
// save; a 30-second interval sweeps up anything the debounce missed. Saves go
// to the old UI's endpoint (POST /api/glossaries) and only run once the
// glossary has an id or a name — a scratch grid is never persisted silently.

import { useCallback, useState, useSyncExternalStore } from 'react'
import { apiGet, apiPost } from './api.js'

const ws = {
  id: null,          // saved-glossary id (null until first save)
  name: '',          // the saved-glossary display name
  glossaryName: '',  // the PDC glossary name used at generate time
  rows: [],          // review-grid rows (Category/Term/Definition/… per column)
  discovery: null,   // data-discovery profile captured with the glossary
  governance: null,  // Govern page's buildGovernance() output (stewardship,
                     // ratings, per-category overrides) — legacy `governance` key
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

export function setUi(key, value) {
  uiCache.set(key, value)
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
  return [v, set]
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
  ws.rows = []; ws.discovery = null; ws.governance = null
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
  ws.governance = g.governance || null
  ws.dirty = false
  ws.savedAt = g.savedAt || null
  ws.saveError = null
  clearUi('review.')   // a different glossary — its filters/resolutions don't apply
  emit()
  return g
}

// Persist the workspace: POST /api/glossaries (save-or-overwrite by id).
export async function save() {
  if (!ws.rows.length || !canAutosave()) return null
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

export function scheduleSave(delay = DEBOUNCE_MS) {
  if (!canAutosave()) return
  clearTimeout(saveTimer)
  saveTimer = setTimeout(() => { save() }, delay)
}

setInterval(() => {
  if (ws.dirty && ws.rows.length && !ws.saving) save()
}, AUTOSAVE_MS)
