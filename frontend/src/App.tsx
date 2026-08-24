import { useState, useRef, useEffect, useCallback, KeyboardEvent } from 'react'
import ReactMarkdown from 'react-markdown'

interface Message {
  role: 'user' | 'assistant'
  content: string
}

interface ToolEvent {
  name: string
  arguments: Record<string, unknown>
  output?: string
}

const SUGGESTIONS = [
  'Read the main entry point of this project',
  'Create a new Python module with a class',
  'Find all TODO comments in the codebase',
  'Run the test suite and fix any failures',
]

export default function App() {
  const [messages, setMessages] = useState<Message[]>([])
  const [toolEvents, setToolEvents] = useState<ToolEvent[]>([])
  const [input, setInput] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [connected, setConnected] = useState(false)
  const [provider, setProvider] = useState('ollama')
  const [model, setModel] = useState('qwen2.5:0.5b')
  const [apiKey, setApiKey] = useState('')
  const wsRef = useRef<WebSocket | null>(null)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const currentAssistant = useRef('')
  const toolBuffer = useRef<ToolEvent[]>([])

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [])

  useEffect(() => {
    connectWebSocket()
    return () => wsRef.current?.close()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    scrollToBottom()
  }, [messages, toolEvents, scrollToBottom])

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 200) + 'px'
    }
  }, [input])

  function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${protocol}//${window.location.host}/ws/chat`)
    wsRef.current = ws

    ws.onopen = () => {
      setConnected(true)
      ws.send(JSON.stringify({ type: 'config', provider, model, api_key: apiKey }))
    }

    ws.onmessage = (event) => {
      const data = JSON.parse(event.data)

      if (data.type === 'session') return

      if (data.type === 'content') {
        currentAssistant.current += data.text
        setMessages(prev => {
          const updated = [...prev]
          const last = updated[updated.length - 1]
          if (last && last.role === 'assistant') {
            updated[updated.length - 1] = { ...last, content: currentAssistant.current }
          } else {
            updated.push({ role: 'assistant', content: currentAssistant.current })
          }
          return updated
        })
        return
      }

      if (data.type === 'tool_start') {
        const evt: ToolEvent = { name: data.name, arguments: data.arguments }
        toolBuffer.current = [...toolBuffer.current, evt]
        setToolEvents([...toolBuffer.current])
        return
      }

      if (data.type === 'tool_result') {
        const updated = [...toolBuffer.current]
        const last = updated[updated.length - 1]
        if (last && last.name === data.name && !last.output) {
          last.output = data.output
        }
        toolBuffer.current = updated
        setToolEvents([...updated])
        return
      }

      if (data.type === 'done') {
        setIsStreaming(false)
        currentAssistant.current = ''
        toolBuffer.current = []
        return
      }

      if (data.type === 'error') {
        setIsStreaming(false)
        currentAssistant.current = ''
        setMessages(prev => [...prev, { role: 'assistant', content: `Error: ${data.message}` }])
        return
      }
    }

    ws.onclose = () => {
      setConnected(false)
      setTimeout(connectWebSocket, 2000)
    }

    ws.onerror = () => setConnected(false)
  }

  function sendMessage(text?: string) {
    const msg = (text || input).trim()
    if (!msg || isStreaming || !wsRef.current) return

    setInput('')
    setToolEvents([])
    toolBuffer.current = []
    setMessages(prev => [...prev, { role: 'user', content: msg }])
    setIsStreaming(true)
    currentAssistant.current = ''

    wsRef.current.send(JSON.stringify({ type: 'chat', message: msg }))

    setTimeout(() => textareaRef.current?.focus(), 50)
  }

  function handleKeyDown(e: KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      sendMessage()
    }
  }

  function newChat() {
    setMessages([])
    setToolEvents([])
    toolBuffer.current = []
    currentAssistant.current = ''
    wsRef.current?.send(JSON.stringify({ type: 'reset' }))
  }

  function applyConfig() {
    wsRef.current?.send(JSON.stringify({
      type: 'config', provider, model, api_key: apiKey,
    }))
  }

  const toolIcon: Record<string, string> = {
    read_file: '📄', write_file: '✏️', edit_file: '🔧',
    run_shell: '⚡', grep: '🔍', glob: '📁',
  }

  return (
    <>
      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="sidebar-logo">
            <div className="logo-icon">S</div>
            <h1>SAB</h1>
            <span className="version">v0.1</span>
          </div>
          <button className="new-chat-btn" onClick={newChat}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
              <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            New Chat
          </button>
        </div>

        <div className="sidebar-section">
          <div className="section-label">Model</div>

          <div className="setting-group">
            <label>Provider</label>
            <select value={provider} onChange={e => setProvider(e.target.value)}>
              <option value="ollama">Ollama (Local)</option>
              <option value="anthropic">Claude (API)</option>
              <option value="openai">GPT (API)</option>
            </select>
          </div>

          <div className="setting-group">
            <label>Model Name</label>
            <input type="text" value={model} onChange={e => setModel(e.target.value)} />
          </div>

          {(provider === 'anthropic' || provider === 'openai') && (
            <div className="setting-group">
              <label>API Key</label>
              <input type="password" value={apiKey} onChange={e => setApiKey(e.target.value)} placeholder="sk-..." />
            </div>
          )}

          <button className="apply-btn" onClick={applyConfig}>Apply Model</button>
        </div>

        <div className="status-bar">
          <div className={`status-dot ${connected ? '' : 'disconnected'}`} />
          <span className="status-text">{connected ? 'Connected' : 'Reconnecting...'}</span>
        </div>
      </aside>

      <main className="main">
        <div className="chat-header">
          <span className="chat-header-title">SAB</span>
          <span className="chat-header-info">
            {messages.length > 0 ? `${messages.length} messages` : 'Ready'}
            {' · '}
            {model}
          </span>
        </div>

        <div className="messages">
          {messages.length === 0 && (
            <div className="welcome">
              <div className="welcome-icon">S</div>
              <h2>What can I help you with?</h2>
              <p>I can read, write, and edit files. Run commands. Search code. All from your terminal.</p>
              <div className="welcome-chips">
                {SUGGESTIONS.map((s, i) => (
                  <button key={i} className="chip" onClick={() => sendMessage(s)}>{s}</button>
                ))}
              </div>
            </div>
          )}

          {messages.map((msg, i) => (
            <div key={i} className={`msg msg-${msg.role}`}>
              {msg.role === 'user' ? (
                <div className="msg-bubble">{msg.content}</div>
              ) : (
                <>
                  <div className="msg-label"><span className="dot" /> SAB</div>
                  <div className="msg-content">
                    <ReactMarkdown>{msg.content}</ReactMarkdown>
                  </div>
                </>
              )}
            </div>
          ))}

          {toolEvents.map((tool, i) => (
            <div key={`tool-${i}`} className="tool-event">
              <div className="tool-badge">
                <span className="tool-icon">{toolIcon[tool.name] || '⚙️'}</span>
                {tool.name}()
              </div>
              {tool.output && (
                <div className="tool-output-box">
                  {tool.output.length > 400 ? tool.output.slice(0, 400) + '\n... (truncated)' : tool.output}
                </div>
              )}
            </div>
          ))}

          {isStreaming && (
            <div className="typing-indicator">
              <div className="typing-dots">
                <span /><span /><span />
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        <div className="input-area">
          <div className="input-wrapper">
            <div className="input-box">
              <textarea
                ref={textareaRef}
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask SAB anything..."
                rows={1}
              />
            </div>
            <button className="send-btn" onClick={() => sendMessage()} disabled={isStreaming || !input.trim()}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="22" y1="2" x2="11" y2="13" />
                <polygon points="22 2 15 22 11 13 2 9 22 2" />
              </svg>
            </button>
          </div>
        </div>
      </main>
    </>
  )
}
