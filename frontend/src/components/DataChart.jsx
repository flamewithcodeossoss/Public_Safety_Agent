import { useEffect, useState } from 'react'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
} from 'recharts'
import { TrendingUp } from 'lucide-react'
import { useTagHistory } from '../hooks/useChat'

const CHART_LIMITS = [
  { label: '20', value: 20 },
  { label: '50', value: 50 },
  { label: '100', value: 100 },
]

function formatChartTimestamp(ts) {
  if (!ts) return ''
  try {
    const d = new Date(ts)
    return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
  } catch {
    return ''
  }
}

const CustomTooltip = ({ active, payload, label }) => {
  if (!active || !payload?.length) return null
  return (
    <div style={{
      background: 'rgba(12, 20, 37, 0.95)',
      border: '1px solid rgba(255,255,255,0.1)',
      borderRadius: '8px',
      padding: '8px 12px',
      fontSize: '0.8rem',
    }}>
      <p style={{ color: '#8892a8', marginBottom: '4px' }}>{label}</p>
      <p style={{ color: '#06d6a0', fontWeight: 600 }}>
        Value: {payload[0].value?.toLocaleString() ?? '—'}
      </p>
    </div>
  )
}

export default function DataChart({ selectedTag, tagLabel }) {
  const [limit, setLimit] = useState(50)
  const { history, loading } = useTagHistory(selectedTag, limit)

  if (!selectedTag) {
    return (
      <div className="chart-section fade-in">
        <div className="chart-header">
          <div>
            <div className="chart-title">
              <TrendingUp size={18} style={{ marginRight: '8px', color: 'var(--accent-primary)' }} />
              Time Series
            </div>
            <div className="chart-subtitle">Click a metric card to view its history</div>
          </div>
        </div>
        <div className="chart-empty">Select a metric card above to view its time-series data</div>
      </div>
    )
  }

  const chartData = history?.data?.map(p => ({
    timestamp: formatChartTimestamp(p.timestamp),
    fullTimestamp: p.timestamp,
    value: p.value,
  })) || []

  return (
    <div className="chart-section fade-in">
      <div className="chart-header">
        <div>
          <div className="chart-title">
            <TrendingUp size={18} style={{ marginRight: '8px', color: 'var(--accent-primary)' }} />
            {tagLabel || selectedTag}
          </div>
          <div className="chart-subtitle">
            {loading ? 'Loading...' : `${chartData.length} data points`}
          </div>
        </div>
        <div className="chart-controls">
          {CHART_LIMITS.map(l => (
            <button
              key={l.value}
              className={`chart-btn ${limit === l.value ? 'active' : ''}`}
              onClick={() => setLimit(l.value)}
            >
              {l.label}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="chart-empty">Loading chart data...</div>
      ) : chartData.length === 0 ? (
        <div className="chart-empty">No data available for this tag</div>
      ) : (
        <ResponsiveContainer width="100%" height={240}>
          <AreaChart data={chartData} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
            <defs>
              <linearGradient id="chartGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#06d6a0" stopOpacity={0.3} />
                <stop offset="95%" stopColor="#06d6a0" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <CartesianGrid
              strokeDasharray="3 3"
              stroke="rgba(255,255,255,0.04)"
              vertical={false}
            />
            <XAxis
              dataKey="timestamp"
              stroke="#5a6478"
              fontSize={11}
              tickLine={false}
              axisLine={false}
            />
            <YAxis
              stroke="#5a6478"
              fontSize={11}
              tickLine={false}
              axisLine={false}
              tickFormatter={v => v.toLocaleString()}
            />
            <Tooltip content={<CustomTooltip />} />
            <Area
              type="monotone"
              dataKey="value"
              stroke="#06d6a0"
              strokeWidth={2}
              fill="url(#chartGradient)"
              dot={false}
              activeDot={{ r: 4, fill: '#06d6a0', stroke: '#0c1425', strokeWidth: 2 }}
            />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </div>
  )
}
