import { useRef, useEffect, useState } from 'react'
import { Send, Bot, User, CheckCircle2, Loader2 } from 'lucide-react'

export default function ChatPanel({ messages, onSend, isLoading }) {
  const [input, setInput] = useState('')
  const messagesEndRef = useRef(null)
  const inputRef = useRef(null)

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!input.trim() || isLoading) return
    onSend(input.trim())
    setInput('')
    inputRef.current?.focus()
  }

  return (
    <div className="chat-section" id="chat-panel">
      {/* Header */}
      <div className="chat-header">
        <Bot size={18} style={{ color: 'var(--accent-primary)' }} />
        <span className="chat-header-title">AI Assistant</span>
        <span className="chat-header-badge">Qwen 2.5</span>
      </div>

      {/* Messages */}
      <div className="chat-messages">
        {messages.map((msg) => (
          <div key={msg.id} className={`chat-message ${msg.type}`}>
            {/* Avatar */}
            <div className={`chat-avatar ${msg.type}`}>
              {msg.type === 'ai' ? <Bot size={16} /> : <User size={16} />}
            </div>

            {/* Bubble */}
            <div>
              {/* Node steps (agent thinking) */}
              {msg.steps && msg.steps.length > 0 && (
                <div className="chat-node-steps">
                  {msg.steps.map((step, i) => (
                    <div
                      key={i}
                      className={`chat-node-step ${step.done ? 'done' : 'active'}`}
                    >
                      {step.done ? (
                        <CheckCircle2 className="step-icon" size={14} />
                      ) : (
                        <Loader2 className="step-icon loading" size={14} />
                      )}
                      <span>{step.label}</span>
                    </div>
                  ))}
                </div>
              )}

              {/* Loading indicator */}
              {msg.isLoading && !msg.steps?.length && (
                <div className="typing-indicator">
                  <div className="typing-dot" />
                  <div className="typing-dot" />
                  <div className="typing-dot" />
                </div>
              )}

              {/* Message text */}
              {msg.text && (
                <div
                  className="chat-bubble"
                  style={msg.isError ? { borderColor: 'var(--accent-rose)', color: 'var(--accent-rose)' } : {}}
                >
                  {msg.text.split('\n').map((line, i) => (
                    <span key={i}>
                      {line}
                      {i < msg.text.split('\n').length - 1 && <br />}
                    </span>
                  ))}
                </div>
              )}

              {/* Timestamp */}
              {msg.text && (
                <div className="chat-timestamp">
                  {new Date(msg.timestamp).toLocaleTimeString('en-US', {
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                </div>
              )}
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Input bar */}
      <form className="chat-input-bar" onSubmit={handleSubmit}>
        <input
          ref={inputRef}
          type="text"
          className="chat-input"
          placeholder="Ask about access control, cameras, or gates..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={isLoading}
          id="chat-input"
        />
        <button
          type="submit"
          className="chat-send-btn"
          disabled={isLoading || !input.trim()}
          id="chat-send-btn"
        >
          <Send size={18} />
        </button>
      </form>
    </div>
  )
}
