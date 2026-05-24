import { Shield } from 'lucide-react'

export default function Header({ isConnected }) {
  return (
    <header className="header app-header">
      <div className="header-brand">
        <div className="header-logo">
          <Shield size={20} />
        </div>
        <div>
          <div className="header-title">Marassi Smart City</div>
          <div className="header-subtitle">Public Safety Monitoring</div>
        </div>
      </div>

      <div className="header-status">
        <span className={`status-dot ${isConnected ? 'online' : 'offline'}`} />
        <span className="status-text">
          {isConnected ? 'Agent Online' : 'Connecting...'}
        </span>
      </div>
    </header>
  )
}
