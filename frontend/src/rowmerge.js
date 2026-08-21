// Row identity and merging for the shared workspace — used by every path
// that brings scanned/harvested rows into a grid that already has rows
// (ConnectPage), and by the Review page's same-source repair.
//
// IDENTITY IS EVIDENCE, NOT LABELS. Rows used to merge on the old UI's
// Category|Term key — but Category and Term are precisely the fields the
// steward settles (renamed categories, AI-corrected names), so after a
// review every re-ingestion missed every existing row and APPENDED the
// whole estate again: 133 kept terms became 248, with 96 names repeating
// across categories (field-caught on the fresh-install exam). A row is
// identified by the source columns it carries — the one thing a steward
// edit never changes. Conceptual rows with no sources fall back to the
// term name alone.
//
// foldSources preserves the steward's work by construction: the kept row's
// edits win, and only source linkage + scan evidence is absorbed.

const splitCols = (s) => String(s || '').split(';').map((t) => t.trim()).filter(Boolean)

export function foldSources(base, nr, { refreshEvidence = false } = {}) {
  const next = { ...base }
  const seen = new Set(splitCols(base.Source_Column))
  const cols = [...seen]
  splitCols(nr.Source_Column).forEach((s) => { if (!seen.has(s)) { seen.add(s); cols.push(s) } })
  next.Source_Column = cols.join('; ')
  for (const f of ['Source_Ratings', 'Source_Keys', 'Source_Quality_Dims']) {
    if (nr[f] && Object.keys(nr[f]).length) next[f] = { ...(base[f] || {}), ...nr[f] }
  }
  const rating = Math.max(parseInt(base.Suggested_Rating || 0, 10) || 0,
                          parseInt(nr.Suggested_Rating || 0, 10) || 0)
  if (rating || base.Suggested_Rating != null) next.Suggested_Rating = rating
  // Only set when non-zero: an unprofilable row (pdf/docx) must stay WITHOUT
  // a score rather than acquire a 0, which would assert measured-and-terrible.
  const quality = Math.max(parseInt(base.Suggested_Quality || 0, 10) || 0,
                           parseInt(nr.Suggested_Quality || 0, 10) || 0)
  if (quality) next.Suggested_Quality = quality
  // VALUE EVIDENCE: fill-only by default (steward work is never disturbed by
  // a rescan). refreshEvidence — for when the DATA has genuinely improved
  // (the estate was rescaled, profiling re-run) — lets the fresh profile win.
  //
  // A fresh observation is ONE observation, not five independent fields, and
  // in refresh mode it replaces the set WHOLE — blanks included. Merging it
  // field-wise was a silent-staleness bug: the repaired AWC columns came back
  // as enums with no regular shape, so Value_Pattern arrived BLANK, and a
  // blank "never erases" left ^[A-Z]{2}[0-9]{4}$ standing on County, Severity,
  // System Type and five more. Those patterns matched zero rows on the estate
  // and would have deployed as methods that could never fire — the refresh
  // reporting success while the row still asserted a shape the data no longer
  // has. A scan that saw NOTHING at all (an unprofilable pdf/docx row) still
  // never erases what is already there.
  const EVIDENCE = ['Value_Signature', 'Value_Pattern', 'Enum_Values', 'Value_Kind', 'Value_Range']
  if (refreshEvidence && EVIDENCE.some((f) => nr[f])) {
    EVIDENCE.forEach((f) => { next[f] = nr[f] || '' })
  } else {
    for (const f of EVIDENCE) {
      if (nr[f] && !next[f]) next[f] = nr[f]
    }
  }
  // Detection_Intent is NOT evidence — it carries the steward's Auto flips —
  // so it stays fill-only in EVERY mode: only a row that never had an intent
  // adopts the nature default.
  if (!next.Detection_Intent && nr.Detection_Intent) next.Detection_Intent = nr.Detection_Intent
  return next
}

// Shared walk: fold each incoming row into the accumulator when any of its
// source columns (or, for sourceless conceptual rows, its term name) already
// belongs to an accumulated row — the OWNER row's edits and Keep stand, the
// duplicate's evidence is absorbed. Order matters and is preserved: settled
// rows come first, later arrivals fold into them.
function foldWalk(acc, incoming, opts = {}) {
  const out = [...acc]
  const bySrc = new Map()
  const byTerm = new Map()
  const index = (r, i) => {
    const srcs = splitCols(r.Source_Column)
    srcs.forEach((s) => { const k = s.toLowerCase(); if (!bySrc.has(k)) bySrc.set(k, i) })
    if (!srcs.length) {
      const t = String(r.Term || '').trim().toLowerCase()
      if (t && !byTerm.has(t)) byTerm.set(t, i)
    }
  }
  out.forEach(index)
  let added = 0
  let dup = 0
  for (const nr of incoming) {
    const srcs = splitCols(nr.Source_Column)
    let owner = null
    for (const s of srcs) {
      const i = bySrc.get(s.toLowerCase())
      if (i != null) { owner = i; break }
    }
    if (owner == null && !srcs.length) {
      const i = byTerm.get(String(nr.Term || '').trim().toLowerCase())
      if (i != null) owner = i
    }
    if (owner != null) {
      out[owner] = foldSources(out[owner], nr, opts)
      dup++
      continue
    }
    index(nr, out.length)
    out.push(nr)
    added++
  }
  return { rows: out, added, dup }
}

// Merge incoming (scanned/harvested) rows into the existing workspace.
// opts.refreshEvidence: overwrite value-evidence fields from the incoming
// rows (steward fields and Detection_Intent untouched) — for rescans after
// the underlying DATA improved.
export function mergeBySource(existing, incoming, opts = {}) {
  return foldWalk(existing || [], incoming || [], opts)
}

// How many rows duplicate an earlier row's identity — the damage counter
// for the Review page's repair button. 0 on a healthy grid.
export function sameSourceCount(rows) {
  return foldWalk([], rows || []).dup
}

// Repair a grid damaged by the old label-keyed merge: every duplicate folds
// into its earlier (steward-settled) owner and disappears.
export function selfFold(rows) {
  const { rows: out, dup } = foldWalk([], rows || [])
  return { rows: out, folded: dup }
}
