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
  'Create a Python module with a class',
  'Find all TODO comments in the codebase',
  'Run the test suite and fix failures',
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
  const endRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const assistantText = useRef('')
  const toolBuf = useRef<ToolEvent[]>([])

  const scroll = useCallback(() => {
    requestAnimationFrame(() => endRef.current?.scrollIntoView({ behavior: 'smooth' }))
  }, [])

  useEffect(() => {
    connectWs()
    return () => wsRef.current?.close()
    // eslint-disable-next-line
  }, [])

  useEffect(() => { scroll() }, [messages, toolEvents, scroll])

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 180) + 'px'
    }
  }, [input])

  function connectWs() {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${proto}//${location.host}/ws/chat`)
    wsRef.current = ws

    ws.onopen = () => {
      setConnected(true)
      ws.send(JSON.stringify({ type: 'config', provider, model, api_key: apiKey }))
    }

    ws.onmessage = (e) => {
      const d = JSON.parse(e.data)

      if (d.type === 'session') return

      if (d.type === 'content') {
        assistantText.current += d.text
        const snapshot = assistantText.current
        setMessages(prev => {
          const m = [...prev]
          const last = m[m.length - 1]
          if (last && last.role === 'assistant') {
            m[m.length - 1] = { role: 'assistant', content: snapshot }
          } else {
            m.push({ role: 'assistant', content: snapshot })
          }
          return m
        })
        return
      }

      if (d.type === 'tool_start') {
        const evt: ToolEvent = { name: d.name, arguments: d.arguments, output: undefined }
        toolBuf.current = [...toolBuf.current, evt]
        setToolEvents([...toolBuf.current])
        return
      }

      if (d.type === 'tool_result') {
        const buf = [...toolBuf.current]
        for (let i = buf.length - 1; i >= 0; i--) {
          if (buf[i].name === d.name && !buf[i].output) {
            buf[i] = { ...buf[i], output: d.output }
            break
          }
        }
        toolBuf.current = buf
        setToolEvents([...buf])
        return
      }

      if (d.type === 'done') {
        setIsStreaming(false)
        return
      }

      if (d.type === 'error') {
        setIsStreaming(false)
        const errText = d.message || 'Unknown error'
        setMessages(prev => {
          const m = [...prev]
          const last = m[m.length - 1]
          if (last && last.role === 'assistant' && last.content) {
            m.push({ role: 'assistant', content: '**Error:** ' + errText })
          } else if (last && last.role === 'assistant') {
            m[m.length - 1] = { role: 'assistant', content: '**Error:** ' + errText }
          } else {
            m.push({ role: 'assistant', content: '**Error:** ' + errText })
          }
          return m
        })
        return
      }
    }

    ws.onclose = () => { setConnected(false); setTimeout(connectWs, 2000) }
    ws.onerror = () => setConnected(false)
  }

  function send(text?: string) {
    const msg = (text || input).trim()
    if (!msg || isStreaming || !wsRef.current) return
    setInput('')
    setToolEvents([])
    toolBuf.current = []
    assistantText.current = ''
    setMessages(p => [...p, { role: 'user', content: msg }])
    setIsStreaming(true)
    wsRef.current.send(JSON.stringify({ type: 'chat', message: msg }))
    setTimeout(() => textareaRef.current?.focus(), 50)
  }

  function onKey(e: KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send() }
  }

  function newChat() {
    setMessages([])
    setToolEvents([])
    toolBuf.current = []
    assistantText.current = ''
    setIsStreaming(false)
    wsRef.current?.send(JSON.stringify({ type: 'reset' }))
  }

  function applyModel() {
    wsRef.current?.send(JSON.stringify({ type: 'config', provider, model, api_key: apiKey }))
  }

  return (
    <>
      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="sidebar-brand">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--red)" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
            </svg>
            <h1>SAB</h1>
            <span className="ver">v0.1</span>
          </div>
          <button className="new-chat-btn" onClick={newChat}>
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
              <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            New Chat
          </button>
        </div>

        <div className="sidebar-body">
          <div className="section-label">Model</div>

          <div className="setting-row">
            <label>Provider</label>
            <select value={provider} onChange={e => setProvider(e.target.value)}>
              <option value="ollama">Ollama (Local)</option>
              <option value="anthropic">Claude (API)</option>
              <option value="openai">GPT (API)</option>
            </select>
          </div>

          <div className="setting-row">
            <label>Model</label>
            <input value={model} onChange={e => setModel(e.target.value)} />
          </div>

          {(provider === 'anthropic' || provider === 'openai') && (
            <div className="setting-row">
              <label>API Key</label>
              <input type="password" value={apiKey} onChange={e => setApiKey(e.target.value)} placeholder="sk-..." />
            </div>
          )}

          <button className="apply-btn" onClick={applyModel}>Apply</button>
        </div>

        <div className="sidebar-footer">
          <div className={`status-dot ${connected ? '' : 'off'}`} />
          {connected ? 'Connected' : 'Reconnecting...'}
        </div>
      </aside>

      <main className="main">
        <div className="top-bar">
          <span className="top-bar-title">SAB</span>
          <span className="top-bar-meta">{messages.length > 0 ? `${messages.length} messages` : 'Ready'} / {model}</span>
        </div>

        <div className="messages">
          {messages.length === 0 && (
            <div className="welcome">
              <div className="welcome-icon">
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
                </svg>
              </div>
              <h2>What can I help you with?</h2>
              <p>Read, write, and edit files. Run commands. Search code. All from your terminal.</p>
              <div className="chips">
                {SUGGESTIONS.map((s, i) => (
                  <button key={i} className="chip" onClick={() => send(s)}>{s}</button>
                ))}
              </div>
            </div>
          )}

          {messages.map((msg, i) => (
            <div key={i} className={`msg ${msg.role === 'user' ? 'msg-user' : 'msg-ai'}`}>
              {msg.role === 'user' ? (
                <div className="bubble">{msg.content}</div>
              ) : (
                <>
                  <div className="msg-label"><span className="dot" /> SAB</div>
                  <div className="msg-content">
                    <ReactMarkdown>{msg.content || ' '}</ReactMarkdown>
                  </div>
                </>
              )}
            </div>
          ))}

          {toolEvents.map((tool, i) => (
            <div key={`t${i}`} className="tool-event">
              <div className="tool-badge">{tool.name}()</div>
              {tool.output && (
                <div className="tool-output-box">
                  {tool.output.length > 300 ? tool.output.slice(0, 300) + '\n...' : tool.output}
                </div>
              )}
            </div>
          ))}

          {isStreaming && (
            <div className="typing"><div className="typing-dots"><span /><span /><span /></div></div>
          )}

          <div ref={endRef} />
        </div>

        <div className="input-bar">
          <div className="input-wrap">
            <textarea
              ref={textareaRef}
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={onKey}
              placeholder="Ask SAB anything..."
              rows={1}
            />
            <button className="send-btn" onClick={() => send()} disabled={isStreaming || !input.trim()}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
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
