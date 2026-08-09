// The Home page's compact workflow map — pure inline SVG, no chart libraries.
// Every box that is a real page navigates via onNavigate(pageId); the two
// chips on the right are external outputs (PDC import / Policy Generator)
// and are intentionally not clickable. All colors come from the theme's CSS
// variables (see pages/home.css) so the diagram adapts to every theme.

// Main pipeline row: x/w in viewBox units, all boxes share y=10 h=36.
// Dictionary sits IN the pipeline — Review streams pending vocabulary into it,
// approval gates Govern — with a dotted back-edge for the flywheel: the
// approved vocabulary governs what Review's agents may propose next.
const MAIN = [
  { id: 'home', label: 'Home', x: 6, w: 52 },
  { id: 'connect', label: 'Connect', x: 76, w: 70 },
  { id: 'review', label: 'Review', x: 164, w: 64 },
  { id: 'dictionary', label: 'Dictionary', x: 246, w: 92 },
  { id: 'govern', label: 'Govern', x: 356, w: 64 },
  { id: 'apply', label: 'Apply', x: 438, w: 56 },
]

// Connect's child pages, indented under it like the sidebar nav.
const CHILDREN = [
  { id: 'schema', label: 'Schema', x: 106, y: 60 },
  { id: 'files', label: 'Files', x: 106, y: 92 },
]

function Node({ id, label, x, y, w, h, small, onNavigate }) {
  const activate = () => onNavigate(id)
  return (
    <g
      className={small ? 'wf-node wf-node-sm' : 'wf-node'}
      role="link"
      tabIndex={0}
      aria-label={`Go to ${label}`}
      onClick={activate}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          activate()
        }
      }}
    >
      <rect x={x} y={y} width={w} height={h} rx="8" />
      <text x={x + w / 2} y={y + h / 2 + 1} textAnchor="middle" dominantBaseline="middle">
        {label}
      </text>
    </g>
  )
}

const Arrow = ({ d, dotted }) => (
  <path d={d} className={dotted ? 'wf-arrow wf-dotted' : 'wf-arrow'} markerEnd="url(#wf-arrowhead)" />
)

export default function WorkflowDiagram({ onNavigate }) {
  return (
    <div className="wf-wrap">
      <svg
        className="wf"
        viewBox="0 0 700 154"
        aria-label="Workflow: Home, then Connect (with Schema and Files), then Review, then the
          Term & Tag Dictionary where the pending vocabulary is approved, then Govern and Apply.
          A dotted arrow from Dictionary back to Review shows that the approved vocabulary governs
          what the AI agents may propose. Apply produces the import JSONL for PDC and the
          Classification Registry for the Policy Generator."
      >
        <defs>
          <marker id="wf-arrowhead" viewBox="0 0 8 8" refX="7" refY="4"
                  markerWidth="8" markerHeight="8" markerUnits="userSpaceOnUse"
                  orient="auto-start-reverse">
            <path className="wf-head" d="M0.5 0.5 L7.5 4 L0.5 7.5 Z" />
          </marker>
        </defs>

        {/* main pipeline: Home → Connect → Review → Dictionary → Govern → Apply */}
        <Arrow d="M62 28 H72" />
        <Arrow d="M150 28 H160" />
        <Arrow d="M232 28 H242" />
        <Arrow d="M342 28 H352" />
        <Arrow d="M424 28 H434" />
        {MAIN.map((n) => (
          <Node key={n.id} {...n} y={10} h={36} onNavigate={onNavigate} />
        ))}

        {/* Connect's child pages, nav-style tree lines (no arrowheads) */}
        <path className="wf-tree" d="M90 46 V104 M90 72 H102 M90 104 H102" />
        {CHILDREN.map((n) => (
          <Node key={n.id} {...n} w={64} h={24} small onNavigate={onNavigate} />
        ))}

        {/* the flywheel: approved vocabulary governs what the agents propose */}
        <Arrow dotted d="M292 46 V56 H196 V47" />

        {/* Apply's two outputs — external hand-offs, not pages */}
        <Arrow d="M466 46 V75 H512" />
        <Arrow d="M466 46 V124 H512" />
        <g className="wf-out">
          <rect x="518" y="62" width="164" height="26" rx="8" />
          <text x="600" y="76" textAnchor="middle" dominantBaseline="middle">
            JSONL → PDC import
          </text>
        </g>
        <g className="wf-out">
          <rect x="518" y="104" width="164" height="40" rx="8" />
          <text x="600" y="119" textAnchor="middle" dominantBaseline="middle">
            Classification Registry
          </text>
          <text x="600" y="133" textAnchor="middle" dominantBaseline="middle">
            → Policy Generator
          </text>
        </g>
      </svg>
    </div>
  )
}
