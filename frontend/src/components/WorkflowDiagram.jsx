// The Home page's compact workflow map — pure inline SVG, no chart libraries.
// Every box that is a real page navigates via onNavigate(pageId); the two
// chips on the right are external outputs (PDC import / Policy Generator)
// and are intentionally not clickable. All colors come from the theme's CSS
// variables (see pages/home.css) so the diagram adapts to every theme.

// Main pipeline row: x/w in viewBox units, all boxes share y=10 h=36.
const MAIN = [
  { id: 'home', label: 'Home', x: 6, w: 64 },
  { id: 'connect', label: 'Connect', x: 96, w: 78 },
  { id: 'review', label: 'Review', x: 200, w: 72 },
  { id: 'govern', label: 'Govern', x: 298, w: 72 },
  { id: 'apply', label: 'Apply', x: 396, w: 64 },
]

// Connect's child pages, indented under it like the sidebar nav.
const CHILDREN = [
  { id: 'schema', label: 'Schema', x: 126, y: 60 },
  { id: 'files', label: 'Files', x: 126, y: 92 },
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
        viewBox="0 0 640 154"
        aria-label="Workflow: Home, then Connect (with Schema and Files), then Review, Govern and Apply.
          Review and Govern feed the Term & Tag Dictionary. Apply produces the import JSONL for PDC
          and the Classification Registry for the Policy Generator."
      >
        <defs>
          <marker id="wf-arrowhead" viewBox="0 0 8 8" refX="7" refY="4"
                  markerWidth="8" markerHeight="8" markerUnits="userSpaceOnUse"
                  orient="auto-start-reverse">
            <path className="wf-head" d="M0.5 0.5 L7.5 4 L0.5 7.5 Z" />
          </marker>
        </defs>

        {/* main pipeline: Home → Connect → Review → Govern → Apply */}
        <Arrow d="M74 28 H90" />
        <Arrow d="M178 28 H194" />
        <Arrow d="M276 28 H292" />
        <Arrow d="M374 28 H390" />
        {MAIN.map((n) => (
          <Node key={n.id} {...n} y={10} h={36} onNavigate={onNavigate} />
        ))}

        {/* Connect's child pages, nav-style tree lines (no arrowheads) */}
        <path className="wf-tree" d="M110 46 V104 M110 72 H122 M110 104 H122" />
        {CHILDREN.map((n) => (
          <Node key={n.id} {...n} w={68} h={24} small onNavigate={onNavigate} />
        ))}

        {/* Review + Govern grow and govern the shared vocabulary (dotted) */}
        <Arrow dotted d="M236 46 V112" />
        <Arrow dotted d="M334 46 V112" />
        <Node id="dictionary" label="Term & Tag Dictionary"
              x={210} y={118} w={160} h={30} small onNavigate={onNavigate} />

        {/* Apply's two outputs — external hand-offs, not pages */}
        <Arrow d="M428 46 V75 H464" />
        <Arrow d="M428 46 V124 H464" />
        <g className="wf-out">
          <rect x="470" y="62" width="164" height="26" rx="8" />
          <text x="552" y="76" textAnchor="middle" dominantBaseline="middle">
            JSONL → PDC import
          </text>
        </g>
        <g className="wf-out">
          <rect x="470" y="104" width="164" height="40" rx="8" />
          <text x="552" y="119" textAnchor="middle" dominantBaseline="middle">
            Classification Registry
          </text>
          <text x="552" y="133" textAnchor="middle" dominantBaseline="middle">
            → Policy Generator
          </text>
        </g>
      </svg>
    </div>
  )
}
