import { useState, useEffect, useRef, useCallback } from 'react'

const API_URL = import.meta.env.VITE_API_URL || ''
const WS_URL = import.meta.env.VITE_WS_URL || window.location.origin.replace('http', 'ws')

/**
 * Custom hook for WebSocket chat with the Smart City agent.
 * Handles connection, reconnection, and message streaming.
 */
export function useChat() {
  const [messages, setMessages] = useState([
    {
      id: 'welcome',
      type: 'ai',
      text: 'Hello! I\'m the Marassi Smart City assistant. Ask me about access control, CCTV cameras, or gate API status. For example:\n\n• "What is the current count at Beaches VIP?"\n• "How many cameras are disabled?"\n• "Show me the gate failure trend"',
      timestamp: new Date().toISOString(),
      steps: [],
    }
  ])
  const [isLoading, setIsLoading] = useState(false)
  const [isConnected, setIsConnected] = useState(false)
  const wsRef = useRef(null)
  const reconnectTimeoutRef = useRef(null)
  const currentStepsRef = useRef([])

  const connect = useCallback(() => {
    try {
      const ws = new WebSocket(`${WS_URL}/api/ws/chat`)

      ws.onopen = () => {
        setIsConnected(true)
        console.log('[ws] Connected to agent')
      }

      ws.onclose = () => {
        setIsConnected(false)
        console.log('[ws] Disconnected, reconnecting in 3s...')
        reconnectTimeoutRef.current = setTimeout(connect, 3000)
      }

      ws.onerror = (err) => {
        console.error('[ws] Error:', err)
        setIsConnected(false)
      }

      ws.onmessage = (event) => {
        const msg = JSON.parse(event.data)

        if (msg.type === 'node_update') {
          // Update current steps
          currentStepsRef.current = [
            ...currentStepsRef.current,
            { node: msg.data.node, label: msg.data.label, done: true }
          ]
          // Update the loading message with steps
          setMessages(prev => {
            const updated = [...prev]
            const loadingIdx = updated.findIndex(m => m.id === 'loading')
            if (loadingIdx >= 0) {
              updated[loadingIdx] = {
                ...updated[loadingIdx],
                steps: [...currentStepsRef.current],
              }
            }
            return updated
          })
        }

        if (msg.type === 'answer') {
          setIsLoading(false)
          setMessages(prev => {
            const updated = prev.filter(m => m.id !== 'loading')
            return [
              ...updated,
              {
                id: `ai-${Date.now()}`,
                type: 'ai',
                text: msg.data.answer,
                timestamp: new Date().toISOString(),
                steps: [...currentStepsRef.current],
              }
            ]
          })
          currentStepsRef.current = []
        }

        if (msg.type === 'error') {
          setIsLoading(false)
          setMessages(prev => {
            const updated = prev.filter(m => m.id !== 'loading')
            return [
              ...updated,
              {
                id: `error-${Date.now()}`,
                type: 'ai',
                text: `Error: ${msg.data.message}`,
                timestamp: new Date().toISOString(),
                steps: [],
                isError: true,
              }
            ]
          })
          currentStepsRef.current = []
        }
      }

      wsRef.current = ws
    } catch (err) {
      console.error('[ws] Connection failed:', err)
      reconnectTimeoutRef.current = setTimeout(connect, 3000)
    }
  }, [])

  useEffect(() => {
    connect()
    return () => {
      if (wsRef.current) wsRef.current.close()
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current)
    }
  }, [connect])

  const sendMessage = useCallback((question) => {
    if (!question.trim() || isLoading) return

    // Add user message
    setMessages(prev => [
      ...prev,
      {
        id: `user-${Date.now()}`,
        type: 'user',
        text: question,
        timestamp: new Date().toISOString(),
      }
    ])

    setIsLoading(true)
    currentStepsRef.current = []

    // Add loading message
    setMessages(prev => [
      ...prev,
      {
        id: 'loading',
        type: 'ai',
        text: '',
        timestamp: new Date().toISOString(),
        steps: [],
        isLoading: true,
      }
    ])

    // Send via WebSocket if connected, otherwise fallback to REST
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({ question }))
    } else {
      // REST fallback
      fetch(`${API_URL}/api/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question }),
      })
        .then(res => res.json())
        .then(data => {
          setIsLoading(false)
          setMessages(prev => {
            const updated = prev.filter(m => m.id !== 'loading')
            return [
              ...updated,
              {
                id: `ai-${Date.now()}`,
                type: 'ai',
                text: data.answer,
                timestamp: new Date().toISOString(),
                steps: [
                  { node: 'nl_understanding', label: 'Understanding your question...', done: true },
                  { node: 'tag_resolver', label: `Resolved to: ${data.resolved_tag || 'unknown'}`, done: true },
                  { node: 'query_builder', label: data.query_description || 'Built query', done: true },
                  { node: 'executor', label: 'Queried database', done: true },
                  { node: 'answer_formatter', label: 'Formatted answer', done: true },
                ],
                meta: {
                  resolved_tag: data.resolved_tag,
                  confidence: data.confidence,
                  query_sql: data.query_sql,
                },
              }
            ]
          })
        })
        .catch(err => {
          setIsLoading(false)
          setMessages(prev => {
            const updated = prev.filter(m => m.id !== 'loading')
            return [
              ...updated,
              {
                id: `error-${Date.now()}`,
                type: 'ai',
                text: `Connection error: ${err.message}. Make sure the backend is running.`,
                timestamp: new Date().toISOString(),
                steps: [],
                isError: true,
              }
            ]
          })
        })
    }
  }, [isLoading])

  return { messages, sendMessage, isLoading, isConnected }
}


/**
 * Fetch latest metrics for all 8 tags.
 */
export function useMetrics() {
  const [metrics, setMetrics] = useState([])
  const [loading, setLoading] = useState(true)

  const refresh = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/api/metrics/latest`)
      if (res.ok) {
        const data = await res.json()
        setMetrics(data)
      }
    } catch (err) {
      console.error('[metrics] Error:', err)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refresh()
    const interval = setInterval(refresh, 30000) // refresh every 30s
    return () => clearInterval(interval)
  }, [refresh])

  return { metrics, loading, refresh }
}


/**
 * Fetch history for a specific tag.
 */
export function useTagHistory(tagName, limit = 50) {
  const [history, setHistory] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!tagName) {
      setHistory(null)
      return
    }

    setLoading(true)
    fetch(`${API_URL}/api/metrics/${encodeURIComponent(tagName)}/history?limit=${limit}`)
      .then(res => res.json())
      .then(data => {
        setHistory(data)
        setLoading(false)
      })
      .catch(err => {
        console.error('[history] Error:', err)
        setLoading(false)
      })
  }, [tagName, limit])

  return { history, loading }
}
