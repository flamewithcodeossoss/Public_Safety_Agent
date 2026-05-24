import {
  Scan,
  Palmtree,
  DoorOpen,
  Camera,
  CameraOff,
  Video,
  XCircle,
  CheckCircle2,
} from 'lucide-react'

const TAG_ICONS = {
  'MRS_Access_Control.AccessChannels_QR': Scan,
  'MRS_Access_Control.Beaches_Vip': Palmtree,
  'MRS_Access_Control.MainGate_Vip': DoorOpen,
  'MRS_CCTV.cameras_total_number': Camera,
  'MRS_CCTV.Total_disabled_cameras': CameraOff,
  'MRS_CCTV.Total_enabled_cameras': Video,
  'MRS_Gate_APIs.Gates.Fail': XCircle,
  'MRS_Gate_APIs.Gates.Success': CheckCircle2,
}

function formatValue(value) {
  if (value === null || value === undefined) return '—'
  return Number(value).toLocaleString()
}

function formatTimestamp(ts) {
  if (!ts) return ''
  try {
    const d = new Date(ts)
    return d.toLocaleDateString('en-US', {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return ts
  }
}

export default function MetricCards({ metrics, loading, onCardClick }) {
  if (loading) {
    return (
      <div className="metrics-grid fade-in">
        {Array.from({ length: 8 }).map((_, i) => (
          <div key={i} className="metric-card" style={{ opacity: 0.3 }}>
            <div className="metric-card-header">
              <span className="metric-card-label">Loading...</span>
            </div>
            <div className="metric-card-value" style={{ color: 'var(--text-muted)' }}>—</div>
          </div>
        ))}
      </div>
    )
  }

  return (
    <div className="metrics-grid fade-in">
      {metrics.map((m) => {
        const Icon = TAG_ICONS[m.tag_name] || Camera
        return (
          <div
            key={m.tag_name}
            className={`metric-card domain-${m.domain}`}
            onClick={() => onCardClick?.(m.tag_name)}
            style={{ cursor: onCardClick ? 'pointer' : 'default' }}
            id={`metric-card-${m.tag_name.replace(/\./g, '-')}`}
          >
            <div className="metric-card-header">
              <span className="metric-card-label">{m.label}</span>
              <div className={`metric-card-icon ${m.domain}`}>
                <Icon size={18} />
              </div>
            </div>
            <div className="metric-card-value">
              {formatValue(m.value)}
            </div>
            <div className="metric-card-timestamp">
              {formatTimestamp(m.timestamp)}
            </div>
          </div>
        )
      })}
    </div>
  )
}
