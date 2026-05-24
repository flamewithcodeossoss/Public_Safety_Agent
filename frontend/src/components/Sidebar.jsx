import { 
  Scan, 
  Palmtree, 
  DoorOpen, 
  Camera, 
  CameraOff, 
  Video, 
  XCircle, 
  CheckCircle2,
  TrendingUp,
  Activity,
  BarChart3
} from 'lucide-react'

const QUICK_QUERIES = [
  {
    category: 'Access Control',
    queries: [
      { text: 'Current count at Beaches VIP?', icon: Palmtree },
      { text: 'Main Gate VIP traffic now?', icon: DoorOpen },
      { text: 'QR channel access count?', icon: Scan },
    ]
  },
  {
    category: 'CCTV Cameras',
    queries: [
      { text: 'How many cameras are disabled?', icon: CameraOff },
      { text: 'Total enabled cameras?', icon: Camera },
      { text: 'Camera count trend', icon: TrendingUp },
    ]
  },
  {
    category: 'Gate APIs',
    queries: [
      { text: 'Current gate failure count?', icon: XCircle },
      { text: 'Gate success rate trend', icon: CheckCircle2 },
      { text: 'Average gate failures today?', icon: BarChart3 },
    ]
  },
]

export default function Sidebar({ onQuickQuery }) {
  return (
    <aside className="sidebar app-sidebar">
      <div>
        <div className="sidebar-section-title">
          <Activity size={12} style={{ display: 'inline', marginRight: '6px', verticalAlign: 'middle' }} />
          Quick Queries
        </div>
      </div>

      {QUICK_QUERIES.map((section) => (
        <div key={section.category}>
          <div className="sidebar-section-title" style={{ fontSize: '0.65rem', opacity: 0.6 }}>
            {section.category}
          </div>
          <ul className="quick-query-list">
            {section.queries.map((q) => (
              <li key={q.text}>
                <button
                  className="quick-query-btn"
                  onClick={() => onQuickQuery(q.text)}
                  id={`quick-query-${q.text.replace(/\s+/g, '-').toLowerCase().slice(0, 30)}`}
                >
                  <q.icon className="icon" size={16} />
                  <span>{q.text}</span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </aside>
  )
}
