import { useState, useCallback } from 'react'
import Header from './components/Header'
import Sidebar from './components/Sidebar'
import MetricCards from './components/MetricCards'
import DataChart from './components/DataChart'
import ChatPanel from './components/ChatPanel'
import { useChat, useMetrics } from './hooks/useChat'

const TAG_LABELS = {
  'MRS_Access_Control.AccessChannels_QR': 'Access Channels (QR)',
  'MRS_Access_Control.Beaches_Vip': 'Beaches VIP Access Point',
  'MRS_Access_Control.MainGate_Vip': 'Main Gate VIP Access Point',
  'MRS_CCTV.cameras_total_number': 'Total CCTV Cameras',
  'MRS_CCTV.Total_disabled_cameras': 'Disabled CCTV Cameras',
  'MRS_CCTV.Total_enabled_cameras': 'Enabled CCTV Cameras',
  'MRS_Gate_APIs.Gates.Fail': 'Gate API Failures',
  'MRS_Gate_APIs.Gates.Success': 'Gate API Successes',
}

export default function App() {
  const { messages, sendMessage, isLoading, isConnected } = useChat()
  const { metrics, loading: metricsLoading } = useMetrics()
  const [selectedTag, setSelectedTag] = useState(null)

  const handleQuickQuery = useCallback((question) => {
    sendMessage(question)
  }, [sendMessage])

  const handleCardClick = useCallback((tagName) => {
    setSelectedTag(prev => prev === tagName ? null : tagName)
  }, [])

  return (
    <div className="app-layout">
      <Header isConnected={isConnected} />
      <Sidebar onQuickQuery={handleQuickQuery} />

      <main className="app-main">
        {/* Metric Cards */}
        <MetricCards
          metrics={metrics}
          loading={metricsLoading}
          onCardClick={handleCardClick}
        />

        {/* Time-Series Chart */}
        <DataChart
          selectedTag={selectedTag}
          tagLabel={selectedTag ? TAG_LABELS[selectedTag] : null}
        />

        {/* Chat Panel */}
        <ChatPanel
          messages={messages}
          onSend={sendMessage}
          isLoading={isLoading}
        />
      </main>
    </div>
  )
}
