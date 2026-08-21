// Value evidence: what a scan OBSERVED about a column's values, and the one
// rule for folding a new observation into a stored one.
//
// There are exactly two intents, and conflating them cost three defects in a
// day:
//
//   CAPTURE  first sight, or a routine rescan. Fill what is missing and never
//            erase - a blank here means "nothing new to say", and the
//            steward's work survives.
//
//   REFRESH  the DATA changed (the estate was rescaled, repaired,
//            re-profiled) and the steward asked for the fresh reading to win.
//            The fresh observation replaces the set WHOLE, blanks included,
//            because it is ONE observation and not five independent fields.
//            A column that used to induce a shape and now induces an enum
//            must not keep the shape: on the AWC estate that left
//            ^[A-Z]{2}[0-9]{4}$ standing on eight terms after the data behind
//            it was repaired - a pattern matching zero rows, which would have
//            deployed as a Data Pattern and silently never fired.
//
// Both modes agree on one thing: a scan that observed NOTHING AT ALL (an
// unprofilable pdf/docx row) never erases anything. Absence of observation is
// not observation of absence.
//
// This is the mirror of glossary_generator/engine/evidence.py - rows are
// merged here, the dictionary is merged there, so the rule is written twice
// by necessity. test_docs.py pins the two to the same fields and modes.

export const EVIDENCE_FIELDS = ['Value_Signature', 'Value_Pattern', 'Enum_Values',
                                'Value_Kind', 'Value_Range']

export const CAPTURE = 'capture'
export const REFRESH = 'refresh'

const val = (o, f) => String((o || {})[f] || '').trim()

// Did this scan see ANY value evidence? A row carrying an enum but no pattern
// DID observe the column - it observed that there is no shape - and its blank
// pattern is a finding. A row carrying nothing observed nothing.
export const observed = (row) => EVIDENCE_FIELDS.some((f) => val(row, f))

// Fold a scan row's evidence into `target`, in place. Returns true if
// anything changed. `fields` maps a target key to the row field feeding it,
// so a store keeping a projection can use the same rule; whether the scan
// observed anything is judged on the WHOLE row either way.
export function mergeEvidence(target, row, mode, fields = null) {
  if (mode !== CAPTURE && mode !== REFRESH) {
    throw new Error(`unknown evidence mode ${mode} - use CAPTURE or REFRESH`)
  }
  const map = fields || Object.fromEntries(EVIDENCE_FIELDS.map((f) => [f, f]))
  const fresh = mode === REFRESH && observed(row)
  let changed = false
  for (const [key, src] of Object.entries(map)) {
    const incoming = val(row, src)
    const current = val(target, key)
    if (incoming) {
      if (incoming !== current) { target[key] = incoming; changed = true }
    } else if (fresh && current) {
      // the fresh reading says this field is empty, and it LOOKED
      target[key] = ''
      changed = true
    }
  }
  return changed
}
