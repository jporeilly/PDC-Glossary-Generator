import { useEffect, useState } from 'react'
import { apiGet, apiDelete } from './../api.js'
import { openGlossary, useWorkspace } from './../state.js'
import WorkflowDiagram from './../components/WorkflowDiagram.jsx'
import './home.css'

const WORKFLOW = [
  { n: 1, page: 'connect', title: 'Connect',
    text: 'Add a connection for each source — a database, a MinIO/S3 document store, or a DDL file. Scan one to start; Add to glossary from others to span structured and unstructured data.' },
  { n: 2, page: 'review', title: 'Review & prune',
    text: 'Every column becomes one candidate term, so you prune rather than hunt for gaps. Edit definition, purpose, sensitivity and tags inline; filter and Keep High+Med conf to cut noise. You can also open an existing glossary export for review, or enhance your scan against one.' },
  { n: 3, page: 'govern', title: 'Govern & generate',
    text: 'First approve any scan-grown pending terms/tags on the Dictionary page — only governed vocabulary flows into the Registry. Then manage the roster, set steward, owner, custodian, status and rating, and Generate JSONL with stewardship baked in. Import via PDC’s Business Glossary → Import.' },
  { n: 4, page: 'apply', title: 'Resolve Term IDs & apply',
    text: 'Once the glossary is imported, push the term↔column links over the API: authenticate once, resolve IDs, then apply with a dry-run before any write. Sensitivity, CDE, verified-lineage and trust score follow.' },
]

// The Home page: landing content ported from the old UI's home section —
// the 4-step workflow, the full working-cycle panel, saved glossaries and
// best practices.
export default function HomePage({ onNavigate }) {
  return (
    <>
      <div className="page-head">
        <h1>Build a Business Glossary for Pentaho Data Catalog</h1>
        <p className="psub">
          Scan your data sources, review and refine suggested terms, assign
          stewardship, and export import-ready JSONL.
        </p>
      </div>

      <section className="card">
        <h2>The workflow <span>click a step to jump there</span></h2>
        <WorkflowDiagram onNavigate={onNavigate} />
        <div className="grid-2">
          {WORKFLOW.map((s) => (
            <div className="tile" key={s.n}>
              <div className="bucket-title"><span className="dot-num">{s.n}</span> {s.title}</div>
              <p className="hint-line">{s.text}</p>
              <button className="ghost" onClick={() => onNavigate(s.page)}>
                Go to {s.title.split(' ')[0]} →
              </button>
            </div>
          ))}
        </div>
      </section>

      <WorkingCycle />
      <SavedGlossaries onNavigate={onNavigate} />

      <section className="card">
        <h2>Best practices</h2>
        <ul className="workcycle">
          <li>Terms export as <b>Draft</b> — proposals until a Business Steward approves them. Review before importing.</li>
          <li>The import <b>replaces the whole glossary</b>; reuse <code>_id</code>s (open an export for review) to update in place.</li>
          <li>Confidence is a <i>review signal</i>: <b>High</b> = a DB comment or key; <b>Low</b> = templated from the name. Enhance against an existing glossary or add column comments to raise it.</li>
          <li><b>CDE</b> (Critical Data Element) is auto-inferred from keys, sensitivity, and critical/compliance terms — and is always the steward's to confirm.</li>
          <li>UUIDs are <b>per-instance</b> (Keycloak). Fetch the roster from the target instance so bindings resolve.</li>
        </ul>
      </section>
    </>
  )
}

// The "full working cycle" panel — one complete pass, from scan to a Registry
// the Policy Generator can consume. Ported verbatim in substance from the old
// UI's home section; the order matters because each step feeds the next.
function WorkingCycle() {
  return (
    <details className="card">
      <summary>The full working cycle — exact order, and why it matters</summary>
      <ol className="workcycle">
        <li><b>Scan or resume.</b> Connect &amp; scan a source, or let the app auto-resume your last saved glossary.</li>
        <li><b>Review the grid.</b> The AI agents assist — Enrich, AI suggest (evidence), AI QA, AI categorize — and the duplicate advisor recommends Merge / Disambiguate / Keep separate. Rename divergent names to their canonical term; the vocabulary's aliases fold them automatically on future scans.</li>
        <li><b>Dictionary: review pending.</b> AI review advises per candidate; the alias action folds near-duplicates. Approve only what belongs — approved items govern the Registry and export into the pack. Mistakes are reversible per item (retire / fold), and a retire is <b>durable</b>: tombstoned through reseeds, offered for removal from the pack at export.</li>
        <li><b>Suggest tags</b> (grid) after any vocabulary change — re-derives every row's tags from the governed allow-list and accretes usage, which fills the facet preview. (Freshly reseeded counters are all zero — that means "no scan yet", never "retire everything".)</li>
        <li><b>Govern.</b> Roster-driven steward/owner/custodian, ratings, review dates.</li>
        <li><b>Save glossary → Generate.</b> Generate writes the import JSONL <b>and the Registry</b>. In PDC: <b>Business Glossary → Import</b> (if terms were <i>renamed</i>, delete the old glossary first — ids are name-based, so renames mint new terms). Then <b>Resolve &amp; stamp IDs</b> (backfills real ids into the Registry) and <b>Apply to PDC</b>.</li>
        <li><b>Export domain pack → Apply to this app → commit.</b> Last, because it exports the <i>reviewed</i> state of everything above. Decide any conflict rows; <b>Apply</b> writes the pack and reseeds the dictionary in one click. Commit the pack to the scenario repo so every future install starts from it.</li>
      </ol>
      <p className="hint-line">
        After step 6 the Registry (<code>registries/registry.&lt;glossary&gt;.json</code>) is
        current; after step 7 the flywheel is closed. <b>Save dictionary</b> is only needed
        after hand-editing tags/rules — approvals and scan accretion persist on their own.
        App state survives <code>git pull</code> untouched; <b>Settings → State snapshot</b>
        covers machine moves and restore points.
      </p>
    </details>
  )
}

function SavedGlossaries({ onNavigate }) {
  const [items, setItems] = useState(null)
  const [error, setError] = useState(null)
  const [busyId, setBusyId] = useState(null)
  const ws = useWorkspace()

  const refresh = () =>
    apiGet('/api/glossaries')
      .then((b) => setItems(b.glossaries ?? []))
      .catch((e) => setError(e.message))

  useEffect(() => { refresh() }, [])

  async function load(id) {
    setBusyId(id)
    setError(null)
    try {
      await openGlossary(id)
      onNavigate('review')
    } catch (err) {
      setError(err.message)
    } finally {
      setBusyId(null)
    }
  }

  async function remove(id) {
    try {
      await apiDelete(`/api/glossaries/${id}`)
      refresh()
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <section className="card">
      <header>
        <h2>Saved glossaries <span>reload and review anytime</span></h2>
        {ws.rows.length > 0 && (
          <span className="badge accent">
            {ws.rows.length} term(s) loaded{ws.dirty ? ' · unsaved changes' : ''}
          </span>
        )}
      </header>
      <p className="hint-line">
        Each saved glossary keeps its terms, governance and data-discovery profile.
        Click one to load it into the review grid.
      </p>
      {error && <div className="error">{error}</div>}
      {items == null && <p className="loading">Loading…</p>}
      {items?.length === 0 && <p className="hint-line">No saved glossaries yet — scan a connection to start one.</p>}
      {items?.length > 0 && (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Name</th><th>Glossary</th><th className="num">Terms</th>
                <th className="num">Kept</th><th>Discovery</th><th>Saved</th><th></th>
              </tr>
            </thead>
            <tbody>
              {items.map((g) => (
                <tr key={g.id} className="row-link" title={`Load ${g.name}`}
                    onClick={() => busyId == null && load(g.id)}>
                  <td className="mapping-link cell-clip">{busyId === g.id ? 'Loading…' : g.name}</td>
                  <td className="cell-clip">{g.glossary_name ?? '—'}</td>
                  <td className="num">{g.terms}</td>
                  <td className="num">{g.kept}</td>
                  <td>{g.has_discovery ? <span className="badge neutral">profile</span> : <span className="notes">—</span>}</td>
                  <td className="notes">{g.savedAt}</td>
                  <td>
                    <button className="ghost" title="Delete this saved glossary"
                            onClick={(e) => { e.stopPropagation(); remove(g.id) }}>
                      ✕
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  )
}
